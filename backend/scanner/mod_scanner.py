# backend/scanner/mod_scanner.py
from collections import defaultdict
import os
import re
import time
import concurrent.futures
from backend.managers.mgr_game_logs import GameLogManager
from backend.managers.mgr_profile import ProfileContext
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
from backend.settings import TOOL_MODS_DIR, settings
from backend.utils.logger import logger # 引入日志
from backend.utils.event_bus import EventBus # 引入事件总线

class ModScanner:
    def __init__(self, context: ProfileContext):
        self.context = context
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
            dlc_parser = DLCParser(self.context.game_dlc_path)
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
            tool_mods_paths_for_deploy = []

            # 获取本地 Mods 根目录 (用于判定是否同级冲突)
            local_mods_root = self.context.local_mods_path
            if local_mods_root: 
                local_mods_root = os.path.normpath(local_mods_root).lower()
            self_mods_root = settings.config.self_mods_path
            if self_mods_root:
                self_mods_root = os.path.normpath(self_mods_root).lower()
            workshop_mods_root = settings.config.workshop_mods_path
            if workshop_mods_root:
                workshop_mods_root = os.path.normpath(workshop_mods_root).lower()
            tool_mods_root = str(TOOL_MODS_DIR)
            if tool_mods_root:
                tool_mods_root = os.path.normpath(tool_mods_root).lower()
            
            shadow_paths_map = {}
            for pid, entries in temp_registry.items():
                # 【关键检查点】：每一条 Mod 解析前检查中断标志
                if self._stop_requested:
                    logger.info("Scan stopped during parsing stage.")
                    self._handle_interruption()
                    return # 直接结束任务

                active_entries = [mod for mod in entries if not mod.get('disabled')]
                disabled_paths = [mod['path'] for mod in entries if mod.get('disabled') and mod.get('path')]
                for mod in entries:
                    path_hash = mod.get('path_hash')
                    if path_hash:
                        shadow_paths_map[path_hash] = disabled_paths if not mod.get('disabled') else []
                
                # 情况 A: 只有一个实例 -> 直接入库
                if len(entries) == 1:
                    mod = entries[0]
                    if not mod.get('_skipped'): # 跳过的不需要重新 Upsert，除非想更新 timestamp
                        mods_to_upsert.append(mod)
                    
                    # 收集部署信息
                    self._classify_for_deploy(mod, local_mods_root, self_mods_root, workshop_mods_root, tool_mods_root,
                        local_mod_ids_for_deploy, self_mods_paths_for_deploy, workshop_paths_for_deploy, tool_mods_paths_for_deploy)
                    continue

                # 情况 B: 多个实例 -> 判定冲突类型
                # 若只有一个启用实例，其余均为禁用副本，则不视为冲突，只做元数据同步。
                if len(active_entries) <= 1:
                    for mod in entries:
                        if not mod.get('_skipped'):
                            mods_to_upsert.append(mod)
                        self._classify_for_deploy( mod, local_mods_root, self_mods_root, workshop_mods_root, tool_mods_root,
                            local_mod_ids_for_deploy, self_mods_paths_for_deploy, workshop_paths_for_deploy, tool_mods_paths_for_deploy
                        )
                    continue

                # 按父目录分组
                by_parent = defaultdict(list)
                for mod in active_entries:
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
                    # 发生硬冲突，同样入库
                    logger.warning(f"Hard conflict detected for {pid}")
                    # 强制将硬冲突也加入待更新列表，否则数据库里没数据
                    for mod in entries:
                        if not mod.get('_skipped'): mods_to_upsert.append(mod)
                        # 硬冲突通常不执行部署(Deploy)，所以跳过 _classify_for_deploy
                    continue # 结束当前这组的后续软冲突逻辑
                
                # --- 检查软冲突 (跨目录遮蔽/共存) ---
                # 走到这里说明 len(entries) > 1 且没有硬冲突
                final_coexistences.append({
                    'package_id': pid,
                    'items': active_entries,      # 禁用副本不参与冲突提示
                    'type': 'different_directory' # 标记类型：跨目录共存
                })

                # 【软冲突/共存】：不同目录下的重复 ID (Local vs Workshop)
                # 策略：全部入库！
                # 数据库会存储多条记录 (path不同，path_hash不同，主键不冲突)
                # 查询时由 DAO 根据 Profile 过滤，部署时由下方逻辑过滤
                for mod in entries:
                    # 优化：跳过未变动的 Mod，避免无意义的数据库重写
                    if not mod.get('_skipped'): mods_to_upsert.append(mod)
                    self._classify_for_deploy(mod, local_mods_root, self_mods_root, workshop_mods_root, tool_mods_root,
                        local_mod_ids_for_deploy, self_mods_paths_for_deploy, workshop_paths_for_deploy, tool_mods_paths_for_deploy)

            # --- 4. 批量入库 ---
            # 这是数据安全最关键的一步
            try:
                if mods_to_upsert: 
                    ModDAO.batch_upsert_mods(mods_to_upsert)
                if shadow_paths_map:
                    ModDAO.batch_update_shadow_paths(shadow_paths_map)
            except Exception as e:
                # txn.rollback() # 万一出错，回滚所有改动
                logger.error(f"批量入库失败: {e}", exc_info=True)
                raise e
            
            
            # --- 6. 自动部署链接 (Deployment) ---
            deploy_msg = "跳过链接部署"
            logger.debug(f"Skip deployment: use_workshop_mods={self.context.use_workshop_mods}, use_self_mods={self.context.use_self_mods}, current_profile_not_default={self.context.profile_id != 'default'}")
            final_links_to_create = []
            final_package_ids = local_mod_ids_for_deploy
            # 管理器模组优先部署
            if self.context.use_self_mods and local_mods_root and os.path.exists(local_mods_root):
                # 遮蔽策略：过滤掉 ID 已经在 Local 存在的 Self Mod
                for path, p_id in self_mods_paths_for_deploy:
                    if p_id not in final_package_ids:
                        final_links_to_create.append(path)
                        final_package_ids.add(p_id)
                    else:
                        # 被本地遮蔽，忽略
                        pass
            # 其次部署 创意工坊模组
            if self.context.use_workshop_mods and self.context.profile_id != 'default' \
                and local_mods_root and os.path.exists(local_mods_root):
                # 遮蔽策略：过滤掉 ID 已经在 Local 和 self 存在的 Workshop Mod
                for path, p_id in workshop_paths_for_deploy:
                    if p_id not in final_package_ids:
                        final_links_to_create.append(path)
                        final_package_ids.add(p_id)
                    else:
                        # 被本地遮蔽，忽略
                        pass
            # 最后部署 系统工具模组
            if settings.config.enable_tool_mods and local_mods_root and os.path.exists(local_mods_root):
                for path, p_id in tool_mods_paths_for_deploy:
                    if p_id not in final_package_ids:
                        final_links_to_create.append(path)
                        final_package_ids.add(p_id)
                    else:
                        # 被本地遮蔽，忽略
                        pass
            
            # 调用 FileManager 执行部署
            # 注意：这里需要传入 local_mods_path 的原始大小写路径（用于创建目录）
            # 增量模式只处理变化项；全量模式则删除全部旧链接后重建。
            if settings.config.link_deployment_mode_full:
                success = FileManager.sync_links_full(local_mods_root, final_links_to_create)
            else:
                success = FileManager.sync_links(local_mods_root, final_links_to_create)
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

            duration = time.time() - start_time
            logger.info(f"Scan finished in {duration:.2f}s. Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Removed: {stats['removed']}, Conflicts: {len(final_conflicts)}, Coexistences: {len(final_coexistences)}. {deploy_msg}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error("Scan task failed", exc_info=True)
            self._finish_scan({'status': 'error', 'message': str(e)})
        finally:
            self._is_scanning = False
            self._stop_requested = False # 清理状态
            # 释放线程绑定的数据库连接
            if not db.is_closed(): db.close()

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
        # 获取最新全量数据，或者让前端自己再调一次 get_all_mods
        # 建议直接通知前端 "scan-complete"，让前端决定是否刷新列表
        
        EventBus.emit('scan-complete', result)

    def _classify_for_deploy(self, mod_data, local_root, self_mods_root, workshop_root, tool_mods_root, local_ids_set, self_mods_paths_list, workshop_paths_list, tool_mods_paths_list):
        """
        辅助函数：将 Mod 分类以便后续部署。
        """
        mod_path = mod_data.get('path')
        if not mod_path or mod_data.get('disabled'): return
        mod_path_norm = os.path.normpath(mod_path).lower()
        pid = mod_data['package_id'].lower()
        # 判断 Local
        if local_root and mod_path_norm.startswith(local_root):
            local_ids_set.add(pid)
        # 判断 Self Mod
        elif self_mods_root and mod_path_norm.startswith(self_mods_root):
            self_mods_paths_list.append((mod_path, pid)) # 保留原大小写路径用于部署
        # 判断 Workshop
        elif workshop_root and mod_path_norm.startswith(workshop_root):
            workshop_paths_list.append((mod_path, pid))
        # 判断 Tool Mod
        elif tool_mods_root and mod_path_norm.startswith(tool_mods_root):
            tool_mods_paths_list.append((mod_path, pid))
        
    def _process_single_mod(self, mod_path, is_dlc_dir, existing_snapshots, dlc_parser: DLCParser | None, forced_update=False):
        """
        处理单个 Mod 的纯函数逻辑。
        返回: Mod数据字典 或 None(无效) 或 {'_skipped': True, 'package_id': ...}
        """
        try:
            about_state = ModAnalyzer.resolve_mod_about_state(mod_path, cleanup_dual_files=True)
        except OSError as e:
            logger.warning(f"Failed to clean duplicate About files for {mod_path}: {e}")
            about_state = ModAnalyzer.resolve_mod_about_state(mod_path, cleanup_dual_files=False)
        about_file = about_state.resolved_path
        is_disabled = about_state.is_disabled
        if not about_file and not is_dlc_dir:
            return None # 既不是 DLC 也没有 About.xml，无效
        
        # 检查 mtime
        try:
            stat = os.stat(about_file) if about_file else os.stat(mod_path)
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
                    return self._build_skipped_result(snapshot, path_hash, mod_path, mtime, current_size, is_disabled)
                # 走到这里说明大小变了，需要继续向下解析
            else:
                # 如果没开大小检测，且修改时间没变，直接视为跳过
                return self._build_skipped_result(snapshot, path_hash, mod_path, mtime, snapshot['size'], is_disabled)
        
        # 解析 XML (CPU 密集)
        # parser 内部如果处理异常会返回默认空结构，这里直接调
        mod_data = self.xml_parser.parse(mod_path, about_path=about_file)
        pkg_id = mod_data.get('package_id','').lower()
        
        # DLC 兜底 ID
        if is_dlc_dir and not pkg_id:
            folder = os.path.basename(mod_path)
            if folder.lower() == 'core': 
                mod_data['package_id_raw'] = 'Ludeon.RimWorld'
            else: 
                mod_data['package_id_raw'] = f'Ludeon.RimWorld.{folder.capitalize()}'
            mod_data['package_id'] = mod_data['package_id_raw'].lower()
            pkg_id = mod_data['package_id']

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
        L_PATH = norm(self.context.local_mods_path)
        W_PATH = norm(settings.config.workshop_mods_path)
        S_PATH = norm(settings.config.self_mods_path)
        T_PATH = norm(str(TOOL_MODS_DIR))
        # 补充 store
        m_path = norm(mod_path)
        if S_PATH and m_path.startswith(S_PATH) and (S_PATH != L_PATH):
            mod_data['store'] = 'self'
        elif T_PATH and m_path.startswith(T_PATH):
            mod_data['store'] = 'self'
        elif W_PATH and m_path.startswith(W_PATH):
            mod_data['store'] = 'workshop'
        else:
            mod_data['store'] = 'local'
        
        # 补充 supported_versions
        if mod_data.get('source','').lower() == 'core':
            mod_data['supported_versions'] = [self.context.game_version[:3]] if self.context.game_version else 'Unknown'  # Core 补充支持版本

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
            'disabled': is_disabled,
        })
        
        return mod_data
    
    def _build_skipped_result(self, snapshot: dict, path_hash, mod_path, mtime, current_size, is_disabled):
        return {
            '_skipped': True, 
            'path_hash': path_hash,
            'package_id': snapshot['package_id'],
            'workshop_id': snapshot.get('workshop_id', ''),
            'name': snapshot.get('name', ''),                         
            'version': snapshot.get('version', ''),
            'store': snapshot.get('store', 'local'),                 
            'supported_versions': snapshot.get('supported_versions', []), 
            'path': mod_path, 
            'file_create_time': snapshot.get('ctime', 0),
            'file_modify_time': mtime,
            'mtime': mtime,
            'file_size': current_size,
            'disabled': is_disabled
        }

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
    
    
