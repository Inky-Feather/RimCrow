# backend/database/migrator.py
import json
import uuid

from playhouse.migrate import SqliteMigrator, migrate
from backend.database.models import GameProfile, GroupData, GroupMod, ModAsset, ModInterlock, UserModData, db, SystemInfo, SubscribedCollection
from backend.utils.logger import logger 
from backend.settings import settings

def run_migrations(old_version):
    migrator = SqliteMigrator(db)
    
    # 策略：根据旧版本号，一级一级往上爬
    
    if old_version == "2":
        _2to3(old_version)
        old_version = "3"
    if old_version == "3":
        _3to4()
        old_version = "4"
    if old_version == "4":
        _4to5()
        old_version = "5"
    
    # 最后更新版本号
    SystemInfo.update(value=old_version).where(SystemInfo.key == 'db_version').execute()
    
    
def _2to3(old_version):
    """数据库迁移主函数
    将Mod表更新为ModAsset，
    并将UserModData和GroupMod更新为新的关联表。
    """
    # 1. 备份原始数据
    # init_db 里已经备份过 .db 文件，这里可以直接操作
    
    try:
        # 检查旧表是否存在 (通过原始 SQL)
        cursor = db.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='mod';")
        if not cursor.fetchone():
            logger.info("未发现旧版 Mod 表，跳过结构迁移。")
            return

        logger.info(f"正在从版本 {old_version} 迁移到新架构...")

        # ---------------------------------------------------------
        # 第一步：在内存中提取并转换数据
        # ---------------------------------------------------------

        # 1.1 提取旧 UserModData (并构建字典以便去重和查找)
        # 结构: { 'package_id': {data_dict} }
        user_data_map = {} 
        try:
            cursor = db.execute_sql("SELECT * FROM usermoddata;")
            # 注意：需要根据旧表的列顺序读取，假设旧表: mod_id(FK), alias_name, notes, tags, sign_color...
            # 建议通过描述获取列名
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                # 旧版外键在数据库里通常存为 mod_id_id (Peewee 默认)
                # 将其转换回新版 CharField 格式的 mod_id (存 package_id)
                pkg_id = item.get('mod_id_id') or item.get('mod_id')
                if pkg_id:
                    pkg_id = pkg_id.lower()
                    item['mod_id'] = pkg_id # 修正键名为新版主键名
                    item.pop('mod_id_id', None) # 清理旧键
                    user_data_map[pkg_id] = item
        except Exception as e:
            logger.warning(f"读取旧 UserModData 失败: {e}")

        # 1.2 提取旧 GroupData
        old_groups = []
        valid_group_ids = set()
        try:
            cursor = db.execute_sql("SELECT * FROM groupdata;")
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                old_groups.append(item)
                if item.get('group_id'):
                    valid_group_ids.add(item['group_id'])
        except Exception as e:
            logger.warning(f"读取旧 GroupData 失败: {e}")

        # 1.3 提取旧 GroupMod
        old_group_mods = []
        # 用于记录那些在分组里出现，但还没在 user_data_map 里的 mod_id
        missing_user_data_ids = set()
        try:
            cursor = db.execute_sql("SELECT * FROM groupmod;")
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                pkg_id = item.get('mod_id_id') or item.get('mod_id')
                group_id = item.get('group_id') or item.get('group_id_id') # 防御性编程
                
                if pkg_id and group_id:
                    pkg_id = pkg_id.lower()
                    
                    # 仅当分组本身有效时才保留关系
                    if group_id in valid_group_ids:
                        item['mod_id'] = pkg_id
                        item['group_id'] = group_id
                        
                        # 清理旧键
                        item.pop('mod_id_id', None)
                        item.pop('group_id_id', None)
                        
                        old_group_mods.append(item)
                        
                        # 【关键修复】：如果这个Mod在分组里，但不在UserModData里，需要标记它
                        if pkg_id not in user_data_map:
                            missing_user_data_ids.add(pkg_id)
        except Exception as e:
            logger.warning(f"读取旧 GroupMod 失败: {e}")

        # ---------------------------------------------------------
        # 第二步：数据补全 (修复“幽灵Mod”问题)
        # ---------------------------------------------------------
        
        if missing_user_data_ids:
            logger.info(f"发现 {len(missing_user_data_ids)} 个Mod存在于分组中但无用户数据，正在自动补全...")
            for missing_id in missing_user_data_ids:
                # 创建一个默认的空 UserModData 对象
                user_data_map[missing_id] = {
                    'mod_id': missing_id,
                    'alias_name': None,
                    'notes': None,
                    'tags': [],
                    'sign_color': None,
                    # 其他字段依靠数据库默认值，或者在这里显式补全
                }

        # ---------------------------------------------------------
        # 第二步：重建表结构
        # ---------------------------------------------------------
        
        with db.atomic():
            # 2.1 临时关闭外键约束
            db.execute_sql('PRAGMA foreign_keys = OFF;')

            # 2.2 删除旧表 (如果存在)
            # 注意：新模型中表名已经变了 (ModAsset)，所以删除旧的 mod 表
            db.execute_sql('DROP TABLE IF EXISTS groupmod;')
            db.execute_sql('DROP TABLE IF EXISTS usermoddata;')
            db.execute_sql('DROP TABLE IF EXISTS mod;') # 旧版 Mod 表数据直接丢弃，依靠重新扫描
            db.execute_sql('DROP TABLE IF EXISTS groupdata;')

            # 2.3 创建新表
            db.create_tables([
                ModAsset, GameProfile, UserModData, GroupData, GroupMod
            ], safe=True)
            game_install_path = ""
            game_data_path = ""
            if(hasattr(settings.config, 'game_install_path') and hasattr(settings.config, 'user_data_path')):
                game_install_path = settings.config.game_install_path or "" # type: ignore
                game_data_path = settings.config.user_data_path or "" # type: ignore
            # 2.4 初始化默认 Profile
            # 因为新版本必须有 Profile，迁移时自动创建一个
            if GameProfile.select().count() == 0:
                GameProfile.create(
                    id='default',
                    name='Default Profile',
                    game_install_path=game_install_path, # 防止 None 报错
                    user_data_path=game_data_path,
                    prefer_steam_launch=True,
                )

            # ---------------------------------------------------------
            # 第四步：注入数据
            # ---------------------------------------------------------

            # 4.1 注入 UserModData (包含原本的 + 为分组补全的)
            if user_data_map:
                data_list = list(user_data_map.values())
                # 分批插入
                for i in range(0, len(data_list), 100):
                    UserModData.insert_many(data_list[i:i+100]).execute()
                logger.info(f"成功迁移 {len(data_list)} 条 UserModData 记录")

            # 4.2 注入 GroupData
            if old_groups:
                GroupData.insert_many(old_groups).execute()
                logger.info(f"成功迁移 {len(old_groups)} 个分组")

            # 4.3 注入 GroupMod
            # 此时所有的 mod_id 都在 UserModData 里了，所以外键是安全的
            if old_group_mods:
                # 去重保护：防止旧数据里有重复的主键
                unique_gms = []
                seen_gms = set()
                for gm in old_group_mods:
                    key = (gm['group_id'], gm['mod_id'])
                    if key not in seen_gms:
                        unique_gms.append(gm)
                        seen_gms.add(key)

                for i in range(0, len(unique_gms), 100):
                    GroupMod.insert_many(unique_gms[i:i+100]).execute()
                logger.info(f"成功迁移 {len(unique_gms)} 条分组关联记录")

            # 恢复外键
            db.execute_sql('PRAGMA foreign_keys = ON;')

        logger.info("数据库架构迁移成功！")

    except Exception as e:
        import traceback
        logger.error(f"迁移失败: {traceback.format_exc()}")
        # 尽量不要在这里 raise，否则可能会导致外层 init_db 崩溃，导致程序无法启动。
        # 最好是记录错误，让程序以空库或半迁移状态启动，或者回滚 .bak
        raise e
    
