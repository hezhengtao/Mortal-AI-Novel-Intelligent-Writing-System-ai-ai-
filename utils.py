

import streamlit as st
import os
import shutil
import base64
import time 
import csv 
import pandas as pd 
import streamlit.components.v1 as components
from config import THEMES 


try:
    from pyvis.network import Network
except ImportError:
    class MockNetwork:
        def __init__(self, *args, **kwargs): pass
        def save_graph(self, *args, **kwargs): pass
    Network = MockNetwork
    components = None


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "system_log.csv")

def ensure_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['time', 'action', 'details'])

def log_operation(action, details=""):
    """记录操作日志"""
    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    if 'operation_logs' not in st.session_state:
        st.session_state.operation_logs = []
    
    log_entry = {'time': current_time, 'action': action, 'details': details}
    st.session_state.operation_logs.append(log_entry)
    
    try:
        ensure_log_file()
        with open(LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([current_time, action, details])
    except Exception as e:
        print(f"日志写入失败: {e}")

# ==============================================================================
# 🛠️ 核心功能区域
# ==============================================================================

def save_avatar_file(uploaded_file, char_id):
    """🔥 修复：新增，用于保存角色头像文件"""
    if uploaded_file is None: return None
    
    # 确保存储目录存在
    save_dir = "static/avatars"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    try:
        file_ext = os.path.splitext(uploaded_file.name)[1]
        file_name = f"char_{char_id}_{int(time.time())}{file_ext}"
        file_path = os.path.join(save_dir, file_name)
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        return file_path
    except Exception as e:
        st.error(f"头像保存失败: {e}")
        return None

def reset_all_settings(db_mgr):
    try:
        for table in ["configs", "books", "volumes", "chapters", "characters", "plots"]:
            db_mgr.execute(f"DELETE FROM {table}")
        
        keys_to_reset = list(st.session_state.keys())
        for k in keys_to_reset:
            if k != 'db': del st.session_state[k]
            
        
        for p in ["logs", "projects/images", "html", "static/avatars"]:
            if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p): os.remove(p)
            
        st.success("数据已清除。")
        st.rerun()
    except Exception as e:
        st.error(f"失败: {e}")
        
def get_svg_uri(svg_str, color):
    svg_str = svg_str.replace("{COLOR}", color)
    b64 = base64.b64encode(svg_str.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64}"

def render_pyvis_graph(net, key):
    if components is None: return
    path = 'html'
    if not os.path.exists(path): os.makedirs(path)
    full_path = os.path.join(path, f'pyvis_chart_{key}.html')
    try:
        net.save_graph(full_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=620)
    except: pass


