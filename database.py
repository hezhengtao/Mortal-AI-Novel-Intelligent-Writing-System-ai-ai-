# mortal_write/database.py

import sqlite3
import os
import time
from PIL import Image
# 确保 path_utils.py 存在于同级目录
from path_utils import load_workspace_config

# --- 1. 动态获取数据目录 ---
# 模块加载时尝试读取一次，但后续可能会变，所以这只是初始值
DATA_DIR = load_workspace_config()

# 辅助函数：获取最新的数据库路径
def get_db_path():
    # 重新从全局变量获取，或者再次读取配置确保最新
    if DATA_DIR:
        return os.path.join(DATA_DIR, "mortal_write.db")
    # 如果全局变量为空，尝试重新读取
    latest_path = load_workspace_config()
    if latest_path:
        return os.path.join(latest_path, "mortal_write.db")
    return None

class DatabaseManager:
    """管理 SQLite 数据库连接和操作"""
    def __init__(self, db_file=None):
        # 🔥 核心修复：优先使用传入的 db_file
        # 如果未传入，则动态根据当前的 DATA_DIR 构建路径，而不是使用可能过期的模块级变量
        if db_file:
            self.db_file = db_file
        else:
            self.db_file = get_db_path()
        
        # 再次检查：如果是首次运行，可能模块变量还没更新
        if not self.db_file:
            # 尝试重新加载一次配置（防御性编程）
            global DATA_DIR
            DATA_DIR = load_workspace_config()
            self.db_file = get_db_path()

        if not self.db_file:
            raise ValueError("数据库路径未初始化！请先配置工作区。")
            
        # 自动初始化目录结构（如果是首次运行且刚刚配置好）
        self._ensure_directories()

        # check_same_thread=False 允许 Streamlit 多线程访问
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
        self.migrate_tables() 
        
    def _ensure_directories(self):
        """确保所有必要的子目录存在"""
        # 重新获取最新的 DATA_DIR
        current_data_dir = DATA_DIR or load_workspace_config()
        
        if current_data_dir:
            if not os.path.exists(current_data_dir):
                 try: os.makedirs(current_data_dir, exist_ok=True)
                 except: pass
                 
            # 创建子目录列表
            sub_dirs = ["images", "knowledge", "logs", "ideas", "projects", "html", "exports", "relations"]
            for sub in sub_dirs:
                path = os.path.join(current_data_dir, sub)
                if not os.path.exists(path):
                    try: os.makedirs(path, exist_ok=True)
                    except: pass

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

        cursor.execute('''CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, role TEXT, gender TEXT, 
            race TEXT, 
            desc TEXT, avatar TEXT, is_major BOOLEAN DEFAULT 0
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER, name TEXT, desc TEXT, 
            type TEXT, status TEXT, importance INTEGER DEFAULT 0, content TEXT,
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
        
        # 定义需要检查的列及其类型
        cols = [
            ("books", "updated_at", "TIMESTAMP"),
            ("volumes", "part_id", "INTEGER"),
            ("characters", "race", "TEXT"),
            ("characters", "desc", "TEXT"),
            ("characters", "is_major", "BOOLEAN DEFAULT 0"),
            ("characters", "avatar", "TEXT"),
            ("plots", "content", "TEXT")
        ]
        
        for table, col, type_ in cols:
            try: 
                # 尝试查询该列，如果报错说明列不存在
                cursor.execute(f"SELECT {col} FROM {table} LIMIT 1")
            except: 
                try:
                    # 添加列
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_}")
                    self.conn.commit()
                except Exception as e:
                    print(f"Migrate Warning ({table}.{col}): {e}")

        cursor.close()
            
    def update_book_timestamp(self, book_id):
        if book_id:
            try:
                self.execute("UPDATE books SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (book_id,))
            except: pass
        
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
    """保存头像到用户选择的数据目录下的 images 文件夹"""
    try:
        if uploaded_file is None: return None
        
        # 确保获取最新的 DATA_DIR
        current_data_dir = DATA_DIR or load_workspace_config()
        if not current_data_dir: return None 
        
        # 简单校验
        if hasattr(uploaded_file, 'type') and uploaded_file.type.startswith('image/'):
            save_dir = os.path.join(current_data_dir, "images")
            if not os.path.exists(save_dir): 
                os.makedirs(save_dir)
            
            # 重新定位文件指针
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            
            file_name = f"char_{char_id}_{int(time.time())}.png"
            save_path = os.path.join(save_dir, file_name)
            img.save(save_path, 'PNG')
            return save_path
        return None
    except Exception as e:
        print(f"Error saving avatar: {e}")
        return None
