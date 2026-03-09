# backend/_version.py
__version__ = "0.18.5"  # 主版本.次版本.补丁
__db_version__ = "4"
__build__ = "dev"      # dev, alpha, beta, stable, release

# 结构化更新日志：按版本从新到旧排列
# type 支持: "feature" (新增), "fix" (修复), "optimize" (优化), "breaking" (重大变更)
APP_CHANGELOG = [
    {
        "version": "0.18.7",
        "date": "2026-03-09",
        "changes": [
            {"type": "feature", "text": "新增「界面引导」功能：手带你熟悉各组件功能，降低上手门槛。"},
            {"type": "optimize", "text": "优化右键菜单布局，操作逻辑更加清晰直观。"},
            {"type": "fix", "text": "修正了单项规则编辑界面中工坊规则的显示异常。"}
        ]
    },
    {
        "version": "0.18.4",
        "date": "2026-03-08",
        "changes": [
            {"type": "feature", "text": "新增「库存转移」功能：支持在不同模组库之间一键搬运模组。"},
            {"type": "feature", "text": "新增「模组时间线」：直观查看模组的订阅、下载及变动轨迹。"},
            {"type": "feature", "text": "引入全新的启动封面图，并增加了内置更新日志查看弹窗。"},
            {"type": "optimize", "text": "增强库存检索能力：支持滚动分页查询，搜索结果显示更丰富（含依赖推荐、同作者作品）。"},
            {"type": "optimize", "text": "操作安全检查：订阅或取消订阅时增加 Steam 运行状态检测。"}
        ]
    },
    {
        "version": "0.18.0",
        "date": "2026-03-02",
        "changes": [
            {"type": "feature", "text": "新增「GitHub 模组支持」：支持直接订阅并追踪 GitHub 上的模组仓库，涵盖版本检测。"},
            {"type": "feature", "text": "新增「库视图工作区」：全新的可视化卡片式矩阵，管理成百上千个模组更轻松。"},
            {"type": "feature", "text": "新增「合集持久化」：支持本地缓存工坊合集快照，离线也能查看已选模组。"},
            {"type": "feature", "text": "支持「模组替代版本」建议：一键检测并跳转至更优的替代版本或缺失的依赖项。"},
            {"type": "optimize", "text": "改进冲突处理逻辑：冲突窗口支持直接转为本地版本或取消订阅，决策更方便。"},
            {"type": "optimize", "text": "智能静默模式：游戏运行时自动进入极简低功耗模式，支持手动唤醒或强制休眠。"}
        ]
    },
    {
        "version": "0.17.10",
        "date": "2026-02-26",
        "changes": [
            {"type": "breaking", "text": "重构底层路径逻辑：现在每个「环境」的路径完全隔离，配置更加严谨安全。"},
            {"type": "feature", "text": "新增「网络代理」支持：解决部分地区访问工坊或 AI 服务不顺畅的问题。"},
            {"type": "feature", "text": "新增「主界面布局自定义」：支持自由调整界面板块的显示顺序和可见性。"},
            {"type": "feature", "text": "新增「网络预览图缓存」：大幅提升模组详情页的加载速度，节省流量。"},
            {"type": "optimize", "text": "增加 DPI 感知支持：在高分屏或多屏环境下运行不再拉伸模糊。"},
            {"type": "optimize", "text": "优化滚动位置记录：在切换列表时会自动记忆上次浏览的位置。"}
        ]
    }
]

def get_all_changelogs():
    """
    获取全量结构化日志给前端，由前端根据 old_version 决定显示增量还是全量
    """
    return APP_CHANGELOG