

import streamlit as st
import os
import pandas as pd
import time

# 1. 导入拆分后的核心模块
from config import defaults, DB_FILE, MODEL_MAPPING, AVAILABLE_MODELS
from database import DatabaseManager
from logic import LogicEngine, load_and_update_model_config
from utils import (
    get_theme_css, 
    render_sidebar, 
    render_reading_modal,
    reset_all_settings
)

# 2. 导入视图模块
from views import (
    dashboard, books, writer, structure, 
    characters, knowledge, idea, settings, donate
)

# ================= 全局配置 & 初始化 =================

st.set_page_config(
    page_title="凡人智能写作系统",
    page_icon="🗡️",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# 目录初始化
for d in ["logs", "pay", "projects/knowledge", "projects/images", "html"]:
    if not os.path.exists(d): 
        os.makedirs(d, exist_ok=True)

# 3. Session State 初始化
for k, v in defaults.items():
    if k not in st.session_state: 
        if k == 'current_theme' and v == "紫气东来 (默认)":
            st.session_state[k] = "紫气东来"
        elif k == 'batch_input_data' and v is None:
            st.session_state[k] = pd.DataFrame([
                {'序号': 1, '章节标题': '新章节标题 1', '大纲/摘要': '本章主要剧情点...'},
                {'序号': 2, '章节标题': '新章节标题 2', '大纲/摘要': '本章主要剧情点...'}
            ])
        else:
            st.session_state[k] = v

if 'sidebar_collapsed' not in st.session_state:
    st.session_state.sidebar_collapsed = False

# 4. 数据库与引擎初始化
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager(DB_FILE)
    
engine = LogicEngine(st.session_state.db)

# ================= UI 渲染 & 路由 =================

# 应用样式
st.markdown(get_theme_css(), unsafe_allow_html=True)

# 刷新检查
if st.session_state.rerun_flag:
    st.session_state.rerun_flag = False
    time.sleep(0.1)
    st.rerun()
    
# 🚀 布局调整：侧边栏折叠逻辑
if st.session_state.sidebar_collapsed:
    # 折叠：保持极窄
    col_ratio = [0.6, 11]  
else:
    # 展开：[1.5, 10.5] -> 窄侧边栏
    col_ratio = [1.5, 10.5]

# 使用 gap="small" 减少中间缝隙
c_nav, c_body = st.columns(col_ratio, gap="small")

with c_nav:
    render_sidebar()

with c_body:
    load_and_update_model_config(engine)
    
    if st.session_state.reading_chapter_id:
        render_reading_modal(st.session_state.reading_chapter_id, st.session_state.db)
        st.stop() 

    # 获取当前数据对象
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