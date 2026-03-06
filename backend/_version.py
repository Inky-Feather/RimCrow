# backend/_version.py
__version__ = "0.18.4"  # 主版本.次版本.补丁
__db_version__ = "4"
__build__ = "dev"      # dev, alpha, beta, stable, release

# 更新日志：按版本从新到旧排列
# 结构: (版本号, 日期, [更新内容列表])
APP_CHANGELOG = [
]

def get_changelog_since(last_version: str):
    """
    获取大于 last_version 的所有更新记录
    """
    from distutils.version import LooseVersion
    updates = []
    for version, date, notes in APP_CHANGELOG:
        # 如果当前循环的版本比上次运行的版本新，则加入显示列表
        if LooseVersion(version) > LooseVersion(last_version):
            updates.append({
                "version": version,
                "date": date,
                "notes": notes
            })
    return updates