def get_theme_css():
    current_name = st.session_state.get('current_theme', '翡翠森林')
    theme_data = THEMES.get(current_name, list(THEMES.values())[0])
    primary = theme_data.get('primary', '#3eaf7c')
    primary_light = theme_data.get('primary_light', '#e8f5e9')
    custom_bg = theme_data.get('backgroundColor') or theme_data.get('bg_body')
    is_dark_mode = False
    
    if custom_bg:
        c_bg_app = custom_bg
        if c_bg_app.startswith('#') and len(c_bg_app) == 7:
             r, g, b = int(c_bg_app[1:3],16), int(c_bg_app[3:5],16), int(c_bg_app[5:7],16)
             is_dark_mode = (r*0.299 + g*0.587 + b*0.114) < 128
        c_bg_sidebar = theme_data.get('secondaryBackgroundColor', theme_data.get('nav_bg', '#1e1e1e' if is_dark_mode else '#f8f9fa'))
    else:
        keywords = ["夜", "黑", "暗", "Dark", "Night", "Black"]
        is_dark_mode = any(k in current_name for k in keywords) or (current_name == "🌃 永夜极光 (黑夜)")
        if is_dark_mode:
            c_bg_app = "#0e0e0e"; c_bg_sidebar = "#151515"
        else:
            c_bg_app = "#ffffff"; c_bg_sidebar = "#fcfcfc"

    if is_dark_mode:
        c_text_main = theme_data.get('text_body', "#e0e0e0") 
        c_text_input = theme_data.get('text_input', "#ffffff")
        c_bg_input = theme_data.get('input_bg', "#1e1e1e")
        c_border = theme_data.get('border', "#333333")
        c_btn_text_default = "white"
        bg_highlight = "rgba(255,255,255,0.05)" 
    else:
        c_text_main = theme_data.get('text_body', "#333333")
        c_text_input = theme_data.get('text_input', "#000000")
        c_bg_input = theme_data.get('input_bg', "#ffffff")
        c_border = theme_data.get('border', "#e0e0e0")
        c_btn_text_default = "white"
        bg_highlight = primary_light

    c_btn_text = theme_data.get('btn_text', c_btn_text_default)
    try: p_r, p_g, p_b = int(primary[1:3],16), int(primary[3:5],16), int(primary[5:7],16)
    except: p_r, p_g, p_b = 66, 185, 131

    css = f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Ma+Shan+Zheng&display=swap');
        :root {{ --primary-color: {primary} !important; --text-color: {c_text_main} !important; --background-color: {c_bg_app} !important; --secondary-background-color: {c_bg_sidebar} !important; accent-color: {primary} !important; }}
        .stApp {{ background-color: {c_bg_app} !important; }}
        [data-testid="stSidebar"] {{ background-color: {c_bg_sidebar} !important; border-right: 1px solid {c_border} !important; }}
        .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp span, .stApp div, .stApp li, .stApp label {{ color: {c_text_main} !important; }}
        .stApp a {{ color: {primary} !important; }}
        ::selection {{ background: {primary} !important; color: #fff !important; }}
        [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] {{ background-color: {c_bg_input} !important; border: 1px solid {c_border} !important; border-radius: 8px !important; box-shadow: none !important; }}
        [data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"]:focus-within {{ border-color: {primary} !important; box-shadow: 0 0 0 1px {primary} !important; outline: none !important; }}
        input[type="text"], input[type="password"], input[type="number"], textarea {{ background-color: transparent !important; border: none !important; box-shadow: none !important; outline: none !important; color: {c_text_input} !important; caret-color: {primary} !important; min-height: 100% !important; }}
        [data-baseweb="base-input"] button {{ background-color: transparent !important; border: none !important; box-shadow: none !important; }}
        [data-baseweb="input"] > div, [data-baseweb="base-input"] > div {{ background-color: transparent !important; border: none !important; }}
        [data-baseweb="select"] > div:first-child {{ background-color: {c_bg_input} !important; border-color: {c_border} !important; }}
        [data-baseweb="popover"], [data-baseweb="menu"] {{ background-color: {c_bg_input} !important; border: 1px solid {c_border} !important; }}
        [data-baseweb="popover"] li[role="option"]:hover, [data-baseweb="popover"] li[role="option"][aria-selected="true"] {{ background-color: {primary} !important; color: white !important; }}
        div[data-baseweb="select"] div {{ background-color: transparent !important; color: {c_text_main} !important; }}
        [data-baseweb="tag"] {{ background-color: {bg_highlight} !important; border: none !important; color: {c_text_main} !important; }}
        [data-baseweb="tag"] span {{ color: {c_text_main} !important; }}
        [data-baseweb="tag"] svg {{ fill: {c_text_main} !important; }}
        [data-baseweb="select"] svg {{ fill: {c_text_main} !important; }}
        button[kind="primary"], [data-testid="baseButton-primary"] {{ background-color: {primary} !important; border-color: {primary} !important; color: {c_btn_text} !important; }}
        [data-testid="stFormSubmitButton"] > button {{ background-color: {primary} !important; border-color: {primary} !important; color: {c_btn_text} !important; }}
        [data-testid="stFormSubmitButton"] > button:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important; opacity: 0.9 !important; }}
        button[kind="primary"]:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important; opacity: 0.9 !important; }}
        button[kind="secondary"], [data-testid="baseButton-secondary"] {{ background-color: transparent !important; border: 1px solid {c_border} !important; color: {c_text_main} !important; }}
        button[kind="secondary"]:hover {{ border-color: {primary} !important; color: {primary} !important; background-color: rgba({p_r}, {p_g}, {p_b}, 0.1) !important; }}
        [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-child[aria-checked="true"], [data-testid="stCheckbox"] [aria-checked="true"] {{ background-color: {primary} !important; border-color: {primary} !important; }}
        [data-testid="stRadio"] div[role="radiogroup"] > div[aria-checked="true"] > div:first-child {{ background-color: {primary} !important; border-color: {primary} !important; }}
        [data-baseweb="toggle"] [data-checked="true"] {{ background-color: {primary} !important; }}
        [data-baseweb="slider"] div[role="slider"] {{ background-color: {primary} !important; }}
        [data-baseweb="slider"] div[data-testid="stTickBar"] + div {{ background-color: {primary} !important; }}
        [data-baseweb="tab-highlight"] {{ background-color: {primary} !important; }}
        [data-testid="stHeader"], [data-testid="stToolbar"], .stDeployButton, [data-testid="InputInstructions"], .st-emotion-cache-16idsys p {{ display: none !important; }}
        .sidebar-header {{ font-family: 'Ma Shan Zheng', cursive !important; font-size: 48px; color: {primary} !important; text-align: center; margin-top: 10px; margin-bottom: 20px; }}
        [data-testid="stAlert"] {{ background-color: {bg_highlight} !important; border: none !important; color: {c_text_main} !important; }}
        [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {{ color: {c_text_main} !important; }}
        [data-testid="stAlert"] svg {{ fill: {primary} !important; color: {primary} !important; }}
    </style>
    """
    return css

def nav_callback(key):
    st.session_state.current_menu = key


def get_sidebar_stats(db_mgr):
    """
    获取侧边栏实时统计数据 (仅当前书籍)
    """
    try:
        # 1. 实时会话消耗 (仅本次运行)
        cost = st.session_state.token_tracker.get('cost', 0.0)
        
        # 2. 当前书籍信息
        current_book_id = st.session_state.get('current_book_id')
        current_book_title = "未选书籍"
        total_chapters = 0
        total_words = 0
        total_volumes = 0
        
        if current_book_id:
            # 标题
            res = db_mgr.query("SELECT title FROM books WHERE id=?", (current_book_id,))
            if res:
                current_book_title = res[0]['title']
            
            # 统计当前书的章节数和字数
            stats_res = db_mgr.query("""
                SELECT count(c.id) as c, sum(length(c.content)) as w 
                FROM chapters c 
                JOIN volumes v ON c.volume_id = v.id 
                WHERE v.book_id = ?
            """, (current_book_id,))
            
            if stats_res:
                total_chapters = stats_res[0]['c'] if stats_res[0]['c'] else 0
                total_words = stats_res[0]['w'] if stats_res[0]['w'] else 0
                
            # 统计当前书的卷数
            vol_res = db_mgr.query("SELECT count(*) as c FROM volumes WHERE book_id=?", (current_book_id,))
            if vol_res:
                total_volumes = vol_res[0]['c']
        
        # 格式化字数 (k/w)
        if total_words > 10000:
            words_display = f"{total_words/10000:.1f}万"
        else:
            words_display = f"{total_words}"

        return {
            "title": current_book_title,
            "cost": f"¥{cost:.2f}",
            "volumes": total_volumes,
            "chapters": total_chapters,
            "words": words_display
        }
    except Exception as e: 
        print(f"Monitor Error: {e}")
        return {
            "title": "N/A", "cost": "0.00", "volumes": 0, "chapters": 0, "words": "0"
        }

def render_sidebar():
    collapsed = st.session_state.get('sidebar_collapsed', False)
    current_name = st.session_state.get('current_theme', '翡翠森林')
    theme_data = THEMES.get(current_name, list(THEMES.values())[0])
    primary = theme_data.get('primary', '#3eaf7c')
    btn_text_color = theme_data.get('btn_text', 'white')
    p_hex = primary.lstrip('#')
    try: rgb = tuple(int(p_hex[i:i+2], 16) for i in (0, 2, 4))
    except: rgb = (62, 175, 124)
    primary_rgb_str = f"{rgb[0]}, {rgb[1]}, {rgb[2]}"

    svg_hamburger_raw = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 18L20 18" stroke="{COLOR}" stroke-width="2.5" stroke-linecap="round"/><path d="M4 12L20 12" stroke="{COLOR}" stroke-width="2.5" stroke-linecap="round"/><path d="M4 6L20 6" stroke="{COLOR}" stroke-width="2.5" stroke-linecap="round"/></svg>"""
    uri_icon = get_svg_uri(svg_hamburger_raw, primary)

    st.markdown(f"""<style>[data-testid="stSidebarNav"] {{ display: none !important; }} .st-key-sidebar_expand button, .st-key-sidebar_collapse button {{ border: none !important; background-color: transparent !important; background-image: url('{uri_icon}') !important; background-repeat: no-repeat !important; background-position: center !important; background-size: 24px !important; width: 40px !important; height: 40px !important; padding: 0 !important; color: transparent !important; box-shadow: none !important; }} .st-key-sidebar_expand button:hover, .st-key-sidebar_collapse button:hover {{ background-color: rgba({primary_rgb_str}, 0.1) !important; transform: scale(1.1); }} .st-key-sidebar_collapse button {{ transform: rotate(90deg); }} .st-key-sidebar_collapse button:hover {{ transform: rotate(90deg) scale(1.1); }} [data-testid="stSidebar"] button[kind="secondary"] {{ border: 1px solid transparent !important; text-align: left !important; padding-left: 20px !important; }} [data-testid="stSidebar"] button[kind="secondary"]:hover {{ border-color: {primary} !important; color: {primary} !important; background-color: rgba({primary_rgb_str}, 0.1) !important; }} [data-testid="stSidebar"] button[kind="primary"] {{ background-color: {primary} !important; border-color: {primary} !important; color: {btn_text_color} !important; font-weight: bold !important; box-shadow: 0 2px 5px rgba(0,0,0,0.2) !important; }} </style>""", unsafe_allow_html=True)

    with st.container():
        if collapsed:
            if st.button(" ", key="sidebar_expand", help="展开", use_container_width=True):
                st.session_state.sidebar_collapsed = False
                st.rerun()
        else:
            c_menu, _ = st.columns([0.25, 0.75]) 
            with c_menu:
                if st.button(" ", key="sidebar_collapse", help="收起", use_container_width=True): 
                    st.session_state.sidebar_collapsed = True
                    st.rerun()
            st.markdown(f"<div class='sidebar-header'>凡人</div>", unsafe_allow_html=True)

        menus = [("dashboard", "📊", "数据看板"),("books", "📚", "书籍管理"),("write", "✍️", "沉浸写作"),("idea", "💡", "灵感模式"),("chapters", "📑", "章节架构"),("chars", "👥", "角色管理"),("knowledge", "🧠", "拆书知识"),("settings", "⚙️", "系统设置"),("donate", "💰", "捐赠支持")]
        for key, icon, label in menus:
            is_active = (st.session_state.current_menu == key)
            btn_label = icon if collapsed else f"{icon}  {label}"
            btn_type = "primary" if is_active else "secondary"
            st.button(btn_label, key=f"nav_{key}", use_container_width=True, type=btn_type, on_click=nav_callback, args=(key,))

        
        if not collapsed:
            stats = get_sidebar_stats(st.session_state.db)
            
           
            st.markdown(f"""
            <div style='background-color:rgba({primary_rgb_str}, 0.06); padding:12px; border-radius:8px; margin-top:15px; border:1px solid rgba({primary_rgb_str}, 0.15);'>
                <div style='color:{primary}; font-weight:700; margin-bottom:10px; font-size:13px; border-bottom:1px dashed rgba({primary_rgb_str}, 0.3); padding-bottom:6px; line-height: 1.4; word-wrap: break-word; overflow-wrap: break-word;'>
                    📖 {stats['title']}
                </div>
                <div style='display: flex; flex-direction: column; gap: 8px; color: {primary}; opacity: 0.9;'>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='opacity:0.8; font-size:12px;'>✒️ 当前字数</span>
                        <span style='font-weight:600; font-size:13px;'>{stats['words']}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='opacity:0.8; font-size:12px;'>📑 当前章数</span>
                        <span style='font-weight:600; font-size:13px;'>{stats['chapters']}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='opacity:0.8; font-size:12px;'>📚 当前卷数</span>
                        <span style='font-weight:600; font-size:13px;'>{stats['volumes']}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; align-items: center;'>
                        <span style='opacity:0.8; font-size:12px;'>💰 会话消耗</span>
                        <span style='font-weight:600; font-size:13px;'>{stats['cost']}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        else:
             st.markdown(f"""<div style='margin-top:10px; text-align:center; font-size:10px; color:{primary}; border-top:1px solid rgba(0,0,0,0.1); padding-top:5px;'><div title='当前书籍'>📖</div><div style='margin-top:4px;' title='字数'>✒️</div></div>""", unsafe_allow_html=True)

def render_header(icon, title):
    current_name = st.session_state.get('current_theme', '翡翠森林')
    theme = THEMES.get(current_name, list(THEMES.values())[0])
    primary = theme.get('primary', '#3eaf7c')
    grad_a = theme.get('grad_a', primary)
    grad_b = theme.get('grad_b', '#888')
    st.markdown(f"""<div style='display:flex;align-items:center; padding-bottom:10px; margin-bottom:20px; margin-top:0px;'><span style='font-size:36px;margin-right:15px; filter: drop_shadow(0 4px 6px rgba(0,0,0,0.1));'>{icon}</span><span class='grad-text' style='background: linear-gradient(135deg, {grad_a}, {grad_b}); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 32px; font-weight: 800;'>{title}</span></div>""", unsafe_allow_html=True)

def render_fixed_top_header(): pass

def render_reading_modal(chap_id, db_mgr):
    current_name = st.session_state.get('current_theme', '翡翠森林')
    theme = THEMES.get(current_name, list(THEMES.values())[0])
    primary = theme.get('primary', '#3eaf7c')
    chap = db_mgr.query("SELECT c.title, c.content, v.name as vol_name FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE c.id=?", (chap_id,))
    if not chap: return
    chap = chap[0]
    modal = st.empty()
    with modal:
        st.markdown(f"""<div style='position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); backdrop-filter: blur(5px); z-index: 2000; display: flex; justify-content: center; align-items: center;'><div style='background: white; padding: 40px; border-radius: 20px; width: 800px; max-width: 90%; max-height: 85vh; overflow-y: auto; box-shadow: 0 20px 50px rgba(0,0,0,0.2);'><div style='display: flex; justify-content: space-between; align-items: center; margin-bottom:20px;'><h3 style='margin: 0; color: {primary}; font-weight:700;'>📖 {chap['vol_name']} - {chap['title']}</h3></div><div style='white-space: pre-wrap; line-height: 1.8; color: #333; font-size: 17px; font-family: "Georgia", serif;'>{chap['content'].replace('\\n', '<br>') or '章节内容为空'}</div><div style='text-align: right; margin-top: 30px;'><button id="close_modal" style='padding: 10px 24px; background-color: {primary}; color: white; border: none; border-radius: 20px; cursor: pointer; font-weight:600; box-shadow: 0 4px 12px rgba(0,0,0,0.15);'>关闭阅读</button></div></div></div>""", unsafe_allow_html=True)
        if st.button("❌ 关闭预览", key="close_read_modal", help="隐藏按钮", type="secondary"):
            st.session_state.reading_chapter_id = None
            st.rerun()

def update_chapter_title_db(chap_id, new_title_key):
    new_title = st.session_state[new_title_key]
    if new_title:
        st.session_state.db.execute("UPDATE chapters SET title=? WHERE id=?", (new_title, chap_id))
        st.session_state.chapter_title_cache[chap_id] = new_title
        st.session_state.rerun_flag = True

def update_chapter_summary_db(chap_id, new_summary_key):
    new_summary = st.session_state[new_summary_key]
    st.session_state.db.execute("UPDATE chapters SET summary=? WHERE id=?", (new_summary, chap_id))

def resequence_chapters(db_mgr, volume_id):
    chaps = db_mgr.query("SELECT id FROM chapters WHERE volume_id=? ORDER BY sort_order", (volume_id,))
    for index, chap in enumerate(chaps):
        db_mgr.execute("UPDATE chapters SET sort_order=? WHERE id=?", (index + 1, chap['id']))

def resequence_volumes(db_mgr, book_id):
    vols = db_mgr.query("SELECT id FROM volumes WHERE book_id=? ORDER BY sort_order", (book_id,))
    for index, vol in enumerate(vols):
        db_mgr.execute("UPDATE volumes SET sort_order=? WHERE id=?", ((index + 1) * 100, vol['id']))

def move_item_in_db(db_mgr, table, item_id, direction):
    pk = 'id'
    context_key = 'book_id' if table == 'volumes' else 'volume_id'
    item = db_mgr.query(f"SELECT * FROM {table} WHERE {pk}=?", (item_id,))
    if not item: return
    item = item[0]
    current_order = item['sort_order']
    context_id = item[context_key]
    sort_op = '<' if direction == 'up' else '>'
    sort_dir = 'DESC' if direction == 'up' else 'ASC'
    target_item_query = f"SELECT {pk}, sort_order FROM {table} WHERE {context_key}=? AND sort_order {sort_op} ? ORDER BY sort_order {sort_dir} LIMIT 1"
    target_item_res = db_mgr.query(target_item_query, (context_id, current_order))
    if not target_item_res: return 
    target_item = target_item_res[0]
    target_id = target_item[pk]
    target_order = target_item['sort_order']
    db_mgr.execute(f"UPDATE {table} SET sort_order=? WHERE {pk}=?", (target_order, item_id))
    db_mgr.execute(f"UPDATE {table} SET sort_order=? WHERE {pk}=?", (current_order, target_id))
    if table == 'chapters': resequence_chapters(db_mgr, context_id)
    elif table == 'volumes': resequence_volumes(db_mgr, context_id)
    st.session_state.rerun_flag = True

def generate_chapter_content(db_mgr, chap_id):
    c_res = db_mgr.query("SELECT * FROM chapters WHERE id=?", (chap_id,))
    if not c_res: return ""
    c = c_res[0]
    return f"### {c['title']}\n\n{c['content'] or ''}"

def generate_export_content_from_ids(db_mgr, chap_ids):
    if not chap_ids: return ""
    sql = """SELECT c.title, c.content FROM chapters c JOIN volumes v ON c.volume_id = v.id WHERE c.id IN ({}) ORDER BY v.sort_order, c.sort_order""".format(','.join(map(str, chap_ids)))
    rows = db_mgr.query(sql)
    content = ""
    for row in rows:
        content += f"\n### {row['title']}\n\n{row['content'] or ''}\n"
    return content.strip()

def generate_book_content(db_mgr, book_id):
    b_res = db_mgr.query("SELECT * FROM books WHERE id=?", (book_id,))
    if not b_res: return ""
    b = b_res[0]
    content = f"《{b['title']}》\n作者：{b['author']}\n简介：{b['intro']}\n\n"
    vols = db_mgr.query("SELECT * FROM volumes WHERE book_id=? ORDER BY sort_order", (book_id,))
    for v in vols:
        content += f"\n=== {v['name']} ===\n"
        if v['summary']: content += f"（卷摘要：{v['summary']}）\n"
        chaps = db_mgr.query("SELECT * FROM chapters WHERE volume_id=? ORDER BY sort_order", (v['id'],))
        for ch in chaps:
            content += f"\n### {ch['title']}\n\n{ch['content'] or ''}\n"
    return content