import time

from backend.startup import StartupCoordinator


class FakeWorkshopDB:
    """只模拟 StartupCoordinator 需要的缓存状态，避免测试依赖真实数据库。"""

    def __init__(self):
        self.cache_loaded = False
        self.load_count = 0

    def load_all_cache(self):
        self.load_count += 1
        self.cache_loaded = True


class FakeRuleManager:
    """记录规则镜像是否在缓存预热后重建。"""

    def __init__(self):
        self.build_count = 0

    def build_workshop_rules(self):
        self.build_count += 1


def wait_until(predicate, timeout=1.0):
    """后台预热在线程里执行，测试用短轮询等待异步动作完成。"""

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_startup_warmup_runs_once_and_rebuilds_workshop_rules(monkeypatch):
    """验证启动预热只启动一次，成功时不打扰用户，也不写入升级上下文。"""

    workshop_db = FakeWorkshopDB()
    rule_mgr = FakeRuleManager()
    messages = []
    toasts = []

    monkeypatch.setattr(
        "backend.startup.coordinator.EventBus.send_toast",
        lambda message, type="info", duration=3000: toasts.append((message, type, duration)),
    )

    coordinator = StartupCoordinator(
        workshop_db,
        rule_mgr_provider=lambda: rule_mgr,
        append_messages=messages.extend,
    )

    assert coordinator.start_background_warmup() is True
    assert coordinator.start_background_warmup() is False

    assert wait_until(lambda: workshop_db.load_count == 1)
    assert rule_mgr.build_count == 1
    assert messages == []
    assert toasts == []
