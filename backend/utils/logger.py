# backend/utils/logger.py
import copy
import linecache
import logging
import json
import math
import os
import sys
import datetime
import hashlib
import traceback
import colorlog  # 引入 colorlog
from logging.handlers import TimedRotatingFileHandler
from icecream import ic

from backend.settings import DATA_DIR


def generate_log_id(timestamp: str, level: str, message: str) -> str:
    """生成基于内容的唯一哈希 ID，保证跨重启和双端的绝对去重"""
    raw_str = f"{timestamp}_{level}_{message}"
    return hashlib.md5(raw_str.encode('utf-8')).hexdigest()[:12]
class BaseLogReader:
    """日志读取基类，封装分页、缓存、去重合并逻辑"""
    def __init__(self, max_blocks=50000):
        self._cache = {}
        self.max_blocks = max_blocks

    def _normalize_log_level(self, data, filepath="", line_num=0, warn=True):
        level = str(data.get('level') or '').strip()
        if level:
            return level
        if warn:
            logger.warning("日志缺少等级字段：filepath=%s line=%s", filepath, line_num)
        return "UNKNOWN"

    def _ensure_cache(self, filepath, loader, cache_key=None):
        """统一的缓存入口，避免不同读取路径重复拼装缓存逻辑。"""
        cache_key = cache_key or filepath
        stat = os.stat(filepath)
        if cache_key not in self._cache or self._cache[cache_key]['mtime'] != stat.st_mtime:
            self._cache[cache_key] = {
                'mtime': stat.st_mtime,
                'filepath': filepath,
                'blocks': loader(filepath)
            }
        return self._cache[cache_key]['blocks']

    def _add_or_merge_block(self, blocks, new_block, lookback_limit=20):
        """通用去重合并逻辑：如果短时间内出现重复日志，则累加 count 并推至末尾"""
        # 确保 new_block 有 raw_lines 列表
        if 'raw_lines' not in new_block:
            new_block['raw_lines'] = []
        if not blocks:
            blocks.append(new_block)
            return

        n = len(blocks)
        start_idx = max(0, n - lookback_limit)
        
        nl, nm, nd = new_block['level'], new_block['message'], new_block['details']
        
        for i in range(n - 1, start_idx - 1, -1):
            b = blocks[i]
            if b['level'] == nl and b['message'] == nm and b['details'] == nd:
                matched_block = blocks.pop(i)
                matched_block['count'] = matched_block.get('count', 1) + new_block.get('count', 1)
                if new_block.get('timestamp'): 
                    matched_block['timestamp'] = new_block['timestamp']
                # 合并物理行号
                if 'raw_lines' not in matched_block:
                    matched_block['raw_lines'] = []
                matched_block['raw_lines'].extend(new_block['raw_lines'])
                blocks.append(matched_block)
                return
        
        if 'count' not in new_block: new_block['count'] = 1
        blocks.append(new_block)

    def get_paged_data(self, blocks, page, page_size):
        """通用的倒序分页算法"""
        total_blocks = len(blocks)
        total_pages = math.ceil(total_blocks / page_size) if total_blocks > 0 else 1
        
        if page > total_pages: return {'status': 'success', 'blocks': [], 'has_more': False, 'total_pages': total_pages}

        end_idx = total_blocks - (page - 1) * page_size
        start_idx = max(0, total_blocks - page * page_size)
        
        return {
            'status': 'success',
            'blocks': blocks[start_idx:end_idx],
            'has_more': page < total_pages,
            'total_pages': total_pages,
            'current_page': page
        }
    
    def get_logs_by_ids(self, log_ids: list, filename: str = '') -> list:
        """根据 ID 列表高效获取日志对象"""
        if not log_ids: return []
        
        # 1. 确定从哪个文件缓存中查找
        #    如果 filename 未指定，需要遍历所有缓存文件，但通常前端会知道当前是哪个文件
        #    这里我们简化为：假设所有 ID 来自最新的缓存文件
        cache_key = next(iter(self._cache)) if self._cache and not filename else filename
        if cache_key not in self._cache:
            cache_key = next(
                (key for key, entry in self._cache.items() if entry.get('filepath') == filename),
                None
            )
        if not cache_key or cache_key not in self._cache: return []

        # 2. 使用 Set 加速查找
        id_set = set(log_ids)
        
        # 3. 遍历缓存并返回
        return [block for block in self._cache[cache_key]['blocks'] if block.get('id') in id_set]
    
    # 基于行号的高效反查机制
    def get_raw_logs_by_lines(self, filepath: str, target_lines: list) -> list:
        """
        通过行号列表，直接从磁盘文件中提取完整的 JSON 字符串，并反序列化。
        这避免了在庞大的 _cache 数组中遍历查找，时间复杂度接近 O(1)。
        """
        if not os.path.exists(filepath) or not target_lines: return []
        raw_logs = []
        # 去重并排序行号，优化读取效率
        unique_lines = sorted(list(set(target_lines)))
        # 使用 Python 内置的 linecache，它针对同一文件的多次随机行读取做了高度优化
        for line_num in unique_lines:
            line_str = linecache.getline(filepath, line_num).strip()
            if line_str:
                try:
                    data = json.loads(line_str)
                    # 必须把这行日志的物理行号注入进去，否则 AI 看不到
                    data['raw_lines'] = [line_num] 
                    # 稳妥起见，顺手把 ID 也生成一下，防止老版本日志没这个字段
                    data['level'] = self._normalize_log_level(data, filepath, line_num)
                    if 'id' not in data:
                        data['id'] = generate_log_id(data.get('timestamp', ''), data['level'], data.get('message', ''))
                    raw_logs.append(data)
                except json.JSONDecodeError:
                    pass
        
        # 清理缓存，防止内存泄漏 (如果是常驻服务)
        # linecache.clearcache() 视情况决定是否调用
        return raw_logs

    def _parse_file_base(self, filepath, line_processor_cb=None, keep_all=False, max_keep_blocks=None):
        """
        【新增】底层通用文件读取与解析器
        处理流式读取、行号注入、基础 JSON 解析与去重。
        line_processor_cb: 回调函数，用于各子类处理特有逻辑（如游戏日志的正则匹配）
        """
        blocks = []
        filename = os.path.basename(filepath)
        realtime_json_names = {
            'RimCrow_Realtime.log', 'RimCrow_Realtime-prev.log',
            'RMM_Realtime.log', 'RMM_Realtime-prev.log',
        }
        is_json = filepath.endswith('.json') or filename in realtime_json_names or 'app.log' in filename
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                if is_json:
                    skipped_count = 0
                    first_skip = None
                    missing_level_count = 0
                    first_missing_level = None
                    for line_idx, line in enumerate(f):
                        line_str = line.strip()
                        if not line_str: continue
                        try:
                            data = json.loads(line_str.lstrip('\ufeff'))
                            # 归一化处理
                            data['level'] = self._normalize_log_level(data, filepath, line_idx + 1, warn=False)
                            if data['level'] == "UNKNOWN":
                                missing_level_count += 1
                                first_missing_level = first_missing_level or (line_idx + 1)
                            data['message'] = str(data.get('message', '') or '').replace('\\n', '\n')
                            data['details'] = str(data.get('details') or data.get('exception', '') or '').replace('\\n', '\n')
                            # 统一生成ID并注入行号
                            data['id'] = generate_log_id(data.get('timestamp', ''), data['level'], data['message'])
                            data['raw_lines'] = [line_idx + 1] # linecache 从 1 开始
                            
                            # 执行子类自定义逻辑
                            if line_processor_cb:
                                data = line_processor_cb(data, is_json=True)
                                
                            if data:
                                self._add_or_merge_block(blocks, data)
                        except Exception as e:
                            skipped_count += 1
                            if first_skip is None:
                                first_skip = (line_idx + 1, str(e), line_str[:200])
                            continue
                        if keep_all and max_keep_blocks and len(blocks) > max_keep_blocks:
                            blocks.pop(0)
                    if skipped_count:
                        first_line, reason, sample = first_skip or ("", "", "")
                        logger.warning(
                            "跳过无法解析的 JSON 日志行：filepath=%s skipped=%s first_line=%s reason=%s sample=%s",
                            filepath, skipped_count, first_line, reason, sample,
                        )
                    if missing_level_count:
                        logger.warning(
                            "日志缺少等级字段：filepath=%s count=%s first_line=%s level=UNKNOWN",
                            filepath, missing_level_count, first_missing_level,
                        )
                else:
                    # 纯文本读取(向下兼容 Player.log)
                    current_block = None
                    # 这里省略了对纯文本的具体处理，子类可以通过重写或继续延用原逻辑
                    pass
        except Exception as e:
            logger.error(f"读取日志失败：{filepath}，错误：{e}", exc_info=True)
            
        return blocks if keep_all else blocks[-self.max_blocks:]
    
    

