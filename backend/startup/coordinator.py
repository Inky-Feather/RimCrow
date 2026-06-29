from __future__ import annotations

import threading
from typing import Callable

from backend.utils.event_bus import EventBus
from backend.utils.logger import logger


class StartupCoordinator:
    """收口启动期后台动作，避免 API 直接承载启动编排细节。

    这里目前只放“不影响首屏打开”的后台预热；数据库修复、迁移等高风险动作仍应放在
    API 初始化前置路径里阻塞执行，避免用户在不可靠状态下进入主界面。
    """

    def __init__(
        self,
        workshop_db_mgr,
        *,
        rule_mgr_provider: Callable[[], object | None] | None = None,
        dlc_cache_warmup: Callable[[], object | None] | None = None,
        append_messages: Callable[[list[str]], None] | None = None,
    ):
        self.workshop_db_mgr = workshop_db_mgr
        self.rule_mgr_provider = rule_mgr_provider
        self.dlc_cache_warmup = dlc_cache_warmup
        self.append_messages = append_messages
        # 预热只允许启动一次；API 可能被前端 ready 事件或测试重复触发。
        self._warmup_started = False
        self._lock = threading.Lock()

    def start_background_warmup(self) -> bool:
        """启动不阻塞首屏的缓存预热任务。重复调用会被忽略。"""
        with self._lock:
            if self._warmup_started:
                return False
            self._warmup_started = True

        threading.Thread(
            target=self._run_background_warmup,
            name="startup-warmup",
            daemon=True,
        ).start()
        return True

    def _run_background_warmup(self):
        startup_messages: list[str] = []
        try:
            if not self.workshop_db_mgr.cache_loaded:
                # 工坊缓存和规则镜像都属于“有则更准”的数据，失败只提示，不阻塞启动。
                logger.info("启动后台预热：开始加载工坊数据缓存并刷新规则索引")
                self.workshop_db_mgr.load_all_cache()
                rule_mgr = self.rule_mgr_provider() if self.rule_mgr_provider else None
                if rule_mgr:
                    # 工坊缓存会影响依赖/替代规则判断，预热完成后同步重建规则镜像。
                    rule_mgr.build_workshop_rules()
            if self.dlc_cache_warmup:
                logger.info("启动后台预热：同步当前语言 DLC 翻译缓存")
                self.dlc_cache_warmup()
        except Exception as exc:
            logger.error(f"启动后台预热失败: {exc}", exc_info=True)
            startup_messages.append("后台数据缓存加载失败，主界面已继续打开；依赖、替代或 DLC 文本可能暂时不完整。")
        finally:
            if not startup_messages:
                return
            if self.append_messages and any("失败" in item for item in startup_messages):
                # 只有失败需要写入启动上下文；成功保持静默，避免启动后重复打扰用户。
                self.append_messages(startup_messages)
            EventBus.send_toast(
                "\n".join(startup_messages),
                type="warning" if any("失败" in item for item in startup_messages) else "info",
            )
