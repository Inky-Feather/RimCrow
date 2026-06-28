"""AI 模块入口。"""

# 保持包初始化轻量，避免导入子模块时提前拉起 service / database 依赖。
__all__: list[str] = []
