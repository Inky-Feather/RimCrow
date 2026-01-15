# backend/scanner/mod_scanner.py
import os
import re
import time
import concurrent.futures


# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径对不对
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        

from backend.database.dao import ModDAO
from backend.scanner.parser_xml import ModXMLParser
from backend.scanner.analyzer import ModAnalyzer
from backend.scanner.parser_dlc import DLCParser
from backend.managers.mgr_files import FileManager
from backend.settings import settings
from backend.utils.logger import logger # 引入日志
from backend.utils.event_bus import EventBus # 引入事件总线

class ModScanner:
    def __init__(self):
        # DLCParser 不在 init 初始化，因为要看扫描路径里有没有 Data
        self.dlc_parser = None
        self.xml_parser = ModXMLParser()
        self.analyzer = ModAnalyzer()
        # 线程池 (扫描通常是 IO 密集型，但 XML 解析是 CPU 密集型，默认 worker 数即可)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._is_scanning = False

    def scan_paths_async(self, search_paths, thumbnail_mgr: FileManager, forced_update=False):
        """
        异步扫描入口。立即返回，任务在后台运行。
        """
        if self._is_scanning:
            return {'status': 'busy', 'message': '扫描已在进行中'}
        
        self._is_scanning = True
        # 提交到线程池
        self.executor.submit(self._scan_paths_task, search_paths, thumbnail_mgr, forced_update)
        return {'status': 'started'}

    def _scan_paths_task(self, search_paths, thumbnail_mgr, forced_update=False):
        """
        后台执行的扫描主逻辑
        """
        logger.info(f"Scan started. Paths: {search_paths}")
        start_time = time.time()
        try:
            EventBus.emit('scan-start')
            
            # --- 0. 预检查与准备 ---
            valid_paths = [p for p in search_paths if p and os.path.exists(p)]
            if not valid_paths:
                self._finish_scan({'error': '没有有效路径'})
                return

            # 初始化 DLC Parser
            data_dir = next((p for p in valid_paths if os.path.basename(p).lower() == 'data'), None)
            dlc_parser = None
            if data_dir:
                user_lang = settings.config.language
                dlc_parser = DLCParser(data_dir)

            existing_mtimes = ModDAO.get_mod_mtimes()   # 从数据库获取已存在的 Mod 时间戳
            
            # --- 1. 快速搜集所有待扫描文件夹 (用于计算进度总数) ---
            EventBus.emit('scan-progress', {'stage': 'indexing', 'message': '正在索引文件...'})
            
            # --- 冲突检测容器 ---
            # session_map: 记录本次扫描已遇到的 { package_id: mod_data }
            # 用于防止同一包名被多次写入数据库，并捕获冲突
            session_map = {} 
            conflict_map = {}  # 记录发生冲突的所有实例 conflict_map: { package_id: [mod_data_1, mod_data_2, ...] }
            
            all_mod_dirs = []
            for base_path in valid_paths:
                try:
                    # 只看一级子目录
                    subdirs = [os.path.join(base_path, d) for d in os.listdir(base_path) 
                               if os.path.isdir(os.path.join(base_path, d))]
                    all_mod_dirs.extend(subdirs)
                except OSError:
                    pass
            
            total_count = len(all_mod_dirs)
            current_count = 0
            # 优化：根据总数动态决定发送频率
            # 如果只有 10 个 Mod，每 1 个发一次
            # 如果有 1000 个 Mod，每 20 个发一次
            report_interval = max(1, total_count // 50) 
            
            # --- 2. 逐个处理 ---
            mods_to_upsert = []
            scanned_package_ids = set()
            stats = {'added': 0, 'updated': 0, 'skipped': 0, 'removed': 0, 'duration': 0.0}
            start_time = time.time()

            # 批量提交大小，每处理 N 个写入一次数据库，防止内存占用过大
            BATCH_SIZE = 50 

            for mod_path in all_mod_dirs:
                current_count += 1
                folder_name = os.path.basename(mod_path)
                
                # 发送进度 (降低频率，每5个发送一次，避免前端渲染卡顿)
                if current_count % report_interval == 0 or current_count == total_count:
                    percent = int((current_count / total_count) * 100)
                    EventBus.emit('scan-progress', {
                        'stage': 'scanning',
                        'current': current_count,
                        'total': total_count,
                        'percent': percent,
                        'message': f"正在分析: {folder_name}"
                    })

                # --- 核心处理逻辑 ---
                is_dlc_dir = (os.path.dirname(mod_path) == data_dir)
                
                # 处理单个 Mod
                mod_data = self._process_single_mod(
                    mod_path, is_dlc_dir, existing_mtimes, 
                    dlc_parser, thumbnail_mgr, forced_update
                )

                if mod_data:
                    # 如果是 Skipped (增量跳过)，返回的是特殊标记或 None? 
                    # 约定 _process_single_mod 返回 None 表示跳过或无效。
                    # 增量跳过的项通常意味着路径没变，大概率不会冲突。如果是新扫描到的，一定要检查。
                    
                    # --- 重复冲突检测 ---
                    pkg_id = mod_data['package_id'].lower() # 统一小写比较
                    if pkg_id in session_map:
                        
                        # 记录冲突供前端处理
                        # 注意：这里不把当前 mod_data 加入 mods_to_upsert
                        # 扫描器遵循“先入为主”原则，先扫到的入库，后扫到的报冲突
                        # 如果现有项是 skipped 状态，强制重读完整信息
                        if mod_data.get('_skipped'):
                            mod_data = self._process_single_mod(
                                mod_path, is_dlc_dir, existing_mtimes, dlc_parser, thumbnail_mgr,
                                forced_update=True # 强制重读
                            ) or mod_data # 兜底防止 None

                        # B. 初始化或更新冲突组
                        if pkg_id not in conflict_map:
                            # 这是该包名第一次发生冲突
                            # 需要把“大房”(第一次遇到的那个) 也拉进冲突组
                            existing = session_map[pkg_id]
                            
                            # 确保“大房”也是完整的
                            if existing.get('_skipped'):
                                existing_full = self._process_single_mod(
                                    existing['path'], 
                                    (os.path.dirname(existing['path']) == data_dir), 
                                    existing_mtimes, dlc_parser, thumbnail_mgr, 
                                    forced_update=True
                                )
                                if existing_full:
                                    existing = existing_full
                                    session_map[pkg_id] = existing # 更新引用
                            
                            # 创建列表：[大房, 二房]
                            conflict_map[pkg_id] = [existing, mod_data]
                        else:
                            # 已经是冲突组了，直接加入“三房、四房...”
                            conflict_map[pkg_id].append(mod_data)
                            
                        print(f"发现重复包名冲突: {pkg_id}", conflict_map)
                        # 即使冲突，我们也记录在 scanned_package_ids 里，防止被当做 missing 删除
                        scanned_package_ids.add(pkg_id)
                        stats['skipped'] += 1 # 计入跳过
                        # 数据库里只保留 session_map 里的那一份（即最先扫到的）
                        # 等用户在前端决定后再修改
                        continue # 关键：跳过入库
                    else:
                        # 第一次遇到，记录到 session_map
                        session_map[pkg_id] = mod_data
                        
                    # 记录逻辑
                    if mod_data.get('_skipped'):
                        stats['skipped'] += 1
                        scanned_package_ids.add(mod_data['package_id']) # 即使跳过也要记录ID以免被当做missing删除
                    else:
                        mods_to_upsert.append(mod_data)
                        scanned_package_ids.add(mod_data['package_id'])
                        if mod_data.get('is_new'):
                            stats['added'] += 1
                        else:
                            stats['updated'] += 1
                
                # 分批写入
                if len(mods_to_upsert) >= BATCH_SIZE:
                    ModDAO.batch_upsert_mods(mods_to_upsert)
                    mods_to_upsert = [] # 清空

            # 处理剩余的
            if mods_to_upsert:
                ModDAO.batch_upsert_mods(mods_to_upsert)

            # --- 3. 清理与收尾 ---
            EventBus.emit('scan-progress', {'stage': 'cleaning', 'message': '正在清理无效数据...'})
            # 扫描缺失的Mod，根据设置删除不存在的 Mod 数据
            all_missing_mods = ModDAO.find_missing_mods(settings.config.delete_missing_mods_data)
            stats['removed'] = len(all_missing_mods['deleted_mods'])
            logger.info(f"{'Deleted' if settings.config.delete_missing_mods_data else 'Find'} {stats['removed']} missing mods.")
            # 清理失效的 Shadow Paths
            shadow_cleaned_count = ModDAO.clean_invalid_shadow_paths()
            if shadow_cleaned_count > 0:
                logger.info(f"Cleaned {shadow_cleaned_count} invalid shadow paths.")
            
            # 将 map 转换为 list 发送给前端
            # 结构: [{ package_id: '...', items: [...] }, ...]
            final_conflicts = []
            for pid, items_list in conflict_map.items():
                final_conflicts.append({
                    'package_id': pid,
                    'items': items_list
                })
            
            # 强制发送 100% 进度
            EventBus.emit('scan-progress', {
                'stage': 'finished',
                'current': total_count,
                'total': total_count,
                'percent': 100,
                'message': '扫描完成'
            })
            
            # 给前端一点点时间处理 100% 的状态，再发送 complete
            time.sleep(0.2) 
            
            stats['duration'] = time.time() - start_time
            result = {
                'status': 'success',
                'total': stats['added'] + stats['updated'] + stats['skipped'],
                'stats': stats,
                'conflicts': final_conflicts  # 发送冲突列表
            }
            self._finish_scan(result)

            duration = time.time() - start_time
            logger.info(f"Scan finished in {duration:.2f}s. Added: {stats['added']}, Updated: {stats['updated']}")
        except Exception as e:
            logger.error("Scan task failed abruptly", exc_info=True)
            import traceback
            traceback.print_exc()
            result = {
                'status': 'error',
                'message': str(e),
            }
            self._finish_scan(result)
        finally:
            self._is_scanning = False

    def _finish_scan(self, result):
        """扫描结束，通知前端并发送最终统计"""
        print(f"Scan finished: {result['stats']}")
        # 获取最新全量数据，或者让前端自己再调一次 get_all_mods
        # 建议直接通知前端 "scan-complete"，让前端决定是否刷新列表
        
        EventBus.emit('scan-complete', result)

    def _process_single_mod(self, mod_path, is_dlc_dir, existing_mtimes, dlc_parser, thumbnail_mgr, forced_update=False):
        """
        处理单个 Mod 的纯函数逻辑。
        返回: Mod数据字典 或 None(无效) 或 {'_skipped': True, 'package_id': ...}
        """
        about_file = os.path.join(mod_path, 'About', 'About.xml')
        disabled_file = os.path.join(mod_path, 'About', 'About.xml.disabled')
        # DLC 可能没有 About.xml，但 Data 目录下的子文件夹我们通常认为是 DLC
        # 这里的判断需要稍微灵活点。如果是在 Data 目录下，即使没有 About 也可能是 Core
        # 如果没有 About.xml，但有 .disabled，说明这是被管理器禁用的重复项，直接跳过（视为不存在）
        if not os.path.exists(about_file):
            if os.path.exists(disabled_file):
                return None  # 这是一个被禁用的影子 Mod，本次扫描忽略
            if not is_dlc_dir:
                return None # 既不是 DLC 也没有 About.xml，无效

        # 检查 mtime
        try:
            mtime = int(os.path.getmtime(about_file)*1000) if os.path.exists(about_file) else 0
            ctime = int(os.path.getctime(about_file)*1000) if os.path.exists(about_file) else 0
        except OSError:
            mtime = 0; ctime = 0

        # 解析
        mod_data = self.xml_parser.parse(mod_path)
        pkg_id = mod_data.get('package_id')
        
        # DLC 兜底 ID
        if is_dlc_dir and not pkg_id:
            folder = os.path.basename(mod_path)
            if folder.lower() == 'core': 
                pkg_id = 'ludeon.rimworld'
            else: pkg_id = f'ludeon.rimworld.{folder.lower()}'
            mod_data['package_id'] = pkg_id

        if not pkg_id: return None

        # 增量检查
        if (pkg_id in existing_mtimes and abs(existing_mtimes[pkg_id] - mtime) < 1.0) and not forced_update:
            return {'_skipped': True, 'package_id': pkg_id, 'path': mod_path, 'mtime': mtime}
        
        # 新增标记
        if (pkg_id not in existing_mtimes):
            mod_data['is_new'] = True
        
        # DLC 注入
        if is_dlc_dir and dlc_parser:
            dlc_parser.enrich_data(mod_data, mod_path)

        # Workshop & Source
        workshop_id = self._resolve_workshop_id(mod_path)
        mod_data['workshop_id'] = workshop_id
        if workshop_id and mod_path.find('\\workshop\\') >= 0:
            mod_data['url'] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
            mod_data['source'] = 'workshop'
        
        # 补充 Source 判断
        url = mod_data.get('url', '').lower()
        if not mod_data.get('source',''):
            if 'github.com' in url: mod_data['source'] = 'github'
            elif url: mod_data['source'] = 'other'
            elif is_dlc_dir: mod_data['source'] = 'dlc' # DLC
            else: mod_data['source'] = 'local'
        # 其他来源的本地 Mod 都视为 'other'
        if mod_data.get('url','') and  mod_path.find('\\Mods\\') >= 0:
            mod_data['source'] = 'other'
        
        # 补充 supported_versions
        if mod_data.get('source','').lower() == 'core':
            mod_data['supported_versions'] = [settings.config.game_version[:3]]  # Core 补充支持版本

        # 图片
        preview_path, icon_path = self._resolve_images(mod_path, mod_data.get('icon_path', ''))
        mod_data['preview_path'] = preview_path
        mod_data['icon_path'] = icon_path

        # 深度分析
        analysis_info = self.analyzer.analyze(mod_path)
        mod_data.update({
            'supported_languages': analysis_info['supported_languages'],
            'file_stats': analysis_info['file_stats'],
            'mod_type': analysis_info['mod_type'],
            'path': mod_path,
            'file_create_time': ctime,
            'file_modify_time': mtime,
        })

        # 缩略图生成 (耗时操作，但在线程池里做是可以的)
        if thumbnail_mgr and preview_path:
            thumbnail_mgr.ensure_thumbnail(pkg_id, preview_path)
            
        return mod_data

    def _resolve_workshop_id(self, mod_path):
        """
        获取 Workshop ID。
        优先级：About/PublishedFileId.txt > 文件夹名(如果是纯数字)
        """
        # 1. 尝试读取 PublishedFileId.txt (最准确)
        id_file = os.path.join(mod_path, 'About', 'PublishedFileId.txt')
        if os.path.exists(id_file):
            try:
                with open(id_file, 'r', encoding='utf-8-sig') as f: 
                    # 使用 'utf-8-sig' 可以自动去除 BOM 头 (\ufeff)
                    content = f.read().strip()
                    # 某些奇怪的情况文件里可能有杂质，提取纯数字
                    match = re.search(r'\d+', content)
                    if match:
                        return match.group()
            except Exception:
                pass
        
        # 2. 尝试使用文件夹名 (如果是纯数字 且 路径中包含 "steamapps\workshop\content\427520")
        # 建议：使用 path 字符串查找，不依赖正则，避免分隔符坑
        norm_path = os.path.normpath(mod_path).lower() # 统一转为小写、标准分隔符
        # 检查路径中是否包含 workshop/content/294100 关键段
        # Windows normpath 会是 workshop\content\294100
        keywords = os.path.join('workshop', 'content', '294100').lower()
        if keywords in norm_path:
            folder_name = os.path.basename(mod_path)
            # 只要是纯数字就认
            if folder_name.isdigit():
                return folder_name
            
        return None

    def _resolve_images(self, mod_path, xml_icon_path):
        """
        解析预览图和图标的绝对路径。
        """
        # --- Preview.png ---
        # 默认位置：About/Preview.png
        # 扩展：RimWorld 也支持 jpg/gif 改名为 png，或者直接识别。
        # 这里简单起见，先只找 About/Preview.png，如果要做得细致，可以 glob 搜索
        preview_path = os.path.join(mod_path, 'About', 'Preview.png')
        if not os.path.isfile(preview_path): preview_path = ""

        # --- ModIcon.png ---
        icon_path = os.path.join(mod_path, 'About', 'ModIcon.png')
        if not os.path.isfile(icon_path): icon_path = ""
        
        rel_xml_icon_path = os.path.join(mod_path, 'Textures', xml_icon_path+'.png')
        if not os.path.isfile(rel_xml_icon_path): rel_xml_icon_path = ""
        
        # 使用 XML 中定义的路径 (RimWorld 1.5+)
        if not icon_path and rel_xml_icon_path:
            icon_path = rel_xml_icon_path

        return preview_path, icon_path
