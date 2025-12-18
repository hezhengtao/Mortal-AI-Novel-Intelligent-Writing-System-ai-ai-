# mortal_write/views/characters.py

import streamlit as st
import streamlit.components.v1 as components
import os
import time
import json
import urllib.parse 
import random
import base64
import html

from database import save_avatar_file
from config import FEATURE_MODELS
from logic import MODEL_MAPPING, OpenAI 
from utils import log_operation 
import database # 🔥 导入 database

# --- 0. 基础配置 ---
THEME_COLOR = "#2e7d32" 
THEME_LIGHT = "#e8f5e9"

def get_relation_dir():
    root = database.DATA_DIR if database.DATA_DIR else "data"
    d = os.path.join(root, "relations")
    if not os.path.exists(d):
        try: os.makedirs(d)
        except: pass
    return d

ROLE_PRIORITY = {
    "主角": 0, "男主角": 0, 
    "女主角": 1, "双主角": 2, "妻子": 3, "夫君": 3, "暗恋者/伴侣": 3,
    "反派BOSS": 10, "大反派": 10,
    "主要配角": 20, "导师/师父": 21, "挚友/死党": 22, 
    "宿敌": 30, 
    "亲属(父母/兄妹)": 40, "金手指/系统化身": 41, "宠物/坐骑": 42,
    "次要配角": 50, 
    "小反派/炮灰": 60, 
    "路人": 99,
    "default": 99
}

if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

def render_header(icon, title): st.markdown(f"## {icon} {title}")

def init_option_state():
    defaults = {
        "role_options": ["主角", "女主角", "双主角", "主要配角", "次要配角", "反派BOSS", "小反派/炮灰", "导师/师父", "挚友/死党", "宿敌", "暗恋者/伴侣", "亲属(父母/兄妹)", "金手指/系统化身", "宠物/坐骑", "路人"],
        "gender_options": ["男", "女", "无性", "双性", "流体性别", "未知/神秘"],
        "race_options": ["人族", "精灵", "矮人", "兽人/半兽人", "龙族", "亡灵/丧尸", "魔族", "妖族", "仙/神族", "机械/仿生人/AI", "灵体/鬼魂", "异虫/怪兽", "吸血鬼", "狼人", "混血", "未知生物"]
    }
    for key, val in defaults.items():
        if key not in st.session_state: st.session_state[key] = val

def update_book_timestamp_by_book_id(book_id):
    if book_id: st.session_state.db.update_book_timestamp(book_id)

def get_role_priority(role_name):
    if not role_name: return 99
    r = role_name.strip()
    if r in ROLE_PRIORITY: return ROLE_PRIORITY[r]
    if "男主" in r or r == "主角": return 0
    if any(k in r for k in ["女主", "双主角", "妻", "道侣", "伴侣", "红颜"]): return 1
    if any(k in r for k in ["反派", "BOSS", "魔尊", "始祖"]): return 2
    if any(k in r for k in ["主要配角", "导师", "师父", "挚友", "死党", "兄弟"]): return 3
    if any(k in r for k in ["宿敌", "亲属", "金手指", "系统"]): return 4
    if any(k in r for k in ["次要", "宠物", "坐骑"]): return 5
    if any(k in r for k in ["炮灰", "路人", "龙套"]): return 6
    return 99

@dialog_decorator("✨ 添加自定义选项")
def custom_option_dialog(list_key, widget_key):
    st.write("请输入新的选项名称：")
    new_val = st.text_input("输入内容", key=f"input_new_{list_key}")
    col_sub, col_can = st.columns([1, 1])
    if col_sub.button("✅ 确认并选中", type="primary", use_container_width=True):
        if new_val and new_val.strip():
            if new_val not in st.session_state[list_key]: st.session_state[list_key].append(new_val)
            st.session_state[widget_key] = new_val
            log_operation('角色', f'添加自定义选项 {new_val} 到 {list_key}')
            st.rerun()
        else: st.warning("内容不能为空")
    if col_can.button("取消", use_container_width=True):
        st.session_state[widget_key] = st.session_state[list_key][0]
        st.rerun()

