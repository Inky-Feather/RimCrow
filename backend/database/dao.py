import datetime
import os
import re
import uuid
from peewee import chunked, fn, JOIN
from backend.database.models import db, Mod, UserModData, GroupData, GroupMod


# 定义不需要更新的字段名 (黑名单)
exclude_names = {'package_id', 'file_create_time'}

class ModDAO:
    """
    Mod 操作的数据访问对象。
    封装所有数据库交互。
    """

    @staticmethod
    def get_all_mods_with_user_data():
        """
        获取所有模组及其用户数据。
        返回字典列表，方便前端直接使用。
        """
        query = (Mod
                 .select(Mod, UserModData)
                 .join(UserModData, on=(Mod.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                 .dicts())
        return list(query)

    @staticmethod
    def get_mod_mtimes():
        """
        获取所有 Mod 的修改时间戳，用于增量扫描对比。
        :return: {package_id: float}
        """
        query = Mod.select(Mod.package_id, Mod.file_modify_time).dicts()
        return {row['package_id']: row['file_modify_time'] for row in query}

    @staticmethod
    def batch_upsert_mods(mods_data_list):
        """
        批量插入或更新 Mod 数据 (核心扫描逻辑)。
        使用原子事务处理。
        """
        if not mods_data_list:
            return

        # 预处理：确保所有 JSON 字段都是 Python 对象（Peewee 会自动序列化），
        # 并补充默认时间戳（如果是新记录）
        now = datetime.datetime.now()
        preserve_fields = [
            # _meta 属性是由 Peewee 的 元类（Metaclass）在运行时动态注入到 Mod 类中的
            field for field in Mod._meta.sorted_fields  # type: ignore
            if field.name not in exclude_names
        ]
        
        with db.atomic():
            # 使用 chunked 分批处理，防止 SQL 语句过长
            for batch in chunked(mods_data_list, 100):
                # insert_many(...).on_conflict_replace() 是最快的方法
                # 注意：这会重置没有在 batch 里提供的字段为默认值，
                # 但由于 Mod 表主要是扫描生成的，全量覆盖是可以接受的。
                # 如果要保留某些非扫描字段，需要先读取再合并，或者由 UserModData 承担。
                Mod.insert_many(batch).on_conflict(
                    conflict_target=[Mod.package_id],
                    preserve=preserve_fields # <--- 这里使用自动生成的列表
                ).execute()

    @staticmethod
    def update_user_data(package_id, data_dict):
        """
        更新用户自定义数据 (Tags, Notes 等)。
        """
        with db.atomic():
            user_data, created = UserModData.get_or_create(mod_id=package_id)
            
            # 动态设置属性
            updated = False
            for key, value in data_dict.items():
                if hasattr(user_data, key):
                    setattr(user_data, key, value)
                    updated = True
            
            if updated:
                user_data.save()
        return True

    @staticmethod
    def find_missing_mods(delete=False):
        """
        查找并处理数据库中路径无效的 Mod。
        :param delete: 
            True  -> 直接删除记录 (会级联删除 UserModData/GroupMod)
            False -> 仅将 path 设为 None (保留用户备注等数据，标记为缺失)
        返回: 无效 Mod 的 package_id 列表
        """
        missing_mods = []
        
        # 1. 遍历检查文件是否存在 (这一步比较耗时，但必须做)
        # 优化：只查询有 path 的记录，已经为 None 的不用查了
        query = Mod.select(Mod.package_id, Mod.path).where(Mod.path.is_null(False)).dicts()
        
        for mod in query:
            pkg_id = mod['package_id']
            path = mod['path']
            # 检查路径是否存在 (注意：path 可能是空字符串)
            if not path or not os.path.exists(path):
                missing_mods.append(pkg_id)
        
        if not missing_mods:
            return []

        # 2. 数据库操作 (原子事务)
        with db.atomic():
            if delete:
                # 如果要删除，直接删，不需要先 update
                # chunked 并不是必须的，除非一次性删几万条，这里直接 in_ 即可
                Mod.delete().where(Mod.package_id.in_(missing_mods)).execute()
            else:
                # 如果不删除，只是标记为丢失 (path = None)
                Mod.update(path=None).where(Mod.package_id.in_(missing_mods)).execute()
        
        return missing_mods
        
        
        
class GroupDAO:
    """
    管理分组逻辑。
    包含：创建、删除、重命名、拖拽排序、成员管理。
    """

    @staticmethod
    def get_all_groups_structured():
        """
        【关键方法】获取完整的分组数据结构，供前端渲染。
        返回格式:
        [
            {
                "group_id": "uuid...",
                "name": "核心模组",
                "color": "#ff0000",
                "is_expanded": True,
                "mod_ids": ["ludeon.rimworld", "ludeon.rimworld.royalty"] // 按 sort_index 排好序的 ID
            },
            ...
        ]
        """
        # 1. 获取所有分组，按分组自身的 sort_index 排序
        groups = list(GroupData.select().order_by(GroupData.sort_index).dicts())
        
        # 2. 获取所有关联关系，按 sort_index 排序
        # 使用 prefetch 或者简单的查全表再内存分配。
        # 这里数据量不大（通常几百个关系），查全表内存分配是最快的，比 N 次 SQL 查询快得多。
        group_mods = list(GroupMod.select().order_by(GroupMod.sort_index).dicts())

        # 3. 在内存中组装 (Python 处理比 SQL Join 更灵活，方便输出前端需要的 JSON 结构)
        # 建立 group_id -> mod_ids list 的映射
        group_map = {g['group_id']: [] for g in groups}
        
        for gm in group_mods:
            g_id = gm['group_id'] # Peewee dicts() 返回的外键是 ID 值
            p_id = gm['mod_id']   # 同上
            
            if g_id in group_map:
                group_map[g_id].append(p_id)

        # 4. 将 mod_ids 填回 groups 列表
        for g in groups:
            g['mod_ids'] = group_map.get(g['group_id'], [])
            
        return groups

    @staticmethod
    def create_group(name, color='#ffffff'):
        """创建新分组"""
        new_id = uuid.uuid4().hex
        # 获取当前最大的 sort_index，以便排在最后
        max_idx = GroupData.select(fn.MAX(GroupData.sort_index)).scalar() or 0
        
        return GroupData.create(
            group_id=new_id,
            name=name,
            color=color,
            sort_index=max_idx + 1,
            is_expanded=True
        )

    @staticmethod
    def delete_group(group_id):
        """删除分组 (级联删除 GroupMod 会由数据库外键约束或Peewee处理)"""
        return GroupData.delete().where(GroupData.group_id == group_id).execute()

    @staticmethod
    def update_group_info(group_id, **kwargs):
        """
        更新分组属性 (重命名、改色、折叠状态)。
        kwargs: {'name': 'NewName', 'color': '...', 'is_expanded': False}
        """
        return GroupData.update(**kwargs).where(GroupData.group_id == group_id).execute()

    @staticmethod
    def add_mods_to_group(group_id, mod_ids):
        """
        向分组添加 Mod (支持批量)。
        自动处理重复添加的情况（如果是联合主键，需要 try-except 或 ignore）。
        """
        if not mod_ids: return

        # 获取该组当前最大的 sort_index
        max_idx = GroupMod.select(fn.MAX(GroupMod.sort_index)).where(GroupMod.group_id == group_id).scalar() or 0
        
        data_source = []
        for i, pid in enumerate(mod_ids):
            data_source.append({
                'group_id': group_id,
                'mod_id': pid,
                'sort_index': max_idx + 1 + i
            })
        
        with db.atomic():
            # 使用 insert_many().on_conflict_ignore() 防止重复添加报错
            GroupMod.insert_many(data_source).on_conflict_ignore().execute()

    @staticmethod
    def remove_mods_from_group(group_id, mod_ids):
        """从分组移除 Mod"""
        query = GroupMod.delete().where(
            (GroupMod.group_id == group_id) & 
            (GroupMod.mod_id.in_(mod_ids))
        )
        return query.execute()

    @staticmethod
    def reorder_groups(group_id_list):
        """
        重新排序分组本身。
        前端拖拽分组位置后，发送新的 group_id 顺序列表。
        """
        with db.atomic():
            for idx, gid in enumerate(group_id_list):
                GroupData.update(sort_index=idx).where(GroupData.group_id == gid).execute()

    @staticmethod
    def reorder_mods_in_group(group_id, mod_id_list):
        """
        重新排序分组内的 Mod。
        前端在组内拖拽 Mod 后，发送该组新的 mod_id 顺序列表。
        """
        with db.atomic():
            # 这种循环更新在几百个 item 内性能是可以接受的 (SQLite很快)
            # 如果数量级很大，可以使用 SQL CASE WHEN 语句优化
            for idx, pid in enumerate(mod_id_list):
                GroupMod.update(sort_index=idx).where(
                    (GroupMod.group_id == group_id) & 
                    (GroupMod.mod_id == pid)
                ).execute()