def _3to4():
    """从版本 3 升级到版本 4
    将旧的 Integer 逻辑转换为新的 Boolean (Null) 逻辑
    旧: -1 (破坏), 0 (未知), 1 (不破坏)
    新: 1 (True, 破坏), NULL (None, 未知), 0 (False, 不破坏)
    """
    try:
        # 1. 检查字段是否存在
        columns = {f.name: f for f in db.get_columns('modasset')}
        if 'save_breaking' not in columns:
            logger.warning("字段 save_breaking 不存在，跳过迁移")
            return
        
        migrator = SqliteMigrator(db)

        with db.atomic(): # 使用事务确保原子性
            # 第一步：转换现有值为临时占位符（避开 NOT NULL 约束）
            # 逻辑：-1 -> 1(True), 1 -> 0(False), 0 -> 3(临时占位)
            db.execute_sql("""
                UPDATE modasset SET save_breaking = CASE 
                    WHEN save_breaking = -1 THEN 1 
                    WHEN save_breaking = 1  THEN 0 
                    WHEN save_breaking = 0  THEN 3 
                    ELSE save_breaking 
                END
                WHERE save_breaking IN (-1, 0, 1);
            """)

            # 第二步：利用 Migrator 移除 NOT NULL 约束
            # 在 SQLite 中，这会触发：创建新表 -> 拷贝数据 -> 替换旧表
            logger.info("正在重构表结构以移除 save_breaking 的 NOT NULL 约束...")
            migrate(migrator.drop_not_null('modasset', 'save_breaking'))

            # 第三步：将占位符 3 转换为真正的 NULL
            db.execute_sql("UPDATE modasset SET save_breaking = NULL WHERE save_breaking = 3;")
            
        logger.info("✅ 已完成 save_breaking 字段的数据迁移与结构更新")
        
    except Exception as e:
        logger.error(f"迁移 save_breaking 时出错: {e}")
        raise # 抛出异常以便上层回滚或停止升级

