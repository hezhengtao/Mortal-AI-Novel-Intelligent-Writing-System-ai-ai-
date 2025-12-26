# knowledge.py

import streamlit as st
import json
import os
import time
import base64
import html
import re
import csv
import uuid
import threading
from datetime import datetime
from utils import render_header, ensure_log_file # log_operation 已废弃

# 🔥 导入 OpenAI 类，以便在自定义模型解析中实例化
from logic import FEATURE_MODELS, MODEL_MAPPING, OpenAI
from config import DATA_DIR 

# ==============================================================================
# 🛡️ 严格审计日志系统 (Knowledge 集成版)
# ==============================================================================

SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_audit.csv")
_log_lock = threading.Lock()

def get_session_id():
    """获取或生成当前会话的唯一追踪ID"""
    if "session_trace_id" not in st.session_state:
        st.session_state.session_trace_id = str(uuid.uuid4())[:8]
    return st.session_state.session_trace_id

def log_audit_event(category, action, details, status="SUCCESS", module="KNOWLEDGE"):
    """
    执行严格的审计日志写入
    """
    try:
        os.makedirs(os.path.dirname(SYSTEM_LOG_PATH), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = get_session_id()
        
        status_map = {"SUCCESS": "成功", "WARNING": "警告", "ERROR": "错误"}
        status_cn = status_map.get(status, status)
        
        module_map = {
            "KNOWLEDGE": "知识库", 
            "CHARACTERS": "角色管理", 
            "BOOKS": "书籍管理", 
            "WRITER": "写作终端", 
            "SETTINGS": "系统设置"
        }
        module_cn = module_map.get(module, module)

        if isinstance(details, (dict, list)):
            try: details = json.dumps(details, ensure_ascii=False)
            except: details = str(details)
            
        row = [timestamp, session_id, module_cn, category, action, status_cn, details]
        
        with _log_lock:
            file_exists = os.path.exists(SYSTEM_LOG_PATH)
            with open(SYSTEM_LOG_PATH, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(SYSTEM_LOG_PATH) == 0:
                    writer.writerow(['时间', '会话ID', '模块', '类别', '操作', '状态', '详情']) 
                writer.writerow(row)
    except Exception as e:
        print(f"❌ 审计日志写入失败: {e}")

# ==============================================================================
#  基础配置 & CSS 样式注入
# ==============================================================================
THEME_COLOR = "#2e7d32"
THEME_LIGHT = "#e8f5e9"

# 设定分类映射
SETTING_TYPES = {
    "Universe": "🌌 宇宙观/物理法则",
    "Geography": "🏰 地理/地图/区域",
    "TimeHistory": "📜 历史/纪年/时间线",
    "PowerSystem": "📈 力量体系/超自然力",
    "PoliticalEconomy": "🚩 政治/经济/资源",
    "Technology": "⚙️ 科技/魔法水平",
    "MajorRaces": "🧬 主要种族/族群",
    "CultureLife": "🎭 文化/风俗/日常",
    "BeliefValue": "🧘 信仰/价值观/哲学",
    "Mysteries": "❓ 神秘禁忌/未解之谜",
    "Organization": "🛡️ 势力/宗门/组织",
    "Creature": "🐉 灵兽/怪物/异种",
    "Item": "⚔️ 物品/法宝/神器",
    "MagicSkill": "⚡ 功法/神通/技能",
    "Other": "📝 其他补充"
}

def inject_custom_css():
    st.markdown(f"""
    <style>
        [data-testid="stFileUploaderDropzone"] > div > div > span {{ display: none; }}
        [data-testid="stFileUploaderDropzone"] > div > div > small {{ display: none; }}
        [data-testid="stFileUploaderDropzone"] button {{ display: none; }}
        [data-testid="stFileUploaderDropzone"]::before {{
            content: "☁️ 拖放 TXT/PDF 文件至此";
            position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%);
            font-size: 16px; font-weight: bold; color: #555; pointer-events: none;
        }}
        [data-testid="stFileUploaderDropzone"] {{
            min-height: 100px; background-color: #f8f9fa; border: 1px dashed #ccc;
        }}
        .setting-tag {{
            display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px;
            background-color: {THEME_LIGHT}; color: {THEME_COLOR}; border: 1px solid {THEME_COLOR}; margin-right: 5px;
        }}
        .mention-highlight {{
            background-color: #fff3cd; padding: 0 2px; border-radius: 3px; font-weight: bold;
        }}
        /* 角色横幅 */
        .char-strip {{
            display: flex; gap: 15px; overflow-x: auto; padding: 10px 5px;
            margin-bottom: 15px; scrollbar-width: thin; border-bottom: 1px dashed #eee;
        }}
        .char-item {{
            display: flex; flex-direction: column; align-items: center;
            min-width: 60px; max-width: 70px; cursor: pointer;
        }}
        .char-img {{
            width: 50px; height: 50px; border-radius: 50%; object-fit: cover;
            border: 2px solid {THEME_LIGHT}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }}
        .char-img:hover {{ transform: scale(1.1); border-color: {THEME_COLOR}; }}
        .char-name {{ font-size: 11px; font-weight: bold; margin-top: 5px; color: #333; }}
        .char-role {{ font-size: 9px; color: #666; }}
    </style>
    """, unsafe_allow_html=True)

# --- 辅助函数 ---
def get_image_src(path_or_url):
    if not path_or_url: return None
    try:
        path_or_url = str(path_or_url).strip()
        if path_or_url.startswith("http") or path_or_url.startswith("data:"): 
            return path_or_url
        if os.path.exists(path_or_url):
            with open(path_or_url, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                ext = os.path.splitext(path_or_url)[1].lower().replace('.', '')
                mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}
                mime = mime_map.get(ext, 'image/png')
                return f"data:{mime};base64,{b64}"
    except Exception as e: 
        print(f"Image load error: {e}")
        return None
    return None

def update_book_timestamp_by_book_id(book_id):
    if book_id:
        try: st.session_state.db.update_book_timestamp(book_id)
        except: pass

def ensure_schema_compatibility(db_mgr):
    try:
        db_mgr.query("SELECT id FROM plots LIMIT 1")
    except:
        try:
            db_mgr.execute("""
                CREATE TABLE IF NOT EXISTS plots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    content TEXT,
                    status TEXT,
                    importance INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except: pass

def find_mentions_in_book(db_mgr, book_id, keyword):
    if not keyword or len(keyword.strip()) < 2: return []
    keyword = keyword.strip()
    results = []
    
    parts = db_mgr.query("SELECT id, name FROM parts WHERE book_id=?", (book_id,))
    for p in parts:
        vols = db_mgr.query("SELECT id, name FROM volumes WHERE part_id=?", (p['id'],))
        for v in vols:
            chaps = db_mgr.query("SELECT id, title, content FROM chapters WHERE volume_id=?", (v['id'],))
            for c in chaps:
                content = c['content'] or ""
                if keyword in content:
                    idx = content.find(keyword)
                    start = max(0, idx - 20)
                    end = min(len(content), idx + len(keyword) + 30)
                    snippet = content[start:end].replace(keyword, f"<span class='mention-highlight'>{keyword}</span>")
                    results.append({
                        "chap_title": f"{v['name']} - {c['title']}",
                        "snippet": snippet,
                        "count": content.count(keyword)
                    })
    return results

# ==============================================================================
# 🔥 新增：自定义模型解析器 (与 Books/Characters 模块保持一致)
# ==============================================================================
def _resolve_ai_client(engine, assigned_key):
    """
    智能解析客户端：支持原生模型 + 自定义模型(CUSTOM::)
    """
    # 1. 拦截自定义模型
    if assigned_key and str(assigned_key).startswith("CUSTOM::"):
        try:
            # 提取真实名称
            target_name = assigned_key.split("::", 1)[1]
            
            # 从数据库读取配置
            settings = engine.get_config_db("ai_settings", {})
            custom_list = settings.get("custom_model_list", [])
            
            # 查找匹配项
            for m in custom_list:
                if m.get("name") == target_name:
                    api_key = m.get("key")
                    base_url = m.get("base")
                    model_id = m.get("api_model")
                    
                    if not api_key or not base_url:
                        return None, None, None
                        
                    # 实例化 OpenAI (使用 logic 中导入的类)
                    client = OpenAI(api_key=api_key, base_url=base_url)
                    return client, model_id, "custom"
            
            print(f"❌ 未找到自定义模型配置: {target_name}")
            return None, None, None
        except Exception as e:
            print(f"❌ 自定义模型解析失败: {e}")
            return None, None, None

    # 2. 原生模型走默认逻辑
    return engine.get_client(assigned_key)

# ==============================================================================
# 核心渲染逻辑
# ==============================================================================

def render_knowledge(engine, current_book_arg, current_chapter):
    """渲染 知识库 & 设定集 页面"""
    inject_custom_css()
    db_mgr = st.session_state.db
    ensure_schema_compatibility(db_mgr)
    
    render_header("🧠", "世界设定 & 知识库")
    
    # --------------------------------------------------------------------------
    # 0. 独立书籍选择器 
    # --------------------------------------------------------------------------
    all_books = db_mgr.query("SELECT id, title FROM books ORDER BY updated_at DESC")
    
    if not all_books:
        st.warning("📚 暂无书籍。请先前往【书籍管理】创建一本新书。")
        return

    book_map = {b['title']: b['id'] for b in all_books}
    book_titles = list(book_map.keys())

    # 默认选中逻辑
    if "knowledge_local_sel" not in st.session_state:
        initial_title = book_titles[0]
        if current_book_arg and current_book_arg['title'] in book_titles:
            initial_title = current_book_arg['title']
        st.session_state["knowledge_local_sel"] = initial_title

    if st.session_state["knowledge_local_sel"] not in book_titles:
        st.session_state["knowledge_local_sel"] = book_titles[0]

    # 🔥 UI对齐优化：使用 vertical_alignment="center"
    c_sel, c_info = st.columns([2, 3], vertical_alignment="center")
    with c_sel:
        selected_title = st.selectbox(
            "📘 当前阅览书籍", 
            book_titles, 
            key="knowledge_local_sel" 
        )
        current_book_id = book_map[selected_title]
    
    with c_info:
        # 使用 Markdown 来微调样式，使其在视觉上更平衡
        st.info("💡 提示：AI 在写作时会自动查阅这些信息。")

    # --------------------------------------------------------------------------
    # Tab 页面渲染
    # --------------------------------------------------------------------------
    tab_lore, tab_extract, tab_transform = st.tabs(["🌍 世界设定集", "🧬 风格提炼", "🖋️ 风格改造"])
    
    # --------------------------------------------------------------------------
    # Tab 1: 世界设定集 (保持功能)
    # --------------------------------------------------------------------------
    with tab_lore:
        # === 顶部：角色快速概览 ===
        try:
            chars_query = db_mgr.query("SELECT * FROM characters WHERE book_id=? ORDER BY is_major DESC, id ASC", (current_book_id,))
            chars = [dict(c) for c in chars_query]
            
            if chars:
                html_parts = ['<div class="char-strip">']
                for c in chars:
                    try:
                        safe_name = html.escape(str(c.get('name') or "未知"))
                        safe_role = html.escape(str(c.get('role') or "配角"))
                        safe_desc = html.escape(str(c.get('desc') or ""))
                        img_src = get_image_src(c.get('avatar'))
                        
                        if not img_src:
                            letter = safe_name[0] if safe_name else "?"
                            img_elem = f"""<div style="width:50px;height:50px;border-radius:50%;background:{THEME_LIGHT};color:{THEME_COLOR};display:flex;align-items:center;justify-content:center;font-weight:bold;border:2px solid {THEME_LIGHT};">{letter}</div>"""
                        else:
                            img_elem = f"""<img src="{img_src}" class="char-img">"""
                        
                        html_parts.append(f"""<div class="char-item" title="{safe_name} ({safe_role}): {safe_desc}">{img_elem}<div class="char-name">{safe_name}</div><div class="char-role">{safe_role}</div></div>""")
                    except Exception as render_err:
                        continue
                html_parts.append('</div>')
                st.markdown("".join(html_parts), unsafe_allow_html=True)
            else:
                st.info("💡 该书籍暂无角色数据，请前往【角色档案】页面添加。")
        except Exception as char_query_err:
            chars = []
        
        # === 主体：设定管理 ===
        col_list, col_detail = st.columns([1.2, 2])
        
        with col_list:
            c_tools_1, c_tools_2 = st.columns(2)
            with c_tools_1: st.markdown("##### 📜 设定目录")
            with c_tools_2:
                with st.popover("📥 导入/共享", use_container_width=True):
                    st.markdown("**从其他书籍导入**")
                    other_books = [b for b in all_books if b['id'] != current_book_id]
                    if other_books:
                        imp_book_title = st.selectbox("选择来源", [b['title'] for b in other_books])
                        if st.button("开始导入"):
                            src_id = book_map[imp_book_title]
                            src_rows = db_mgr.query("SELECT content, status, importance FROM plots WHERE book_id=? AND status LIKE 'Setting_%'", (src_id,))
                            count = 0
                            for row_raw in src_rows:
                                row = dict(row_raw)
                                db_mgr.execute("INSERT INTO plots (book_id, content, status, importance) VALUES (?,?,?,?)", 
                                               (current_book_id, row['content'], row['status'], row['importance']))
                                count += 1
                            
                            # 🔥 审计：导入设定
                            log_audit_event("设定管理", "导入设定", {"来源书籍": imp_book_title, "条目数": count})
                            
                            st.toast(f"✅ 成功导入 {count} 条设定")
                            time.sleep(1); st.rerun()
                    else: st.caption("无其他书籍")

            book_info = db_mgr.query("SELECT intro FROM books WHERE id=?", (current_book_id,))
            book_intro = book_info[0]['intro'] if book_info else ""
            
            selection_map = {}
            st.caption("🤖 系统档案")
            if book_intro:
                key = "📚 书籍简介 & 标签"
                selection_map[key] = {"type": "sys_book", "content": book_intro}
                if st.button(key, use_container_width=True, type="secondary"): st.session_state['know_sel_key'] = key

            char_key = f"👥 角色档案管理 ({len(chars)})"
            selection_map[char_key] = {"type": "sys_chars", "data": chars}
            if st.button(char_key, use_container_width=True, type="secondary"): st.session_state['know_sel_key'] = char_key
            
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            
            st.caption("✍️ 手动设定集")
            if st.button("➕ 新建设定条目", use_container_width=True, type="primary"):
                st.session_state['know_sel_key'] = "新建条目"
            
            manual_settings = db_mgr.query("SELECT id, content, status FROM plots WHERE book_id=? AND status LIKE 'Setting_%' ORDER BY id DESC", (current_book_id,))
            
            if not manual_settings:
                st.markdown("<div style='color:#888; font-size:12px; margin-top:10px;'>暂无自定义设定<br>点击上方按钮添加</div>", unsafe_allow_html=True)
            
            type_keys_base = list(SETTING_TYPES.keys())
            grouped_settings = {k: [] for k in type_keys_base}
            
            for row in manual_settings:
                status = row['status']
                sType = status.split("Setting_")[1] if status.startswith("Setting_") else "Other"
                if sType not in SETTING_TYPES: sType = "Other" 
                
                f_content = row['content'] or ""
                raw_title = f_content.split('\n')[0].strip()
                # 列表显示时也清理一下标题
                clean_title = re.sub(r'^【.*?】', '', raw_title).strip()
                if not clean_title: clean_title = "未命名条目"
                if len(clean_title) > 20: clean_title = clean_title[:20] + "..."
                
                grouped_settings[sType].append({"id": row['id'], "title": clean_title, "content": f_content, "full_type": sType})

            for type_key, type_label in SETTING_TYPES.items():
                items = grouped_settings.get(type_key, [])
                if items:
                    expanded_default = type_key in ["Universe", "PowerSystem", "Geography"]
                    with st.expander(f"{type_label} ({len(items)})", expanded=expanded_default): 
                        for item in items:
                            btn_label = f"{item['title']}"
                            u_key = f"setting_{item['id']}"
                            selection_map[u_key] = {"type": "manual", "data": item}
                            if st.button(btn_label, key=f"btn_{u_key}", use_container_width=True):
                                st.session_state['know_sel_key'] = u_key

        with col_detail:
            sel_key = st.session_state.get('know_sel_key', "新建条目")
            if sel_key == "NEW_ENTRY": sel_key = "新建条目"
            
            if sel_key == "新建条目":
                st.subheader("➕ 新建设定")
                with st.form("new_setting"):
                    c_type, c_title = st.columns([1, 2])
                    type_opts = list(SETTING_TYPES.keys())
                    sel_type = c_type.selectbox("分类", type_opts, format_func=lambda x: SETTING_TYPES[x])
                    n_title = c_title.text_input("名称 (必填)", placeholder="例如：青云门、境界划分")
                    n_content = st.text_area("详细内容", height=300, placeholder="在此输入详细描述、规则、历史背景等...")
                    if st.form_submit_button("保存", type="primary", use_container_width=True):
                        if n_title and n_content:
                            db_mgr.execute("INSERT INTO plots (book_id, content, status, importance) VALUES (?, ?, ?, 0)", 
                                           (current_book_id, f"{n_title}\n{n_content}", f"Setting_{sel_type}"))
                            update_book_timestamp_by_book_id(current_book_id)
                            
                            # 🔥 审计：新建设定
                            log_audit_event("设定管理", "新建设定", {"分类": sel_type, "标题": n_title})
                            
                            st.toast("✅ 保存成功"); time.sleep(0.5); st.rerun()
                        else: st.error("请填写完整")

            elif sel_key in selection_map:
                data = selection_map[sel_key]
                
                # 系统档案/角色编辑
                if data['type'].startswith('sys'):
                    if data['type'] == "sys_book":
                        st.subheader("📚 书籍简介")
                        st.text_area("预览", value=data['content'], height=400, disabled=True)
                        
                    elif data['type'] == "sys_chars":
                        st.subheader("👥 角色档案编辑器")
                        
                        char_list = data.get('data', [])
                        if not char_list:
                            st.info("暂无角色，请在 AI 导入或架构生成中创建。")
                        else:
                            char_names = [f"{c['name']} ({c['role']})" for c in char_list]
                            sel_idx = 0
                            if 'last_edit_char_idx' in st.session_state and st.session_state.last_edit_char_idx < len(char_names):
                                sel_idx = st.session_state.last_edit_char_idx
                                
                            sel_char_str = st.selectbox("选择要编辑的角色", char_names, index=sel_idx, key="char_edit_sel")
                            
                            sel_char_idx = char_names.index(sel_char_str)
                            st.session_state.last_edit_char_idx = sel_char_idx
                            target_char = char_list[sel_char_idx]
                            
                            st.markdown(f"**正在编辑：{target_char['name']}**")
                            
                            with st.form(key=f"form_char_{target_char['id']}"):
                                with st.expander("📝 基础信息", expanded=True):
                                    c1, c2, c3 = st.columns(3)
                                    e_name = c1.text_input("姓名", value=target_char.get('name',''))
                                    e_role = c2.text_input("定位 (主角/反派/配角)", value=target_char.get('role',''))
                                    e_gender = c3.text_input("性别", value=target_char.get('gender',''))
                                    e_race = st.text_input("种族", value=target_char.get('race',''))

                                with st.expander("🏙️ 背景与身份", expanded=True):
                                    c1, c2 = st.columns(2)
                                    e_origin = c1.text_input("出身背景", value=target_char.get('origin','') or "")
                                    e_profession = c2.text_input("职业/天赋", value=target_char.get('profession','') or "")
                                    e_social = st.text_input("社会角色/地位", value=target_char.get('social_role','') or "")
                                    
                                with st.expander("⚔️ 能力与外挂", expanded=True):
                                    e_cheat = st.text_input("金手指/核心能力", value=target_char.get('cheat_ability','') or "")
                                    c1, c2 = st.columns(2)
                                    e_power = c1.text_input("当前境界/等级", value=target_char.get('power_level','') or "")
                                    e_limit = c2.text_input("能力代价/副作用", value=target_char.get('ability_limitations','') or "")
                                    
                                with st.expander("👀 形象与关系", expanded=True):
                                    e_look = st.text_area("外貌特征 (记忆点)", value=target_char.get('appearance_features','') or "", height=70)
                                    e_sign = st.text_input("标志性动作/口头禅", value=target_char.get('signature_sign','') or "")
                                    e_rel_mc = st.text_input("与主角关系", value=target_char.get('relationship_to_protagonist','') or "")
                                    e_feuds = st.text_area("恩仇与债务 (剧情钩子)", value=target_char.get('debts_and_feuds','') or "", height=70)

                                st.markdown("---")
                                e_desc = st.text_area("📜 综合简介 (AI 主要参考此字段)", value=target_char.get('desc',''), height=150, help="如果上方字段为空，AI 会尝试从这里提取信息。")

                                if st.form_submit_button("💾 保存角色修改", type="primary", use_container_width=True):
                                    db_mgr.execute("""
                                        UPDATE characters SET 
                                        name=?, role=?, gender=?, race=?, "desc"=?,
                                        origin=?, profession=?, social_role=?,
                                        cheat_ability=?, power_level=?, ability_limitations=?,
                                        appearance_features=?, signature_sign=?,
                                        relationship_to_protagonist=?, debts_and_feuds=?
                                        WHERE id=?
                                    """, (
                                        e_name, e_role, e_gender, e_race, e_desc,
                                        e_origin, e_profession, e_social,
                                        e_cheat, e_power, e_limit,
                                        e_look, e_sign,
                                        e_rel_mc, e_feuds,
                                        target_char['id']
                                    ))
                                    update_book_timestamp_by_book_id(current_book_id)
                                    
                                    # 🔥 审计：更新角色
                                    log_audit_event("角色档案", "更新角色详情", {"ID": target_char['id'], "姓名": e_name})
                                    
                                    st.toast(f"✅ 角色 {e_name} 更新成功！")
                                    time.sleep(0.5)
                                    st.rerun()

                # 手动设定编辑
                elif data['type'] == 'manual':
                    item = data['data']
                    f_text = item['content']
                    curr_title, curr_body = (f_text.split("\n", 1) + [""])[:2]
                    
                    # 🔥 [Logic 更新] 清洗旧数据中的英文标签 (如 【Geography】)，只显示纯标题
                    curr_title = re.sub(r'^【.*?】', '', curr_title).strip()
                    
                    st.subheader(f"📝 编辑：{curr_title}")
                    with st.expander("🔍 查找文中引用"):
                        if st.button("开始搜索", key=f"tk_{item['id']}"):
                            ms = find_mentions_in_book(db_mgr, current_book_id, curr_title)
                            if ms:
                                for m in ms: st.markdown(f"**{m['chap_title']}** ({m['count']}次)<br>...{m['snippet']}...", unsafe_allow_html=True)
                            else: st.warning("未找到引用")

                    with st.form(key=f"ed_{item['id']}"):
                        c_t, c_n = st.columns([1, 2])
                        curr_type = item['full_type']
                        try: idx = list(SETTING_TYPES.keys()).index(curr_type)
                        except ValueError: idx = 0 
                        
                        n_type = c_t.selectbox("分类", list(SETTING_TYPES.keys()), index=idx, format_func=lambda x: SETTING_TYPES[x])
                        n_title_val = c_n.text_input("名称", value=curr_title)
                        n_body_val = st.text_area("内容", value=curr_body, height=350)
                        
                        c_del, c_upd = st.columns([1, 1])
                        if c_del.form_submit_button("🗑️ 删除", type="secondary"):
                            db_mgr.execute("DELETE FROM plots WHERE id=?", (item['id'],))
                            
                            # 🔥 审计：删除设定
                            log_audit_event("设定管理", "删除设定", {"ID": item['id'], "标题": curr_title}, status="WARNING")
                            
                            st.session_state['know_sel_key'] = "新建条目"; st.rerun()
                        if c_upd.form_submit_button("💾 保存", type="primary"):
                            # 🔥 保存时也不带英文标签，保持数据纯净
                            db_mgr.execute("UPDATE plots SET content=?, status=? WHERE id=?", 
                                           (f"{n_title_val}\n{n_body_val}", f"Setting_{n_type}", item['id']))
                            update_book_timestamp_by_book_id(current_book_id)
                            
                            # 🔥 审计：更新设定
                            log_audit_event("设定管理", "更新设定", {"ID": item['id'], "标题": n_title_val, "分类": n_type})
                            
                            st.toast("✅ 更新成功"); time.sleep(0.5); st.rerun()

    # --------------------------------------------------------------------------
    # Tab 2: 风格提炼 (🔥 增加直接粘贴 & 进度条)
    # --------------------------------------------------------------------------
    with tab_extract:
        st.markdown("#### 📖 风格学习")
        st.info(f"ℹ️ 这里提炼的风格仅属于当前书籍《{selected_title}》。")
        
        # 分栏：文件上传 vs 直接粘贴
        t_mode = st.radio("输入方式", ["📂 上传文件 (TXT/PDF)", "📝 直接粘贴文本"], horizontal=True, label_visibility="collapsed")
        
        source_text = None
        source_name = None
        
        if t_mode == "📂 上传文件 (TXT/PDF)":
            up_file = st.file_uploader("上传参考文本", type=["txt", "docx", "pdf"], key="up_ex", label_visibility="collapsed")
            if up_file:
                try:
                    up_file.seek(0)
                    source_text = up_file.read().decode('utf-8', errors='ignore')[:15000]
                    source_name = up_file.name
                except Exception as e:
                    st.error(f"文件读取失败: {e}")
        else:
            paste_text = st.text_area("在此粘贴大神作品片段...", height=200, placeholder="粘贴 500-2000 字的精彩片段，让 AI 学习其文笔特征。")
            if paste_text.strip():
                source_text = paste_text[:15000]
                source_name = f"粘贴片段_{int(time.time())}"
        
        if st.button("🚀 开始提炼风格 DNA", type="primary", use_container_width=True):
            if source_text:
                # 🔥 修复：使用支持自定义模型的解析器
                # 原代码: client, model, _ = engine.get_client("knowledge_analyze")
                assigned_key = engine.get_config_db("model_assignments", {}).get("knowledge_analyze", FEATURE_MODELS["knowledge_analyze"]['default'])
                client, model, _ = _resolve_ai_client(engine, assigned_key)
                
                if client:
                    ensure_log_file()
                    
                    # 🔥 审计：启动风格提炼
                    log_audit_event("AI辅助", "启动风格提炼", {"源文本名": source_name, "文本长度": len(source_text)})
                    
                    # 🔥 进度条逻辑
                    progress_bar = st.progress(0, text="🚀 正在启动 AI 引擎...")
                    
                    try:
                        time.sleep(0.2)
                        progress_bar.progress(20, text="📖 正在深度阅读文本...")
                        
                        # 模拟分析进度 (因为 API 是阻塞的，只能模拟)
                        time.sleep(0.5)
                        progress_bar.progress(50, text="🧠 正在提取修辞、句式与情感特征...")
                        
                        res = engine.generate_style_analysis(source_text, client, model) 
                        
                        progress_bar.progress(85, text="💾 正在生成风格档案...")
                        
                        sn = res.get('style_name', f'风格_{int(time.time())}')
                        db_mgr.execute("INSERT INTO plots (book_id, content, status, importance) VALUES (?, ?, 'StyleDNA', 5)", (current_book_id, sn))
                        update_book_timestamp_by_book_id(current_book_id)
                        
                        progress_bar.progress(100, text="✅ 提炼完成！")
                        
                        # 🔥 审计：风格提炼成功
                        log_audit_event("AI辅助", "风格提炼完成", {"风格名称": sn})
                        
                        st.success(f"风格档案已保存：{sn}")
                        time.sleep(1); st.rerun()
                    except Exception as e: 
                        progress_bar.empty()
                        
                        # 🔥 审计：风格提炼失败
                        log_audit_event("AI辅助", "风格提炼失败", {"错误": str(e)}, status="ERROR")
                        
                        st.error(f"分析失败: {e}")
                else: st.error("未配置 AI 模型")
            else: st.error("请提供有效文本")
        
        st.divider()
        st.markdown("##### 🧬 当前书籍的风格库")
        styles = db_mgr.query("SELECT id, content FROM plots WHERE status='StyleDNA' AND book_id=? ORDER BY id DESC", (current_book_id,))
        if styles:
            for s in styles:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**🎨 {s['content']}**")
                if c2.button("🗑️", key=f"ds_{s['id']}"):
                    db_mgr.execute("DELETE FROM plots WHERE id=?", (s['id'],))
                    
                    # 🔥 审计：删除风格
                    log_audit_event("AI辅助", "删除风格", {"ID": s['id'], "内容": s['content']}, status="WARNING")
                    
                    st.rerun()
        else: st.info("📭 暂无数据。请上传大神作品（如金庸小说片段）来提取风格。")

    # --------------------------------------------------------------------------
    # Tab 3: 风格改造 (🔥 修复功能缺失)
    # --------------------------------------------------------------------------
    with tab_transform:
        st.markdown("#### 💡 风格重写 (全局可用)")
        
        c_ch, c_st = st.columns([1.5, 1])
        
        # 1. 选择章节 (可选)
        parts = db_mgr.query("SELECT id FROM parts WHERE book_id=?", (current_book_id,))
        chap_opts = {"(不使用章节，直接粘贴)": {"id": None, "content": ""}}
        
        for p in parts:
            vols = db_mgr.query("SELECT id, name FROM volumes WHERE part_id=?", (p['id'],))
            for v in vols:
                chaps = db_mgr.query("SELECT id, title, content FROM chapters WHERE volume_id=?", (v['id'],))
                for c in chaps: 
                    label = f"{c['title']}"
                    chap_opts[label] = {"id": c['id'], "content": c['content']}
        
        chap_keys = list(chap_opts.keys())
        # 尝试选中当前阅读的章节
        default_idx = 0
        if current_chapter and current_chapter.get('title') in chap_keys:
            default_idx = chap_keys.index(current_chapter['title'])
            
        sel_ch = c_ch.selectbox("1. 导入来源 (可选)", chap_keys, index=default_idx)
        
        t_id = chap_opts[sel_ch]['id']
        t_content_db = chap_opts[sel_ch]['content']
        
        # 2. 选择风格
        avail_styles = db_mgr.query("SELECT DISTINCT content FROM plots WHERE status='StyleDNA'")
        s_list = sorted(list(set([s['content'] for s in avail_styles]))) + ["通用大神优化"]
        sel_style = c_st.selectbox("2. 选择目标风格", s_list)
        
        # 3. 输入框 (🔥 永远显示，如果有章节内容则预填充)
        st.caption("待重写内容 (可手动修改):")
        input_content = st.text_area("input_rewrite", value=t_content_db, height=200, label_visibility="collapsed", placeholder="在此输入或粘贴需要重写的段落...")
        
        # 4. 按钮 (🔥 永远显示)
        # 5. 输出结果 (🔥 新增文本框显示)
        
        c_act, c_res = st.columns([1, 2])
        
        with c_act:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🪄 开始重写 ➤", type="primary", use_container_width=True):
                if not input_content.strip():
                    st.warning("⚠️ 请先输入内容")
                else:
                    # 🔥 修复：使用支持自定义模型的解析器
                    # 原代码: client, model, _ = engine.get_client("knowledge_style_gen")
                    assigned_key = engine.get_config_db("model_assignments", {}).get("knowledge_style_gen", FEATURE_MODELS["knowledge_style_gen"]['default'])
                    client, model, _ = _resolve_ai_client(engine, assigned_key)
                    
                    if client:
                        ensure_log_file()
                        
                        # 🔥 审计：启动重写
                        log_audit_event("AI辅助", "启动风格重写", {"目标风格": sel_style, "字数": len(input_content)})
                        
                        progress_text = "✨ AI 正在挥毫泼墨..."
                        my_bar = st.progress(0, text=progress_text)
                        
                        try:
                            # 模拟进度
                            for i in range(30):
                                time.sleep(0.02); my_bar.progress(i + 1, text=progress_text)

                            p = f"请模仿【{sel_style}】的文笔风格对以下文本进行润色重写。保留原意，但提升文学性。" if "通用" not in sel_style else "请优化文笔节奏，使其更具文学性。"
                            
                            stream = client.chat.completions.create(
                                model=model, messages=[{"role": "user", "content": f"{p}\n\n【原文】：\n{input_content}"}], stream=True
                            )
                            
                            full_res = ""
                            res_box = st.empty() # 占位
                            
                            for chunk in stream:
                                if chunk.choices[0].delta.content:
                                    full_res += chunk.choices[0].delta.content
                                    # 实时更新 session 以便渲染
                                    st.session_state['last_trans'] = full_res
                            
                            my_bar.progress(100, text="✅ 重写完成！")
                            
                            # 🔥 审计：重写完成
                            log_audit_event("AI辅助", "风格重写完成", {"输出字数": len(full_res)})
                            
                            time.sleep(0.5); my_bar.empty()
                            st.rerun() # 刷新以显示结果在下方文本框
                            
                        except Exception as e:
                            # 🔥 审计：重写失败
                            log_audit_event("AI辅助", "风格重写失败", {"错误": str(e)}, status="ERROR")
                            st.error(f"AI 调用错误: {e}")
                    else: st.error("未配置 AI 模型")

            # 保存按钮
            if t_id and 'last_trans' in st.session_state:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 覆盖原章节", type="secondary", use_container_width=True, help="将右侧结果保存回当前章节"):
                    db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (st.session_state['last_trans'], t_id))
                    
                    # 🔥 审计：保存重写
                    log_audit_event("内容编辑", "保存重写内容", {"章节ID": t_id, "长度": len(st.session_state['last_trans'])})
                    
                    st.toast("✅ 已保存至章节！")
                    time.sleep(1)

        with c_res:
            st.caption("重写结果 (可直接复制):")
            res_val = st.session_state.get('last_trans', "")
            st.text_area("output_rewrite", value=res_val, height=350, label_visibility="collapsed", placeholder="AI 重写后的内容将显示在这里...")