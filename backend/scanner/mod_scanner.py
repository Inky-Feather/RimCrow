# backend/scanner/mod_scanner.py
from collections import defaultdict
import os
import re
import time
import concurrent.futures
from backend.managers.mgr_game_logs import GameLogManager
from backend.utils.tools import generate_path_hash, get_folder_size
from backend.database.models import db

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
        # DLCParser 不在 init 初始化，因为要看扫描路径里有没有 DLC 目录
        self.dlc_parser = None
        self.xml_parser = ModXMLParser()
        self.analyzer = ModAnalyzer()
        # 线程池 (扫描通常是 IO 密集型，但 XML 解析是 CPU 密集型，默认 worker 数即可)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._is_scanning = False
        self._stop_requested = False  # 中断请求标志

    def stop_scan(self):
        """外部调用：请求中断扫描"""
        if self._is_scanning:
            self._stop_requested = True
            logger.warning("Scan interruption requested by user.")
            
    def scan_paths_async(self, search_paths, forced_update=False):
        """
        异步扫描入口。立即返回，任务在后台运行。
        """
        EventBus.resume()   # 恢复事件总线
        if self._is_scanning:
            return {'status': 'busy', 'message': '扫描已在进行中'}
        
        self._is_scanning = True
        self._stop_requested = False  # 启动前重置标志
        # 提交到线程池
        self.executor.submit(self._scan_paths_task, search_paths, forced_update)
        return {'status': 'started'}

    def _scan_paths_task(self, search_paths, forced_update=False):
        """
        后台执行的扫描主逻辑
        """
        logger.info(f"Scan started. Paths: {search_paths}")
        start_time = time.time()
        db.connect(reuse_if_open=True) # 确保线程有连接
        stats = {'added': 0, 'updated': 0, 'skipped': 0, 'removed': 0, 'duration': 0.0}
        with db.atomic() as txn:
            try:
                # --- 5. 清理失效数据 ---
                # 扫描缺失的 Mod (物理文件没了)
                deletion_result = ModDAO.find_missing_mods(settings.config.delete_missing_mods_data)
                stats['removed'] = len(deletion_result['deleted_mods'])
                logger.info(f"{'Deleted' if settings.config.delete_missing_mods_data else 'Find'} {stats['removed']} missing mods.")
                # 清理失效的 Shadow Paths
                ModDAO.clean_invalid_shadow_paths()
            except Exception as e:
                txn.rollback() # 万一出错，回滚所有改动
                raise e
        try:
            EventBus.emit('scan-start')
            # --- 0. 预检查与准备 ---
            valid_paths = [p for p in search_paths if p and os.path.exists(p)]
            if not valid_paths:
                self._finish_scan({'error': '没有有效路径'})
                return
            # 初始化 DLC Parser
            dlc_dir = next((p for p in valid_paths if os.path.basename(p).lower() == 'data'), None)
            dlc_parser = DLCParser(dlc_dir) if dlc_dir else None
            existing_snapshots = ModDAO.get_mod_snapshots()   # 从数据库获取已存在的 Mod 时间戳及大小
            # --- 1. 快速搜集所有待扫描文件夹 (用于计算进度总数) ---
            EventBus.emit('scan-progress', {'stage': 'indexing', 'message': '正在索引文件...'})
            mod_folders = [] # [(folder_path, is_dlc), ...]
            for base_path in valid_paths:
                try:
                    # 判断是否是 DLC 目录 (Data)
                    is_data_dir = (os.path.basename(base_path).lower() == 'data')
                    with os.scandir(base_path) as it:
                        for entry in it:
                            if entry.is_dir():
                                # 遇到链接生成目录直接跳过，防止无限递归和重复
                                if entry.name.startswith(FileManager.LINK_PREFIX): continue
                                mod_folders.append((entry.path, is_data_dir))
                except OSError as e:
                    logger.warning(f"无法访问路径 {base_path}: {e}")
            total_count = len(mod_folders)
            # 优化：根据总数动态决定发送频率
            report_interval = max(1, total_count // 50) 
            # --- 2. 扫描与解析阶段 ---
            # 使用 temp_registry 暂存所有扫描结果，而不是一边扫一边入库
            # 结构: { package_id: [mod_data_1, mod_data_2] }
            temp_registry = defaultdict(list)
            scanned_package_ids = set()
            start_time = time.time()
            for idx, (mod_path, is_dlc) in enumerate(mod_folders):
                # 【关键检查点】：每一条 Mod 解析前检查中断标志
                if self._stop_requested:
                    logger.info("Scan stopped during parsing stage.")
                    self._handle_interruption()
                    return # 直接结束任务，不进入写库阶段
                # 进度报告
                if (idx + 1) % report_interval == 0:
                    percent = int(((idx + 1) / total_count) * 100)
                    EventBus.emit('scan-progress', {
                        'stage': 'scanning',
                        'current': (idx + 1),
                        'total': total_count,
                        'percent': percent,
                        'message': f"分析中: {os.path.basename(mod_path)}"
                    })
                # 处理单个 Mod
                mod_data = self._process_single_mod(
                    mod_path, is_dlc, existing_snapshots, 
                    dlc_parser, forced_update
                )
                if mod_data:
                    # 如果是增量跳过，需要补全 package_id 以便后续逻辑使用
                    # _process_single_mod 返回 {'_skipped': True, 'package_id': ...}
                    pid = mod_data['package_id'].lower()
                    # 记录到暂存区
                    temp_registry[pid].append(mod_data)
                    scanned_package_ids.add(pid)
                    if mod_data.get('_skipped'):
                        stats['skipped'] += 1
                    elif mod_data.get('is_new'):
                        stats['added'] += 1
                    else:
                        stats['updated'] += 1
                        
            # 【关键检查点】：解析完成后检查中断标志
            if self._stop_requested:
                logger.info("Scan stopped during parsing stage.")
                self._handle_interruption()
                return # 直接结束任务，不进入写库阶段
            # --- 3. 冲突仲裁与入库决策 ---
            EventBus.emit('scan-progress', {'stage': 'analyzing', 'message': '正在处理冲突与部署...'})
            
            mods_to_upsert = []
            final_conflicts = [] # 发送给前端的硬冲突列表
            final_coexistences = []  # 发送给前端的软冲突列表
            
            # 部署准备：Local Mod 集合 (用于部署时排除)
            local_mod_ids_for_deploy = set()
            # 部署准备：Workshop Mod 和 Self Mod 候选列表 (路径)
            self_mods_paths_for_deploy = []
            workshop_paths_for_deploy = []

            # 获取本地 Mods 根目录 (用于判定是否同级冲突)
            local_mods_root = settings.config.local_mods_path
            if local_mods_root: 
                local_mods_root = os.path.normpath(local_mods_root).lower()
            
            self_mods_root = settings.config.self_mods_path
            if self_mods_root:
                self_mods_root = os.path.normpath(self_mods_root).lower()
            
            workshop_mods_root = settings.config.workshop_mods_path
            if workshop_mods_root:
                workshop_mods_root = os.path.normpath(workshop_mods_root).lower()

            for pid, entries in temp_registry.items():
                # 【关键检查点】：每一条 Mod 解析前检查中断标志
                if self._stop_requested:
                    logger.info("Scan stopped during parsing stage.")
                    self._handle_interruption()
                    return # 直接结束任务
                
                # 情况 A: 只有一个实例 -> 直接入库
                if len(entries) == 1:
                    mod = entries[0]
                    if not mod.get('_skipped'): # 跳过的不需要重新 Upsert，除非想更新 timestamp
                        mods_to_upsert.append(mod)
                    
                    # 收集部署信息
                    self._classify_for_deploy(mod, local_mods_root,self_mods_root, workshop_mods_root, 
                        local_mod_ids_for_deploy, self_mods_paths_for_deploy, workshop_paths_for_deploy)
                    continue

                # 情况 B: 多个实例 -> 判定冲突类型
                # 按父目录分组
                by_parent = defaultdict(list)
                for mod in entries:
                    # 如果是 skipped 的，为了入库数据的完整性，这里其实应该强制重读一次完整数据
                    # 但为了性能，如果只是位置冲突判断，路径就够了。如果决定入库，则必须保证数据完整。
                    if mod.get('_skipped'):
                        # 触发重读 (这里为了代码简洁，简略处理，实际建议封装 recover 方法)
                        # 实际上，如果发生冲突（多个实例），其中一个是 skipped，只要涉及多实例判定，强制全部重读，确保 source/path 准确。
                        full_mod = self._process_single_mod(
                            mod['path'], (os.path.basename(os.path.dirname(mod['path'])).lower() == 'data'),
                            existing_snapshots, dlc_parser, forced_update=True
                        )
                        if full_mod:
                            mod.update(full_mod) # 更新为完整数据
                            del mod['_skipped']
                    parent_dir = os.path.dirname(mod['path']).lower()
                    by_parent[parent_dir].append(mod)

                # 判定逻辑
                has_hard_conflict = False
                for parent, group in by_parent.items():
                    if len(group) > 1:
                        # 【硬冲突】：同一个目录下有重复 ID
                        # 例如 LocalMods/A 和 LocalMods/B 都是同一个 ID
                        has_hard_conflict = True
                        final_conflicts.append({
                            'package_id': pid,
                            'items': group,         # 发送冲突的具体条目
                            'type': 'same_directory' # 标记类型：同级目录冲突
                        })
                if has_hard_conflict:
                    # 发生硬冲突，暂时都不入库，让用户去修
                    logger.warning(f"Hard conflict detected for {pid}")
                    # continue
                # --- 检查软冲突 (跨目录遮蔽/共存) ---
                # 走到这里说明 len(entries) > 1 且没有硬冲突
                final_coexistences.append({
                    'package_id': pid,
                    'items': entries,            # 包含 Local 和 Workshop 的所有版本
                    'type': 'different_directory' # 标记类型：跨目录共存
                })

                # 【软冲突/共存】：不同目录下的重复 ID (Local vs Workshop)
                # 策略：全部入库！
                # 数据库会存储多条记录 (path不同，path_hash不同，主键不冲突)
                # 查询时由 DAO 根据 Profile 过滤，部署时由下方逻辑过滤
                for mod in entries:
                    mods_to_upsert.append(mod)
                    self._classify_for_deploy(mod, local_mods_root,self_mods_root, workshop_mods_root, 
                        local_mod_ids_for_deploy, self_mods_paths_for_deploy, workshop_paths_for_deploy)

            # --- 4. 批量入库 ---
            # 这是数据安全最关键的一步
            with db.atomic() as txn:
                try:
                    if mods_to_upsert: 
                        ModDAO.batch_upsert_mods(mods_to_upsert)
                except Exception as e:
                    txn.rollback() # 万一出错，回滚所有改动
                    raise e
            
            
            # --- 6. 自动部署链接 (Deployment) ---
            deploy_msg = "跳过链接部署"
            logger.debug(f"Skip deployment: {settings.config.use_workshop_mods} and {settings.config.use_self_mods}, current_profile {settings.config.current_profile_id != 'default'}")
            final_links_to_create = []
            if settings.config.use_self_mods and local_mods_root and os.path.exists(local_mods_root):
                # 遮蔽策略：过滤掉 ID 已经在 Local 存在的 Workshop Mod
                for w_path, w_id in self_mods_paths_for_deploy:
                    if w_id not in local_mod_ids_for_deploy:
                        final_links_to_create.append(w_path)
                    else:
                        # 被本地遮蔽，忽略
                        pass
            
            if settings.config.use_workshop_mods and settings.config.use_self_mods and settings.config.current_profile_id != 'default' \
                and local_mods_root and os.path.exists(local_mods_root):
                # 遮蔽策略：过滤掉 ID 已经在 Local 和 self 存在的 Workshop Mod
                self_mods_ids_for_deploy = [w_id for w_path, w_id in self_mods_paths_for_deploy]
                for w_path, w_id in workshop_paths_for_deploy:
                    if w_id not in local_mod_ids_for_deploy and w_id not in self_mods_ids_for_deploy:
                        final_links_to_create.append(w_path)
                    else:
                        # 被本地遮蔽，忽略
                        pass
                    
            # 调用 FileManager 执行部署
            # 注意：这里需要传入 local_mods_path 的原始大小写路径（用于创建目录）
            success = FileManager.sync_links_fast(local_mods_root, final_links_to_create)
            if final_links_to_create:
                deploy_msg = f"Deployed {len(final_links_to_create)} links" if success else "Deployment failed"

            # --- 7. 完成 ---
            stats['duration'] = time.time() - start_time
            
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
            
            result = {
                'status': 'success',
                'total': stats['added'] + stats['updated'] + stats['skipped'],
                'stats': stats,
                'conflicts': final_conflicts,
                'coexistences': final_coexistences,
                'deploy_message': deploy_msg
            }
            self._finish_scan(result)
            logger.info(f"Scan finished. {stats}. {deploy_msg}")

            duration = time.time() - start_time
            logger.info(f"Scan finished in {duration:.2f}s. Added: {stats['added']}, Updated: {stats['updated']}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error("Scan task failed", exc_info=True)
            self._finish_scan({'status': 'error', 'message': str(e)})
        finally:
            self._is_scanning = False
            self._stop_requested = False # 清理状态

    def _handle_interruption(self):
        """处理中断后的清理和通知"""
        self._is_scanning = False
        EventBus.emit('scan-complete', {
            'status': 'cancelled',
            'message': '扫描已由用户中止，未对数据库进行任何修改。'
        })
        logger.info("Scan cancelled safely.")

    def _finish_scan(self, result):
        """扫描结束，通知前端并发送最终统计"""
        logger.info(f"Scan finished: {result['stats']}")
        # 获取最新全量数据，或者让前端自己再调一次 get_all_mods
        # 建议直接通知前端 "scan-complete"，让前端决定是否刷新列表
        
        EventBus.emit('scan-complete', result)

    def _classify_for_deploy(self, mod_data, local_root, self_mods_root, workshop_root, local_ids_set, self_mods_paths_list, workshop_paths_list):
        """
        辅助函数：将 Mod 分类以便后续部署。
        """
        if not mod_data.get('path'): return
        
        mod_path = os.path.normpath(mod_data['path']).lower()
        pid = mod_data['package_id'].lower()
        
        # 判断 Local
        if local_root and local_root in mod_path:
            local_ids_set.add(pid)
            return
        # 判断 Self Mod
        if self_mods_root and self_mods_root in mod_path:
            self_mods_paths_list.append((mod_data['path'], pid))
            return
        # 判断 Workshop (如果是 DLC 也不需要部署)
        if workshop_root and workshop_root in mod_path:
            # 记录 (路径, ID) 元组
            workshop_paths_list.append((mod_data['path'], pid))
        
    def _process_single_mod(self, mod_path, is_dlc_dir, existing_snapshots, dlc_parser: DLCParser | None, forced_update=False):
        """
        处理单个 Mod 的纯函数逻辑。
        返回: Mod数据字典 或 None(无效) 或 {'_skipped': True, 'package_id': ...}
        """
        about_file = os.path.join(mod_path, 'About', 'About.xml')
        disabled_file = os.path.join(mod_path, 'About', 'About.xml.disabled')
        is_disabled = False 
        # 存在性快速检查 (0 IO)
        # 如果没有 About.xml，但有 .disabled，说明这是被管理器禁用的重复项，直接跳过（视为不存在）
        if not os.path.exists(about_file):
            if os.path.exists(disabled_file):
                about_file = disabled_file  
                is_disabled = True
                # return None  # 这是一个被禁用的影子 Mod，本次扫描忽略
            if not is_dlc_dir:
                return None # 既不是 DLC 也没有 About.xml，无效
        
        # 检查 mtime
        try:
            stat = os.stat(about_file)
            mtime = int(stat.st_mtime * 1000)
            ctime = int(stat.st_ctime * 1000)
        except OSError:
            mtime = 0; ctime = 0
            
        # 物理路径作为哈希主键
        path_hash = generate_path_hash(mod_path)
        # 增量比对 - 第一阶段：仅比对修改时间
        snapshot = existing_snapshots.get(path_hash)
        # 在开启开关或者强制更新的情况下，才需要计算大小
        need_size_check = settings.config.enable_file_size_scan or forced_update

        # 如果快照存在且被禁用，直接跳过
        if snapshot and is_disabled:
            return {
                '_skipped': True, 
                'path_hash': path_hash,
                'package_id': snapshot['package_id'],
                'path': mod_path, 
                'mtime': mtime,
                'file_size': snapshot['size'], # 复用旧大小
                'disabled': is_disabled
            }
            
        disabled_change = not(snapshot and snapshot['disabled'] is is_disabled)
        
        # 增量检测逻辑 (Time AND Size)
        # 如果快照存在且修改时间一致
        if disabled_change: pass
        
        elif snapshot and abs(snapshot['mtime'] - mtime) < 1.0 and not forced_update :
            # 修改时间没变，此时通过开关决定是否开启“深层大小检测”
            if need_size_check:
                # 优化点：只有在修改时间没变时，才执行耗时的 get_folder_size
                current_size = get_folder_size(mod_path)
                if snapshot['size'] > 0 and snapshot['size'] == current_size:
                    # 时间和大小都一致，判定为没变，跳过解析
                    return {
                        '_skipped': True, 
                        'path_hash': path_hash,
                        'package_id': snapshot['package_id'],
                        'path': mod_path, 
                        'mtime': mtime,
                        'file_size': current_size,
                        'disabled': is_disabled
                    }
                # 走到这里说明大小变了，需要继续向下解析
            else:
                # 如果没开大小检测，且修改时间没变，直接视为跳过
                return {
                    '_skipped': True, 
                    'path_hash': path_hash,
                    'package_id': snapshot['package_id'],
                    'path': mod_path, 
                    'mtime': mtime,
                    'file_size': snapshot['size'], # 复用旧大小
                    'disabled': is_disabled
                }
        
        # 解析 XML (CPU 密集)
        # parser 内部如果处理异常会返回默认空结构，这里直接调
        mod_data = self.xml_parser.parse(mod_path)
        pkg_id = mod_data.get('package_id','').lower()
        
        # DLC 兜底 ID
        if is_dlc_dir and not pkg_id:
            folder = os.path.basename(mod_path)
            if folder.lower() == 'core': pkg_id = 'ludeon.rimworld'
            else: pkg_id = f'ludeon.rimworld.{folder.lower()}'
            mod_data['package_id'] = pkg_id

        if not pkg_id: return None
        
        # DLC 注入翻译
        if is_dlc_dir and dlc_parser:
            dlc_parser.enrich_data(mod_data, mod_path)
            mod_data['supported_languages'] = list(dlc_parser.translations.keys())
            

        # 路径与来源分析
        workshop_id = self._resolve_workshop_id(mod_path)
        mod_data['workshop_id'] = workshop_id
        
            
        # Source 补全逻辑
        if workshop_id:
            mod_data['url'] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
            mod_data['source'] = 'workshop'
        elif is_dlc_dir:
            mod_data['source'] = 'dlc' if pkg_id != 'ludeon.rimworld' else 'core'
        elif 'github.com' in mod_data.get('url', '').lower():
            mod_data['source'] = 'github'
        elif mod_data.get('url', ''):
            mod_data['source'] = 'other'
        else:
            mod_data['source'] = 'local'
        

        # 路径标准化 (用于 Python 端比对，统一转小写)
        # 标准化路径用于严格匹配 (增加结尾分隔符确保匹配精确)
        def norm(p): return os.path.normpath(p).lower() + os.sep if p else ""
        L_PATH = norm(os.path.normpath(settings.config.local_mods_path).lower())
        W_PATH = norm(settings.config.workshop_mods_path)
        S_PATH = norm(settings.config.self_mods_path)
        # 补充 store
        m_path = norm(mod_path)
        if S_PATH and m_path.startswith(S_PATH) and (S_PATH != L_PATH):
            mod_data['store'] = 'self'
        elif W_PATH and m_path.startswith(W_PATH):
            mod_data['store'] = 'workshop'
        else:
            mod_data['store'] = 'local'
        
        # 补充 supported_versions
        if mod_data.get('source','').lower() == 'core':
            mod_data['supported_versions'] = [settings.config.game_version[:3]] if settings.config.game_version else 'Unknown'  # Core 补充支持版本

        # 图片
        preview_path, icon_path = self._resolve_images(mod_path, mod_data.get('icon_path', ''))
        mod_data['preview_path'] = preview_path
        mod_data['icon_path'] = icon_path

        # 深度分析
        analysis_info = self.analyzer.analyze(mod_path)
        
        final_size = snapshot.get('size', 0) if snapshot and 'size' in snapshot else 0
        # 新增标记
        if (path_hash not in existing_snapshots):
            mod_data['is_new'] = True
            final_size = get_folder_size(mod_path) # 新增 Mod 时，计算大小
        elif (need_size_check):
            final_size = get_folder_size(mod_path) # 增量 Mod 时，在需要检测大小的情况下，计算大小
            
        mod_data.update({
            'path_hash': path_hash,
            'supported_languages': analysis_info['supported_languages'] if not is_dlc_dir else mod_data.get('supported_languages', []),
            'file_stats': analysis_info['file_stats'],
            'mod_type': analysis_info['mod_type'],
            'path': mod_path,
            'file_create_time': ctime,
            'file_modify_time': mtime,
            'file_size': final_size,
            'source': mod_data.get('source', 'local'), # 来源
            'disabled': False, # 如果它存在 About.xml，说明它是激活的。强制重置为 False
        })

        # 缩略图生成 (耗时操作，线程池内执行)
        if mod_data.get('preview_path'):
            from backend.managers.mgr_files import file_mgr
            file_mgr.ensure_thumbnail(pkg_id, mod_data['preview_path'])
            
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
                    if match: return match.group()
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
    
    
