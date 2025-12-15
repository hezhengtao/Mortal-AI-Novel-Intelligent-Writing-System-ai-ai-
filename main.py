# mortal_write/main.py

import streamlit as st
import os
import pandas as pd
import time
import sys
import importlib 
import streamlit.components.v1 as components 

# ================= 0. 页面配置 =================
st.set_page_config(
    page_title="凡人智能写作系统",
    page_icon="🗡️",
    layout="wide",
    initial_sidebar_state="expanded" 
)

# 定义通信函数：向父窗口发送消息控制遮罩
def send_mask_signal(action):
    """
    action: 'show_mask' 或 'hide_mask'
    使用 window.top.postMessage 突破 iframe 跨域限制
    """
    js_code = f"""
    <script>
        try {{
            window.top.postMessage('{action}', '*');
        }} catch(e) {{
            console.log('Failed to send message:', e);
        }}
    </script>
    """
    components.html(js_code, height=0, width=0)

# ================= 1. 导入路径工具 =================
from path_utils import save_workspace_config, select_folder_dialog, reset_workspace_config, get_executable_dir
import database 

# 核心修复：每次运行前检查是否需要强制刷新数据目录
from path_utils import load_workspace_config
_disk_path = load_workspace_config()

if _disk_path and not database.DATA_DIR:
    importlib.reload(database) 
    if 'db' in st.session_state: del st.session_state['db']
    if 'engine' in st.session_state: del st.session_state['engine']
    st.rerun() 

# ================= 2. 启动引导页 =================
if not database.DATA_DIR:
    # 🛑 在引导页：强制显示遮罩
    send_mask_signal('show_mask')
    
    st.markdown("""
    <style>
    .big-title { font-size: 32px !important; font-weight: bold; color: #2e7d32; margin-bottom: 10px; text-align: center; }
    .sub-title { font-size: 16px; color: #666; margin-bottom: 40px; text-align: center; }
    .stButton button { width: 100%; border-radius: 8px; height: 50px; font-size: 18px; }
    </style>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="big-title">👋 欢迎使用凡人写作助手</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-title">您的私人 AI 写作助手</div>', unsafe_allow_html=True)
        
        st.info("这是您第一次运行，请选择一个文件夹用于存储所有数据。")
        
        default_path = os.path.join(get_executable_dir(), "MortalWrite_Data")
        if 'temp_selected_path' in st.session_state:
            current_val = st.session_state['temp_selected_path']
        else:
            current_val = default_path
            
        path_display = st.text_input("数据存储位置：", value=current_val)

        col_pick, col_conf = st.columns([1, 1], gap="medium")
        
        with col_pick:
            if st.button("📂 选择文件夹"):
                selected = select_folder_dialog()
                if selected:
                    st.session_state['temp_selected_path'] = selected
                    st.rerun()

        with col_conf:
            if st.button("✅ 确认并开始", type="primary"):
                target_path = path_display.strip()
                if not target_path:
                    st.error("路径不能为空")
                else:
                    try:
                        if not os.path.exists(target_path): os.makedirs(target_path)
                        save_workspace_config(target_path)
                        database.DATA_DIR = target_path
                        
                        st.success("初始化成功！正在进入...")
                        
                        # ⚠️ 修改：这里不再发送 hide_mask 信号
                        # 让遮罩保持显示，直到 Rerun 完成进入下方的主程序逻辑后再隐藏
                        # 这样可以盖住最后几秒的重载过程
                        
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"配置失败: {e}")
    
    st.stop() # 🛑 停止往下执行

# ================= 3. 主程序加载 =================

# ✅ 进入主程序：此时界面已准备好，发送信号隐藏遮罩
send_mask_signal('hide_mask')

from config import defaults
from logic import LogicEngine, load_and_update_model_config
from utils import get_theme_css, render_sidebar, render_reading_modal
from views import dashboard, books, writer, structure, characters, knowledge, idea, settings, donate

# 初始化数据库与引擎
if 'db' not in st.session_state:
    try:
        st.session_state.db = database.DatabaseManager()
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        from path_utils import reset_workspace_config
        if st.button("重置配置"):
            reset_workspace_config()
            st.rerun()
        st.stop()

engine = LogicEngine(st.session_state.db)
if 'engine' not in st.session_state:
    st.session_state.engine = engine

for k, v in defaults.items():
    if k not in st.session_state: 
        if k == 'batch_input_data' and v is None:
             st.session_state[k] = pd.DataFrame([{'序号': 1, '章节标题': '', '大纲/摘要': ''}])
        else:
             st.session_state[k] = v
if 'sidebar_collapsed' not in st.session_state: st.session_state.sidebar_collapsed = False

st.markdown(get_theme_css(), unsafe_allow_html=True)

if st.session_state.rerun_flag:
    st.session_state.rerun_flag = False
    time.sleep(0.1)
    st.rerun()

# 布局渲染
# 修改：稍微增加左侧导航栏的宽度比例，防止按钮换行 (1.5 -> 2)
col_ratio = [0.6, 11] if st.session_state.sidebar_collapsed else [2, 10]
c_nav, c_body = st.columns(col_ratio, gap="small")

with c_nav:
    render_sidebar()
    st.markdown("---")
    
    # 美化后的工作区设置
    with st.expander("⚙️ 工作区", expanded=False): 
        # 使用 st.code 显示路径，自动处理长文本，比 caption 更整洁
        st.code(database.DATA_DIR, language="text")
        
        # 修改：缩短按钮文字，增加图标，避免换行
        if st.button("🔄 切换目录", type="secondary", use_container_width=True): 
            reset_workspace_config()
            if 'db' in st.session_state: del st.session_state['db']
            importlib.reload(database)
            st.rerun() 

with c_body:
    load_and_update_model_config(engine)
    if st.session_state.reading_chapter_id:
        render_reading_modal(st.session_state.reading_chapter_id, st.session_state.db)
        st.stop()

    current_book = None
    if st.session_state.current_book_id:
        res = st.session_state.db.query("SELECT * FROM books WHERE id=?", (st.session_state.current_book_id,))
        if res: current_book = dict(res[0])
            
    current_chapter = None
    if st.session_state.current_chapter_id:
        res = st.session_state.db.query("SELECT * FROM chapters WHERE id=?", (st.session_state.current_chapter_id,))
        if res: current_chapter = dict(res[0])

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
