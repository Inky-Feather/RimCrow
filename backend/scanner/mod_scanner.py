# backend/scanner/mod_scanner.py
from collections import defaultdict
import os
import re
import time
import uuid
import concurrent.futures
from typing import Any
from urllib.parse import urlparse
from backend.managers.mgr_game_logs import GameLogManager
from backend.managers.mgr_profile import ProfileContext
from backend.paths.rimworld_layout import resolve_rimworld_layout
from backend.utils.constants import RIMWORLD_STEAM_APP_ID_STR
from backend.utils.tools import generate_path_hash, get_folder_size, normalize_path_for_storage, same_path
from backend.database.models import MOD_ASSET_STATE_DELETED, MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_PRESENT, db

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
        

from backend.database.dao import ModDAO, ModMaintenanceDAO
from backend.scanner.parser_xml import ModXMLParser
from backend.scanner.analyzer import ModAnalyzer
from backend.scanner.parser_dlc import DLCParser
from backend.managers.mgr_files import FileManager
from backend.utils.profile_runtime import resolve_profile_runtime_capabilities
from backend.managers.mgr_steam import SteamManager
from backend.settings import TOOL_MODS_DIR, settings
from backend.utils.constants import normalize_language_codes
from backend.utils.logger import logger # 引入日志
from backend.utils.event_bus import EventBus # 引入事件总线

GIT_REPO_SOURCE_HOSTS = {"github.com", "gitlab.com", "gitgud.io"}

def _is_git_repo_source_url(value: str) -> bool:
    try:
        host = urlparse(str(value or "")).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return False
    return host in GIT_REPO_SOURCE_HOSTS

