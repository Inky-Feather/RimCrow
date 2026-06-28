import datetime
from functools import reduce
import operator
import os
import re
from typing import Any, Dict, List
import uuid
from peewee import chunked, fn, JOIN
from backend.database.models import GameProfile, db, ModAsset, UserModData, GroupData, GroupMod
from backend.settings import settings
from backend.utils.logger import logger


# 定义不需要更新的字段名 (黑名单)
exclude_names = {'path_hash'}

class ModDAO:
    """
    Mod 操作的数据访问对象。
    封装所有数据库交互。
    """

    @staticmethod
    def get_profile_mods(profile_id: str = ''):
        """
        根据当前环境获取模组列表。
        实现了 Context Filtering (环境过滤) 和 Shadowing Strategy (遮蔽策略)。
        :param profile_id: 环境ID，为空则读取全局配置的当前环境
        :return: List[Dict] 处理后的模组列表
        """
        # 1. 解析环境上下文 (Context Resolution)
        if not profile_id:
            profile_id = settings.config.current_profile_id

        # 获取环境配置
        # 兜底逻辑：如果 ID 是 default 或者 库里没查到，就用 settings 的全局配置
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        
        if profile:
            local_root = profile.game_install_path
            use_workshop_mods = profile.use_workshop_mods
        else:
            # Default 环境兜底
            local_root = settings.config.game_install_path
            use_workshop_mods = settings.config.use_workshop_mods
            
        workshop_root = settings.config.workshop_mods_path

        # 路径标准化 (用于 Python 端比对，统一转小写)
        if local_root: local_root = os.path.normpath(local_root).lower()
        if workshop_root: workshop_root = os.path.normpath(workshop_root).lower()

        # 2. 数据库查询 (SQL Filtering)
        # 目的：只拉取属于当前 Local 目录的，或者属于公共 Workshop 的模组。
        # 避免把其他 Profile 的 Local Mod 拉进来。
        
        # 构造 OR 查询条件
        conditions = []
        
        # 条件 A: 路径包含 Local Root (使用 contains 或 startswith 模拟)
        # 注意：SQLite 的 LIKE 不区分大小写(默认情况)，但为了保险最好在 Python 层再严谨校验一次
        if local_root:
            conditions.append(ModAsset.path.contains(local_root)) # 宽泛匹配，防止盘符差异
        
        # 条件 B: 路径包含 Workshop Root (仅当启用工坊时)
        if use_workshop_mods and workshop_root:
            conditions.append(ModAsset.path.contains(workshop_root))
            
        if not conditions:
            return [] # 没有任何有效路径配置

        # 使用 reduce 和 operator.or_ 替代 fn.OR
        # 这会生成标准的 (condition1 OR condition2 OR ...) 结构
        combined_cond = reduce(operator.or_, conditions)
        # 执行查询：(Path A OR Path B) AND (Joined UserData)
        query = (ModAsset.select(ModAsset, UserModData)
                 .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                 .where(combined_cond) # 组合 OR 条件
                 .dicts())

        # 预加载分组映射 (Preload Group Mapping)，建立 { package_id: ["分组A", "分组B"] } 的映射
        group_map = {}
        try:
            # 联查 GroupMod 和 GroupData，只取必要的字段
            # SELECT gm.mod_id, g.name FROM groupmod gm JOIN groupdata g ON gm.group_id = g.group_id
            g_query = (GroupMod.select(GroupMod.mod_id, GroupData.name)
                       .join(GroupData, on=(GroupMod.group_id == GroupData.group_id))
                       .dicts())
            
            for row in g_query:
                mid = row['mod_id'].lower()
                gname = row['name']
                if mid not in group_map:
                    group_map[mid] = []
                group_map[mid].append(gname)
        except Exception as e:
            logger.error(f"Failed to load group map: {e}")
        
        # 3. 内存处理 (Python Logic)
        # 实现 "Local Trumps Workshop" (本地优先于工坊)
        
        merged_map = {} # { package_id: mod_data }

        for mod in query:
            # 路径清洗
            if not mod['path']: continue
            mod_path = os.path.normpath(mod['path']).lower()
            pkg_id = mod['package_id'] # 注意：数据库里已经是小写了
            
            # 注入分组名称列表
            mod['groups'] = group_map.get(pkg_id, [])
            
            # 判定来源类型
            is_local_mod = False
            if local_root and local_root in mod_path:
                is_local_mod = True
                mod['is_local'] = True # 标记供前端展示文件夹图标
            # 判定是否是 DLC (Data 目录下的)
            # 也可以简单判断：source == 'dlc' 或 'core'
            is_dlc = mod.get('source') in ['core', 'dlc']

            # 冲突仲裁逻辑：
            # 1. 如果是 Local Mod 或 DLC -> 强制覆盖 (优先级最高)
            # 2. 如果是 Workshop Mod -> 只有当 Dictionary 里还没这个 ID 时才加入
            
            if is_local_mod or is_dlc:
                merged_map[pkg_id] = mod
            else:
                # 是 Workshop Mod
                # 只有当不存在 同名 Local Mod 时才加入
                if pkg_id not in merged_map:
                    mod['is_local'] = False # 标记供前端展示 Steam 图标
                    merged_map[pkg_id] = mod
                else:
                    # 可以在这里记录一下 "被遮蔽" 的信息
                    merged_map[pkg_id]['_shadowed_workshop'] = True
                    pass

        return list(merged_map.values())

    @staticmethod
    def clean_orphaned_data():
        """
        清理孤立的 UserModData 和 GroupMod。
        即：删除那些没有任何 ModAsset 关联的配置数据（彻底丢失的 Mod）。
        """
        # 清理 UserModData
        # 删除 mod_id 不在 existing_ids 中的记录
        with db.atomic():
            deleted_user_data = UserModData.delete().where(UserModData.mod_id.not_in(ModAsset.package_id)).execute()
            # 清理 GroupMod (分组关联)
            # 这一步通常由数据库外键级联处理，但为了保险手动清理
            deleted_group_mod = GroupMod.delete().where(GroupMod.mod_id.not_in(ModAsset.package_id)).execute()
        return {
            'deleted_user_configs': deleted_user_data,
            'deleted_group_relations': deleted_group_mod
        }
    
    @staticmethod
    def get_all_mods_with_user_data(ignore_missing: bool = False):
        """
        获取所有模组及其用户数据。
        如果 ignore_missing 为 True，则排除缺失的 Mod。
        返回字典列表，方便前端直接使用。
        """
        query = (ModAsset.select(ModAsset, UserModData)
                 .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                 .where(ModAsset.path.is_null(False) | (not ignore_missing))
                 .dicts())
        return list(query)
    
    @staticmethod
    def get_all_user_data():
        """
        获取所有用户数据。
        返回字典列表，方便前端直接使用。
        """
        query = UserModData.select().dicts()
        return list(query)

    @staticmethod
    def get_mod_mtimes():
        """
        获取所有 Mod 的修改时间戳，用于增量扫描对比。
        :return: {package_id: float}
        """
        query = ModAsset.select(ModAsset.package_id, ModAsset.file_modify_time).dicts()
        return {row['package_id']: row['file_modify_time'] for row in query}

    @staticmethod
    def batch_upsert_mods(mods_data_list: List[Dict[str, Any]]):
        """
        批量插入或更新 Mod 数据 (核心扫描逻辑)。
        使用原子事务处理。
        """
        if not mods_data_list: return
        # 1. 获取所有合法的数据库字段名
        # Mod._meta.fields 是一个字典 {field_name: FieldObject}
        valid_field_names = set(ModAsset._meta.fields.keys()) # type: ignore
        
        # 2. 准备 upsert 时需要保留（更新）的字段列表
        # 这里排除掉主键和其他不想被覆盖的字段
        preserve_fields = [
            # _meta 属性是由 Peewee 的 元类（Metaclass）在运行时动态注入到 Mod 类中的，编辑器报错可以忽略
            field for field in ModAsset._meta.sorted_fields  # type: ignore
            if field.name not in exclude_names
        ]
        
        with db.atomic():
            # 使用 chunked 分批处理，防止 SQL 语句过长
            for batch in chunked(mods_data_list, 100):
                # insert_many(...).on_conflict_replace() 是最快的方法
                # 注意：这会重置没有在 batch 里提供的字段为默认值，
                # 但由于 Mod 表主要是扫描生成的，全量覆盖是可以接受的。
                # 如果要保留某些非扫描字段，需要先读取再合并，或者由 UserModData 承担。
                
                # 遍历 batch 中的每个字典，只保留 valid_field_names 中存在的键
                clean_batch = []
                for mod_data in batch:
                    clean_data = {
                        k: v for k, v in mod_data.items() 
                        if k in valid_field_names
                    }
                    clean_batch.append(clean_data)
                
                ModAsset.insert_many(clean_batch).on_conflict(
                    conflict_target=[ModAsset.path_hash],
                    preserve=preserve_fields # <--- 这里使用自动生成的列表
                ).execute()

    @staticmethod
    def batch_update_mods(mods_data_list: List[Dict[str, Any]]):
        """
        批量更新 Mod 的特定字段 (仅用于已存在的 Mod)。
        """
        if not mods_data_list: return
        # 获取要更新的字段名 (假设所有字典的 key 是一样的，或者取并集)
        # 注意：bulk_update 需要模型对象列表，或者字典列表 + 字段列表
        update_fields = set(mods_data_list[0].keys()) - {'package_id'}
        # 将字典转换为模型实例 (Peewee bulk_update 需要实例)
        model_instances = [ModAsset(**data) for data in mods_data_list]
        with db.atomic():
            # batch_size 自动处理分批
            ModAsset.bulk_update(model_instances, fields=list(update_fields), batch_size=100)
    
    @staticmethod
    def update_user_data(package_id: str, data_dict: Dict[str, Any]):
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
    def batch_upsert_user_data(user_data_list: List[Dict[str, Any]]):
        """
        批量插入或更新用户自定义数据 (Tags, Notes 等)。
        使用原子事务处理。
        """
        if not user_data_list: return
        # 1. 动态获取字段信息
        # 排除主键 mod_id (作为冲突检测目标) 和其他不应通过此接口更新的字段
        exclude_fields = {'mod_id'}
        # 获取所有有效字段名
        valid_field_names = set(UserModData._meta.fields.keys()) # type: ignore
        # 确定冲突时需要更新的字段 (On Conflict Update)
        # 获取 user_data_list 中出现过的所有键，取交集，确保只更新传入的字段
        input_keys = set().union(*(d.keys() for d in user_data_list))
        update_fields = [
            field for field in UserModData._meta.sorted_fields  # type: ignore
            if field.name in input_keys and field.name not in exclude_fields
        ]
        with db.atomic():
            for batch in chunked(user_data_list, 100):
                # 数据清洗：移除数据库模型中不存在的字段，防止报错
                # clean_batch = []
                # for user_data in batch:
                #     clean_data = {
                #         k: v for k, v in user_data.items() 
                #         if k in valid_field_names
                #     }
                #     clean_batch.append(clean_data)
                # if not clean_batch: continue
                clean_batch = [
                    {k: v for k, v in d.items() if k in UserModData._meta.fields} # type: ignore
                    for d in batch
                ]
                # 执行 Upsert
                # 如果记录不存在 -> Insert
                # 如果记录存在 (mod_id冲突) -> Update preserve 列表中的字段
                UserModData.insert_many(clean_batch).on_conflict(
                    conflict_target=[UserModData.mod_id], 
                    preserve=update_fields 
                ).execute()
    
    @staticmethod
    def link_mods(mod_ids: List[str]):
        """
        Mod 联锁操作。
        :param mod_ids: 有序的 Mod ID 列表，例如 ['core', 'royalty', 'ideology']
        """
        if not mod_ids or len(mod_ids) < 1:
            return
        user_data_batch = []
        total_len = len(mod_ids)
        for i, pkg_id in enumerate(mod_ids):
            # 计算前驱和后继
            prev_id = mod_ids[i-1] if i > 0 else None
            next_id = mod_ids[i+1] if i < total_len - 1 else None
            # 构建数据字典
            user_data_batch.append({
                'mod_id': pkg_id,
                'lock_previous_mod': prev_id,
                'lock_next_mod': next_id
            })
        # 直接复用批量更新方法，一次性写入数据库
        # 这会自动处理“记录不存在则创建”的情况
        ModDAO.batch_upsert_user_data(user_data_batch)
        return {'link_mods': user_data_batch}
        
    @staticmethod
    def unlink_mods(mod_ids: List[str]):
        """
        解除指定 Mods 的联锁状态 (将前后锁置空)。
        :param mod_ids: list[str] 要解锁的 Mod ID 列表
        """
        if not mod_ids: return
        # 构造更新数据：将两个字段设为 None
        data = [ {'mod_id': mid, 'lock_previous_mod': None, 'lock_next_mod': None} for mid in mod_ids ]
        ModDAO.batch_upsert_user_data(data)
        return {'unlink_mods': mod_ids}
    
    @staticmethod
    def set_user_mods_type(mod_ids: List[str], new_type: str):
        """
        批量设置用户自定义 Mod 类型
        """
        data = [{'mod_id': mid, 'user_mod_type': new_type} for mid in mod_ids]
        ModDAO.batch_upsert_user_data(data)
        
    @staticmethod
    def set_mods_color(mod_ids: List[str], color_hex: str):
        """
        批量设置 Mod 颜色。
        """
        if not mod_ids: return
        # 验证颜色格式
        if color_hex and not re.match(r'^#[0-9a-fA-F]{6}$', color_hex):
            raise ValueError("Invalid color format. Use #RRGGBB.")
        # 构造数据调用 batch_upsert
        data = [{'mod_id': mid, 'sign_color': color_hex} for mid in mod_ids]
        ModDAO.batch_upsert_user_data(data)
        
    @staticmethod
    def add_tags_to_mods(mod_ids: List[str], new_tags: List[str]):
        """
        向指定 Mod 追加标签（自动去重）。
        """
        if not mod_ids or not new_tags: return
        
        with db.atomic():
            # 1. 查出已有的记录
            existing_records = UserModData.select().where(UserModData.mod_id.in_(mod_ids))
            existing_map = {r.mod_id_id: r for r in existing_records} # Peewee 中外键ID属性常带_id后缀
            batch_data = []
            for mid in mod_ids:
                record = existing_map.get(mid)
                current_tags = record.tags if record and record.tags else []
                # 集合运算：合并并去重
                # 注意：JSONField 读取出来通常是 List
                updated_tags = list(set(current_tags + new_tags))
                batch_data.append({
                    'mod_id': mid,
                    'tags': updated_tags
                })
                
            # 2. 写入
            ModDAO.batch_upsert_user_data(batch_data)
    
    @staticmethod
    def remove_tags_from_mods(mod_ids: List[str], remove_tags: List[str]):
        """
        从指定 Mod 中批量移除标签。
        :param mod_ids: list[str] Mod ID 列表
        :param remove_tags: list[str] 要移除的标签列表
        """
        if not mod_ids or not remove_tags: return
        
        # 转换为集合提高查找效率
        remove_set = set(remove_tags)

        with db.atomic():
            # 1. 查出已有的记录（只查涉及的 Mod）
            existing_records = UserModData.select().where(UserModData.mod_id.in_(mod_ids))
            existing_map = {r.mod_id_id: r for r in existing_records}
            
            batch_data = []
            for mid in mod_ids:
                record = existing_map.get(mid)
                
                # 如果数据库里没记录，或者记录里没标签，直接跳过（不用更新）
                if not record or not record.tags:
                    continue
                
                current_tags = record.tags # 这是一个 list
                
                # 过滤逻辑：保留不在 remove_set 中的标签
                # 使用列表推导式保持原有顺序（虽然 Tag 顺序通常不重要，但保持更好）
                new_tags = [t for t in current_tags if t not in remove_set]
                
                # 只有当标签数量确实发生变化时才加入更新队列（性能优化）
                if len(new_tags) != len(current_tags):
                    batch_data.append({
                        'mod_id': mid,
                        'tags': new_tags
                    })
            
            # 2. 只有在有数据变动时才执行数据库写入
            if batch_data:
                ModDAO.batch_upsert_user_data(batch_data)
    
    @staticmethod
    def find_missing_mods(delete: bool = False):
        """
        查找并处理数据库中路径无效的 Mod。
        :param delete: 
            True  -> 直接删除记录 (会级联删除 UserModData/GroupMod)
            False -> 仅将 path 设为 None (保留用户备注等数据，标记为缺失)
        返回: 无效 Mod 的 package_id 列表 (包含缺失和删除的)
        {'missing_mods': [], 'deleted_mods': []}
        """
        missing_mods = []   # 之前缺失文件的 Mod
        deleted_mods = []   # 上次删除的 Mod
        
        # 1. 遍历检查文件是否存在 (这一步比较耗时，但必须做)
        # 只查询有 path 的记录，已经为 None 的不用查了
        query = ModAsset.select(ModAsset.path_hash, ModAsset.path).dicts()
        
        for asset in query:
            path = asset['path']
            if not path:
                missing_mods.append(asset['path_hash'])
            elif not os.path.exists(path):
                deleted_mods.append(asset['path_hash'])
        
        total_invalid_mods = missing_mods + deleted_mods
        # # 从 GroupMod 中删除这些 Mod 的关联
        # GroupMod.delete().where(GroupMod.mod_id.in_(total_invalid_mods)).execute()
        
        if not total_invalid_mods:
            return {'missing_mods': missing_mods, 'deleted_mods': deleted_mods}

        # 2. 数据库操作 (原子事务)
        with db.atomic():
            if delete:
                # 如果要删除，直接删，不需要先 update
                # chunked 并不是必须的，除非一次性删几万条，这里直接 in_ 即可
                ModAsset.delete().where(ModAsset.path_hash.in_(total_invalid_mods)).execute()
            else:
                # 如果不删除，只是标记为丢失 (path = '')
                ModAsset.update(path='').where(ModAsset.path_hash.in_(deleted_mods)).execute()
        
        return {'missing_mods': missing_mods, 'deleted_mods': deleted_mods}
    
    @staticmethod
    def clean_invalid_shadow_paths():
        """
        清理所有 Mod 中失效的 shadow_paths。
        遍历检查物理路径是否存在，不存在则移除。
        返回: 清理了多少个失效路径
        """
        cleaned_count = 0
        
        # 1. 筛选出可能有 shadow_paths 的记录
        # 注意：SQLite 中 JSON 存为 TEXT，我们可以简单查不为空的
        # 或者直接查所有，Python处理（Mod数量通常几千个，全量遍历内存开销很小，逻辑更稳）
        mods_with_shadows = ModAsset.select().where(ModAsset.shadow_paths.is_null(False))
        
        with db.atomic():
            for mod in mods_with_shadows:
                current_paths = mod.shadow_paths
                if not current_paths or not isinstance(current_paths, list):
                    continue
                
                # 2. 过滤有效路径
                # 判断标准：路径存在，且里面有 About/About.xml.disabled (更严谨)
                # 或者简单点：只要文件夹还在就行 (宽容)
                # 这里建议：只要文件夹存在即可，防止用户误删了 .disabled 文件但文件夹还在的情况
                valid_paths = [
                    p for p in current_paths 
                    if p and os.path.exists(p)
                ]
                
                # 3. 如果有变化，更新数据库
                if len(valid_paths) != len(current_paths):
                    removed_num = len(current_paths) - len(valid_paths)
                    cleaned_count += removed_num
                    
                    mod.shadow_paths = valid_paths
                    mod.save()
                    logger.info(f"Cleaned {removed_num} shadow paths for {mod.package_id}")

        return cleaned_count
    
    
        
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
    def get_groups_structured_by_mod_ids(allowed_ids: List[str]):
        """
        获取结构化分组数据，并根据给定的 ID 集合过滤内容。
        :param allowed_ids: 当前环境下可见的模组 package_id 集合 (Set 提高查找效率)
        """
        # 1. 获取所有分组
        groups = list(GroupData.select().order_by(GroupData.sort_index).dicts())
        
        # 2. 获取所有分组关联
        group_mods = list(GroupMod.select().order_by(GroupMod.sort_index).dicts())

        # 3. 过滤逻辑
        # 建立当前环境的 Set 提高查询速度
        available_set = set(allowed_ids)
        
        group_map = {g['group_id']: [] for g in groups}
        
        for gm in group_mods:
            g_id = gm['group_id']
            p_id = gm['mod_id'] # 这里存的是 package_id
            
            # 【关键点】只有当该 Mod 在当前环境下“物理存在”时，才分发给前端展示
            if p_id in available_set:
                group_map[g_id].append(p_id)

        # 4. 组装
        for g in groups:
            g['mod_ids'] = group_map.get(g['group_id'], [])
            
        return groups

    @staticmethod
    def create_group(name: str, color: str = '#ffffff'):
        """创建新分组"""
        # 验证颜色格式
        if not color or not re.match(r'^#[0-9a-fA-F]{6}$', color):
            color = '#ffffff'
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
    def delete_group(group_id: str):
        """删除分组 (级联删除 GroupMod 会由数据库外键约束或Peewee处理)"""
        return GroupData.delete().where(GroupData.group_id == group_id).execute()

    @staticmethod
    def update_group_info(group_id: str, **kwargs):
        """
        更新分组属性 (重命名、改色、折叠状态)。
        kwargs: {'name': 'NewName', 'color': '...', 'is_expanded': False}
        """
        return GroupData.update(**kwargs).where(GroupData.group_id == group_id).execute()

    @staticmethod
    def add_mods_to_group(group_id: str, mod_ids: List[str]):
        """
        向分组添加 Mod (支持批量)。
        自动处理重复添加的情况（如果是联合主键，需要 try-except 或 ignore）。
        """
        if not mod_ids: return
        with db.atomic():
            # 先确保 UserModData 存在，否则外键约束会报错
            stubs = [{'mod_id': mid} for mid in mod_ids]
            UserModData.insert_many(stubs).on_conflict_ignore().execute()   # 批量插入忽略重复

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
    def remove_mods_from_group(group_id: str, mod_ids: List[str]):
        """从分组移除 Mod"""
        query = GroupMod.delete().where(
            (GroupMod.group_id == group_id) & 
            (GroupMod.mod_id.in_(mod_ids))
        )
        return query.execute()

    @staticmethod
    def update_all_expansion_state(is_expanded: bool):
        """
        一次性展开或折叠所有分组
        耗时: 几毫秒
        """
        GroupData.update(is_expanded=is_expanded).execute()

    @staticmethod
    def reorder_groups(group_id_list: List[str]):
        """
        重新排序分组本身。
        前端拖拽分组位置后，发送新的 group_id 顺序列表。
        """
        with db.atomic():
            for idx, gid in enumerate(group_id_list):
                GroupData.update(sort_index=idx).where(GroupData.group_id == gid).execute()

    @staticmethod
    def reorder_mods_in_group(group_id: str, mod_id_list: List[str]):
        """
        重新排序分组内的 Mod。
        优化策略：直接删除该组旧关系，批量插入新关系。
        这样只有 2 次 SQL IO，而不是 N 次。
        """
        if not mod_id_list:
            # 如果列表为空，说明清空了分组
            GroupMod.delete().where(GroupMod.group_id == group_id).execute()
            return
        # 确保 UserModData 中存在这些 ID，否则外键约束会报错
        # 使用 insert_many + on_conflict_ignore 批量创建不存在的记录
        user_data_stubs = [{'mod_id': mid.lower()} for mid in mod_id_list]
        with db.atomic():
            # 先确保父表 (UserModData) 有这些 ID
            UserModData.insert_many(user_data_stubs).on_conflict_ignore().execute()
        
            data_source = []
            for idx, pid in enumerate(mod_id_list):
                data_source.append({
                    'group_id': group_id,
                    'mod_id': pid,
                    'sort_index': idx
                })
                
            # 1. 删除该组所有旧关联
            GroupMod.delete().where(GroupMod.group_id == group_id).execute()
            
            # 2. 批量插入新顺序
            # chunked 并非必须，除非 mod_id_list 超过 999 (SQLite 限制)
            for batch in chunked(data_source, 500):
                GroupMod.insert_many(batch).execute()
    
    
    
    
    
    
    
    