# backend/managers/mgr_game_logs.py
import copy
import json
import os
import re
from datetime import datetime
import threading
import time

from backend.load_order.package_tokens import parse_package_token
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext
from backend.utils.event_bus import EventBus
from backend.utils.logger import BaseLogReader, generate_log_id, logger


class LogAnalyzer:
    """启发式日志诊断分析器：推断错误类型并提取关联的 Mod ID 或 文件路径"""
    def __init__(self):
        # 常见错误特征匹配
        self.rules = {
            'XMLSyntaxError': re.compile(r'XML error|XML parsing error', re.IGNORECASE),
            'DefConfigError': re.compile(r'Config error in', re.IGNORECASE),
            'CrossRefError': re.compile(r'Could not resolve cross-reference|cross-reference|Could not resolve reference to object with loadID', re.IGNORECASE),
            'AssemblyConflict': re.compile(r'ReflectionTypeLoadException|MissingMethodException|TypeLoadException', re.IGNORECASE),
            'TickException': re.compile(r'Exception ticking', re.IGNORECASE),
            'DrawException': re.compile(r'Exception drawing', re.IGNORECASE),
            'NullReference': re.compile(r'NullReferenceException', re.IGNORECASE),
            'OutOfMemory': re.compile(r'System\.OutOfMemoryException|Could not allocate memory', re.IGNORECASE),
            'MissingTexture': re.compile(r'Failed to find any texture|Could not load UnityEngine\.Texture2D', re.IGNORECASE)
        }
        # 提取 Mod 包名 (通常格式为 Author.ModName，或者被[] 包裹)
        self.mod_id_pattern = re.compile(r'\[([a-zA-Z0-9\-_]{2,}\.[a-zA-Z0-9\-_]{2,})\]')
        # 提取相关 XML 文件路径
        self.file_pattern = re.compile(r'([A-Za-z0-9_\-\/\\]+\.xml)', re.IGNORECASE)

    def analyze(self, block, is_realtime_json=False, active_mods=None):
        """
        :param block: 日志数据块
        :param is_realtime_json: 是否为伴生 Mod 产生的安全 JSON 数据
        """
        # 核心：如果 C# 伴生 Mod 已经提供了精确上下文，我们只填补空白，绝不覆盖！
        has_csharp_context = 'context' in block and isinstance(block['context'], dict)
        
        # 1. 伴生 Mod 日志处理逻辑 (高可信度)
        if has_csharp_context or is_realtime_json:
            if not has_csharp_context:
                block['context'] = {'inferredType': None, 'relatedModIds': [], 'relatedFiles': []}
            context = block['context']
            
            # 补救推断：如果 C# 没有识别出类型，Python 端利用丰富的正则库再补救一下
            details = block.get('details', '')
            if not context.get('inferredType') and block.get('level') in ['ERROR', 'WARNING']:
                full_text = block.get('message', '') + "\n" + details
                for err_type, pattern in self.rules.items():
                    if pattern.search(full_text):
                        context['inferredType'] = err_type
                        break
                        
            return block
        # 2. 原版 Player.log 的降级正则提取逻辑 (低可信度，兜底用)，安全获取 details，防止 KeyError
        details = block.get('details', '')
        full_text = block.get('message', '') + "\n" + details
        if not full_text.strip(): return block
        context = {
            'inferredType': None,
            'relatedModIds': [],
            'relatedFiles': []
        }
        if block['level'] in['ERROR', 'WARNING']:
            for err_type, pattern in self.rules.items():
                if pattern.search(full_text):
                    context['inferredType'] = err_type
                    break
        mod_matches = self.mod_id_pattern.findall(full_text)
        if mod_matches:
            # Python端同样过滤底层框架噪音
            invalid_ids = {
                'ludeon.rimworld', 'system.reflection', 'system.object',
                'brrainz.harmony', 'unlimitedhugs.hugslib', 'imranfish.xmlextensions', 
                'startupprofiler.mypatches', 'zetrith.prepatcher', 'taranchuk.moderrorchecker'
            }
            valid_mods =[]
            for m in mod_matches:
                m_lower = m.lower()
                if m_lower in invalid_ids:
                    continue
                
                # 💡 终极交叉比对核心逻辑
                if active_mods:
                    # 情况A: 如果这个提取出来的 ID 确实在我们的激活列表里，100% 是真实的 Mod，直接放行！
                    if m_lower in active_mods:
                        valid_mods.append(m_lower)
                    else:
                        # 情况B: 这个 ID 不在激活列表里。
                        # 可能是玩家缺失了某个前置依赖（游戏报错找不到该Mod），
                        # 也可能是正则误伤了纯数字版本号（比如[1.4], [1.5.2]）。
                        # 我们加一个简单的正则，把所有纯数字+小数点的伪装者干掉！
                        if not re.match(r'^\d+\.\d+(\.\d+)?$', m_lower):
                            valid_mods.append(m_lower)
                else:
                    # 如果没有激活列表(比如查看的是历史快照日志)，则仅执行数字版本号过滤
                    if not re.match(r'^\d+\.\d+(\.\d+)?$', m_lower):
                        valid_mods.append(m_lower)
                        
            context['relatedModIds'] = list(dict.fromkeys(valid_mods)) 
            
        file_matches = self.file_pattern.findall(full_text)
        if file_matches:
            context['relatedFiles'] = list(dict.fromkeys(file_matches))
            
        if context['inferredType'] or context['relatedModIds'] or context['relatedFiles']:
            block['context'] = context
            
        return block