class ModScanner:
    def __init__(self, context: ProfileContext, runtime_link_sync_handler=None):
        self.context = context
        self.runtime_link_sync_handler = runtime_link_sync_handler
        # DLCParser 不在 init 初始化，因为要看扫描路径里有没有 DLC 目录
        self.dlc_parser = None
        self.xml_parser = ModXMLParser()
        self.analyzer = ModAnalyzer()
        # 线程池 (扫描通常是 IO 密集型，但 XML 解析是 CPU 密集型，默认 worker 数即可)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._is_scanning = False
        self._stop_requested = False  # 中断请求标志
        self._current_task_id: str | None = None

    @property
    def is_scanning(self) -> bool: return self._is_scanning

    def stop_scan(self, task_id: str | None = None) -> bool:
        """外部调用：请求中断扫描"""
        if not self._is_scanning: return False
        if task_id and self._current_task_id and task_id != self._current_task_id:
            logger.warning("忽略过期扫描中断请求：requested=%s active=%s", task_id, self._current_task_id)
            return False
        self._stop_requested = True
        logger.warning("用户请求中断扫描：task_id=%s", self._current_task_id)
        return True

    def wait_until_idle(self, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
        """等待扫描任务彻底结束并释放线程内连接。"""
        deadline = time.time() + max(0.0, timeout)
        while time.time() < deadline:
            if not self._is_scanning: return True
            time.sleep(max(0.01, poll_interval))
        return not self._is_scanning

    def _scan_mod_detail(self, path_hash: str, mod_path: str, snapshot: dict | None = None, message: str = "") -> dict[str, Any]:
        return {
            "path_hash": path_hash,
            "package_id": (snapshot or {}).get("package_id", ""),
            "name": (snapshot or {}).get("name", ""),
            "path": mod_path,
            "message": message,
        }

    @staticmethod
    def _should_refresh_core_after_scan(stats: dict | None, forced_update: bool = False) -> bool:
        if forced_update:
            return True
        stats = stats or {}
        return any(
            int(stats.get(key) or 0) > 0
            for key in (
                'added', 'updated', 'removed',
                'external_enabled', 'strict_restored_disabled', 'strict_restore_failed',
                'about_conflict_cleaned', 'shadow_path_cleaned',
            )
        )

    def scan_paths_async( self, search_paths, forced_update=False, size_check_override: bool | None = None, size_check_paths: list[str] | None = None, emit_events: bool = True, residue_scan_enabled: bool | None = None ):
        """
        异步扫描入口。立即返回，任务在后台运行。
        """
        EventBus.resume()   # 恢复事件总线
        if self._is_scanning: return {'status': 'busy', 'message': '扫描已在进行中'}
        
        self._is_scanning = True
        self._stop_requested = False  # 启动前重置标志
        task_id = uuid.uuid4().hex
        self._current_task_id = task_id
        if emit_events:
            EventBus.emit_progress(
                task_id,
                "scan",
                status="pending",
                progress=0,
                message="准备扫描任务...",
                metrics={ "title": "模组扫描", "forced_update": forced_update, "size_check_override": size_check_override, "size_check_paths_count": len(size_check_paths or []) },
            )
        # 提交到线程池
        self.executor.submit( self._scan_paths_task, task_id, search_paths, forced_update, size_check_override, size_check_paths, emit_events, residue_scan_enabled )
        return {'status': 'started', 'task_id': task_id}

    def _scan_paths_task( self, task_id, search_paths, forced_update=False, size_check_override: bool | None = None, size_check_paths: list[str] | set[str] | None = None, emit_events: bool = True, residue_scan_enabled: bool | None = None ):
        """
        后台执行的扫描主逻辑
        """
        logger.info(f"扫描已开始，路径：{search_paths}")
        start_time = time.time()
        db.connect(reuse_if_open=True) # 确保线程有连接
        stats = {
            'added': 0, 'updated': 0, 'skipped': 0, 'removed': 0, 'duration': 0.0,
            'external_enabled': 0, 'strict_restored_disabled': 0, 'strict_restore_failed': 0,
            'about_conflict_cleaned': 0, 'shadow_path_cleaned': 0,
        }
        scan_details = {
            'external_enabled_mods': [],
            'strict_restored_disabled_mods': [],
            'strict_restore_failed_mods': [],
            'about_conflict_cleaned_mods': [],
        }
        if emit_events:
            EventBus.emit_progress(
                task_id,
                "scan",
                status="running",
                progress=1,
                message="正在准备扫描...",
                metrics={'stage': 'preparing', 'current': 0, 'total': 0, 'title': '模组扫描'},
            )
        with db.atomic() as txn:
            try:
                # --- 5. 清理失效数据 ---
                # 扫描缺失的 Mod (物理文件没了)
                workshop_status = SteamManager().workshop_merged_data()
                subscribed_workshop_ids = [wid for wid, data in workshop_status.items() if data.get("is_subscribed")]
                deletion_result = ModMaintenanceDAO.find_missing_mods(settings.config.delete_missing_mods_data, subscribed_workshop_ids)
                missing_count = len(deletion_result.get('missing_mods') or [])
                deleted_count = len(deletion_result.get('deleted_mods') or [])
                stats['removed'] = missing_count + deleted_count if settings.config.delete_missing_mods_data else deleted_count
                logger.info(
                    "库存失效检测完成: missing=%s deleted=%s restored=%s delete_data=%s",
                    missing_count,
                    deleted_count,
                    len(deletion_result.get('restored_mods') or []),
                    settings.config.delete_missing_mods_data,
                )
                # 清理失效的 Shadow Paths
                stats['shadow_path_cleaned'] = ModMaintenanceDAO.clean_invalid_shadow_paths()
            except Exception as e:
                txn.rollback() # 万一出错，回滚所有改动
                raise e
        try:
            # --- 0. 预检查与准备 ---
            # SteamCMD 下载目录与管理器自管目录当前共用同一份物理数据。
            # 扫描前先把 ACF 中“目录已不存在”的陈旧安装记录清掉，
            # 避免后续任何 SteamCMD 下载又被旧记录拖入 Missing game files 校验失败。
            SteamManager().reconcile_steamcmd_acf()
            valid_paths = [
                normalize_path_for_storage(p)
                for p in search_paths
                if p and os.path.exists(p)
            ]
            if not valid_paths:
                if emit_events:
                    EventBus.emit_progress(task_id, "scan", status="failed", progress=0, message="没有有效路径", metrics={"title": "模组扫描"})
                self._finish_scan({'error': '没有有效路径', 'task_id': task_id}, task_id, emit_events=emit_events)
                return
            size_check_path_set = {
                normalize_path_for_storage(path)
                for path in (size_check_paths or [])
                if path
            }
            if emit_events:
                EventBus.emit_progress(
                    task_id,
                    "scan",
                    status="running",
                    progress=3,
                    message="正在读取游戏基础信息...",
                    metrics={'stage': 'preparing', 'current': 0, 'total': 0, 'title': '模组扫描'},
                )
            # 扫描只需要 DLC 基础定义；全语言 tar 缓存按需或后台同步，避免首次扫描被解包阻塞。
            dlc_parser = DLCParser(self.context.game_dlc_path, sync_translations=False, current_language_code=settings.config.language)
            existing_snapshots = ModDAO.get_mod_snapshots()   # 从数据库获取已存在的 Mod 时间戳及大小
            # --- 1. 快速搜集所有待扫描文件夹 (用于计算进度总数) ---
            if emit_events:
                EventBus.emit_progress(
                    task_id,
                    "scan",
                    status="running",
                    progress=5,
                    message='正在索引文件...',
                    metrics={'stage': 'indexing', 'current': 0, 'total': 0, 'title': '模组扫描'},
                )
            mod_folders = [] # [(folder_path, is_dlc), ...]
            official_data_root = str(getattr(self.context, "game_dlc_path", "") or "").strip()
            install_layout = resolve_rimworld_layout(str(getattr(self.context, "game_install_path", "") or "").strip())
            resource_data_root = install_layout.resource_data_root
            for base_path in valid_paths:
                try:
                    is_data_dir = bool(official_data_root and same_path(base_path, official_data_root))
                    if resource_data_root and same_path(base_path, resource_data_root):
                        is_data_dir = False
                    if not is_data_dir:
                        about_state = ModAnalyzer.resolve_mod_about_state(base_path, cleanup_dual_files=False)
                        if about_state.resolved_path:
                            mod_folders.append((normalize_path_for_storage(base_path), False))
                            continue
                    with os.scandir(base_path) as it:
                        for entry in it:
                            if entry.is_dir():
                                # 遇到链接生成目录直接跳过，防止无限递归和重复
                                if entry.name.startswith(FileManager.LINK_PREFIX): continue
                                mod_folders.append((normalize_path_for_storage(entry.path), is_data_dir))
                except OSError as e:
                    logger.warning(f"无法访问路径 {base_path}: {e}")
            total_count = len(mod_folders)
            # 优化：根据总数动态决定发送频率
            report_interval = max(1, total_count // 50) 
            # --- 2. 扫描与解析阶段 ---
            # 使用 temp_registry 暂存所有扫描结果，而不是一边扫一边入库
            # 结构: { package_id: [mod_data_1, mod_data_2] }
            temp_registry = defaultdict(list)
            start_time = time.time()
            for idx, (mod_path, is_dlc) in enumerate(mod_folders):
                # 【关键检查点】：每一条 Mod 解析前检查中断标志
                if self._stop_requested:
                    logger.info("扫描在解析阶段停止。")
                    self._handle_interruption(task_id)
                    return # 直接结束任务，不进入写库阶段
                # 进度报告
                if (idx + 1) % report_interval == 0:
                    percent = min(98, 5 + int(((idx + 1) / total_count) * 93))
                    if emit_events:
                        EventBus.emit_progress(
                            task_id,
                            "scan",
                            status="running",
                            progress=percent,
                            message=f"分析中: {os.path.basename(mod_path)}",
                            metrics={
                                'stage': 'scanning',
                                'current': (idx + 1),
                                'total': total_count,
                                'title': '模组扫描',
                            },
                        )
                # 处理单个 Mod
                mod_data = self._process_single_mod( mod_path, is_dlc, existing_snapshots, dlc_parser, forced_update, size_check_override, size_check_path_set, stats, scan_details )
                if mod_data:
                    # 如果是增量跳过，需要补全 package_id 以便后续逻辑使用
                    # _process_single_mod 返回 {'_skipped': True, 'package_id': ...}
                    pid = mod_data['package_id'].lower()
                    # 记录到暂存区
                    temp_registry[pid].append(mod_data)
                    if mod_data.get('_skipped'):
                        stats['skipped'] += 1
                    elif mod_data.get('is_new'):
                        stats['added'] += 1
                    else:
                        stats['updated'] += 1
                        
            # 【关键检查点】：解析完成后检查中断标志
            if self._stop_requested:
                logger.info("扫描在解析阶段停止。")
                self._handle_interruption(task_id, emit_events=emit_events)
                return # 直接结束任务，不进入写库阶段
            # --- 3. 库存落库与运行态分析 ---
            if emit_events:
                EventBus.emit_progress(
                    task_id,
                    "scan",
                    status="running",
                    progress=99 if total_count else 90,
                    message='正在处理冲突与运行态收敛...',
                    metrics={'stage': 'analyzing', 'current': total_count, 'total': total_count, 'title': '模组扫描'},
                )
            
            mods_to_upsert = []
            mods_to_touch = []

            shadow_paths_map = {}
            for entries in temp_registry.values():
                # 【关键检查点】：每一条 Mod 解析前检查中断标志
                if self._stop_requested:
                    logger.info("扫描在解析阶段停止。")
                    self._handle_interruption(task_id, emit_events=emit_events)
                    return # 直接结束任务

                disabled_paths = [mod['path'] for mod in entries if mod.get('disabled') and mod.get('path')]
                for mod in entries:
                    path_hash = mod.get('path_hash')
                    if path_hash:
                        shadow_paths_map[path_hash] = disabled_paths if not mod.get('disabled') else []
                    # 扫描阶段只负责同步库存事实，不在这里做 Profile 遮蔽。
                    if mod.get('_skipped'):
                        # 跳过解析不代表这次没看见；轻量回写可让 missing/seen 状态保持可信。
                        mods_to_touch.append({
                            'path_hash': path_hash,
                            'path': mod.get('path'),
                            'file_modify_time': mod.get('file_modify_time', 0),
                            'file_size': mod.get('file_size', 0),
                            'disabled': mod.get('disabled', False),
                            'state': MOD_ASSET_STATE_PRESENT,
                            'last_seen_at': mod.get('last_seen_at', 0),
                            'last_scanned_at': mod.get('last_scanned_at', 0),
                        })
                    else:
                        mods_to_upsert.append(mod)

            # --- 4. 批量入库 ---
            # 这是数据安全最关键的一步
            try:
                if mods_to_upsert: 
                    ModDAO.batch_upsert_mods(mods_to_upsert)
                if mods_to_touch:
                    ModDAO.batch_update_mods(mods_to_touch)
                if shadow_paths_map:
                    ModDAO.batch_update_shadow_paths(shadow_paths_map)
                # 扫描完成后再基于本轮 self 域磁盘结果补齐 SteamCMD ACF，
                # 让 ACF 记录集合与真实目录集合保持同步。
                SteamManager().reconcile_steamcmd_acf(scan_mods=mods_to_upsert)
            except Exception as e:
                # txn.rollback() # 万一出错，回滚所有改动
                logger.error(f"批量入库失败: {e}", exc_info=True)
                raise e
            # 入库完成后，再按当前 Profile 的启用域统一分析冲突与运行态收敛依据。
            runtime_caps = resolve_profile_runtime_capabilities(self.context)
            runtime_analysis = ModDAO.get_profile_conflict_analysis(
                self.context,
                include_workshop_in_detection=bool(runtime_caps.get('workshop_detection_enabled')),
                include_workshop_in_deploy=bool(runtime_caps.get('workshop_deploy_enabled')),
            )
            final_conflicts = runtime_analysis['hard_conflicts']
            final_coexistences = runtime_analysis['coexistences']
            # --- 6. 扫描后通知运行态收敛 ---
            runtime_sync_msg = "Runtime link sync not configured"
            if callable(self.runtime_link_sync_handler):
                runtime_sync_msg = self.runtime_link_sync_handler(self.context.profile_id)

            # --- 7. 完成 ---
            stats['duration'] = time.time() - start_time
            should_check_mod_residue = bool(getattr(settings.config, "enable_mod_residue_scan", True)) if residue_scan_enabled is None else bool(residue_scan_enabled)
            core_refresh_required = self._should_refresh_core_after_scan(stats, forced_update)
            
            if emit_events:
                EventBus.emit_progress(
                    task_id,
                    "scan",
                    status="success",
                    progress=100,
                    message='扫描完成',
                    metrics={
                        'stage': 'finished',
                        'current': total_count,
                        'total': total_count,
                        'stats': stats,
                        'conflict_count': len(final_conflicts),
                        'coexistence_count': len(final_coexistences),
                        'should_check_mod_residue': should_check_mod_residue,
                        'core_refresh_required': core_refresh_required,
                        'runtime_sync_message': runtime_sync_msg,
                        'title': '模组扫描',
                    },
                )
            
            result = {
                'status': 'success',
                'task_id': task_id,
                'total': stats['added'] + stats['updated'] + stats['skipped'],
                'stats': stats,
                'conflicts': final_conflicts,
                'coexistences': final_coexistences,
                'runtime_sync_message': runtime_sync_msg,
                'strict_disable_restore_failures': scan_details['strict_restore_failed_mods'],
                'should_check_mod_residue': should_check_mod_residue,
                'core_refresh_required': core_refresh_required,
            }
            self._finish_scan(result, task_id, emit_events=emit_events)

            duration = time.time() - start_time
            logger.info(
                "扫描完成，用时 %.2fs。新增：%s，更新：%s，跳过：%s，移除：%s，"
                "外部启用：%s，严格恢复：%s，严格恢复失败：%s，About 冲突清理：%s，"
                "影子路径清理：%s，冲突：%s，共存：%s，核心刷新：%s，残留检测：%s。%s",
                duration, stats['added'], stats['updated'], stats['skipped'], stats['removed'],
                stats['external_enabled'], stats['strict_restored_disabled'], stats['strict_restore_failed'],
                stats['about_conflict_cleaned'], stats['shadow_path_cleaned'], len(final_conflicts),
                len(final_coexistences), "需要" if core_refresh_required else "跳过",
                "待检测" if should_check_mod_residue else "跳过",
                runtime_sync_msg,
            )
            disabled_debug = {
                key: [
                    item.get("package_id") or item.get("path") or item.get("path_hash")
                    for item in items
                ]
                for key, items in scan_details.items()
                if items
            }
            conflict_debug = [
                {
                    "package_id": item.get("package_id"),
                    "paths": [entry.get("path") for entry in item.get("items", []) if entry.get("path")],
                }
                for item in final_conflicts
            ]
            coexistence_debug = [
                {
                    "package_id": item.get("package_id"),
                    "paths": [entry.get("path") for entry in item.get("items", []) if entry.get("path")],
                }
                for item in final_coexistences
            ]
            logger.debug("扫描禁用状态详情: %s", disabled_debug)
            logger.debug("扫描冲突详情: conflicts=%s coexistences=%s should_check_mod_residue=%s", conflict_debug, coexistence_debug, should_check_mod_residue)
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error("扫描任务失败", exc_info=True)
            if emit_events:
                EventBus.emit_progress(task_id, "scan", status="failed", progress=0, message=f"扫描失败: {e}", metrics={'title': '模组扫描'})
            self._finish_scan({'status': 'error', 'message': str(e), 'task_id': task_id}, task_id, emit_events=emit_events)
        finally:
            self._is_scanning = False
            self._stop_requested = False # 清理状态
            self._current_task_id = None
            # 释放线程绑定的数据库连接
            if not db.is_closed(): db.close()

    def _handle_interruption(self, task_id: str, emit_events: bool = True):
        """处理中断后的清理和通知"""
        self._is_scanning = False
        if emit_events:
            EventBus.emit_progress(task_id, "scan", status="cancelled", progress=0, message="扫描已由用户中止", metrics={'title': '模组扫描'})
        self._finish_scan({
            'status': 'cancelled',
            'message': '扫描已由用户中止，未对数据库进行任何修改。',
        }, task_id, emit_events=emit_events)
        logger.info("扫描已安全取消。")

    def _finish_scan(self, result, task_id: str | None = None, emit_events: bool = True):
        """扫描结束，通知前端并发送最终统计"""
        # 获取最新全量数据，或者让前端自己再调一次 get_all_mods
        # 建议直接通知前端 "scan-complete"，让前端决定是否刷新列表
        payload: dict[str, Any] = dict(result or {}) if isinstance(result, dict) else {'message': str(result or '')}
        normalized_status = str(payload.get('status') or '').strip().lower()
        if normalized_status == 'error':
            normalized_status = 'failed'
        if normalized_status not in {'success', 'failed', 'cancelled'}:
            normalized_status = 'success'
        if task_id:
            payload.setdefault('task_id', task_id)
        payload['status'] = normalized_status
        payload.setdefault('type', 'scan')
        payload.setdefault('id', payload.get('task_id', ''))
        payload.setdefault('progress', 100 if normalized_status == 'success' else 0)
        payload.setdefault('message', '扫描完成' if normalized_status == 'success' else '')
        payload.setdefault('metrics', {})
        if emit_events:
            EventBus.emit('scan-complete', payload)

    def _process_single_mod( self, mod_path, is_dlc_dir, existing_snapshots, dlc_parser: DLCParser | None, forced_update=False, size_check_override: bool | None = None, size_check_paths: set[str] | None = None, stats: dict | None = None, scan_details: dict | None = None ):
        """
        处理单个 Mod 的纯函数逻辑。
        返回: Mod数据字典 或 None(无效) 或 {'_skipped': True, 'package_id': ...}
        """
        mod_path = normalize_path_for_storage(mod_path)
        try:
            about_state = ModAnalyzer.resolve_mod_about_state(mod_path, cleanup_dual_files=True)
        except OSError as e:
            logger.warning(f"清理重复 About 文件失败：{mod_path}，错误：{e}")
            about_state = ModAnalyzer.resolve_mod_about_state(mod_path, cleanup_dual_files=False)
        about_file = about_state.resolved_path
        is_disabled = about_state.is_disabled
        if not about_file and not is_dlc_dir: return None # 既不是 DLC 也没有 About.xml，无效
        
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
        detail = self._scan_mod_detail(path_hash, mod_path, snapshot)
        if getattr(about_state, 'cleaned_conflict', False) and stats is not None and scan_details is not None:
            stats['about_conflict_cleaned'] = int(stats.get('about_conflict_cleaned') or 0) + 1
            scan_details.setdefault('about_conflict_cleaned_mods', []).append(detail)

        if snapshot and snapshot.get('disabled') is True and not is_disabled:
            if bool(getattr(settings.config, 'strict_disabled_mode', False)):
                success, message = ModMaintenanceDAO.set_mod_disabled_status(mod_path, True)
                if success:
                    if stats is not None:
                        stats['strict_restored_disabled'] = int(stats.get('strict_restored_disabled') or 0) + 1
                    if scan_details is not None:
                        scan_details.setdefault('strict_restored_disabled_mods', []).append({**detail, "message": message})
                    about_state = ModAnalyzer.resolve_mod_about_state(mod_path, cleanup_dual_files=False)
                    about_file = about_state.resolved_path or about_file
                    is_disabled = True
                else:
                    if stats is not None:
                        stats['strict_restore_failed'] = int(stats.get('strict_restore_failed') or 0) + 1
                    if scan_details is not None:
                        scan_details.setdefault('strict_restore_failed_mods', []).append({**detail, "message": message})
                    is_disabled = True
            else:
                if stats is not None:
                    stats['external_enabled'] = int(stats.get('external_enabled') or 0) + 1
                if scan_details is not None:
                    scan_details.setdefault('external_enabled_mods', []).append(detail)
        # 在开启开关或者强制更新的情况下，才需要计算大小
        # 直启前检查同步会显式绕过“大文件夹体积统计”，避免为了启动准备把耗时放大。
        if size_check_override is None:
            need_size_check = settings.config.enable_file_size_scan or forced_update
        else:
            need_size_check = bool(size_check_override)
        if not need_size_check and size_check_paths and mod_path in size_check_paths:
            need_size_check = True

        disabled_change = not(snapshot and snapshot['disabled'] is is_disabled)
        snapshot_missing = bool(
            snapshot and (
                str(snapshot.get("state") or "").strip().lower() in {MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_DELETED}
                or not str(snapshot.get("path") or "").strip()
            )
        )
        
        # 增量检测逻辑 (Time AND Size)
        # 如果快照存在且修改时间一致
        if disabled_change: pass
        
        elif snapshot and not snapshot_missing and abs(snapshot['mtime'] - mtime) < 1.0 and not forced_update :
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
            mod_data['supported_languages'] = normalize_language_codes(dlc_parser.translations.keys())
            
        # 路径与来源分析
        workshop_id = self._resolve_workshop_id(mod_path)
        mod_data['workshop_id'] = workshop_id
            
        # Source 补全逻辑
        if workshop_id:
            mod_data['url'] = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
            mod_data['source'] = 'workshop'
        elif is_dlc_dir:
            mod_data['source'] = 'dlc' if pkg_id != 'ludeon.rimworld' else 'core'
        elif _is_git_repo_source_url(mod_data.get('url', '')):
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
        if S_PATH and m_path.startswith(S_PATH) and (S_PATH != L_PATH) and (S_PATH != W_PATH):
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
            
        scan_time = int(time.time() * 1000)
        mod_data.update({
            'path_hash': path_hash,
            'supported_languages': normalize_language_codes(
                analysis_info['supported_languages'] if not is_dlc_dir else mod_data.get('supported_languages', [])
            ),
            'file_stats': analysis_info['file_stats'],
            'mod_type': analysis_info['mod_type'],
            'path': mod_path,
            'file_create_time': ctime,
            'file_modify_time': mtime,
            'file_size': final_size,
            'source': mod_data.get('source', 'local'), # 来源
            'disabled': is_disabled,
            'state': MOD_ASSET_STATE_PRESENT,
            'last_seen_at': scan_time,
            'last_scanned_at': scan_time,
        })
        
        return mod_data
    
    def _build_skipped_result(self, snapshot: dict, path_hash, mod_path, mtime, current_size, is_disabled):
        scan_time = int(time.time() * 1000)
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
            'disabled': is_disabled,
            'state': MOD_ASSET_STATE_PRESENT,
            'last_seen_at': scan_time,
            'last_scanned_at': scan_time,
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
        
        # 2. 尝试使用文件夹名 (如果是纯数字且路径位于 RimWorld Workshop 内容目录)
        # 建议：使用 path 字符串查找，不依赖正则，避免分隔符坑
        norm_path = os.path.normpath(mod_path).lower() # 统一转为小写、标准分隔符
        # Windows normpath 会把关键段转换成系统分隔符。
        keywords = os.path.join('workshop', 'content', RIMWORLD_STEAM_APP_ID_STR).lower()
        if keywords in norm_path:
            folder_name = os.path.basename(mod_path)
            # 只要是纯数字就认
            if folder_name.isdigit(): return folder_name
            
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
        if os.path.isfile(preview_path): preview_path = normalize_path_for_storage(preview_path)
        else: preview_path = ""

        # --- ModIcon.png ---
        icon_path = os.path.join(mod_path, 'About', 'ModIcon.png')
        if os.path.isfile(icon_path): icon_path = normalize_path_for_storage(icon_path)
        else: icon_path = ""
        
        rel_xml_icon_path = os.path.join(mod_path, 'Textures', xml_icon_path+'.png')
        if os.path.isfile(rel_xml_icon_path): rel_xml_icon_path = normalize_path_for_storage(rel_xml_icon_path)
        else: rel_xml_icon_path = ""
        
        # 使用 XML 中定义的路径 (RimWorld 1.5+)
        if not icon_path and rel_xml_icon_path:
            icon_path = rel_xml_icon_path

        return preview_path, icon_path
    
    
