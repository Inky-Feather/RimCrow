# backend/managers/mgr_logs.py
import os
import re
import html
from datetime import datetime
from backend.settings import settings
from backend.utils.logger import logger

class GameLogManager:
    def __init__(self):
        # 预编译正则，提高分析效率
        self._patterns = {
            'error': re.compile(r'error|exception|crash|fail', re.IGNORECASE),
            'warning': re.compile(r'warning', re.IGNORECASE),
            # 用来判断是否是一个新的日志条目的开头
            # Unity日志通常新条目顶格，堆栈信息会缩进，或者新条目非空
            # 这里采用简单策略：非空行且不以 "  at " (堆栈特征) 开头视为新条目
            'stack_trace': re.compile(r'^\s+at |^\(Filename:'),
        }
        # 读取限制，防止读取几GB的垃圾日志撑爆内存
        self.MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB

    def get_log_files(self):
        """
        获取可用的游戏日志文件列表
        """
        base_path = settings.config.user_data_path
        if not base_path or not os.path.exists(base_path):
            return []

        candidates = ['Player.log', 'Player-prev.log']
        result = []

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
        return result

    def read_and_parse_log(self, filename):
        """
        读取并解析指定日志文件
        返回: { 'content': [...ParsedBlocks...], 'is_truncated': bool }
        """
        base_path = settings.config.user_data_path
        if not base_path:
            return {'error': '配置中未找到 LocalLow 路径'}
            
        filepath = os.path.join(base_path, filename)
        if not os.path.exists(filepath):
            return {'error': '文件不存在'}

        file_size = os.path.getsize(filepath)
        is_truncated = False
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                # 如果文件过大，只读最后 10MB (通常错误都在最后)
                if file_size > self.MAX_LOG_SIZE:
                    f.seek(file_size - self.MAX_LOG_SIZE)
                    is_truncated = True
                    # 丢弃第一行，因为它可能是不完整的
                    f.readline()
                
                raw_lines = f.readlines()

            parsed_blocks = self._parse_lines_to_blocks(raw_lines)
            
            return {
                'status': 'success',
                'filename': filename,
                'blocks': parsed_blocks,
                'is_truncated': is_truncated,
                'total_lines': len(raw_lines)
            }

        except Exception as e:
            logger.error(f"Error reading game log {filename}: {e}", exc_info=True)
            return {'error': str(e)}

    def _parse_lines_to_blocks(self, lines):
        """
        将原始行解析为逻辑块 (Block)。
        一个 Block 可能包含多行 (例如一条错误信息 + 紧接着的堆栈追踪)。
        """
        blocks = []
        current_block = None

        for line in lines:
            line_content = line.rstrip()
            if not line_content: continue 

            # 判定是否为堆栈信息 (以 "  at " 开头 或 "(Filename:" 结尾)
            is_stack = self._patterns['stack_trace'].search(line_content) is not None
            
            if is_stack and current_block:
                current_block['text'] += '\n' + line_content
                current_block['has_stack'] = True
            else:
                # 结算上一条 Block
                if current_block:
                    self._add_or_merge_block(blocks, current_block)
                
                # 新 Block
                level = 'INFO'
                if self._patterns['error'].search(line_content): level = 'ERROR'
                elif self._patterns['warning'].search(line_content): level = 'WARNING'
                
                current_block = {
                    'level': level,
                    'text': line_content,
                    'has_stack': False,
                    'count': 1, # 新增计数器
                    'id': 0 # 占位，最后统一生成
                }

        # 结算最后一条
        if current_block:
            self._add_or_merge_block(blocks, current_block)
        
        # 重新生成 ID
        for idx, b in enumerate(blocks):
            b['id'] = idx

        return blocks

    def _add_or_merge_block(self, blocks, new_block):
        """
        核心去重逻辑：如果新块的内容与列表中最后一个块相同，则合并计数
        """
        if not blocks:
            blocks.append(new_block)
            return

        last_block = blocks[-1]
        
        # 只有当 级别相同 且 文本内容完全一致 时才合并
        # 注意：这里对比的是包含堆栈的全文本，防止堆栈不同的错误被错误合并
        if last_block['level'] == new_block['level'] and last_block['text'] == new_block['text']:
            last_block['count'] += 1
        else:
            blocks.append(new_block)