def check_and_trigger_custom(selection, list_key, widget_key):
    if selection == "自定义...": custom_option_dialog(list_key, widget_key)

@dialog_decorator("🖼️ 编辑角色头像")
def edit_avatar_dialog(char_id, current_avatar, char_name, current_book_id):
    st.caption(f"正在修改 **{char_name}** 的头像")
    col_prev, col_input = st.columns([1, 2.5], gap="medium", vertical_alignment="center")
    with col_prev:
        if current_avatar:
            if current_avatar.startswith("http") or current_avatar.startswith("data:"): st.image(current_avatar, width=110)
            elif os.path.exists(current_avatar): st.image(current_avatar, width=110)
            else: st.info("无图")
        else: st.info("无图")
    with col_input:
        new_url = st.text_input("头像 URL", value=current_avatar if isinstance(current_avatar, str) and current_avatar.startswith("http") else "")
        new_file = st.file_uploader("上传图片 (JPG/PNG)", type=['jpg', 'png'])

    if st.button("💾 保存更改", type="primary", use_container_width=True):
        final_path = current_avatar
        if new_file:
            saved_path = save_avatar_file(new_file, char_id)
            if saved_path: final_path = saved_path
        elif new_url != current_avatar: final_path = new_url
            
        if final_path != current_avatar:
            st.session_state.db.execute("UPDATE characters SET avatar=? WHERE id=?", (final_path, char_id))
            update_book_timestamp_by_book_id(current_book_id)
            log_operation('角色', f'更新头像：{char_name} (ID: {char_id})')
            st.toast("✅ 头像已更新！"); time.sleep(0.5); st.rerun()
        else: st.warning("未检测到更改")

def get_node_image_content(path_or_url):
    if not path_or_url: return None
    path_or_url = str(path_or_url).strip()
    if path_or_url.startswith("http://") or path_or_url.startswith("https://") or path_or_url.startswith("data:"): return path_or_url
    if os.path.exists(path_or_url):
        try:
            with open(path_or_url, "rb") as img_file:
                b64_string = base64.b64encode(img_file.read()).decode('utf-8')
                ext = path_or_url.split('.')[-1].lower()
                mime_type = "image/png" if ext == "png" else "image/jpeg"
                return f"data:{mime_type};base64,{b64_string}"
        except: return None
    return None

def generate_bing_search_image(keyword):
    if not keyword: return ""
    encoded = urllib.parse.quote(keyword)
    return f"https://tse2.mm.bing.net/th?q={encoded}&w=300&h=300&c=7&rs=1&p=0"

def generate_pollinations_url(desc, name):
    if not desc: return ""
    safe_desc = desc[:80].replace("\n", " ")
    prompt = f"portrait of {name}, {safe_desc}, fantasy art, high quality"
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true&seed={random.randint(0,999)}"

