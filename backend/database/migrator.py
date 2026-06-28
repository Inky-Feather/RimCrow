# backend/database/migrator.py
from playhouse.migrate import SqliteMigrator, migrate
from backend.database.models import GameProfile, GroupData, GroupMod, ModAsset, UserModData, db, SystemInfo
from backend.utils.logger import logger 
from backend.settings import settings

def run_migrations(old_version):
    migrator = SqliteMigrator(db)
    
    # 策略：根据旧版本号，一级一级往上爬
    
    if old_version == "2":
        _2to3(old_version)
        old_version = "3"

    # 情况 2: 从版本 2 升级到版本 3 ... (以此类推)
    # if old_version == "2":
    #     ...
    
    # 最后更新版本号
    SystemInfo.update(value=old_version).where(SystemInfo.key == 'db_version').execute()
    
    
def _2to3(old_version):
    """
    数据库迁移主函数
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

        # 1.2 提取 UserModData
        old_user_data = []
        try:
            cursor = db.execute_sql("SELECT * FROM usermoddata;")
            # 注意：需要根据旧表的列顺序读取，假设旧表: mod_id(FK), alias_name, notes, tags, sign_color...
            # 建议通过描述获取列名
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                # 旧版外键在数据库里通常存为 mod_id_id (Peewee 默认)
                # 我们将其转换回新版 CharField 格式的 mod_id (存 package_id)
                pkg_id = item.get('mod_id_id') or item.get('mod_id')
                if pkg_id:
                    item['mod_id'] = pkg_id.lower()
                    # 移除旧版可能存在的、新版模型没有的干扰键
                    item.pop('mod_id_id', None)
                    old_user_data.append(item)
        except Exception as e:
            logger.warning(f"读取旧 UserModData 失败: {e}")

        # 1.3 提取分组数据
        old_groups = []
        try:
            cursor = db.execute_sql("SELECT * FROM groupdata;")
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                old_groups.append(dict(zip(columns, row)))
        except Exception as e:
            logger.warning(f"读取旧 GroupData 失败: {e}")

        # 1.4 提取分组与 Mod 的关系
        old_group_mods = []
        try:
            cursor = db.execute_sql("SELECT * FROM groupmod;")
            columns = [description[0] for description in cursor.description]
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                pkg_id = item.get('mod_id_id') or item.get('mod_id')
                if pkg_id:
                    item['mod_id'] = pkg_id.lower()
                    item.pop('mod_id_id', None)
                    old_group_mods.append(item)
        except Exception as e:
            logger.warning(f"读取旧 GroupMod 失败: {e}")

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
            db.execute_sql('DROP TABLE IF EXISTS mod;')
            db.execute_sql('DROP TABLE IF EXISTS groupdata;')

            # 2.3 创建新表
            db.create_tables([
                ModAsset, GameProfile, UserModData, GroupData, GroupMod
            ], safe=True)

            # 2.4 初始化默认 Profile
            # 因为新版本必须有 Profile，迁移时自动创建一个
            if GameProfile.select().count() == 0:
                GameProfile.create(
                    id='default',
                    name='Default Profile',
                    game_install_path=settings.config.game_install_path, # 留给后续扫描补全
                    user_data_path=settings.config.user_data_path,
                )

            # ---------------------------------------------------------
            # 第三步：注入转换后的数据
            # ---------------------------------------------------------
            
            # 用于记录实际插入成功的 ID，用于过滤脏数据
            valid_mod_ids = set()
            valid_group_ids = set()

            # 3.1 注入 UserModData
            if old_user_data:
                unique_user_data = []
                seen_ids = set()
                for d in old_user_data:
                    # 确保 mod_id 存在且不重复
                    if d['mod_id'] and d['mod_id'] not in seen_ids:
                        unique_user_data.append(d)
                        seen_ids.add(d['mod_id'])
                        valid_mod_ids.add(d['mod_id']) # 记录有效ID
                
                if unique_user_data:
                    # 分批插入防止 SQL 语句过长
                    for i in range(0, len(unique_user_data), 100):
                        UserModData.insert_many(unique_user_data[i:i+100]).execute()

            # 3.2 注入 GroupData
            if old_groups:
                for g in old_groups:
                    # 记录有效的 Group ID (注意：GroupData主键是 group_id)
                    if g.get('group_id'):
                        valid_group_ids.add(g['group_id'])
                GroupData.insert_many(old_groups).execute()

            # 3.3 注入 GroupMod (关键修复点)
            if old_group_mods:
                clean_group_mods = []
                skipped_count = 0
                
                for gm in old_group_mods:
                    mod_id = gm.get('mod_id')
                    group_id = gm.get('group_id')
                    
                    # 【核心修复】：只有当 mod_id 和 group_id 都存在于刚才插入的新表中时，才保留这条关系
                    if mod_id in valid_mod_ids and group_id in valid_group_ids:
                        clean_group_mods.append(gm)
                    else:
                        skipped_count += 1
                
                if skipped_count > 0:
                    logger.warning(f"迁移过程中清理了 {skipped_count} 条无效的分组关联记录(脏数据)。")

                if clean_group_mods:
                    # 同样建议分批插入
                    for i in range(0, len(clean_group_mods), 100):
                        GroupMod.insert_many(clean_group_mods[i:i+100]).execute()

            # 恢复外键
            db.execute_sql('PRAGMA foreign_keys = ON;')

        logger.info("数据库架构迁移成功！")

    except Exception as e:
        import traceback
        logger.error(f"迁移失败: {traceback.format_exc()}")
        raise e