def _4to5():
    """从版本 4 升级到版本 5
    从旧表中移除字段 SubscribedCollection 的 need_download
    重构联锁机制：将 UserModData 中的 lock_previous_mod 和 lock_next_mod 双向链表
    提取并转换为全新的 ModInterlock 数组结构。
    """
    from playhouse.migrate import SqliteMigrator, migrate
    migrator = SqliteMigrator(db)
    
    # 数据处理 (Data Processing)
    try:
        # 获取最新的列名，确认应该往哪个列写
        # Peewee 的 ForeignKeyField 迁移后的实际列名通常是 "字段名_id"
        current_columns = [f.name for f in db.get_columns('usermoddata')]
        target_col = 'interlock_id_id' if 'interlock_id_id' in current_columns else 'interlock_id'

        # 防御性检查：确保旧字段还存在才提取数据
        if not ('lock_previous_mod' in current_columns and 'lock_next_mod' in current_columns):
            logger.info("旧版联锁字段已不存在，无需数据提取。")
            return
        
        cursor = db.execute_sql("SELECT mod_id, lock_previous_mod, lock_next_mod FROM usermoddata WHERE lock_previous_mod IS NOT NULL OR lock_next_mod IS NOT NULL;")
        rows = cursor.fetchall()
        
        if not rows:
            logger.info("未发现旧版联锁数据，跳过转换。")
        else:
            mod_map = {}
            for mod_id, prev_id, next_id in rows:
                mod_map[mod_id.lower()] = {
                    'prev': prev_id.lower() if prev_id else None,
                    'next': next_id.lower() if next_id else None
                }
                
            visited = set()
            chains = []
            for mod_id in list(mod_map.keys()):
                if mod_id in visited: continue
                
                curr = mod_id
                path_visited = set()
                while mod_map.get(curr) and mod_map[curr]['prev']:
                    prev_id = mod_map[curr]['prev']
                    if prev_id in path_visited: break
                    path_visited.add(prev_id)
                    curr = prev_id
                    
                head = curr
                chain = []
                curr = head
                path_visited = set()
                while curr:
                    if curr in path_visited: break
                    path_visited.add(curr)
                    chain.append(curr)
                    visited.add(curr)
                    curr = mod_map.get(curr, {}).get('next')
                    
                if len(chain) > 1:
                    chains.append(chain)
            
            # 批量写入
            with db.atomic():
                for chain in chains:
                    new_id = uuid.uuid4().hex
                    # 使用原生 SQL 插入序列，确保 JSONField 正确序列化
                    db.execute_sql("INSERT INTO modinterlock (id, chain) VALUES (?, ?);", (new_id, json.dumps(chain)))
                    # 使用正确的列名执行更新
                    placeholders = ', '.join(['?'] * len(chain))
                    sql = f"UPDATE usermoddata SET {target_col} = ? WHERE mod_id IN ({placeholders});"
                    db.execute_sql(sql, [new_id] + chain)
                
            logger.info(f"成功迁移 {len(chains)} 条联锁序列。")
            
    except Exception as e:
        logger.error(f"数据迁移阶段失败: {e}", exc_info=True)
        raise e

    # 清理旧字段
    try:
        with db.transaction():
            # 移除 UserModData 中的 lock_previous_mod 和 lock_next_mod
            columns = [f.name for f in db.get_columns('usermoddata')]
            if 'lock_previous_mod' in columns:
                migrate(migrator.drop_column('usermoddata', 'lock_previous_mod'))
            if 'lock_next_mod' in columns:
                migrate(migrator.drop_column('usermoddata', 'lock_next_mod'))
            
            # 移除 SubscribedCollection.need_download
            columns = [f.name for f in db.get_columns('subscribedcollection')]
            if 'need_download' in columns:
                logger.info("正在移除 need_download...")
                migrate(migrator.drop_column('subscribedcollection', 'need_download'))
        
        logger.info("已完成联锁机制数据结构升级")

    except Exception as e:
        logger.error(f"数据迁移阶段失败: {e}", exc_info=True)
        raise e




