# mortal_write/main.py

import streamlit as st
import os
import pandas as pd
import time
import json
import urllib.parse
import sys

# ==========================================
# 1. 核心修复：工作区动态注入
# ==========================================
# 必须在导入 views 之前执行，确保所有模块使用同一个数据目录
def resolve_workspace_path():
    """解析真实的工作区路径"""
    target_path = None
    
    # A. 优先检查 URL 参数 (run.py 传递)
    try:
        query_params = st.query_params
        if "workspace" in query_params:
            val = query_params["workspace"]
            # 兼容处理: Streamlit 不同版本 query_params 行为差异
            url_path = val if isinstance(val, str) else val[0]
            decoded = urllib.parse.unquote(url_path)
            if decoded and os.path.exists(decoded):
                target_path = decoded
    except: pass

    # B. 其次检查配置文件 (run.py 生成的 workspace_config.json)
    if not target_path:
        # main.py 通常在 mortal_write 目录，config 可能在上一级(根目录)或同级
        app_root = os.path.dirname(os.path.abspath(__file__))
        possible_configs = [
            os.path.join(app_root, 'workspace_config.json'),           # 同级
            os.path.join(os.path.dirname(app_root), 'workspace_config.json') # 上一级
        ]
        
        for cfg_path in possible_configs:
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        p = data.get('workspace_path')
                        if p and os.path.exists(p):
                            target_path = p; break
                except: pass
    
    return target_path

# 获取目标路径
WORKSPACE_PATH = resolve_workspace_path()

# ==========================================
# 2. 动态 Patch Config 模块
# ==========================================
import config  # 先导入模块对象

if WORKSPACE_PATH:
    # 🔥 核心操作：强制修改 config 模块中的全局变量
    # 这样后续所有 import config 的模块都会看到这个新路径
    config.DATA_DIR = WORKSPACE_PATH
    config.DB_FILE = os.path.join(WORKSPACE_PATH, "novels.db")
    
    # 确保目录存在
    if not os.path.exists(config.DATA_DIR):
        try: os.makedirs(config.DATA_DIR)
        except: pass
    
    # 🔥 核心修改：防止日志刷屏
    # 检查 session_state，只有当路径从未记录过或发生变化时才打印
    if 'last_workspace_log' not in st.session_state or st.session_state.last_workspace_log != config.DATA_DIR:
        print(f"🚀 [Main] Workspace switched to: {config.DATA_DIR}")
        st.session_state.last_workspace_log = config.DATA_DIR

else:
    # 同样防止默认路径的日志刷屏
    current_default = config.DATA_DIR
    if 'last_workspace_log' not in st.session_state or st.session_state.last_workspace_log != current_default:
        print(f"📂 [Main] Using default data dir: {current_default}")
        st.session_state.last_workspace_log = current_default

# ==========================================
# 3. 正常导入业务逻辑
# ==========================================
# 从(可能被修改过的) config 对象中提取变量
defaults = config.defaults
DB_FILE = config.DB_FILE
MODEL_MAPPING = config.MODEL_MAPPING
AVAILABLE_MODELS = config.AVAILABLE_MODELS
DATA_DIR = config.DATA_DIR

from database import DatabaseManager
from logic import LogicEngine, load_and_update_model_config
from utils import (get_theme_css, render_sidebar, render_reading_modal)
# 导入 Views 时，它们内部 import config 也会获取到上面修改后的 DATA_DIR
from views import (dashboard, books, writer, structure, characters, knowledge, idea, settings, donate)

st.set_page_config(
    page_title="凡人智能写作系统",
    page_icon="🗡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 4. 隐藏 Streamlit 右上角功能按钮
# ==========================================
st.markdown("""
    <style>
    /* 隐藏右上角汉堡菜单和 Deploy 按钮 */
    [data-testid="stToolbar"] {
        display: none !important;
        visibility: hidden !important;
    }
    [data-testid="stHeader"] {
        display: none !important;
        visibility: hidden !important;
    }
    .main .block-container {
        padding-top: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# 确保子目录存在 (基于最终确认的 DATA_DIR)
for d in ["logs", "pay", "projects/knowledge", "projects/images", "html", os.path.join(DATA_DIR, "relations")]:
    if not os.path.exists(d): 
        try: os.makedirs(d, exist_ok=True)
        except: pass

# 初始化 Session State
for k, v in defaults.items():
    if k not in st.session_state: 
        if k == 'current_theme' and v == "紫气东来 (默认)": st.session_state[k] = "紫气东来"
        elif k == 'batch_input_data' and v is None: st.session_state[k] = pd.DataFrame([{'序号': 1, '章节标题': '示例', '大纲/摘要': '...'}])
        else: st.session_state[k] = v

if 'sidebar_collapsed' not in st.session_state: st.session_state.sidebar_collapsed = False

# ==========================================
# 【核心修改点】数据库初始化与自动清理
# ==========================================
if 'db' not in st.session_state: 
    # 初始化数据库连接
    st.session_state.db = DatabaseManager(DB_FILE)
    
    # 🔥 自动执行一次数据清理
    # 这样每次 App 启动/重置时，会自动删除那些“没书的章节”和“没书的角色”
    # 确保数据看板的数字是 100% 准确的
    st.session_state.db.clean_orphaned_data()

engine = LogicEngine(st.session_state.db)

st.markdown(get_theme_css(), unsafe_allow_html=True)

# 处理 Rerun 标志
if st.session_state.rerun_flag:
    st.session_state.rerun_flag = False
    time.sleep(0.1)
    st.rerun()

# 布局渲染
if st.session_state.sidebar_collapsed: col_ratio = [0.6, 11]  
else: col_ratio = [1.5, 10.5]
c_nav, c_body = st.columns(col_ratio, gap="small")

with c_nav:
    render_sidebar()

with c_body:
    load_and_update_model_config(engine)
    
    # 阅读模式弹窗
    if st.session_state.reading_chapter_id:
        render_reading_modal(st.session_state.reading_chapter_id, st.session_state.db)
        st.stop() 

    # 获取当前数据上下文
    current_book = None
    if st.session_state.current_book_id:
        res = st.session_state.db.query("SELECT * FROM books WHERE id=?", (st.session_state.current_book_id,))
        if res: current_book = dict(res[0])
            
    current_chapter = None
    if st.session_state.current_chapter_id:
        chap_res = st.session_state.db.query("SELECT * FROM chapters WHERE id=?", (st.session_state.current_chapter_id,))
        if chap_res:
            current_chapter = dict(chap_res[0])
            current_chapter['title'] = st.session_state.chapter_title_cache.get(st.session_state.current_chapter_id, current_chapter['title'])

    # 路由
    menu = st.session_state.current_menu
    if menu == "dashboard": dashboard.render_dashboard(engine)
    elif menu == "books": books.render_books(engine)
    elif menu == "write": writer.render_writer(engine, current_book, current_chapter)
    elif menu == "idea": idea.render_idea(engine)
    elif menu == "chapters": structure.render_structure(engine, current_book)
    elif menu == "chars": characters.render_characters(engine, current_book)
    elif menu == "knowledge": knowledge.render_knowledge(engine, current_book, current_chapter)
    elif menu == "settings": settings.render_settings(engine)
    elif menu == "donate": donate.render_donate()