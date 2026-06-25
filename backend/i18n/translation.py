from typing import Any, Dict
import logging

logger = logging.getLogger("RimModManager")

# Message catalog for localization
MESSAGES: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "lang_code": "zh-CN",
        # static_page - idle_home
        "static_page.idle_home.title": "RimModManager - 挂起中",
        "static_page.idle_home.running": "RimWorld 正在运行",
        "static_page.idle_home.desc": "管理器已释放内存并进入静默休眠状态。",
        "static_page.idle_home.view_logs": "查看游戏日志",
        "static_page.idle_home.exit_silent": "退出静默",
        "static_page.idle_home.connecting": "正在建立连接...",
        "static_page.idle_home.try_again": "请稍后重试",
        
        # static_page - idle_logs
        "static_page.idle_logs.title": "RimModManager - 游戏日志",
        "static_page.idle_logs.header": "游戏日志",
        "static_page.idle_logs.search_placeholder": "搜索日志内容",
        "static_page.idle_logs.refresh_seconds": "刷新秒数",
        "static_page.idle_logs.auto_refresh": "自动刷新",
        "static_page.idle_logs.copy_selected": "复制选中",
        "static_page.idle_logs.back": "返回",
        "static_page.idle_logs.exit_silent": "退出静默",
        "static_page.idle_logs.ready": "准备就绪",
        "static_page.idle_logs.api_not_ready": "接口尚未准备好",
        "static_page.idle_logs.paused": "已暂停",
        "static_page.idle_logs.no_logs": "当前没有可显示的日志。",
        "static_page.idle_logs.collapse_details": "收起详情",
        "static_page.idle_logs.expand_details": "展开详情",
        "static_page.idle_logs.copy": "复制",
        "static_page.idle_logs.copied_success": "已复制当前日志",
        "static_page.idle_logs.copy_failed": "复制失败",
        "static_page.idle_logs.get_files_failed": "获取日志文件失败",
        "static_page.idle_logs.no_files_detected": "当前未检测到游戏日志文件。",
        "static_page.idle_logs.reading_logs": "正在读取日志...",
        "static_page.idle_logs.read_logs_failed": "读取日志失败",
        "static_page.idle_logs.refreshed": "已刷新 {file}",
        "static_page.idle_logs.back_failed": "返回失败",
        "static_page.idle_logs.wake_failed": "唤醒失败",
        "static_page.idle_logs.refresh_interval_adjusted": "刷新间隔已调整为 {seconds} 秒",
        "static_page.idle_logs.auto_refresh_resumed": "已恢复自动刷新",
        "static_page.idle_logs.auto_refresh_paused": "已暂停自动刷新",
        "static_page.idle_logs.select_log_first": "请先选择日志",
        "static_page.idle_logs.copied_n_logs": "已复制 {count} 条日志",
        "static_page.idle_logs.load_failed": "加载失败",
        
        # static_page - workshop_error
        "static_page.workshop_error.load_failed": "加载失败",
        "static_page.workshop_error.tip": "如果原网页能正常访问，可以直接打开原地址继续浏览。",
        "static_page.workshop_error.no_url": "未提供目标地址",
        "static_page.workshop_error.open_original": "打开原网页",

        # static_page - sub_browser
        "static_page.sub_browser.no_url": "未提供目标 URL",
        "static_page.sub_browser.open_original": "打开原页面",
        "static_page.sub_browser.open_in_steam": "在Steam打开",
        "static_page.sub_browser.subscribe": "订阅",
        "static_page.sub_browser.unsubscribe": "取消订阅",
        "static_page.sub_browser.download": "SteamCMD 下载",
        "static_page.sub_browser.footnote": "如果目标站点禁止 iframe 预览，下面区域会空白，但操作按钮仍可正常工作。",
        "static_page.sub_browser.op_completed": "操作已完成",
        "static_page.sub_browser.op_failed": "操作失败",
        "static_page.sub_browser.no_page": "未提供可打开的页面",
        "static_page.sub_browser.no_workshop_id": "未识别到 Workshop ID，仅保留打开页面。",
        "static_page.sub_browser.no_content": "未识别到可操作内容。",
        "static_page.sub_browser.opening_in_steam": "正在尝试在 Steam 中打开当前页面...",
        "static_page.sub_browser.subscribing": "正在发送订阅请求...",
        "static_page.sub_browser.unsubscribing": "正在发送取消订阅请求...",
        "static_page.sub_browser.downloading": "正在启动 SteamCMD 下载...",
        
        # share_code
        "share_code.invalid_format": "分享码里的模组条目格式无效",
        "share_code.no_entries": "当前没有可生成分享码的模组条目",
        "share_code.invalid_prefix": "分享码前缀无效，当前只支持 RMM1 分享码",
        "share_code.invalid_structure": "分享码结构无效",
        "share_code.verification_failed": "分享码校验失败，可能已损坏或复制不完整",
        "share_code.invalid_payload": "分享码载荷无效",
        "share_code.unsupported_version": "不支持的分享码版本: {version}",
        "share_code.invalid_list": "分享码模组列表无效",
        "share_code.no_valid_entries": "分享码中没有可用的模组条目",
        
        # text_search
        "search.query_empty": "搜索词不能为空",
        "search.unsupported_scope": "不支持的搜索范围: {scope}",
        "search.ripgrep_not_found": "未找到 ripgrep，可在外部工具检查中下载安装。",
        "search.ripgrep_found": "已找到 ripgrep{version}",
        "search.ripgrep_win_only": "当前自动下载 ripgrep 仅支持 Windows 平台。",
        "search.download_start": "开始下载 ripgrep 工具包",
        "search.install_start": "ripgrep 工具包获取成功，正在解压...",
        "search.task_queued": "搜索任务已加入后台队列",
        "search.task_queued_replacing": "搜索任务已加入后台队列，正在替换 {count} 个旧任务",
        "search.not_activated": "当前环境未激活，无法执行搜索",
        "search.title": "文件内容搜索",
        "search.task_replaced": "搜索任务已被新的搜索请求替换",
        "search.ripgrep_download_success": "ripgrep 下载完成: {path}",
        "search.ripgrep_download_failed": "ripgrep 下载失败",
        "search.unit_label.effective_roots": "有效搜索根",
        "search.unit_label.mod_directories": "模组目录",
        "search.progress.scanning": "已锁定 {count} 个{unit}，正在使用 {backend} 扫描",
        "search.progress.preparing": "正在整理{stage} {current}/{total}: {name}",
        "search.prepare.effective_roots": "正在准备有效搜索根与缓存签名",
        "search.prepare.mod_directories": "正在准备搜索模组目录",
        "search.progress.cancelled": "搜索任务已取消",
        "search.progress.completed": "搜索完成，共命中 {matched_count} 条结果",
        "search.progress.cancelled_stage": "搜索任务已在{stage}阶段取消",
        "search.progress.failed": "搜索失败: {error}",
        "search.progress.scanned": "已扫描 {processed}/{total} 个{unit}",
        
        # import_check
        "import_check.unknown_package": "<未知包名>",
        "import_check.unknown_mod": "未知模组",
        "import_check.status.exact_match": "已和当前环境中的安装项精确匹配。",
        "import_check.status.has_replacement": "该工坊项目已有替代版本",
        "import_check.status.package_match": "当前环境存在同包名模组，但导入项没有有效 Workshop ID，无法继续区分具体版本。",
        "import_check.status.replacement": "该导入项对应了已安装模组的替代版本。",
        "import_check.status.replacement_installed": "当前环境已经安装了替代版本。",
        "import_check.status.other_version": "当前环境存在同包名模组，但对应的是另一个 Workshop 版本。",
        "import_check.status.missing": "当前环境未发现该导入项对应的可用安装项。",
        "import_check.status.unknown": "无法从导入项、本地缓存或外置数据库补全有效的 Workshop 信息。",
        "import_check.detail.imported_wid": "导入项 Workshop ID：",
        "import_check.detail.imported_url": "导入项来源 URL：",
        "import_check.detail.target_wid": "补全/替代后的目标 Workshop ID：",
        "import_check.detail.info_source": "信息来源：",
        "import_check.detail.original_candidate": "原版候选：",
        "import_check.detail.alternative_candidate": "替代候选：",
        "import_check.detail.fallback_note": "（原版来源不可用，已回退到替代项）",
        "import_check.detail.note": "备注：",
        "import_check.report.wid_mismatch": "已通过 Workshop ID 对应了已安装项，但包名与导入记录不一致",
        "import_check.report.alt_installed": "当前环境安装的是替代版本",
        "import_check.report.diff_version_installed": "当前环境存在同包名但不同工坊版本",
        "import_check.report.wid_match_installed": "已通过补全后的 Workshop ID 对应到了安装项",
        "import_check.report.wid_not_found": "无法查找到对应 Workshop ID，无法进行订阅或下载",
        "import_check.report.core_skip": "官方核心包不参与缺失下载判定",
        "import_check.report.unknown_item": "未知导入项",
        "import_check.report.wid_only_missing": "仅提供了 Workshop ID，当前环境未发现对应安装项",
        
        # scanner
        "scanner.title": "模组扫描",
        "scanner.scan_in_progress": "扫描已在进行中",
        "scanner.preparing_scan_task": "准备扫描任务...",
        "scanner.no_valid_path": "没有有效路径",
        "scanner.indexing_files": "正在索引文件...",
        "scanner.cannot_access_path": "无法访问路径 {path}: {error}",
        "scanner.analyzing_mod": "分析中: {name}",
        "scanner.processing_conflicts": "正在处理冲突与运行态收敛...",
        "scanner.batch_insert_failed": "批量入库失败: {error}",
        "scanner.scan_completed": "扫描完成",
        "scanner.scan_failed": "扫描失败: {error}",
        "scanner.scan_cancelled_by_user": "扫描已由用户中止",
        "scanner.scan_cancelled_by_user_desc": "扫描已由用户中止，未对数据库进行任何修改。",
        
        # workshop/bridge
        "workshop.error.missing_url": "未提供目标工坊页面地址",
        "workshop.error.steam_only": "当前仅代理 Steam 创意工坊相关页面",
        "workshop.error.load_failed_reason": "加载页面失败: {exc}",
        "workshop.id.unrecognized": "未识别",
        "workshop.bridge.not_ready": "页面桥接尚未就绪，请稍后重试。",
        "workshop.bridge.no_workshop_id": "当前页面未识别到 Workshop ID，可继续浏览其它工坊页面。",
        "workshop.bridge.navigate_failed": "页面跳转失败",
        "workshop.bridge.get_forms_only": "当前仅接管 GET 导航表单，已保留原页面行为。",
    },
    "en": {
        "lang_code": "en",
        # static_page - idle_home
        "static_page.idle_home.title": "RimModManager - Suspended",
        "static_page.idle_home.running": "RimWorld is running",
        "static_page.idle_home.desc": "The manager has released memory and entered silent sleep mode.",
        "static_page.idle_home.view_logs": "View Game Logs",
        "static_page.idle_home.exit_silent": "Exit Silent Mode",
        "static_page.idle_home.connecting": "Connecting...",
        "static_page.idle_home.try_again": "Please try again later",
        
        # static_page - idle_logs
        "static_page.idle_logs.title": "RimModManager - Game Logs",
        "static_page.idle_logs.header": "Game Logs",
        "static_page.idle_logs.search_placeholder": "Search log content",
        "static_page.idle_logs.refresh_seconds": "Refresh Interval",
        "static_page.idle_logs.auto_refresh": "Auto Refresh",
        "static_page.idle_logs.copy_selected": "Copy Selected",
        "static_page.idle_logs.back": "Back",
        "static_page.idle_logs.exit_silent": "Exit Silent Mode",
        "static_page.idle_logs.ready": "Ready",
        "static_page.idle_logs.api_not_ready": "API is not ready yet",
        "static_page.idle_logs.paused": "Paused",
        "static_page.idle_logs.no_logs": "No logs available to display.",
        "static_page.idle_logs.collapse_details": "Collapse Details",
        "static_page.idle_logs.expand_details": "Expand Details",
        "static_page.idle_logs.copy": "Copy",
        "static_page.idle_logs.copied_success": "Logs copied successfully",
        "static_page.idle_logs.copy_failed": "Copy failed",
        "static_page.idle_logs.get_files_failed": "Failed to get log files",
        "static_page.idle_logs.no_files_detected": "No game log files detected.",
        "static_page.idle_logs.reading_logs": "Reading logs...",
        "static_page.idle_logs.read_logs_failed": "Failed to read logs",
        "static_page.idle_logs.refreshed": "Refreshed {file}",
        "static_page.idle_logs.back_failed": "Failed to go back",
        "static_page.idle_logs.wake_failed": "Failed to wake up",
        "static_page.idle_logs.refresh_interval_adjusted": "Refresh interval set to {seconds} seconds",
        "static_page.idle_logs.auto_refresh_resumed": "Auto refresh resumed",
        "static_page.idle_logs.auto_refresh_paused": "Auto refresh paused",
        "static_page.idle_logs.select_log_first": "Please select a log first",
        "static_page.idle_logs.copied_n_logs": "Copied {count} log entries",
        "static_page.idle_logs.load_failed": "Failed to load",
        
        # static_page - workshop_error
        "static_page.workshop_error.load_failed": "Failed to load",
        "static_page.workshop_error.tip": "If the webpage can be accessed normally, you can open the original URL to continue browsing.",
        "static_page.workshop_error.no_url": "No target URL provided",
        "static_page.workshop_error.open_original": "Open Original Page",

        # static_page - sub_browser
        "static_page.sub_browser.no_url": "No target URL provided",
        "static_page.sub_browser.open_original": "Open Original Page",
        "static_page.sub_browser.open_in_steam": "Open in Steam",
        "static_page.sub_browser.subscribe": "Subscribe",
        "static_page.sub_browser.unsubscribe": "Unsubscribe",
        "static_page.sub_browser.download": "SteamCMD Download",
        "static_page.sub_browser.footnote": "If the target site blocks iframe previews, this area will be empty, but action buttons will work.",
        "static_page.sub_browser.op_completed": "Operation completed",
        "static_page.sub_browser.op_failed": "Operation failed",
        "static_page.sub_browser.no_page": "No openable page provided",
        "static_page.sub_browser.no_workshop_id": "No Workshop ID recognized. Only the page can be opened.",
        "static_page.sub_browser.no_content": "No actionable content recognized.",
        "static_page.sub_browser.opening_in_steam": "Attempting to open current page in Steam...",
        "static_page.sub_browser.subscribing": "Sending subscription request...",
        "static_page.sub_browser.unsubscribing": "Sending unsubscribe request...",
        "static_page.sub_browser.downloading": "Starting SteamCMD download...",
        
        # share_code
        "share_code.invalid_format": "Invalid mod entry format in share code",
        "share_code.no_entries": "No mod entries available to generate share code",
        "share_code.invalid_prefix": "Invalid share code prefix, only RMM1 share codes are supported",
        "share_code.invalid_structure": "Invalid share code structure",
        "share_code.verification_failed": "Share code verification failed, it may be corrupted or incomplete",
        "share_code.invalid_payload": "Invalid share code payload",
        "share_code.unsupported_version": "Unsupported share code version: {version}",
        "share_code.invalid_list": "Invalid mod list in share code",
        "share_code.no_valid_entries": "No valid mod entries found in share code",
        
        # text_search
        "search.query_empty": "Search query cannot be empty",
        "search.unsupported_scope": "Unsupported search scope: {scope}",
        "search.ripgrep_not_found": "ripgrep not found. It can be downloaded and installed in External Tools check.",
        "search.ripgrep_found": "ripgrep found{version}",
        "search.ripgrep_win_only": "Automatic downloading of ripgrep is currently supported on Windows only.",
        "search.download_start": "Starting download of ripgrep package",
        "search.install_start": "ripgrep package downloaded successfully, extracting...",
        "search.task_queued": "Search task added to background queue",
        "search.task_queued_replacing": "Search task added to background queue, replacing {count} old tasks",
        "search.not_activated": "Current environment is not activated, cannot perform search",
        "search.title": "File Content Search",
        "search.task_replaced": "Search task has been replaced by a new search request",
        "search.ripgrep_download_success": "ripgrep download completed: {path}",
        "search.ripgrep_download_failed": "ripgrep download failed",
        "search.unit_label.effective_roots": "effective search root",
        "search.unit_label.mod_directories": "mod directory",
        "search.progress.scanning": "Locked {count} {unit}(s), scanning with {backend}",
        "search.progress.preparing": "Preparing {stage} {current}/{total}: {name}",
        "search.prepare.effective_roots": "Preparing effective search roots and cache signatures...",
        "search.prepare.mod_directories": "Preparing to search mod directories...",
        "search.progress.cancelled": "Search task has been cancelled",
        "search.progress.completed": "Search completed with {matched_count} result(s)",
        "search.progress.cancelled_stage": "Search task cancelled at {stage} stage",
        "search.progress.failed": "Search failed: {error}",
        "search.progress.scanned": "Scanned {processed}/{total} {unit}(s)",
        
        # import_check
        "import_check.unknown_package": "<Unknown Package ID>",
        "import_check.unknown_mod": "Unknown Mod",
        "import_check.status.exact_match": "Exactly matched with the current environment installation.",
        "import_check.status.has_replacement": "This workshop item has an alternative version.",
        "import_check.status.package_match": "A mod with the same package ID exists, but the import entry has no valid Workshop ID, cannot distinguish the version.",
        "import_check.status.replacement": "This import entry corresponds to an alternative version of the installed mod.",
        "import_check.status.replacement_installed": "An alternative version is already installed in the current environment.",
        "import_check.status.other_version": "A mod with the same package ID exists, but it corresponds to a different Workshop version.",
        "import_check.status.missing": "No available installation found for this import entry in the current environment.",
        "import_check.status.unknown": "Cannot retrieve valid Workshop info from import entry, local cache, or external database.",
        "import_check.detail.imported_wid": "Imported Workshop ID: ",
        "import_check.detail.imported_url": "Imported Source URL: ",
        "import_check.detail.target_wid": "Target Workshop ID after completion/alternative: ",
        "import_check.detail.info_source": "Source of Information: ",
        "import_check.detail.original_candidate": "Original Candidate: ",
        "import_check.detail.alternative_candidate": "Alternative Candidate: ",
        "import_check.detail.fallback_note": "(Original source unavailable, fell back to alternative)",
        "import_check.detail.note": "Note: ",
        "import_check.report.wid_mismatch": "Matched installed item via Workshop ID, but package ID does not match import record",
        "import_check.report.alt_installed": "An alternative version is installed in the current environment",
        "import_check.report.diff_version_installed": "A different workshop version is installed with the same package ID",
        "import_check.report.wid_match_installed": "Matched installation using completed Workshop ID",
        "import_check.report.wid_not_found": "Could not find Workshop ID, cannot subscribe or download",
        "import_check.report.core_skip": "Official core package is excluded from missing download check",
        "import_check.report.unknown_item": "Unknown import item",
        "import_check.report.wid_only_missing": "Only Workshop ID was provided, not found in current environment",
        
        # scanner
        "scanner.title": "Mod Scan",
        "scanner.scan_in_progress": "Scan is already in progress",
        "scanner.preparing_scan_task": "Preparing scan task...",
        "scanner.no_valid_path": "No valid search paths found",
        "scanner.indexing_files": "Indexing files...",
        "scanner.cannot_access_path": "Cannot access path {path}: {error}",
        "scanner.analyzing_mod": "Analyzing: {name}",
        "scanner.processing_conflicts": "Processing conflicts and runtime convergence...",
        "scanner.batch_insert_failed": "Batch insert failed: {error}",
        "scanner.scan_completed": "Scan completed",
        "scanner.scan_failed": "Scan failed: {error}",
        "scanner.scan_cancelled_by_user": "Scan cancelled by user",
        "scanner.scan_cancelled_by_user_desc": "Scan cancelled by user; no changes were made to the database.",
        
        # workshop/bridge
        "workshop.error.missing_url": "No target workshop page URL provided",
        "workshop.error.steam_only": "Only Steam Workshop pages are currently proxied",
        "workshop.error.load_failed_reason": "Failed to load page: {exc}",
        "workshop.id.unrecognized": "Unrecognized",
        "workshop.bridge.not_ready": "Page bridge is not ready, please try again later.",
        "workshop.bridge.no_workshop_id": "No Workshop ID recognized on the current page, you can continue browsing other workshop pages.",
        "workshop.bridge.navigate_failed": "Failed to navigate",
        "workshop.bridge.get_forms_only": "Only GET navigation forms are currently intercepted; original page behavior is preserved.",
    }
}

def t(key: str, **kwargs: Any) -> str:
    """
    Translate a message key into the user's active language.
    If the key is not found, it returns the key itself.
    """
    try:
        from backend.settings import settings
        lang = settings.config.language
    except Exception:
        lang = "en"
        
    # Normalize language to supported ones, default to English
    if not lang or lang not in MESSAGES:
        if lang and lang.startswith("zh"):
            lang = "zh-CN"
        else:
            lang = "en"
            
    msg = MESSAGES.get(lang, {}).get(key)
    if msg is None:
        # Fallback to English
        msg = MESSAGES.get("en", {}).get(key)
        
    if msg is None:
        # Return the key itself as fallback
        return key
        
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception as e:
            logger.warning(f"Failed to format translation key '{key}' with args {kwargs}: {e}")
            return msg
            
    return msg
