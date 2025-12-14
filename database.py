

import sqlite3
import os
import time
from PIL import Image

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
            desc TEXT, avatar TEXT, is_major BOOLEAN
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, desc TEXT, 
            type TEXT, status TEXT,
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
        """自动迁移旧数据库结构"""
        cursor = self.conn.cursor()
        
        
        try: cursor.execute("SELECT updated_at FROM books LIMIT 1")
        except: 
            cursor.execute("ALTER TABLE books ADD COLUMN updated_at TIMESTAMP")
            self.conn.commit()

       
        try: cursor.execute("SELECT part_id FROM volumes LIMIT 1")
        except:
            cursor.execute("ALTER TABLE volumes ADD COLUMN part_id INTEGER")
            self.conn.commit()

        try: cursor.execute("SELECT race FROM characters LIMIT 1")
        except:
            cursor.execute("ALTER TABLE characters ADD COLUMN race TEXT")
            self.conn.commit()
            
       
        try: cursor.execute("SELECT desc FROM characters LIMIT 1")
        except:
            try: cursor.execute("ALTER TABLE characters ADD COLUMN desc TEXT")
            except: pass 
            self.conn.commit()

        
        try: cursor.execute("SELECT is_major FROM characters LIMIT 1")
        except:
            cursor.execute("ALTER TABLE characters ADD COLUMN is_major BOOLEAN DEFAULT 0")
            self.conn.commit()
            print("Database Migrated: Added is_major to characters.")

       
        try: cursor.execute("SELECT avatar FROM characters LIMIT 1")
        except:
            cursor.execute("ALTER TABLE characters ADD COLUMN avatar TEXT")
            self.conn.commit()
            print("Database Migrated: Added avatar to characters.")

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
    try:
        if uploaded_file is None: return None
        if hasattr(uploaded_file, 'type') and uploaded_file.type.startswith('image/'):
            img = Image.open(uploaded_file)
            img.verify()
            img = Image.open(uploaded_file)
            if not os.path.exists("projects/images"): os.makedirs("projects/images")
            file_name = f"char_{char_id}_{int(time.time())}.png"
            save_path = os.path.join("projects/images", file_name)
            img.save(save_path, 'PNG')
            return save_path
        return None
    except Exception as e:
        print(f"Error saving avatar: {e}")
        return None