# 定义日志格式
class JSONFormatter(logging.Formatter):
    """
    结构化 JSON 格式化器
    方便前端 LogViewer 解析和搜索，也方便后续 AI 读取上下文
    """
    def format(self, record):
        timestamp = datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        msg = record.getMessage()
        exc = self.formatException(record.exc_info) if record.exc_info else ""
        
        log_record = {
            "id": generate_log_id(timestamp, record.levelname, msg),
            "timestamp": timestamp,
            "level": record.levelname,
            "message": msg,
            "details": exc,
            "count": 1,
            "context": {
                "source": "app",
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
                "path": record.pathname
            }
        }
        error_code = getattr(record, "error_code", "")
        extra_context = getattr(record, "extra_context", None)
        if error_code:
            log_record["error_code"] = error_code
        if extra_context:
            log_record["extra_context"] = extra_context
        return json.dumps(log_record, ensure_ascii=False, default=str)

class WebviewHandler(logging.Handler):
    """
    将日志实时推送到前端的 Handler
    """
    def __init__(self):
        super().__init__()
        self._app_log_path = str(DATA_DIR / 'logs' / 'app.log')
        self._last_known_line = None
        self._last_known_size = None

    def _resolve_raw_line(self):
        try:
            current_size = os.path.getsize(self._app_log_path)
        except OSError:
            return []

        needs_recount = (
            self._last_known_line is None
            or self._last_known_size is None
            or current_size < self._last_known_size
        )

        if needs_recount:
            try:
                with open(self._app_log_path, 'r', encoding='utf-8', errors='replace') as fh:
                    self._last_known_line = sum(1 for _ in fh)
            except OSError:
                return []
        elif self._last_known_line:
            self._last_known_line += 1

        self._last_known_size = current_size
        return [self._last_known_line] if self._last_known_line else []

    def emit(self, record):
        from backend.utils.event_bus import EventBus
        # 如果 EventBus 没有窗口引用，直接跳过，防止报错
        # 这里的 _window 是在 EventBus 中定义的类变量，只有在前端完全就绪时才推送日志
        if not getattr(EventBus, '_window', None) or not getattr(EventBus, '_frontend_ready', False): return 
        try:
            timestamp = datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            msg = record.getMessage()
            # 模块正确格式化堆栈
            exc = ""
            if record.exc_info:
                # 将 exc_info 元组转换为标准的堆栈字符串
                exc = "".join(traceback.format_exception(*record.exc_info))
            # 如果没有 exc_info 但有手动传入的 exc_text (某些库会这么干)
            elif record.exc_text:
                exc = record.exc_text
            
            log_entry = {
                "id": generate_log_id(timestamp, record.levelname, msg),
                "timestamp": timestamp,
                "level": record.levelname,
                "message": msg,
                "details": exc,
                "count": 1,
                "raw_lines": self._resolve_raw_line(),
                "context": {
                    "source": "app",
                    "module": record.module,
                    "func": record.funcName
                }
            }
            error_code = getattr(record, "error_code", "")
            extra_context = getattr(record, "extra_context", None)
            if error_code:
                log_entry["error_code"] = error_code
            if extra_context:
                log_entry["extra_context"] = extra_context
            # 通过 EventBus 发送给前端
            # 前端监听 'app-log' 事件即可
            EventBus.emit('app-log', log_entry)
        except Exception:
            self.handleError(record)

