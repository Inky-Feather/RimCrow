# backend/managers/mgr_game_logs.py
import json
import os
import re
from datetime import datetime
import threading
import time

from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext
from backend.utils.event_bus import EventBus
from backend.utils.logger import BaseLogReader, generate_log_id, logger
from backend.settings import DATA_DIR


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
    def __init__(self, context: ProfileContext):
        # 游戏日志通常较长，这里限制为最近 2 万条结构化 Block，避免长时间运行后占用过多内存
        super().__init__(max_blocks=20000) # 初始化 BaseLogReader 的缓存和内存限制
        self.context = context
        self.analyzer = LogAnalyzer()
        # 实时监视器相关状态
        self._realtime_thread = None
        self._stop_event = threading.Event()
        self.realtime_log_file = os.path.join(self.context.user_data_path, 'RMM_Realtime.log')
        
        self._patterns = {
            'error': re.compile(r'error|exception|crash|fail', re.IGNORECASE),
            'warning': re.compile(r'warning', re.IGNORECASE)
        }


    # 启动/停止实时监视器
    def start_realtime_monitor(self):
        """启动后台线程来实时监视 RMM_Realtime.log 文件"""
        if self._realtime_thread and self._realtime_thread.is_alive():
            return # 已经启动
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
                # 直接跳到文件末尾
                f.seek(0, 2)
                while not self._stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(0.1) # 没有新内容，短暂休眠
                        continue
                    
                    # 有新内容，解析并推送
                    try:
                        data = json.loads(line)
                        data['id'] = generate_log_id(data.get('timestamp', ''), data.get('level', 'INFO'), data.get('message', ''))
                        EventBus.emit('game-log', data)
                    except json.JSONDecodeError:
                        # 忽略无法解析的行
                        pass
        except Exception as e:
            logger.error(f"日志监视线程异常退出: {e}", exc_info=True)


    def get_log_files(self):
        """获取日志文件列表，支持 app(软件日志) 和 game(游戏日志)"""
        result =[]
        # 游戏日志
        base_path = self.context.user_data_path
        if base_path and os.path.exists(base_path):
            candidates = ['RMM_Realtime.log', 'RMM_Realtime-prev.log', 'Player.log', 'Player-prev.log']
            for filename in candidates:
                filepath = os.path.join(base_path, filename)
                if os.path.exists(filepath):
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
        # 1. 确定物理路径
        filepath = os.path.join(self.context.user_data_path, filename)
            
        if not os.path.exists(filepath): return {'error': '文件不存在'}

        stat = os.stat(filepath)

        # 使用缓存机制，避免重复读文件
        if filepath not in self._cache or self._cache[filepath]['mtime'] != stat.st_mtime:
            self._cache[filepath] = {
                'mtime': stat.st_mtime,
                'blocks': self._parse_file_to_blocks(filepath)
            }

        # 3. 计算分页切片 (倒序分页算法)
        result = self.get_paged_data(self._cache[filepath]['blocks'], page, page_size)
        
        # 如果请求的页数超出了总页数，返回空
        if result['status'] == 'success':
            self._analyze_page(result['blocks'], filename)
            
        return result

    def _analyze_page(self, page_blocks, filename):
        """游戏日志特有的分析逻辑"""
        is_json_log = filename.startswith('RMM_Realtime') or filename.endswith('.json')
        # 获取激活 Mod 列表用于交叉比对
        active_mods_set = set()
        try:
            lo_mgr = LoadOrderManager(self.context)
            active_mods = lo_mgr.read_active_mods().get('active_mods', [])
            active_mods_set = {m.lower() for m in active_mods}
        except Exception: pass

        for block in page_blocks:
            if 'context' not in block or 'inferredType' not in block.get('context', {}):
                self.analyzer.analyze(block, is_realtime_json=is_json_log, active_mods=active_mods_set)

    def _parse_file_to_blocks(self, filepath):
        """
        流式读取文件，并转为结构化 Block 列表
        修正：不再物理截断老旧日志
        """
        blocks =[]
        filename = os.path.basename(filepath)
        is_json = filename.endswith('.json') or filename.startswith('RMM_Realtime')
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                # --- JSON 流式读取 ---
                if is_json:
                    for line in f:
                        try:
                            data = json.loads(line)
                            # 历史数据兼容与格式归一化
                            data['message'] = data.get('message', '').replace('\\n', '\n')
                            
                            data['details'] = data.get('details', '').replace('\\n', '\n')
                            
                            # 为来自文件的数据统一打上强一致性 Hash ID
                            data['id'] = generate_log_id(data.get('timestamp', ''), data.get('level', 'INFO'), data['message'])
                            
                            # 注意：移除了这里的 analyzer.analyze()，交给了上面的 read_log_page
                            self._add_or_merge_block(blocks, data)
                        except: continue
                # --- 纯文本流式读取 (向下兼容) ---
                else:
                    current_block = None
                    idx = 0
                    for line in f:
                        line_content = line.rstrip('\r\n')
                        if not line_content: continue
                        
                        if line_content.startswith((' ', '\t', 'at ', '(Filename:')) and current_block:
                        
                            current_block['details'] += '\n' + line_content
                        else:
                            if current_block: 
                                self._add_or_merge_block(blocks, current_block)
                            
                            level = 'INFO'
                            if self._patterns['error'].search(line_content): level = 'ERROR'
                            elif self._patterns['warning'].search(line_content): level = 'WARNING'
                            
                            current_block = {
                                # Player.log 同一文本会在文件中反复出现；仅用 message 生成 id 会导致前端虚拟列表 key 冲突
                                # 这里把块序号并入 id，保证同文件内每个 block 都有稳定且唯一的标识
                                'id': generate_log_id(f'playerlog_{idx}', level, line_content),
                                'timestamp': '', 'level': level, 'message': line_content, 'details': '', 'count': 1
                            }
                            idx += 1

                    if current_block:
                        self._add_or_merge_block(blocks, current_block)
            
                
        except Exception as e:
            logger.error(f"Error reading log {filepath}: {e}", exc_info=True)

        return blocks[-self.max_blocks:]