def save_relations_to_disk(book_id, relations_data):
    rd = get_relation_dir()
    file_path = os.path.join(rd, f"book_{book_id}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f: json.dump(relations_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e: print(f"Save Error: {e}"); return False

def load_relations_from_disk(book_id):
    rd = get_relation_dir()
    file_path = os.path.join(rd, f"book_{book_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f: return json.load(f)
        except: return None
    return None

def ensure_schema_compatibility(db_mgr):
    for col in ["race", "desc", "avatar", "is_major"]:
        try: db_mgr.query(f"SELECT {col} FROM characters LIMIT 1")
        except: 
            try: db_mgr.execute(f"ALTER TABLE characters ADD COLUMN {col} TEXT")
            except: pass

def ai_extract_characters(engine, db_mgr, current_book, current_book_id, progress_callback=None):
    log_operation('角色', f'启动 AI 角色提取任务: {current_book["title"]}')
    feature_key = "character_extract"
    assigned_model_key = engine.get_config_db("model_assignments", {}).get(feature_key, FEATURE_MODELS[feature_key]['default'])
    client, model_name, _ = engine.get_client(assigned_model_key)
    feat_name = FEATURE_MODELS[feature_key]['name']
    display_model_name = MODEL_MAPPING.get(assigned_model_key, {}).get('name', model_name)
    
    if not client: 
        log_operation('角色', '提取失败：未配置 AI 模型')
        return False, f"❌ AI 模型未配置。请在【系统设置】->【功能调度】中为 [{feat_name}] 选择模型并保存。"

    if progress_callback: progress_callback(10, "正在比对现有角色库...")
    existing_res = db_mgr.query("SELECT name FROM characters WHERE book_id=?", (current_book_id,))
    existing_names = {r['name'] for r in existing_res} if existing_res else set()

    if progress_callback: progress_callback(20, "正在读取小说内容...")
    content_snippet = ""
    if hasattr(engine, 'get_book_content_prefix'): content_snippet = engine.get_book_content_prefix(current_book_id, length=15000)
    
    if progress_callback: progress_callback(40, f"正在调用 {display_model_name} 检索角色数据...")
    
    prompt = f"""
    请深入分析小说《{current_book['title']}》。
    {f"参考小说前文片段：{content_snippet[:2000]}..." if content_snippet else "请基于你的知识库。"}
    任务：提取该小说中最重要的 5-10 个角色。
    返回 JSON 格式：[{{ "name": "韩立", "gender": "男", "race": "人族", "role": "主角", "desc": "皮肤黝黑...", "is_major": true, "avatar": "" }}]
    排除以下角色：{list(existing_names)}
    """
    try:
        response = client.chat.completions.create(model=model_name, messages=[{"role": "user", "content": prompt}], temperature=0.3)
        if progress_callback: progress_callback(70, "正在执行多级头像匹配策略...")
        content = response.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        char_list = json.loads(content)
        final_list = []
        for c in char_list:
            if c['name'] not in existing_names:
                avatar_url = c.get('avatar', '').strip()
                if not avatar_url or not avatar_url.startswith("http"): avatar_url = generate_bing_search_image(f"{current_book['title']} {c['name']} 插画")
                if c.get('is_major') and (not avatar_url): avatar_url = generate_pollinations_url(c.get('desc'), c.get('name'))
                if not avatar_url: avatar_url = f"https://api.dicebear.com/9.x/adventurer/svg?seed={c['name']}&flip=true"
                c['avatar'] = avatar_url; final_list.append(c)
        if progress_callback: progress_callback(100, "分析完成！")
        log_operation('角色', f'提取成功：AI 发现了 {len(final_list)} 个新角色。')
        return True, final_list
    except Exception as e:
        log_operation('角色', f'提取异常：{str(e)}'); return False, f"提取失败: {str(e)}"

def generate_graph_html(nodes, edges, height="600px"):
    nodes_json = json.dumps(nodes); edges_json = json.dumps(edges)
    vis_js_url = "https://lib.baomitu.com/vis/4.21.0/vis.min.js"; vis_css_url = "https://lib.baomitu.com/vis/4.21.0/vis.min.css"
    html_template = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><script type="text/javascript" src="{vis_js_url}"></script><link href="{vis_css_url}" rel="stylesheet" type="text/css" /><style type="text/css">#mynetwork {{ width: 100%; height: {height}; border: 1px solid #eee; background-color: #ffffff; }} div.vis-network div.vis-manipulation {{ display: none !important; }} div.vis-tooltip {{ position: absolute; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); padding: 12px; font-family: "Microsoft YaHei", sans-serif; font-size: 13px; line-height: 1.6; color: #333; width: auto; max-width: 320px; white-space: normal; word-wrap: break-word; z-index: 9999; visibility: visible; pointer-events: none; }} div.vis-tooltip strong {{ color: #2e7d32; font-size: 15px; display: block; margin-bottom: 4px; }} div.vis-tooltip span.meta {{ color: #888; font-size: 12px; display: block; margin-bottom: 8px; border-bottom: 1px dashed #eee; padding-bottom: 4px; }}</style></head><body><div id="mynetwork"></div><script type="text/javascript"> var nodes = new vis.DataSet({nodes_json}); var edges = new vis.DataSet({edges_json}); var container = document.getElementById('mynetwork'); var data = {{ nodes: nodes, edges: edges }}; var options = {{ locale: 'cn', nodes: {{ shape: 'dot', size: 30, font: {{ size: 15, color: '#333333', face: 'arial', strokeWidth: 4, strokeColor: '#ffffff', vadjust: 6 }}, borderWidth: 4, borderWidthSelected: 6, shadow: {{ enabled: true, color: 'rgba(0,0,0,0.15)', size: 10, x: 2, y: 4 }}, shapeProperties: {{ useBorderWithImage: true }} }}, edges: {{ width: 2, color: {{ color: '#bbbbbb', highlight: '#2e7d32' }}, smooth: {{ type: 'continuous', roundness: 0.5 }}, arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }}, font: {{ align: 'middle', strokeWidth: 3, strokeColor: '#ffffff', size: 12 }} }}, physics: {{ enabled: true, forceAtlas2Based: {{ gravitationalConstant: -100, centralGravity: 0.015, springLength: 120, springConstant: 0.08, damping: 0.4, avoidOverlap: 0.8 }}, maxVelocity: 50, minVelocity: 0.1, solver: 'forceAtlas2Based', stabilization: {{ enabled: false, iterations: 1000 }} }}, manipulation: {{ enabled: false }}, interaction: {{ navigationButtons: true, keyboard: true, hover: true, zoomView: true, dragView: true }} }}; var network = new vis.Network(container, data, options); setTimeout(function() {{ network.fit({{ animation: {{ duration: 1000, easingFunction: 'easeInOutQuad' }} }}); }}, 1500); network.on("doubleClick", function (params) {{ if (params.nodes.length > 0) {{ network.focus(params.nodes[0], {{ scale: 1.5, animation: true }}); }} else {{ network.fit({{ animation: true }}); }} }}); network.on("afterDrawing", function() {{ if (this.tooltipsInjected) return; this.tooltipsInjected = true; setTimeout(function() {{ var map = {{ 'vis-zoomExtends': '全屏复位', 'vis-zoomIn': '放大', 'vis-zoomOut': '缩小', 'vis-up': '上移', 'vis-down': '下移', 'vis-left': '左移', 'vis-right': '右移' }}; for (var cls in map) {{ var el = document.querySelector('.' + cls); if (el) el.setAttribute('title', map[cls]); }} }}, 500); }}); </script></body></html>"""
    return html_template

def render_characters(engine, current_book_arg=None):
    db_mgr = st.session_state.db; ensure_schema_compatibility(db_mgr); init_option_state() 
    render_header("👥", "角色档案")
    
    st.markdown(f"""<style>input[type="checkbox"] {{ accent-color: {THEME_COLOR} !important; }} div[role="radiogroup"] label > div:first-child[aria-checked="true"] {{ background-color: {THEME_COLOR} !important; border-color: {THEME_COLOR} !important; }} [data-testid="StyledFullScreenButton"] {{ display: none !important; visibility: hidden !important; opacity: 0 !important; }} button[kind="header"] {{ display: none !important; }} [data-testid='stFileUploaderDropzone'] {{ border: 1px dashed #bbb !important; background-color: #fafafa !important; border-radius: 4px !important; padding: 0 !important; min-height: 40px !important; height: 40px !important; display: flex !important; align-items: center !important; justify-content: center !important; cursor: pointer; }} [data-testid='stFileUploaderDropzone']:hover {{ border-color: {THEME_COLOR} !important; background-color: #f1f8e9 !important; }} [data-testid='stFileUploaderDropzone'] > div > div > svg, [data-testid='stFileUploaderDropzone'] > div > div > small, [data-testid='stFileUploaderDropzone'] span {{ display: none !important; }} [data-testid='stFileUploaderDropzone']::after {{ content: "📷 点击更换"; display: block !important; color: #666; font-size: 13px; font-weight: 500; visibility: visible !important; }} [data-testid='stFileUploader'] button[kind="secondary"] {{ display: none !important; }} .char-card-title {{ margin: -15px 0 0 0 !important; font-weight: bold; }}</style>""", unsafe_allow_html=True)
    
    all_books_res = db_mgr.query("SELECT id, title FROM books")
    all_books = {r['title']: int(r['id']) for r in all_books_res} if all_books_res else {}
    book_titles = list(all_books.keys())
    if not all_books: st.warning("数据库中没有书籍，请先在 [书籍管理] 中添加书籍。"); return

    current_book_id = st.session_state.get('current_book_id')
    if not current_book_id:
        last_viewed = engine.get_config_db("last_viewed_book_id", None)
        if last_viewed and int(last_viewed) in all_books.values(): current_book_id = int(last_viewed); st.session_state['current_book_id'] = current_book_id
    
    default_idx = 0
    if current_book_id:
        for idx, t in enumerate(book_titles):
            if all_books[t] == current_book_id: default_idx = idx; break
    
    def on_book_change():
        new_title = st.session_state.character_manager_book_selector; new_id = all_books[new_title]
        st.session_state['current_book_id'] = new_id; engine.set_config_db("last_viewed_book_id", new_id)
        
    selected_title = st.selectbox("📚 **选择要管理的角色书籍：**", book_titles, index=default_idx, key="character_manager_book_selector", on_change=on_book_change)
    selected_book_id = int(all_books.get(selected_title))
    if selected_book_id != st.session_state.get('current_book_id'): st.session_state['current_book_id'] = selected_book_id; engine.set_config_db("last_viewed_book_id", selected_book_id)
    current_book_id = selected_book_id; current_book = None
    if current_book_id: res = db_mgr.query("SELECT * FROM books WHERE id=?", (current_book_id,)); current_book = res[0] if res else None
    if not current_book: return
    st.info(f"当前管理书籍：《{current_book['title']}》")
    
    col_graph, col_edit = st.columns([2, 1]) 
    with col_graph:
        st.subheader("🕸️ 人物关系图谱")
        chars_graph_rows = db_mgr.query("SELECT * FROM characters WHERE book_id=?", (current_book_id,))
        if not chars_graph_rows: st.info("暂无角色，请在右侧添加。")
        else:
            chars_graph = [dict(r) for r in chars_graph_rows]
            saved_relations = load_relations_from_disk(current_book_id); has_cache = saved_relations is not None
            c_tools_1, c_tools_2 = st.columns([1, 1])
            with c_tools_1:
                btn_label = "🔄 重新生成图谱" if has_cache else "🤖 AI 生成图谱"
                if st.button(btn_label, key="gen_chart_btn", type="primary", use_container_width=True):
                    feature_key = "books_arch_gen"
                    assigned_model = engine.get_config_db("model_assignments", {}).get(feature_key, FEATURE_MODELS[feature_key]['default'])
                    client, model_name, model_key = engine.get_client(assigned_model)
                    if not client: st.error(f"请先配置图谱生成模型")
                    else:
                        log_operation('角色', f'开始生成关系图谱: {current_book["title"]}')
                        with st.spinner("AI 正在阅读分析人物关系..."):
                            ok, res = engine.generate_char_relation_map_pyvis(current_book_id, chars_graph, client, model_name, model_key)
                            if ok and isinstance(res, list): save_relations_to_disk(current_book_id, res); saved_relations = res; log_operation('角色', f'图谱生成成功并保存 ({len(res)} 条关系)。'); st.rerun()
                            else: st.error(f"生成失败: {res}")
            
            relations_data = saved_relations if saved_relations else []
            try:
                role_colors = { "主角": "#d32f2f", "双主角": "#d32f2f", "反派BOSS": "#212121", "主要配角": "#1976d2", "次要配角": "#64b5f6", "挚友/死党": "#388e3c", "暗恋者/伴侣": "#e91e63", "导师/师父": "#fbc02d", "default": "#9e9e9e" }
                nodes = []; node_ids = set()
                for char in chars_graph:
                    node_ids.add(char['id']); color = role_colors.get(char.get('role'), role_colors["default"]); size = 35 if char.get('is_major') else 20
                    image_url = get_node_image_content(char.get('avatar')); shape = 'circularImage' if image_url else 'dot'
                    desc_raw = (char.get('desc') or "暂无描述").replace('\n', ' ')
                    tooltip_html = f"<strong>{html.escape(char['name'])}</strong><span class=\"meta\">{char.get('role', '未知')} | {char.get('race', '未知')}</span><hr style=\"margin:5px 0;border:0;border-top:1px solid #eee;\"><div style=\"font-size:12px;\">{html.escape(desc_raw)}</div>"
                    nodes.append({ "id": char['id'], "label": char['name'], "title": tooltip_html, "shape": shape, "image": image_url if image_url else None, "color": color, "size": size, "borderWidth": 4, "borderWidthSelected": 6, "color": { "border": color, "background": "#ffffff" } })
                edges = []
                for rel in relations_data:
                    if rel.get('source') in node_ids and rel.get('target') in node_ids: edges.append({ "from": rel.get('source'), "to": rel.get('target'), "label": rel.get('label'), "title": rel.get('label'), "width": max(1, rel.get('weight', 1) * 0.8) })
                html_code = generate_graph_html(nodes, edges, height="600px")
                components.html(html_code, height=620, scrolling=False)
            except Exception as e: st.error(f"渲染构建错误: {e}")

    with col_edit:
        tab_add, tab_rels, tab_list, tab_ai = st.tabs(["➕ 添加角色", "🔗 关系管理", "📋 列表管理", "🤖 AI 提取"])
        
        with tab_add:
            st.caption("添加新角色并可直接绑定关系。")
            name = st.text_input("姓名", key="manual_name")
            r_list = st.session_state.role_options + ["自定义..."]; g_list = st.session_state.gender_options + ["自定义..."]; rc_list = st.session_state.race_options + ["自定义..."]
            kp_man = "man"; role_sel = st.selectbox("定位", r_list, key=f"{kp_man}_role"); gen_sel = st.selectbox("性别", g_list, key=f"{kp_man}_gen"); race_sel = st.selectbox("种族", rc_list, key=f"{kp_man}_race")
            up_new_add = st.file_uploader("上传头像", type=['jpg','png'], key="man_up", label_visibility="collapsed"); av_url = st.text_input("头像 URL", key="manual_av"); desc = st.text_area("描述", height=250, key="manual_desc")
            st.markdown("**🔗 初始关系绑定**")
            char_rows = db_mgr.query("SELECT id, name FROM characters WHERE book_id=?", (current_book_id,)); char_options = {c['name']: c['id'] for c in char_rows}; char_names = ["(无)"] + list(char_options.keys())
            rel_target_name = st.selectbox("关联对象", char_names, key="man_rel_target"); rel_desc = st.text_input("关系描述 (如: 义妹)", key="man_rel_desc")

            if st.button("确认添加", type="primary", use_container_width=True):
                if name:
                    final_av = av_url
                    if up_new_add: temp_id = int(time.time()); saved_path = save_avatar_file(up_new_add, temp_id); final_av = saved_path if saved_path else final_av
                    if not final_av:
                         final_av = generate_bing_search_image(f"{current_book['title']} {name} 插画")
                         if not final_av: final_av = f"https://api.dicebear.com/9.x/adventurer/svg?seed={name}&flip=true"

                    new_char_id = db_mgr.execute("INSERT INTO characters (book_id, name, role, gender, race, desc, is_major, avatar) VALUES (?,?,?,?,?,?,?,?)", (current_book_id, name, role_sel, gen_sel, race_sel, desc, True, final_av))
                    if rel_target_name != "(无)" and rel_desc:
                        target_id = char_options[rel_target_name]; current_relations = load_relations_from_disk(current_book_id) or []
                        current_relations.append({ "source": new_char_id, "target": target_id, "label": rel_desc, "weight": 1 })
                        save_relations_to_disk(current_book_id, current_relations); log_operation('角色', f'添加关联: {name} -> {rel_target_name}')
                    update_book_timestamp_by_book_id(current_book_id); log_operation('角色', f'手动添加角色：{name}'); st.toast(f"✅ {name} 已添加！"); time.sleep(0.5); st.rerun()

            check_and_trigger_custom(role_sel, "role_options", f"{kp_man}_role"); check_and_trigger_custom(gen_sel, "gender_options", f"{kp_man}_gen"); check_and_trigger_custom(race_sel, "race_options", f"{kp_man}_race")

        with tab_rels:
            st.caption("管理角色间的连线。")
            char_rows = db_mgr.query("SELECT id, name FROM characters WHERE book_id=?", (current_book_id,)); char_options = {c['name']: c['id'] for c in char_rows}; char_names = list(char_options.keys())
            c_src, c_tgt = st.columns([1, 1])
            with c_src: src_name = st.selectbox("角色 A", char_names, key="rel_src")
            with c_tgt: tgt_name = st.selectbox("角色 B", char_names, key="rel_tgt")
            if src_name and tgt_name and src_name != tgt_name:
                src_id = char_options[src_name]; tgt_id = char_options[tgt_name]; current_relations = load_relations_from_disk(current_book_id) or []; existing_rel = None; existing_idx = -1
                for i, r in enumerate(current_relations):
                    if (r['source'] == src_id and r['target'] == tgt_id) or (r['source'] == tgt_id and r['target'] == src_id): existing_rel = r; existing_idx = i; break
                rel_label = st.text_input("关系描述", value=existing_rel['label'] if existing_rel else "", key="rel_label_input")
                c_act_1, c_act_2 = st.columns([1, 1])
                if existing_rel:
                    with c_act_1:
                        if st.button("更新关系", type="primary", use_container_width=True): current_relations[existing_idx]['label'] = rel_label; save_relations_to_disk(current_book_id, current_relations); log_operation('角色', f'更新关系：{src_name}-{tgt_name} ({rel_label})'); st.toast("✅ 关系已更新"); time.sleep(0.5); st.rerun()
                    with c_act_2:
                        if st.button("删除连线", type="secondary", use_container_width=True): current_relations.pop(existing_idx); save_relations_to_disk(current_book_id, current_relations); log_operation('角色', f'删除关系：{src_name}-{tgt_name}'); st.toast("🗑️ 关系已删除"); time.sleep(0.5); st.rerun()
                else:
                    if st.button("➕ 建立新关系", type="primary", use_container_width=True): new_rel = { "source": src_id, "target": tgt_id, "label": rel_label, "weight": 1 }; current_relations.append(new_rel); save_relations_to_disk(current_book_id, current_relations); log_operation('角色', f'新建关系：{src_name}-{tgt_name} ({rel_label})'); st.toast("✅ 关系已建立"); time.sleep(0.5); st.rerun()

        with tab_list:
            c_count, c_view = st.columns([2, 1])
            with c_count: rows = db_mgr.query("SELECT * FROM characters WHERE book_id=? ORDER BY is_major DESC, id DESC", (current_book_id,)); count = len(rows) if rows else 0; st.markdown(f"**共 {count} 名角色** <span style='color:grey;font-size:0.8em'>(已按重要性排序)</span>", unsafe_allow_html=True)
            with c_view: avatar_shape = st.radio("头像形状", ["⚪ 圆形", "⬜ 方形"], index=0, horizontal=True, label_visibility="collapsed", key="shape_toggle")
            radius_style = "50%" if avatar_shape == "⚪ 圆形" else "6px"
            if not rows: st.info("暂无角色")
            else:
                all_chars_res = [dict(r) for r in rows]; all_chars_res.sort(key=lambda x: get_role_priority(x.get('role')))
                for ch in all_chars_res:
                    with st.expander(f"{ch['name']} ({ch['role']})"):
                        c_header, c_gear = st.columns([5, 1])
                        with c_header: st.caption("编辑信息")
                        with c_gear:
                            if st.button("⚙️", key=f"gear_{ch['id']}", help="编辑头像"): edit_avatar_dialog(ch['id'], ch.get('avatar'), ch['name'], current_book_id)
                        kp = f"cedit_{ch['id']}"; c_thumb, c_name = st.columns([1, 4])
                        with c_thumb:
                             img_src = get_node_image_content(ch.get('avatar'))
                             if img_src: st.markdown(f"""<img src="{img_src}" style="width: 60px; height: 60px; border-radius: {radius_style}; object-fit: cover; border: 1px solid #ddd; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">""", unsafe_allow_html=True)
                             else: st.markdown(f"""<div style="width: 60px; height: 60px; border-radius: {radius_style}; background-color: #f0f2f6; color: #555; font-size: 20px; line-height: 60px; text-align: center; border: 1px solid #ddd;">?</div>""", unsafe_allow_html=True)
                        with c_name: n_new = st.text_input("姓名", ch['name'], key=f"{kp}_n", label_visibility="collapsed"); av_text_new = st.text_input("头像 URL", ch.get('avatar', ''), key=f"{kp}_av_text"); up_new = st.file_uploader("更换头像", type=['jpg','png'], key=f"{kp}_up", label_visibility="collapsed")
                        d_new = st.text_area("描述", ch.get('desc', ''), height=200, key=f"{kp}_d")
                        c_del, c_save = st.columns([1, 1])
                        if c_del.button("删除", key=f"del_{ch['id']}", type="secondary", use_container_width=True): db_mgr.execute("DELETE FROM characters WHERE id=?", (ch['id'],)); update_book_timestamp_by_book_id(current_book_id); log_operation('角色', f'删除角色：{ch["name"]}'); st.rerun()
                        if c_save.button("保存", key=f"save_{ch['id']}", type="primary", use_container_width=True):
                             final_avatar = av_text_new
                             if up_new: saved_path = save_avatar_file(up_new, ch['id']); final_avatar = saved_path if saved_path else final_avatar
                             if n_new != ch['name'] or d_new != ch.get('desc') or final_avatar != ch.get('avatar'): db_mgr.execute("UPDATE characters SET name=?, desc=?, avatar=? WHERE id=?", (n_new, d_new, final_avatar, ch['id'])); update_book_timestamp_by_book_id(current_book_id); log_operation('角色', f'编辑角色：{n_new}'); st.rerun()

        with tab_ai:
            if st.button("🚀 AI 分析本书角色", type="primary", use_container_width=True):
                progress_bar = st.progress(0); status_text = st.empty()
                def update_progress(p, text): progress_bar.progress(p); status_text.text(text)
                ok, result = ai_extract_characters(engine, db_mgr, current_book, current_book_id, update_progress)
                if ok: st.session_state[f"extracted_chars_{current_book_id}"] = result; st.success(f"发现 {len(result)} 个角色"); st.rerun()
                else: st.error(result)
            extracted_data = st.session_state.get(f"extracted_chars_{current_book_id}", [])
            if extracted_data:
                if st.button("📥 全部添加", use_container_width=True):
                    for char_data in extracted_data:
                        try: db_mgr.execute("INSERT INTO characters (book_id, name, role, gender, race, desc, is_major, avatar) VALUES (?,?,?,?,?,?,?,?)", (current_book_id, char_data['name'], char_data.get('role', '路人'), char_data.get('gender', '未知'), char_data.get('race', '人族'), char_data.get('desc', ''), char_data.get('is_major', False), char_data.get('avatar', '')))
                        except: pass
                    st.session_state[f"extracted_chars_{current_book_id}"] = []; update_book_timestamp_by_book_id(current_book_id); st.rerun()
                for idx, char_data in enumerate(extracted_data): st.info(f"{char_data['name']} - {char_data.get('role')}")