class CustomColoredFormatter(colorlog.ColoredFormatter):
    """
    自定义的控制台格式化器
    能够智能识别是否为 icecream 的调试信息，并去除多余的 logger.py 调用栈信息
    """
    def format(self, record):
        # 保存原始的格式字符串
        original_fmt = self._style._fmt
        
        # 检查是否标记为 icecream 的日志 (在 log_to_debug 中设置)
        if getattr(record, 'is_icecream', False):
            # 对于 ic() 的输出，移除 %(name)s:%(module)s:%(lineno)d 部分
            # 因为 ic() 的 message 内容本身就已经包含了原本的文件名和行号
            # 这样就避免了打印出 "RimCrow:logger:133" 这种无效信息
            self._style._fmt = '%(log_color)s%(asctime)s | %(levelname)-8s | %(message)s'
        
        # 调用父类的 format 方法进行格式化
        result = super().format(record)
        
        # 恢复原始格式，保证普通 logger.info/debug 不受影响
        self._style._fmt = original_fmt
        return result

class LoggerManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        from backend.settings import settings
        # 1. 防止重复初始化 (单例模式下 __init__ 会被多次调用)
        if getattr(self, '_initialized', False): return
        self._initialized = True

        # 1. 创建 Logger
        self._logger = logging.getLogger("RimCrow")
        self._logger.setLevel(logging.DEBUG if settings.config.debug_mode else logging.INFO)
        self._logger.propagate = False # 防止重复打印

        # 2. 准备路径
        log_dir = str(DATA_DIR / 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = str(DATA_DIR / 'logs' / 'app.log')

        # 3. Handler: 文件输出 (JSON 结构化，按天轮转)
        file_handler = TimedRotatingFileHandler(
            log_file, when='midnight', interval=1, backupCount=settings.config.log_retention_days, encoding='utf-8'
        )
        file_handler.setFormatter(JSONFormatter())
        file_handler.setLevel(logging.DEBUG) # 文件里尽可能记录所有细节
        self._logger.addHandler(file_handler)

        # 4. Handler: 控制台输出 (Colorlog 美化)
        # 解决 Windows GBK 编码崩溃问题
        
        # 1. 尝试强制重配置 stdout/stderr 为 UTF-8
        if sys.platform.startswith('win'):
            try:
                # Python 3.7+ 支持直接 reconfigure
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8') # type: ignore
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8') # type: ignore
            except Exception:
                # 如果处于某些特殊无控制台环境 (pythonw.exe)，sys.stdout 可能是 None
                pass
        # 2. 安全地添加控制台 Handler
        # 只有当 sys.stdout 存在（不是 None）时才添加，避免 --noconsole 模式下报错
        if sys.stdout is not None:
            try:
                console_handler = logging.StreamHandler(sys.stdout)
        
                # 使用自定义的 CustomColoredFormatter
                color_formatter = CustomColoredFormatter(
                    fmt='%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s:%(module)s:%(lineno)d - %(message)s',
                    datefmt='%H:%M:%S',
                    reset=True,
                    log_colors={
                        'DEBUG':    'cyan',
                        'INFO':     'white',
                        'WARNING':  'yellow',
                        'ERROR':    'red',
                        'CRITICAL': 'red,bg_white',
                    },
                    secondary_log_colors={},
                    style='%'
                )
                
                console_handler.setFormatter(color_formatter)
                console_handler.setLevel(logging.DEBUG if settings.config.debug_mode else logging.INFO)
                self._logger.addHandler(console_handler)
            except Exception as e:
                # 如果控制台初始化还是失败，记录错误但不让程序崩溃
                # 这里只能用文件记录了，因为控制台坏了
                file_handler.emit(logging.LogRecord(
                    "Logger", logging.ERROR, "", 0, f"Console handler init failed: {e}", (), None
                ))
                
        # 5. Handler: Webview 推送 (前端 UI 显示)
        webview_handler = WebviewHandler()
        webview_handler.setLevel(logging.DEBUG)
        self._logger.addHandler(webview_handler)

        # 6. 集成 Icecream (关键步骤)
        self._configure_icecream(settings.config.debug_mode)
        self._logger.info("日志系统已初始化，控制台和文件日志已就绪。")

    def _configure_icecream(self, debug_mode: bool):
        """ 配置 icecream 的行为 """
        if debug_mode:
            ic.enable()
            # 【核心】将 ic 的输出重定向到 logger.debug
            # 这样 ic() 打印的内容既会在控制台高亮显示（ic自带），也会被写入 log 文件
            def log_to_debug(text):
                # 移除 icecream 自动添加的 'ic| ' 前缀
                # 注意：如果希望在控制台看到 'IC| '，可以不 replace，或者只在 JSON 里 replace
                clean_text = text.replace('IC| ', '') 
                if self._logger:
                    # 【修改点】添加 extra 参数，告诉 Formatter 这是一条来自 icecream 的消息
                    self._logger.debug(clean_text, extra={'is_icecream': True})
            
            ic.configureOutput(prefix='IC| ', includeContext=True, outputFunction=log_to_debug)
        else:
            # 生产环境禁用 ic，避免性能损耗和敏感信息泄露
            ic.disable()

    @property
    def logger(self) -> logging.Logger:
        return self._logger

class AppLogReader(BaseLogReader):
    def __init__(self):
        # App 日志默认在前端只展示最近几千条，这里适当降低后端缓存上限，减少长期占用内存
        super().__init__(max_blocks=20000)
        self.log_dir = DATA_DIR / 'logs'
        
    def get_log_files(self):
        result = []
        if self.log_dir.exists():
            for f in self.log_dir.glob('app.log*'):
                stat = os.stat(f)
                result.append({
                    'name': f.name,
                    'path': str(f),
                    'size': stat.st_size,
                    'mtime': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        # 按修改时间倒序
        result.sort(key=lambda x: x['mtime'], reverse=True)
        return result

    def read_log_page(self, filename, page=1, page_size=1000):
        filepath = os.path.join(self.log_dir, filename)
        if not os.path.exists(filepath): return {'error': '文件不存在'}

        blocks = self._ensure_cache(
            filepath,
            lambda path: self._parse_file(path, keep_all=True),
            cache_key=f"{filepath}::browse"
        )
        return self.get_paged_data(blocks, page, page_size)

    def get_all_blocks(self, filepath, full_scan=False):
        """返回当前文件的完整结构化日志块，供 AI 全局扫描复用。"""
        if not os.path.exists(filepath): return []
        # 全局扫描时走一次完整解析，避免被前端分页缓存的块数上限截断。
        blocks = self._parse_file(filepath, keep_all=True, max_keep_blocks=80000) if full_scan else self._ensure_cache(filepath, self._parse_file)
        logger.debug(
            f"[App日志] 读取日志块 filepath={filepath} block_count={len(blocks)} full_scan={full_scan}"
        )
        return copy.deepcopy(blocks)

    def _parse_file(self, filepath, keep_all=False, max_keep_blocks=None):
        """利用基类重构 App 日志读取"""
        def _app_processor(data, is_json):
            # App 专属上下文规范化
            if 'module' in data and 'context' not in data:
                data['context'] = {
                    'source': 'app',
                    'module': data.pop('module'),
                    'func': data.pop('func', ''),
                    'line': data.pop('line', '')
                }
            return data
            
        return self._parse_file_base(
            filepath,
            line_processor_cb=_app_processor,
            keep_all=keep_all,
            max_keep_blocks=max_keep_blocks
        )


# 暴露单例供 API 路由使用
app_log_reader = AppLogReader()

# 全局单例
logger_manager = LoggerManager()
# 导出 logger 实例供其他模块使用
logger = logger_manager.logger
