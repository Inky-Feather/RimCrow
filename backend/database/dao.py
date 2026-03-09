import datetime
from functools import reduce
import operator
import os
import re
from typing import Any, Dict, List, cast
import uuid
from peewee import chunked, fn, JOIN
from backend.database.models import SubscribedCollection, db, ModAsset, UserModData, GroupData, GroupMod
from backend.managers.mgr_files import file_mgr
from backend.managers.mgr_profile import ProfileContext
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
    def get_profile_mods(context: ProfileContext|None):
        """
        根据当前环境获取模组列表。
        实现了 Context Filtering (环境过滤) 和 Shadowing Strategy (遮蔽策略)。
        :param profile_id: 环境ID，为空则读取全局配置的当前环境
        :return: List[Dict] 处理后的模组列表
        """
        # 1. 解析环境上下文 (Context Resolution)
        if not context: return [] # 空上下文直接返回空列表

        # 获取环境配置
        local_root = context.local_mods_path
        dlc_root = context.game_dlc_path
        use_workshop_mods = context.use_workshop_mods
        use_self_mods = context.use_self_mods
            
        workshop_root = settings.config.workshop_mods_path
        self_mods_root = settings.config.self_mods_path

        # 路径标准化 (用于 Python 端比对，统一转小写)
        # 标准化路径用于严格匹配 (增加结尾分隔符确保匹配精确)
        def norm(p): return os.path.normpath(p).lower() + os.sep if p else ""
        
        L_PATH = norm(local_root)
        D_PATH = norm(dlc_root)
        W_PATH = norm(workshop_root)
        S_PATH = norm(self_mods_root)

        # 2. 构造查询条件 (只拉取当前环境涉及到的物理路径)
        conditions = []
        # 条件 A: 路径包含 Local Root (使用 contains 或 startswith 模拟)
        if L_PATH: conditions.append(ModAsset.path.startswith(L_PATH))
        if D_PATH: conditions.append(ModAsset.path.startswith(D_PATH))
        # 条件 C: 路径包含 Workshop Root (仅当启用工坊时)
        if use_workshop_mods and W_PATH: conditions.append(ModAsset.path.startswith(W_PATH)) # 宽泛匹配，防止盘符差异
        # 条件 B: 路径包含 Self Mods Path (仅当启用管理器Mod时)
        if use_self_mods and S_PATH: conditions.append(ModAsset.path.startswith(S_PATH))
        
        if local_root: local_root = os.path.normpath(local_root).lower()
        if dlc_root: dlc_root = os.path.normpath(dlc_root).lower()
        if workshop_root: workshop_root = os.path.normpath(workshop_root).lower()
        if self_mods_root: self_mods_root = os.path.normpath(self_mods_root).lower()
            
        if not conditions: return [] # 没有任何有效路径配置

        # 使用 reduce 和 operator.or_ 替代 fn.OR
        # 这会生成标准的 (condition1 OR condition2 OR ...) 结构
        combined_cond = reduce(operator.or_, conditions)
        # 追加过滤条件，不读取已被禁用的 Mod。
        active_cond = (ModAsset.disabled == False) | (ModAsset.disabled.is_null()) # type: ignore
        # 执行查询：(Path A OR Path B) AND (Joined UserData)
        query = (ModAsset.select(ModAsset, UserModData)
                .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                .where(combined_cond & active_cond) # 组合 OR 条件
                .dicts())
         # 3. 核心仲裁逻辑：实现 Local > Self > Workshop
        # 我们先对查询结果按优先级排序，这样后处理时高优先级的自然会覆盖低优先级的
        def get_priority(mod):
            m_path = norm(mod['path'])
            if D_PATH and m_path.startswith(D_PATH): return 0 # 最高优先级
            if L_PATH and m_path.startswith(L_PATH): return 1
            if S_PATH and m_path.startswith(S_PATH): return 2
            if W_PATH and m_path.startswith(W_PATH): return 3
            return 9

        # 关键：按优先级【从低到高】排序，这样循环时高优先级会覆盖前面的
        sorted_mods = sorted(list(query), key=get_priority, reverse=True)
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
        for mod in sorted_mods:
            pkg_id = mod['package_id'].lower()
            # 标记来源供 UI 显示图标
            # m_path = norm(mod['path'])
            # if (L_PATH and m_path.startswith(L_PATH)) or (D_PATH and m_path.startswith(D_PATH)):
            #     mod['store'] = 'local'
            # elif S_PATH and m_path.startswith(S_PATH):
            #     mod['store'] = 'self'
            # elif W_PATH and m_path.startswith(W_PATH):
            #     mod['store'] = 'workshop'
            # else:
            #     mod['store'] = 'unknown'
            merged_map[pkg_id] = mod
            
            # 记录遮蔽信息 (覆盖策略：高优先级在后)
            if pkg_id in merged_map:
                # 记录被遮蔽的记录
                # 例如：如果 merged_map 里已经是 Local，现在的 mod 是 Workshop
                # 可以在这里给被选中的那个 Mod 增加一个属性，告诉前端它遮蔽了谁
                merged_map[pkg_id]['_has_shadow_version'] = True
                
            

        return list(merged_map.values())

    @staticmethod
    def get_triple_domain_assets(context: ProfileContext|None):
        """
        全量获取三域 Mod 资产，不进行 Profile 遮蔽过滤。
        返回格式: { 'workshop': [], 'manager': [], 'local': [] }
        """
        # 1. 直接查询 ModAsset 全表，并关联 UserModData
        all_assets = (ModAsset.select(ModAsset, UserModData)
                      .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                      .dicts())
        result = {'workshop': [], 'self': [], 'local': [], 'missing': [], 'unknown': []}
        
        # # 1. 解析环境上下文 (Context Resolution)
        
        local_root = context.local_mods_path if context else ''
        dlc_root = context.game_dlc_path if context else ''
        
        # # 获取管理器和工坊的基准路径 (用于判断来源)
        # manager_root = os.path.normpath(settings.config.self_mods_path).lower()
        # workshop_root = os.path.normpath(settings.config.workshop_mods_path).lower()
        local_root = local_root.lower()
        dlc_root = dlc_root.lower()

        for asset in all_assets:
            path = os.path.normpath(asset['path']).lower()
            # 1. 尝试获取已生成的缩略图路径 (物理路径)
            # thumb_path = file_mgr.get_thumbnail_path(asset['package_id'])
            # # 2. 决定列表图标 (优先用缩略图，没有则用原图)
            # list_thumb_path = thumb_path if thumb_path else asset['preview_path']
            # # 3. 转换为 HTTP URL
            # asset['thumb_url'] = file_mgr.get_asset_url(list_thumb_path) if list_thumb_path else None
            
            # asset['thumb_url'] = file_mgr.get_asset_url(asset['preview_path']) # 直接把原图发过去，提高效率
            # # 4. 详情页大图 URL
            # asset['preview_url'] = file_mgr.get_asset_url(asset['preview_path']) if asset['preview_path'] else None
            # # 5. 图标 URL
            # asset['icon_url'] = file_mgr.get_asset_url(asset['icon_path']) if asset['icon_path'] else None
            
            # # 分流逻辑
            # if workshop_root and workshop_root in path:
            #     result['workshop'].append(asset)
            # elif manager_root and manager_root in path:
            #     result['self'].append(asset)
            # elif local_root and local_root in path or dlc_root and dlc_root in path:
            #     # 剩下的默认为 local (当前环境或其他环境的 Mods 目录)
            #     result['local'].append(asset)
            
            store = asset['store']
            if store == 'workshop':
                result['workshop'].append(asset)
            elif store == 'self':
                result['self'].append(asset)
            elif local_root and local_root in path or dlc_root and dlc_root in path:
                result['local'].append(asset)
            elif not asset['path']:
                result['missing'].append(asset)
            else:
                result['unknown'].append(asset)
                # logger.warning(f"未知存储域: {store}")
            
        return result
        
    @staticmethod
    def get_all_mods_with_user_data(ignore_missing: bool = False):
        """
        获取所有模组及其用户数据。
        如果 ignore_missing 为 True，则排除缺失的 Mod。
        返回字典列表，方便前端直接使用。
        """
        query = (ModAsset.select(ModAsset, UserModData)
                .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
                .where(cast(Any, ModAsset.path).is_null(False) | (not ignore_missing))
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
    def get_mod_snapshots():
        """
        获取所有 Mod 的物理快照。
        Key: path_hash (物理路径哈希)
        Value: { mtime, size, package_id }
        """
        # 需要 package_id，以便在跳过 XML 解析时依然能告诉扫描器这个 Mod 是谁
        query = ModAsset.select( ModAsset.path_hash, ModAsset.file_modify_time, ModAsset.file_size, 
                                ModAsset.package_id, ModAsset.workshop_id, ModAsset.disabled, ModAsset.name, ModAsset.version, 
                                ModAsset.store, ModAsset.supported_versions ).dicts()
        
        snapshots = {}
        for row in query:
            # 只有 path_hash 才是物理文件的唯一身份证
            snapshots[row['path_hash']] = {
                'mtime': row['file_modify_time'] or 0,
                'size': row['file_size'] or 0,
                'package_id': row['package_id'].lower(), # 缓存 ID
                'workshop_id': row['workshop_id'],
                'disabled': row['disabled'],
                'name': row.get('name', ''),
                'version': row.get('version', ''),
                'store': row.get('store', 'local'),
                'supported_versions': row.get('supported_versions', [])
            }
        return snapshots

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
        # 获取要更新的字段名
        # 注意：bulk_update 需要模型对象列表，或者字典列表 + 字段列表
        update_fields = set(mods_data_list[0].keys()) - {'path_hash'}
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
            existing_records = UserModData.select().where(cast(Any, UserModData.mod_id).in_(mod_ids))
            existing_map = {r.mod_id: r for r in existing_records} # Peewee 中外键ID属性常带_id后缀
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
            existing_records = UserModData.select().where(cast(Any, UserModData.mod_id).in_(mod_ids))
            existing_map = {r.mod_id: r for r in existing_records}
            batch_data = []
            for mid in mod_ids:
                record = existing_map.get(mid)
                # 如果数据库里没记录，或者记录里没标签，直接跳过（不用更新）
                if not record or not record.tags: continue
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
    def set_mod_disabled_status(path: str, disable: bool = True):
        """
        物理禁用/启用 Mod：重命名 About.xml 并同步数据库状态
        """
        about_xml = os.path.join(path, 'About', 'About.xml')
        disabled_xml = about_xml + '.disabled'

        src = about_xml if disable else disabled_xml
        dst = disabled_xml if disable else about_xml

        # 1. 物理文件操作
        if os.path.exists(src):
            try:
                if os.path.exists(dst): os.remove(dst) # 清理残留
                os.rename(src, dst)
            except Exception as e:
                return False, f"文件操作失败: {e}"
        else:
            # 如果文件不存在，可能是已经被手动删改，但我们仍需同步数据库以防万一
            pass

        # 2. 数据库状态更新
        ModAsset.update(disabled=disable).where(ModAsset.path == path).execute()
        return True, "成功"

    @staticmethod
    def delete_mod_physically(path: str):
        """
        物理删除 Mod (移入回收站) 并抹除数据库记录
        """
        from send2trash import send2trash
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            try:
                send2trash(abs_path)
                # 级联删除 UserModData/GroupMod 通常由外键处理
                ModAsset.delete().where(ModAsset.path == path).execute()
                return True, "成功"
            except Exception as e:
                return False, f"删除失败: {e}"
        return False, "路径不存在"

    @staticmethod
    def add_shadow_path(keep_path_hash: str, shadow_path: str):
        """
        为“保留的 Mod”记录“被遮蔽的 Mod”路径
        """
        mod = ModAsset.get_or_none(ModAsset.path_hash == keep_path_hash)
        if mod:
            current_paths = mod.shadow_paths or []
            if shadow_path not in current_paths:
                current_paths.append(shadow_path)
                mod.shadow_paths = current_paths
                mod.save()
                return True
        return False
    
    @staticmethod
    def clean_invalid_shadow_paths():
        """
        清理所有 Mod 中失效的 shadow_paths。
        遍历检查物理路径是否存在，不存在则移除。
        返回: 清理了多少个失效路径
        """
        cleaned_count = 0
        
        # 1. 筛选出可能有 shadow_paths 的记录
        # 注意：SQLite 中 JSON 存为 TEXT，可以简单查不为空的
        # 或者直接查所有，Python处理（Mod数量通常几千个，全量遍历内存开销很小，逻辑更稳）
        mods_with_shadows = ModAsset.select().where(cast(Any, ModAsset.shadow_paths).is_null(False))
        
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
                ModAsset.delete().where(cast(Any, ModAsset.path_hash).in_(total_invalid_mods)).execute()
            else:
                # 如果不删除，只是标记为丢失 (path = '')
                ModAsset.update(path='').where(cast(Any, ModAsset.path_hash).in_(deleted_mods)).execute()
        
        return {'missing_mods': missing_mods, 'deleted_mods': deleted_mods}
    
    @staticmethod
    def clean_orphaned_data():
        """
        清理孤立的 UserModData 和 GroupMod。
        即：删除那些没有任何 ModAsset 关联的配置数据（彻底丢失的 Mod）。
        """
        # 清理 UserModData
        # 删除 mod_id 不在 existing_ids 中的记录
        with db.atomic():
            deleted_user_data = UserModData.delete().where(cast(Any, UserModData.mod_id).not_in(ModAsset.package_id)).execute()
            # 清理 GroupMod (分组关联)
            # 这一步通常由数据库外键级联处理，但为了保险手动清理
            deleted_group_mod = GroupMod.delete().where(cast(Any, GroupMod.mod_id).not_in(ModAsset.package_id)).execute()
        return {
            'deleted_user_configs': deleted_user_data,
            'deleted_group_relations': deleted_group_mod
        }
    
    
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
            (cast(Any, GroupMod.mod_id).in_(mod_ids))
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
    
    
class CollectionDAO:
    @staticmethod
    def get_all():
        """获取所有收录的合集，按创建时间降序"""
        return list(SubscribedCollection.select().order_by(SubscribedCollection.created_time.desc()).dicts()) # type: ignore

    @staticmethod
    def get_collection_by_id(coll_id: str):
        """获取单个合集的完整缓存"""
        return SubscribedCollection.get_or_none(SubscribedCollection.id == str(coll_id))

    @staticmethod
    def upsert_collection(coll_id: str, meta: dict, children: list, total: int, need_download: int):
        """持久化合集及其子项的所有元数据"""
        return SubscribedCollection.insert(
            id=str(coll_id),
            title=meta.get('title'),
            description=meta.get('description'),
            preview_url=meta.get('preview_url'),
            children=children, # 存入完整的子项列表快照
            total=total,
            need_download=need_download,
            time_updated=meta.get('time_updated', 0)
        ).on_conflict_replace().execute()

    @staticmethod
    def delete(coll_id: str):
        """删除合集记录"""
        return SubscribedCollection.delete().where(SubscribedCollection.id == str(coll_id)).execute()
    
    
    
    
    