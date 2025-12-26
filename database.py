# mortal_write/database.py

import sqlite3
import os
import time
from PIL import Image

# 【修改】引入 config 模块本身，而不是直接引入变量
# 这样可以确保 main.py 中修改 config.DATA_DIR 后，这里能获取到最新值
import config 

class DatabaseManager:
    """管理 SQLite 数据库连接和操作"""
    def __init__(self, db_file):
        # check_same_thread=False 允许 Streamlit 多线程访问
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.migrate_tables() 

    def create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, author TEXT, genre TEXT, 
            intro TEXT, style_dna TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, summary TEXT, sort_order INTEGER
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS volumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, part_id INTEGER, 
            name TEXT, summary TEXT, sort_order INTEGER
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volume_id INTEGER, title TEXT, content TEXT, 
            summary TEXT, sort_order INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 完整表结构定义
        cursor.execute('''CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, role TEXT, gender TEXT, 
            race TEXT, 
            desc TEXT, avatar TEXT, is_major BOOLEAN,
            
            origin TEXT,            -- 出身
            profession TEXT,        -- 职业
            cheat_ability TEXT,     -- 金手指
            power_level TEXT,       -- 境界
            ability_limitations TEXT, -- 代价
            appearance_features TEXT, -- 外貌特征
            signature_sign TEXT,      -- 标志性物品
            relationship_to_protagonist TEXT, -- 与主角关系
            social_role TEXT,                 -- 社会角色
            debts_and_feuds TEXT              -- 恩仇
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, desc TEXT, content TEXT, 
            type TEXT, status TEXT, importance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, content TEXT, style_dna TEXT, source TEXT
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS configs (
            key TEXT PRIMARY KEY, value TEXT
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS book_categories (
            book_id INTEGER, category_id INTEGER,
            PRIMARY KEY (book_id, category_id)
        )''')
        
        self.conn.commit()
        cursor.close()

    def migrate_tables(self):
        """自动迁移旧数据库结构 - 修复版"""
        cursor = self.conn.cursor()
        
        # --- 辅助函数：安全检查列是否存在 ---
        def column_exists(table_name, column_name):
            try:
                # 查询表结构信息
                cursor.execute(f"PRAGMA table_info({table_name})")
                # info[1] 是列名字段
                columns = [info[1] for info in cursor.fetchall()] 
                return column_name in columns
            except Exception:
                return False

        # 1. 迁移 books 表
        if not column_exists("books", "updated_at"):
            try: cursor.execute("ALTER TABLE books ADD COLUMN updated_at TIMESTAMP")
            except: pass

        # 2. 迁移 volumes 表 (🔥 核心修复：防止 duplicate column name: part_id)
        if not column_exists("volumes", "part_id"):
            try: 
                cursor.execute("ALTER TABLE volumes ADD COLUMN part_id INTEGER")
                print("✅ 数据库迁移：已添加 volumes.part_id 列")
            except Exception as e: print(f"Migration error (volumes.part_id): {e}")

        # 3. 迁移 plots 表
        if not column_exists("plots", "content"):
            try: cursor.execute("ALTER TABLE plots ADD COLUMN content TEXT")
            except: pass
            
        if not column_exists("plots", "importance"):
            try: cursor.execute("ALTER TABLE plots ADD COLUMN importance INTEGER DEFAULT 0")
            except: pass

        # 4. 迁移 characters 表 (批量检查)
        new_char_cols = {
            "race": "TEXT", "desc": "TEXT", "is_major": "BOOLEAN DEFAULT 0", "avatar": "TEXT",
            "origin": "TEXT", "profession": "TEXT", "cheat_ability": "TEXT", "power_level": "TEXT",
            "ability_limitations": "TEXT", "appearance_features": "TEXT", "signature_sign": "TEXT",
            "relationship_to_protagonist": "TEXT", "social_role": "TEXT", "debts_and_feuds": "TEXT"
        }
        
        # 只有当 characters 表存在时才进行迁移检查
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters'")
        if cursor.fetchone():
            # 重新获取当前所有列，避免多次查询
            cursor.execute("PRAGMA table_info(characters)")
            existing_cols = {info[1] for info in cursor.fetchall()}
            
            for col, col_type in new_char_cols.items():
                if col not in existing_cols:
                    try: 
                        cursor.execute(f"ALTER TABLE characters ADD COLUMN {col} {col_type}")
                        print(f"✅ 数据库迁移：已添加 characters.{col} 列")
                    except: pass
        
        self.conn.commit()
        cursor.close()

    # ==========================================================
    # 【新增】核心修复功能：清理孤儿数据 & 彻底删除书籍
    # ==========================================================
    def clean_orphaned_data(self):
        """清理孤儿数据（没有对应书或卷的数据），解决数据看板虚高问题"""
        cursor = self.conn.cursor()
        try:
            # 1. 清理没有对应【卷】的章节
            cursor.execute("DELETE FROM chapters WHERE volume_id NOT IN (SELECT id FROM volumes)")
            deleted_chapters = cursor.rowcount
            
            # 2. 清理没有对应【书】的卷
            cursor.execute("DELETE FROM volumes WHERE book_id NOT IN (SELECT id FROM books)")
            deleted_volumes = cursor.rowcount

            # 3. 清理没有对应【书】的分卷
            cursor.execute("DELETE FROM parts WHERE book_id NOT IN (SELECT id FROM books)")
            
            # 4. 清理没有对应【书】的角色
            cursor.execute("DELETE FROM characters WHERE book_id NOT IN (SELECT id FROM books)")
            deleted_chars = cursor.rowcount
            
            # 5. 清理没有对应【书】的大纲
            cursor.execute("DELETE FROM plots WHERE book_id NOT IN (SELECT id FROM books)")
            
            # 6. 清理没有对应【书】的分类关联
            cursor.execute("DELETE FROM book_categories WHERE book_id NOT IN (SELECT id FROM books)")

            self.conn.commit()
            if deleted_chapters > 0 or deleted_volumes > 0 or deleted_chars > 0:
                print(f"🧹 [DB Clean] 已清理: {deleted_chapters}章, {deleted_volumes}卷, {deleted_chars}角色")
            return True
        except Exception as e:
            print(f"❌ 清理失败: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()

    def delete_book_fully(self, book_id):
        """彻底删除一本书及其所有关联数据（级联删除）"""
        cursor = self.conn.cursor()
        try:
            # 1. 删章节 (通过卷找到章节)
            cursor.execute("DELETE FROM chapters WHERE volume_id IN (SELECT id FROM volumes WHERE book_id=?)", (book_id,))
            
            # 2. 删卷和分卷
            cursor.execute("DELETE FROM volumes WHERE book_id=?", (book_id,))
            cursor.execute("DELETE FROM parts WHERE book_id=?", (book_id,))
            
            # 3. 删角色、大纲、分类关联
            cursor.execute("DELETE FROM characters WHERE book_id=?", (book_id,))
            cursor.execute("DELETE FROM plots WHERE book_id=?", (book_id,))
            cursor.execute("DELETE FROM book_categories WHERE book_id=?", (book_id,))
            
            # 4. 最后删书
            cursor.execute("DELETE FROM books WHERE id=?", (book_id,))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"删除书籍失败: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()
            
    def update_book_timestamp(self, book_id):
        self.execute("UPDATE books SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (book_id,))
        
    def query(self, sql, params=()):
        c = self.conn.cursor()
        try:
            c.execute(sql, params)
            return c.fetchall()
        except Exception as e:
            print(f"Query Error: {e} | SQL: {sql}")
            return []
        finally:
            c.close()

    def execute(self, sql, params=()):
        c = self.conn.cursor()
        try:
            c.execute(sql, params)
            self.conn.commit()
            return c.lastrowid
        except Exception as e:
            print(f"Execute Error: {e} | SQL: {sql}")
            raise e 
        finally:
            c.close()

    def close(self):
        self.conn.close()

def save_avatar_file(uploaded_file, char_id):
    """保存头像文件"""
    try:
        if uploaded_file is None: return None
        if hasattr(uploaded_file, 'type') and uploaded_file.type.startswith('image/'):
            img = Image.open(uploaded_file)
            try:
                img.verify() 
            except Exception:
                return None 
            
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            
            # 【修改】使用 config.DATA_DIR 动态获取路径
            images_dir = os.path.join(config.DATA_DIR, "images")
            if not os.path.exists(images_dir): 
                os.makedirs(images_dir)
                
            file_name = f"char_{char_id}_{int(time.time())}.png"
            save_path = os.path.join(images_dir, file_name)
            
            img.save(save_path, 'PNG')
            return save_path
        return None
    except Exception as e:
        print(f"Error saving avatar: {e}")
        return None