class GameLogManager(BaseLogReader): # 继承基类
    _GAME_LOG_FILENAMES = ('RMM_Realtime.log', 'RMM_Realtime-prev.log', 'Player.log', 'Player-prev.log')

    def __init__(self, context: ProfileContext):
        # 游戏日志通常较长，这里限制为最近 2 万条结构化 Block，避免长时间运行后占用过多内存
        super().__init__(max_blocks=20000) # 初始化 BaseLogReader 的缓存和内存限制
        self.context = context
        self.analyzer = LogAnalyzer()
        # 实时监视器相关状态
        self._realtime_thread = None
        self._stop_event = threading.Event()
        self.realtime_log_file = self.resolve_log_file_path('RMM_Realtime.log', must_exist=False)
        
        self._patterns = {
            'error': re.compile(r'error|exception|crash|fail', re.IGNORECASE),
            'warning': re.compile(r'warning', re.IGNORECASE)
        }

    def _build_realtime_log_paths(self, filename: str) -> list[str]:
        candidates = []
        context_root = str(getattr(self.context, "user_data_path", "") or "").strip()
        if context_root:
            candidates.append(os.path.join(context_root, filename))
        candidates.extend(
            os.path.join(root, filename)
            for root in GameManager.get_default_user_data_paths()
        )
        return list(dict.fromkeys(candidates))

    def _build_log_path_candidates(self, filename: str) -> list[str]:
        normalized_name = os.path.basename(str(filename or "").strip())
        if not normalized_name:
            return []
        if normalized_name.startswith('Player'):
            return GameManager.get_default_player_log_paths(normalized_name)
        if normalized_name.startswith('RMM_Realtime'):
            return self._build_realtime_log_paths(normalized_name)
        return []

    def resolve_log_file_path(self, filename: str, *, must_exist: bool = True) -> str:
        """解析游戏日志路径：Player 固定默认目录，RMM_Realtime 跟随当前环境。"""
        for filepath in self._build_log_path_candidates(filename):
            if not must_exist or os.path.exists(filepath):
                return filepath
        return ""

    def get_preferred_log_directory(self) -> str:
        for filename in ('RMM_Realtime.log', 'RMM_Realtime-prev.log', 'Player.log', 'Player-prev.log'):
            filepath = self.resolve_log_file_path(filename)
            if filepath:
                return os.path.dirname(filepath)

        context_root = str(getattr(self.context, "user_data_path", "") or "").strip()
        if context_root:
            return context_root

        fallback_roots = GameManager.get_default_user_data_paths()
        if fallback_roots:
            return fallback_roots[0]

        player_candidates = GameManager.get_default_player_log_paths('Player.log')
        return os.path.dirname(player_candidates[0]) if player_candidates else ""

    def get_log_files_for_root(self, user_data_root: str = "", *, player_only: bool = False):
        """
        按指定用户数据根目录解析日志文件。
        主前端仍使用当前活动环境；静默页会把运行环境根目录显式传进来。
        """
        result = []
        normalized_root = str(user_data_root or "").strip()
        for filename in self._GAME_LOG_FILENAMES:
            if player_only and not filename.startswith("Player"):
                continue
            if filename.startswith("RMM_Realtime") and normalized_root:
                filepath = os.path.join(normalized_root, filename)
            else:
                filepath = self.resolve_log_file_path(filename)
            if filepath and os.path.exists(filepath):
                stat = os.stat(filepath)
                result.append({
                    'name': filename,
                    'path': filepath,
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        result.sort(key=lambda x: x['mtime'], reverse=True)
        return result

    def read_log_page_for_root(self, filename, user_data_root: str = "", page=1, page_size=1000):
        normalized_name = os.path.basename(str(filename or "").strip())
        if normalized_name.startswith('RMM_Realtime') and str(user_data_root or "").strip():
            filepath = os.path.join(str(user_data_root).strip(), normalized_name)
        else:
            filepath = self.resolve_log_file_path(normalized_name)
        if not filepath or not os.path.exists(filepath):
            return {'error': '文件不存在'}

        blocks = self._ensure_cache(
            filepath,
            lambda path: self._parse_file_to_blocks(path, keep_all=True),
            cache_key=f"{filepath}::browse"
        )
        result = self.get_paged_data(blocks, page, page_size)
        if result['status'] == 'success':
            self._analyze_page(result['blocks'], normalized_name)
        return result


    # 启动/停止实时监视器
    def start_realtime_monitor(self):
        """启动后台线程来实时监视 RMM_Realtime.log 文件"""
        if self._realtime_thread and self._realtime_thread.is_alive(): return # 已经启动
        # 确保日志文件存在
        if not os.path.exists(self.realtime_log_file):
            logger.warning(f"实时日志文件不存在，无法启动监视: {self.realtime_log_file}")
            return
        self._stop_event.clear()
        self._realtime_thread = threading.Thread(target=self._tail_log_file, daemon=True)
        self._realtime_thread.start()
        logger.info(f"游戏实时日志监视器已启动 -> {self.realtime_log_file}")

    def stop_realtime_monitor(self):
        """停止监视线程"""
        if self._realtime_thread and self._realtime_thread.is_alive():
            self._stop_event.set()
            # self._realtime_thread.join(timeout=2) # 等待线程优雅退出
            logger.info("游戏实时日志监视器已停止。")
            
    def _tail_log_file(self):
        """后台线程的核心工作函数：Tailing the log file"""
        try:
            with open(self.realtime_log_file, 'r', encoding='utf-8', errors='replace') as f:
                current_line_no = sum(1 for _ in f)
                # 直接跳到文件末尾
                f.seek(0, 2)
                while not self._stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(0.1) # 没有新内容，短暂休眠
                        continue
                    current_line_no += 1
                    
                    # 有新内容，解析并推送
                    try:
                        data = json.loads(line)
                        data['id'] = generate_log_id(data.get('timestamp', ''), data.get('level', 'INFO'), data.get('message', ''))
                        data['raw_lines'] = [current_line_no]
                        EventBus.emit('game-log', data)
                    except json.JSONDecodeError:
                        # 忽略无法解析的行
                        pass
        except Exception as e:
            logger.error(f"日志监视线程异常退出: {e}", exc_info=True)


    def get_log_files(self):
        """获取日志文件列表，支持 app(软件日志) 和 game(游戏日志)"""
        result =[]
        for filename in self._GAME_LOG_FILENAMES:
            filepath = self.resolve_log_file_path(filename)
            if filepath and os.path.exists(filepath):
                stat = os.stat(filepath)
                result.append({
                    'name': filename,
                    'path': filepath,
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
                        
        # 按修改时间倒序排列
        result.sort(key=lambda x: x['mtime'], reverse=True)
        return result

    def read_log_page(self, filename, page=1, page_size=1000):
        """
        分页读取日志，支持向上懒加载。
        page=1 代表最新的一页（文件末尾）。page 越大，读取的数据越旧（越靠前）。
        """
        # 1. 确定文件路径
        filepath = self.resolve_log_file_path(filename)
            
        if not os.path.exists(filepath): return {'error': '文件不存在'}

        # 使用统一缓存入口，避免全局扫描和分页读取走出两套状态。
        blocks = self._ensure_cache(
            filepath,
            lambda path: self._parse_file_to_blocks(path, keep_all=True),
            cache_key=f"{filepath}::browse"
        )
        # 3. 计算分页切片 (倒序分页算法)
        result = self.get_paged_data(blocks, page, page_size)
        
        # 如果请求的页数超出了总页数，返回空
        if result['status'] == 'success':
            self._analyze_page(result['blocks'], filename)
            
        return result

    def get_raw_logs_by_lines(self, filepath: str, target_lines: list) -> list:
        """按块反查游戏日志，兼容 JSON 与 Player.log 纯文本块。"""
        if not os.path.exists(filepath) or not target_lines: return []

        blocks = self._ensure_cache(filepath, self._parse_file_to_blocks)

        target_line_set = set(target_lines)
        matched_blocks = [
            block for block in blocks
            if target_line_set.intersection(block.get('raw_lines', []))
        ]

        if matched_blocks:
            self._analyze_page(matched_blocks, os.path.basename(filepath))

        return [copy.deepcopy(block) for block in matched_blocks]

    def get_all_blocks(self, filepath: str, full_scan: bool = False) -> list:
        """返回完整结构化日志块，并补齐分析上下文，供 AI 全局扫描复用。"""
        if not os.path.exists(filepath): return []

        # 全局扫描时单独走完整解析，避免被常规缓存上限截断较早的错误块。
        blocks = self._parse_file_to_blocks(filepath, keep_all=True, max_keep_blocks=80000) if full_scan else self._ensure_cache(filepath, self._parse_file_to_blocks)
        self._analyze_page(blocks, os.path.basename(filepath))
        logger.debug(
            f"[游戏日志] 读取日志块 filepath={filepath} block_count={len(blocks)} full_scan={full_scan}"
        )
        return [copy.deepcopy(block) for block in blocks]

    def _analyze_page(self, page_blocks, filename):
        """游戏日志特有的分析逻辑"""
        is_json_log = filename.startswith('RMM_Realtime') or filename.endswith('.json')
        # 获取激活 Mod 列表用于交叉比对
        active_mods_set = set()
        try:
            lo_mgr = LoadOrderManager(self.context)
            active_mods = lo_mgr.read_active_mods().get('active_mods', [])
            active_mods_set = {
                token_info.canonical_package_id
                for mod_id in active_mods
                for token_info in [parse_package_token(mod_id)]
                if token_info.canonical_package_id
            }
        except Exception: pass

        for block in page_blocks:
            if 'context' not in block or 'inferredType' not in block.get('context', {}):
                self.analyzer.analyze(block, is_realtime_json=is_json_log, active_mods=active_mods_set)

    def _parse_file_to_blocks(self, filepath, keep_all=False, max_keep_blocks=None):
        """重写：使用基类方法处理 JSON，保留纯文本特化逻辑"""
        filename = os.path.basename(filepath)
        is_json = filename.endswith('.json') or filename.startswith('RMM_Realtime')
        
        # 如果是 JSON，直接复用基类的高效解析
        if is_json:
            # 注意：分析逻辑交给了 read_log_page 里的 _analyze_page，所以这里不传回调直接返回
            return self._parse_file_base(filepath, keep_all=keep_all, max_keep_blocks=max_keep_blocks)
            
        # --- 下面保留原有的纯文本流式读取逻辑 (Player.log) ---
        blocks = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                current_block = None
                for idx, line in enumerate(f):
                    line_content = line.rstrip('\r\n')
                    if not line_content: continue
                    
                    if line_content.startswith((' ', '\t', 'at ', '(Filename:')) and current_block:
                        current_block['details'] += '\n' + line_content
                        current_block['raw_lines'].append(idx + 1)
                    else:
                        if current_block: 
                            self._add_or_merge_block(blocks, current_block)
                        
                        level = 'INFO'
                        if self._patterns['error'].search(line_content): level = 'ERROR'
                        elif self._patterns['warning'].search(line_content): level = 'WARNING'
                        
                        current_block = {
                            'id': generate_log_id(f'playerlog_{idx}', level, line_content),
                            'timestamp': '', 'level': level, 'message': line_content, 'details': '', 'count': 1,
                            'raw_lines': [idx + 1] # 文本模式同样注入行号
                        }
                if current_block:
                    self._add_or_merge_block(blocks, current_block)
        except Exception as e:
            logger.error(f"Error reading text log {filepath}: {e}", exc_info=True)
            
        return blocks if keep_all else blocks[-self.max_blocks:]


class LogCondenser:
    """
    智能日志浓缩器：
    负责将海量/冗长的日志裁剪提炼为低 Token、高信息密度的摘要，供 AI 分析隐性冲突。
    """
    
    # 匹配无用堆栈的正则（Unity、Mono、系统底层核心）
    JUNK_STACK_PATTERN = re.compile(r'^(UnityEngine\.|System\.|Mono\.|Verse\.Log:|mscorlib|System\.Runtime)', re.IGNORECASE)

    @classmethod
    def clean_stack_trace(cls, stack_trace: str, max_lines: int = 6) -> str:
        """清洗堆栈：剔除废话，仅保留触发点和源头"""
        if not stack_trace: return ""
        
        lines =[line.strip() for line in stack_trace.split('\n') if line.strip()]
        # 剔除垃圾堆栈，保留业务代码（如 RimWorld 源码、Mod 源码）
        cleaned_lines =[line for line in lines if not cls.JUNK_STACK_PATTERN.match(line)]
        
        # 如果清洗后依然很长，保留头部（异常抛出点）和尾部（最初的调用源头）
        if len(cleaned_lines) > max_lines:
            half = max_lines // 2
            return "\n".join(cleaned_lines[:half]) + "\n\n...[其它调用堆栈已折叠]...\n\n" + "\n".join(cleaned_lines[-half:])
        return "\n".join(cleaned_lines)

    @classmethod
    def _normalize_raw_lines(cls, raw_lines: list) -> list:
        normalized = []
        for raw_line in raw_lines or []:
            try:
                normalized.append(int(raw_line))
            except (TypeError, ValueError):
                continue
        return sorted(set(normalized))

    @classmethod
    def _build_fingerprint(cls, log: dict) -> str:
        """用错误类型 + 消息摘要做聚合键，避免不同错误被硬合并。"""
        ctx = log.get("context", {}) or {}
        inferred_type = str(ctx.get("inferredType") or "").strip()
        message = str(log.get("message", "") or "").strip()
        
        # 【优化点】抹平内存地址、数字、特定实例后缀
        message = re.sub(r'0x[0-9a-fA-F]+', '<HEX>', message)
        message = re.sub(r'(Thing_|Pawn_|Bullet_)[\w\d]+', r'\1<ID>', message)
        message = re.sub(r'\d+', '<NUM>', message)
        message = re.sub(r'\s+', ' ', message)
        
        return f"{inferred_type}|{message}".lower()
    
    
    @classmethod
    def _extract_stack_preview(cls, details: str, preview_lines: int) -> str:
        """为目录项提取少量堆栈预览，便于 AI 先做快速判断。"""
        if preview_lines <= 0 or not details: return ""
        cleaned = cls.clean_stack_trace(details, max_lines=max(preview_lines, 2))
        source_text = cleaned or details
        preview = [line.strip() for line in source_text.splitlines() if line.strip()]
        return "\n".join(preview[:preview_lines])

    @classmethod
    def condense_for_ai(cls, raw_logs: list, token_limit: int = 8000, char_budget_ratio: float = 0.65, stack_preview_lines: int = 0 ) -> dict:
        """
        动态漏斗提取核心要点（目录模式）
        """
        if not raw_logs: return {"error": "无有效日志输入"}
        # 1. 过滤出真正的错误
        error_logs = [log for log in raw_logs if log.get("level", "").upper() in ("ERROR", "WARNING", "EXCEPTION")]
        if not error_logs:
            error_logs = raw_logs

        # 2. 统一排序，优先使用首个行号，其次才是时间戳。
        error_logs.sort(key=lambda x: (
            cls._normalize_raw_lines(x.get("raw_lines", []))[0] if cls._normalize_raw_lines(x.get("raw_lines", [])) else 10**12,
            x.get("timestamp", "")
        ))

        grouped_items = {}
        for log in error_logs:
            ctx = log.get("context", {}) or {}
            raw_lines = cls._normalize_raw_lines(log.get("raw_lines", []))
            target_line = raw_lines[0] if raw_lines else 0
            fingerprint = cls._build_fingerprint(log)
            repeat_count = max(1, int(log.get("count", 1) or 1))
            suspect_mods = [str(mod).strip() for mod in ctx.get("relatedModIds", []) if str(mod).strip()]
            stack_preview = cls._extract_stack_preview(str(log.get("details", "") or ""), stack_preview_lines)

            if fingerprint not in grouped_items:
                grouped_items[fingerprint] = {
                    "target_line": target_line,  # 绝对唯一，给AI调用的凭证
                    "repeat_count": repeat_count,
                    "merged_block_count": 1,
                    # "time": log.get("timestamp", ""),
                    "level": str(log.get("level", "") or "").upper(),
                    "type": ctx.get("inferredType", "Unknown"),
                    "suspect_mods": suspect_mods,
                    "related_files": [str(path).strip() for path in ctx.get("relatedFiles", []) if str(path).strip()],
                    "message_preview": str(log.get("message", "") or "").strip(),
                    "stack_preview": stack_preview
                }
                continue

            item = grouped_items[fingerprint]
            item["repeat_count"] += repeat_count
            item["merged_block_count"] += 1
            if not item.get("time") and log.get("timestamp"):
                item["time"] = log.get("timestamp", "")
            if target_line and (not item.get("target_line") or target_line < item["target_line"]):
                item["target_line"] = target_line
                item["log_id"] = log.get("id")
            if not item.get("stack_preview") and stack_preview:
                item["stack_preview"] = stack_preview

            merged_mods = item.get("suspect_mods", []) + suspect_mods
            item["suspect_mods"] = list(dict.fromkeys(merged_mods))
            merged_files = item.get("related_files", []) + [str(path).strip() for path in ctx.get("relatedFiles", []) if str(path).strip()]
            item["related_files"] = list(dict.fromkeys(merged_files))

        # 3. 一键排错更关注“重复次数高 + 更像错误”的摘要，便于 AI 优先抓主因。
        level_rank = {"EXCEPTION": 0, "ERROR": 1, "WARNING": 2}
        grouped_list = sorted(
            grouped_items.values(),
            key=lambda item: (
                -int(item.get("repeat_count", 1) or 1),
                level_rank.get(str(item.get("level", "")).upper(), 9),
                int(item.get("target_line", 0) or 0)
            )
        )

        max_safe_chars = int(token_limit * max(0.20, min(char_budget_ratio, 0.90)) * 2.5)
        current_chars = 0
        toc_list = []
        for item in grouped_list:
            item_str = json.dumps(item, ensure_ascii=False)
            item_chars = len(item_str)
            if toc_list and current_chars + item_chars > max_safe_chars:
                break
            toc_list.append(item)
            current_chars += item_chars

        total_repeat_count = sum(int(item.get("repeat_count", 1) or 1) for item in grouped_list)
        compression_notice = (
            f"已压缩完成：从 {len(raw_logs)} 条日志块中筛出 {len(error_logs)} 条错误日志块，"
            f"合并为 {len(toc_list)} 条摘要，总出现 {total_repeat_count} 次。"
        )

        logger.debug(
            f"[日志压缩] input_blocks={len(raw_logs)} error_blocks={len(error_logs)} token_limit={token_limit} "
            f"grouped_items={len(grouped_list)} output_items={len(toc_list)} "
            f"char_budget_ratio={char_budget_ratio:.2f} stack_preview_lines={stack_preview_lines}"
            f"total_repeat_count={total_repeat_count} used_chars={current_chars} max_chars={max_safe_chars}"
        )

        return {
            "errors": toc_list,
            "total_repeat_count": total_repeat_count,
            "selected_error_count": len(toc_list),
            "truncated": len(toc_list) < len(grouped_list),
            "summary": compression_notice,
        }
    
