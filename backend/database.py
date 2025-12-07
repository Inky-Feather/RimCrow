import sqlite3
import json
import os
import time

DB_PATH = 'rim_manager.db'

class DatabaseManager:
    '''管理 RimModManager 的 SQLite 数据库连接和操作'''
    def __init__(self):
        # check_same_thread=False 允许跨线程调用，但必须管理好 cursor
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row # 让查询结果可以通过列名访问
        self.init_db()

    def init_db(self):
        '''初始化数据库表结构'''
        cursor = self.conn.cursor()
        # 开启 WAL 模式 (Write-Ahead Logging)，大幅提升并发读写性能
        cursor.execute('PRAGMA journal_mode=WAL;') 
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mods (
                package_id TEXT PRIMARY KEY,
                workshop_id TEXT,
                name TEXT,
                alias TEXT,
                version TEXT,
                supported_versions TEXT, -- JSON list
                author TEXT,
                description TEXT,
                notes TEXT,
                tags TEXT, -- JSON list
                preview_path TEXT,
                gallery_paths TEXT, -- JSON list
                dependencies TEXT, -- JSON list
                load_after TEXT, -- JSON list
                load_before TEXT, -- JSON list
                url TEXT,
                path TEXT,
                previous TEXT,
                next TEXT,
                mod_type TEXT, -- 'Workshop', 'Local', 'Other'
                file_created_time REAL,
                file_modified_time REAL,
                last_active_time REAL,
                last_moved_time REAL
            )
        ''')
        self.conn.commit()
        cursor.close()

    def get_table_columns(self, table_name='mods'):
        """获取表的字段列表，用于验证列名有效性"""
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row['name'] for row in cursor.fetchall()]
        cursor.close()
        return columns

    def get_mod_mtime_by_id(self, package_id):
        """获取数据库中记录的文件修改时间，用于增量更新对比"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT file_modified_time FROM mods WHERE package_id = ?', (package_id,))
        row = cursor.fetchone()
        cursor.close()
        return row['file_modified_time'] if row else 0
    
    def get_all_mods_mtimes(self):
        """一次性获取所有 Mod 的修改时间，用于快速增量比对"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT package_id, file_modified_time FROM mods')
        result = {row['package_id']: row['file_modified_time'] for row in cursor.fetchall()}
        cursor.close()
        return result

    def get_all_mods_path(self):
        """一次性获取所有 Mod 的文件路径，用于快速差异比对"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT package_id, path FROM mods')
        result = {row['package_id']: row['path'] for row in cursor.fetchall()}
        cursor.close()
        return result
    
    def get_all_mods(self, columns='*', order_by='name'):
        """
        动态获取模组数据
        :param columns: 字符串 (如 "name, package_id") 或 "*"
        """
        cursor = self.conn.cursor()
        
        # 1. 验证列名安全性 (防止 SQL 注入)
        valid_columns = self.get_table_columns()
        select_clause = "*"
        
        if columns != '*':
            # 移除空格并分割
            req_cols = [c.strip() for c in columns.split(',')]
            # 过滤出有效列
            safe_cols = [c for c in req_cols if c in valid_columns]
            if not safe_cols:
                print("警告：未提供有效的列，正在使用 *")
            else:
                select_clause = ', '.join(safe_cols)
        
        # 2. 执行查询
        sql = f'SELECT {select_clause} FROM mods ORDER BY {order_by} COLLATE NOCASE'
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        # 3. 获取当前查询结果的列名 (用于字典映射)
        # cursor.description 返回 (name, type_code, ...)
        col_names = [desc[0] for desc in cursor.description]
        
        mods = []
        for row in rows:
            # 将 sqlite3.Row 或 tuple 转为字典
            d = dict(zip(col_names, row))
            
            # 4. 智能 JSON 解析
            # 不再依赖硬编码列表，而是遍历所有字段，尝试解析看起来像 list/dict 的字符串
            for key, value in d.items():
                if isinstance(value, str):
                    stripped = value.strip()
                    # 简单的启发式检查：如果以 [ 或 { 开头和结尾，尝试解析
                    if (stripped.startswith('[') and stripped.endswith(']')) or \
                       (stripped.startswith('{') and stripped.endswith('}')):
                        try:
                            d[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            # 解析失败则保留原字符串
                            pass
                    # 如果是 None，转为空字符串或空列表? 视情况而定，这里保持 None 或转空
                    
            mods.append(d)
            
        cursor.close()
        return mods

    def upsert_mod(self, mod_data):
        """插入或更新 Mod，使用 named placeholders 提高可读性"""
        cursor = self.conn.cursor()
        
        # 转换列表为 JSON 字符串
        json_fields = ['supported_versions', 'tags', 'gallery_paths', 'dependencies', 'load_after', 'load_before']
        for field in json_fields:
            if field in mod_data and isinstance(mod_data[field], list):
                mod_data[field] = json.dumps(mod_data[field])
            elif field not in mod_data:
                mod_data[field] = '[]'

        # 补全默认字段防止报错
        defaults = {
            'workshop_id':'', 'alias': '', 'notes': '', 'url': '', 'mod_type': '',
            'file_created_time': 0, 'file_modified_time': 0, 
            'last_active_time': 0, 'last_moved_time': 0,
            'preview_path': '', 'version': '', 'previous': '', 'next': ''
        }
        for k, v in defaults.items():
            if k not in mod_data:
                mod_data[k] = v

        sql = '''
            INSERT OR REPLACE INTO mods (
                package_id, workshop_id, name, alias, version, supported_versions,
                author, description, notes, tags, preview_path, gallery_paths,
                dependencies, load_after, load_before, url, path, mod_type, previous, next,
                file_created_time, file_modified_time, last_active_time, last_moved_time
            ) VALUES (
                :package_id, :workshop_id, :name, :alias, :version, :supported_versions,
                :author, :description, :notes, :tags, :preview_path, :gallery_paths,
                :dependencies, :load_after, :load_before, :url, :path, :mod_type, :previous, :next,
                :file_created_time, :file_modified_time, :last_active_time, :last_moved_time
            )
        '''
        try:
            cursor.execute(sql, mod_data)
            self.conn.commit()
        except Exception as e:
            print(f"Database error on {mod_data.get('package_id')}: {e}")
        finally:
            cursor.close()

    def upsert_fields_by_id(self, package_id, fields):
        """更新字段，fields 是一个字典，支持多字段更新"""
        if not fields: return
        
        cursor = self.conn.cursor()
        
        # 1. 验证列名安全性
        valid_columns = self.get_table_columns()
        set_clauses = []
        params = {}
        
        for key, value in fields.items():
            if key in valid_columns:
                set_clauses.append(f"{key} = :{key}")
                params[key] = value
        
        if not set_clauses:
            print("Warning: No valid fields to update.")
            return
        
        params['package_id'] = package_id
        set_clause_str = ', '.join(set_clauses)
        
        sql = f'UPDATE mods SET {set_clause_str} WHERE package_id = :package_id'
        
        try:
            cursor.execute(sql, params)
            self.conn.commit()
        except Exception as e:
            print(f"Database error on updating {package_id}: {e}")
        finally:
            cursor.close()
        
    def save_mods_batch(self, mods_list):
        """
        【核心优化】批量插入/更新
        开启一个事务，处理所有数据，最后只 Commit 一次。
        """
        if not mods_list:
            return

        cursor = self.conn.cursor()
        try:
            # 显式开启事务
            cursor.execute("BEGIN TRANSACTION")
            
            sql = '''
                INSERT OR REPLACE INTO mods (
                    package_id, workshop_id, name, alias, version, supported_versions,
                    author, description, notes, tags, preview_path, gallery_paths,
                    dependencies, load_after, load_before, url, path, mod_type, previous, next,
                    file_created_time, file_modified_time, last_active_time, last_moved_time
                ) VALUES (
                    :package_id, :workshop_id, :name, :alias, :version, :supported_versions,
                    :author, :description, :notes, :tags, :preview_path, :gallery_paths,
                    :dependencies, :load_after, :load_before, :url, :path, :mod_type, :previous, :next,
                    :file_created_time, :file_modified_time, :last_active_time, :last_moved_time
                )
            '''
            
            # 处理数据预处理（JSON序列化等）
            processed_list = []
            defaults = {
                'workshop_id':'', 'alias': '', 'notes': '', 'url': '', 'mod_type': 'Unknown',
                'file_created_time': 0, 'file_modified_time': 0, 
                'last_active_time': 0, 'last_moved_time': 0,
                'preview_path': '', 'version': 'Unknown'
            }
            
            json_fields = ['supported_versions', 'tags', 'gallery_paths', 'dependencies', 'load_after', 'load_before']

            for mod in mods_list:
                # 浅拷贝一份防止修改原数据
                data = mod.copy()
                # 补全默认值
                for k, v in defaults.items():
                    if k not in data:
                        data[k] = v
                # JSON 序列化
                for field in json_fields:
                    if field in data and isinstance(data[field], list):
                        data[field] = json.dumps(data[field])
                    else:
                        data[field] = '[]'
                processed_list.append(data)

            # 批量执行 (executemany 比循环 execute 快得多)
            cursor.executemany(sql, processed_list)
            
            # 提交事务 (Only ONCE)
            self.conn.commit()
            print(f"数据库：已成功批量更新 {len (processed_list)} 个模组信息。")
            
        except Exception as e:
            self.conn.rollback() # 出错回滚
            print(f"数据库批处理错误: {e}")
        finally:
            cursor.close()

    def cleanup_removed_mods(self):
        """
        清理数据库中路径已不存在的模组
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT package_id, path FROM mods')
        rows = cursor.fetchall()
        
        ids_to_delete = []
        for row in rows:
            path = row['path']
            # 检查路径是否存在
            if not path or not os.path.exists(path):
                ids_to_delete.append(row['package_id'])
        
        if ids_to_delete:
            print(f"从数据库中清理 {len (ids_to_delete)} 个已移除的模组信息...")
            # 批量删除
            # sql placeholder 需要根据列表长度生成 (?,?,?)
            placeholders = ','.join(['?'] * len(ids_to_delete))
            sql = f'DELETE FROM mods WHERE package_id IN ({placeholders})'
            try:
                cursor.execute(sql, tuple(ids_to_delete))
                self.conn.commit()
                print("Cleanup complete.")
            except Exception as e:
                print(f"Cleanup error: {e}")
        else:
            print("数据库清理：未移除任何模组。")
        
        cursor.close()

    
    