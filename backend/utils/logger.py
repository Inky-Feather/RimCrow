# backend/utils/logger.py
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

    def _add_or_merge_block(self, blocks, new_block, lookback_limit=20):
        """通用去重合并逻辑：如果短时间内出现重复日志，则累加 count 并推至末尾"""
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
                blocks.append(matched_block)
                return
        
        if 'count' not in new_block: new_block['count'] = 1
        blocks.append(new_block)

    def get_paged_data(self, blocks, page, page_size):
        """通用的倒序分页算法"""
        total_blocks = len(blocks)
        total_pages = math.ceil(total_blocks / page_size) if total_blocks > 0 else 1
        
        if page > total_pages:
            return {'status': 'success', 'blocks': [], 'has_more': False, 'total_pages': total_pages}

        end_idx = total_blocks - (page - 1) * page_size
        start_idx = max(0, total_blocks - page * page_size)
        
        return {
            'status': 'success',
            'blocks': blocks[start_idx:end_idx],
            'has_more': page < total_pages,
            'total_pages': total_pages,
            'current_page': page
        }

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
        return json.dumps(log_record, ensure_ascii=False)

class WebviewHandler(logging.Handler):
    """
    将日志实时推送到前端的 Handler
    """
    def emit(self, record):
        from backend.utils.event_bus import EventBus
        # 如果 EventBus 没有窗口引用，直接跳过，防止报错
        # 这里的 _window 是在 EventBus 中定义的类变量，只有在前端完全就绪时才推送日志
        if not getattr(EventBus, '_window', None) or not getattr(EventBus, '_frontend_ready', False): 
            return 
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
                "context": {
                    "source": "app",
                    "module": record.module,
                    "func": record.funcName
                }
            }
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
            # 这样就避免了打印出 "RimModManager:logger:133" 这种无效信息
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
        self._logger = logging.getLogger("RimModManager")
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
        self._logger.info("Logger system initialized with Colorlog.")

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

        stat = os.stat(filepath)

        # 缓存机制：如果文件未修改，直接取缓存
        if filepath not in self._cache or self._cache[filepath]['mtime'] != stat.st_mtime:
            self._cache[filepath] = {
                'mtime': stat.st_mtime,
                'blocks': self._parse_file(filepath)
            }
            
        return self.get_paged_data(self._cache[filepath]['blocks'], page, page_size)

    def _parse_file(self, filepath):
        blocks = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        data = json.loads(line)
                        # 归一化处理
                        data['message'] = data.get('message', '').replace('\\n', '\n')
                        
                        data['details'] = (data.get('details') or data.get('exception', '')).replace('\\n', '\n')
                        
                        # 生成统一哈希ID
                        data['id'] = generate_log_id(data.get('timestamp', ''), data.get('level', 'INFO'), data['message'])
                            
                        # 规范化上下文
                        if 'module' in data and 'context' not in data:
                            data['context'] = {
                                'source': 'app',
                                'module': data.pop('module'),
                                'func': data.pop('func', ''),
                                'line': data.pop('line', '')
                            }
                        
                        self._add_or_merge_block(blocks, data)
                    except Exception: continue
		    
        except Exception as e:
            import traceback
            print(f"Error reading app log {filepath}: {e}")
        return blocks[-self.max_blocks:]

# 暴露单例供 API 路由使用
app_log_reader = AppLogReader()

# 全局单例
logger_manager = LoggerManager()
# 导出 logger 实例供其他模块使用
logger = logger_manager.logger
