# mortal_write/views/books.py

import streamlit as st
import re
import os
import time
import json
import csv
import urllib.parse
import random
from datetime import datetime
from utils import render_header, log_operation, generate_book_content, ensure_log_file
from logic import FEATURE_MODELS, get_ntp_time, MODEL_MAPPING 
import database

# ==============================================================================
# 🌟 网文流派全集 (内置数据)
# ==============================================================================
NOVEL_GENRES = {
    "玄幻奇幻": ["东方玄幻", "异世大陆", "王朝争霸", "高武世界", "西方奇幻", "领主种田", "魔法校园"],
    "仙侠修真": ["凡人流", "古典仙侠", "修真文明", "幻想修仙", "洪荒封神", "无敌流", "苟道流"],
    "都市现实": ["都市异能", "都市修仙", "神医赘婿", "文娱明星", "商战职场", "校花贴身", "鉴宝捡漏"],
    "科幻末世": ["末世危机", "星际文明", "赛博朋克", "时空穿梭", "进化变异", "古武机甲", "无限流"],
    "历史军事": ["架空历史", "穿越重生", "秦汉三国", "两宋元明", "外国历史", "谍战特工", "军旅生涯"],
    "游戏竞技": ["虚拟网游", "电子竞技", "游戏异界", "体育竞技", "卡牌游戏", "桌游棋牌"],
    "悬疑灵异": ["侦探推理", "诡异修仙", "盗墓探险", "风水秘术", "克苏鲁", "神秘复苏"],
    "轻小说/二次元": ["原生幻想", "恋爱日常", "综漫同人", "变身入替", "搞笑吐槽", "系统流"]
}

FLAT_GENRE_LIST = []
for main, subs in NOVEL_GENRES.items():
    for sub in subs:
        FLAT_GENRE_LIST.append(f"{main}-{sub}")

# ==============================================================================
# 🛠️ 基础工具
# ==============================================================================

if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

def ensure_export_dir():
    root = database.DATA_DIR if database.DATA_DIR else "data"
    export_dir = os.path.join(root, "exports")
    if not os.path.exists(export_dir): os.makedirs(export_dir)
    return export_dir

def get_cached_file_path(book_id, book_title):
    root = database.DATA_DIR if database.DATA_DIR else "data"
    safe_title = re.sub(r'[\\/*?:"<>|]', "", str(book_title)).strip()
    return os.path.join(root, "exports", f"{book_id}_{safe_title}.txt")

# 获取关系数据存储目录
def get_relation_dir():
    root = database.DATA_DIR if database.DATA_DIR else "data"
    d = os.path.join(root, "relations")
    if not os.path.exists(d):
        try: os.makedirs(d)
        except: pass
    return d

# 保存关系数据到 JSON
def save_relations_to_disk(book_id, relations_data):
    rd = get_relation_dir()
    file_path = os.path.join(rd, f"book_{book_id}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(relations_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Save Relation Error: {e}")
        return False

# 生成 Bing 图片搜索 URL (用于头像)
def generate_bing_search_image(keyword):
    if not keyword: return ""
    encoded = urllib.parse.quote(keyword)
    return f"https://tse2.mm.bing.net/th?q={encoded}&w=300&h=300&c=7&rs=1&p=0"

def audit_download_callback(book_title, book_id):
    try:
        ensure_log_file()
        log_operation("数据导出", f"用户下载书籍TXT: 《{book_title}》 (ID:{book_id})")
    except Exception as e: print(f"Logging Error: {e}")

def record_usage_log(model_key, input_tokens, output_tokens):
    try:
        log_dir = os.path.join(database.DATA_DIR, "logs") if database.DATA_DIR else "logs"
        if not os.path.exists(log_dir): os.makedirs(log_dir)
        csv_path = os.path.join(log_dir, "usage_log.csv")
        
        cost = (input_tokens * 18 + output_tokens * 72) / 1_000_000
        
        model_info = MODEL_MAPPING.get(model_key, {})
        provider = model_info.get('provider', 'Unknown')
        model_name = model_info.get('name', model_key)
        
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'provider', 'model', 'input', 'output', 'cost'])
            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), provider, model_name, input_tokens, output_tokens, f"{cost:.6f}"])
            
        if 'model_usage_stats' not in st.session_state: st.session_state.model_usage_stats = {}
        if model_key not in st.session_state.model_usage_stats:
            st.session_state.model_usage_stats[model_key] = {'input': 0, 'output': 0, 'cost': 0.0}
        
        s = st.session_state.model_usage_stats[model_key]
        s['input'] += input_tokens
        s['output'] += output_tokens
        s['cost'] += cost
    except Exception as e:
        print(f"Usage Log Error: {e}")

# ==============================================================================
# 🪟 弹窗组件
# ==============================================================================

@dialog_decorator("➕ 添加自定义流派")
def dialog_add_custom_genre():
    st.markdown("请输入新的流派名称：")
    new_genre = st.text_input("流派名称", key="input_custom_genre_modal")
    
    if st.button("确认添加", type="primary", use_container_width=True):
        if new_genre and new_genre.strip():
            val = new_genre.strip()
            if 'custom_genres_list' not in st.session_state:
                st.session_state.custom_genres_list = []
            if val not in st.session_state.custom_genres_list:
                st.session_state.custom_genres_list.append(val)
                st.session_state['new_genre_selection'] = val
            st.rerun()
        else:
            st.warning("名称不能为空")

@dialog_decorator("🎉 架构与角色生成报告")
def dialog_gen_success(book_title, total_chapters, char_count, relation_count, usage_info):
    st.markdown(f"### 《{book_title}》")
    
    # 删除了所有分割线 ---
    c1, c2 = st.columns(2)
    with c1:
        st.success(f"✅ 构建 **{total_chapters}** 章大纲")
    with c2:
        if char_count > 0:
            st.info(f"👥 导入 **{char_count}** 名角色")
        else:
            st.warning("⚠️ 未提取到角色")
            
    if relation_count > 0:
        st.caption(f"🔗 已自动建立 {relation_count} 条人物关系，已生成头像。")
    
    if usage_info:
        cost = (usage_info.get('total_tokens', 0) * 0.00004) 
        st.caption(f"💰 本次消耗: {usage_info.get('total_tokens', 0)} Tokens (约 ¥{cost:.4f})")
    
    if st.button("✅ 确定", type="primary", use_container_width=True):
        st.rerun()

# ==============================================================================
# 🧠 AI 架构生成核心逻辑 (含头像、关系)
# ==============================================================================

def generate_structure_via_ai(engine, title, intro, genre="玄幻-东方玄幻"):
    feature_key = "novel_structure_gen"
    default_model = "GPT_4o" 
    assigned_key = engine.get_config_db("model_assignments", {}).get(feature_key, default_model)
    client, model_name, _ = engine.get_client(assigned_key)
    
    if not client:
        return False, "⚠️ 未配置 AI 模型", {}, None

    # 🔥 Prompt 升级：请求头像关键词和关系列表
    prompt = f"""
    你是一位资深的【{genre}】流派网文主编。请为《{title}》设计大纲、人设及关系网。
    
    【书籍信息】
    - 书名：{title}
    - 核心流派：{genre}
    - 简介：{intro}

    【绝对指令】
    1. **结构**：生成 3卷，**第一卷必须包含 50 个章节！** 章节大纲限25字内。
    2. **角色**：请设计 **8-12 名** 核心角色。
       - 必须包含：姓名、角色定位(如主角/反派)、性别、种族、简述。
       - **关键**：为每个角色提供一个【头像关键词】(avatar_kw)，例如"Handsome young cultivator, blue robes, fantasy art"。
    3. **关系**：请设计角色间的人物关系。
       - 格式：角色A姓名, 角色B姓名, 关系描述(如"师徒", "死敌")。
    4. **格式**：严格返回 JSON 对象。

    【JSON 格式范例】：
    {{
        "characters": [
            {{ "name": "萧火火", "role": "男主角", "gender": "男", "race": "人族", "desc": "...", "avatar_kw": "young hero fire magic fantasy face" }},
            {{ "name": "纳兰", "role": "未婚妻", "gender": "女", "race": "人族", "desc": "...", "avatar_kw": "beautiful noble girl fantasy art" }}
        ],
        "relations": [
            {{ "char1": "萧火火", "char2": "纳兰", "desc": "退婚宿敌" }}
        ],
        "structure": [
            {{
                "part_name": "第一篇",
                "volumes": [
                    {{
                        "vol_name": "第一卷",
                        "chapters": [
                            {{ "title": "第1章", "summary": "..." }},
                            ... (列出50章)
                        ]
                    }}
                ]
            }}
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model=model_name, 
            messages=[{"role": "user", "content": prompt}], 
            temperature=0.75,
            max_tokens=8000
        )
        content = response.choices[0].message.content.strip()
        
        usage_info = {}
        if hasattr(response, 'usage') and response.usage:
            usage_info = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            record_usage_log(assigned_key, response.usage.prompt_tokens, response.usage.completion_tokens)

        content = content.replace("```json", "").replace("```", "").strip()
        if not content.endswith("}"): 
            last_brace = content.rfind("}")
            if last_brace != -1: content = content[:last_brace+1] + "]}]}" 

        data = json.loads(content)
        
        # 兼容性处理
        if isinstance(data, list): data = {"structure": data, "characters": [], "relations": []}
        if "relations" not in data: data["relations"] = []
            
        return True, data, usage_info, assigned_key

    except json.JSONDecodeError:
        return False, f"JSON 截断或格式错误。", {}, None
    except Exception as e:
        return False, f"AI 调用失败: {str(e)}", {}, None

# ==============================================================================
# 📖 书籍导入解析逻辑
# ==============================================================================
def robust_decode(data_bytes):
    encodings = ['utf-8', 'gb18030', 'gbk', 'big5', 'utf-16']
    for enc in encodings:
        try: return data_bytes.decode(enc)
        except UnicodeDecodeError: continue
    return data_bytes.decode('gb18030', errors='ignore')

def _parse_book_structure(full_text):
    return [{'part_name': '正文', 'volumes': [{'vol_name': '全书', 'chapters': [{'title': '全文内容', 'content': full_text}]}]}]

def _import_book_process(db_mgr, engine, uploaded_file, book_id, book_title, book_author):
    content_bytes = uploaded_file.getvalue()
    full_text = robust_decode(content_bytes)
    part_id = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, '正文', 100)", (book_id,))
    vol_id = db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, '全书', 100)", (book_id, part_id))
    db_mgr.execute("INSERT INTO chapters (volume_id, title, content, summary, sort_order) VALUES (?, '全文', ?, '导入内容', 1)", (vol_id, full_text))
    return 0, 1

# ==============================================================================
# 🎨 UI 渲染
# ==============================================================================

def render_import_section(engine):
    db_mgr = st.session_state.db
    with st.expander("📥 导入书籍"):
        st.caption("支持 txt 格式，自动识别 篇-卷-章 结构。")
        uploaded_file = st.file_uploader("TXT文件上传区", type=["txt"], key="import_file_real", label_visibility="collapsed")
        with st.form("form_import_action"):
            c1, c2 = st.columns(2); title_input = c1.text_input("书名 (必填)", key="import_book_title_ui"); author_input = c2.text_input("作者", value="未知", key="import_book_author_ui"); submitted = st.form_submit_button("🚀 开始导入", type="primary", use_container_width=True)
        if submitted:
            if not uploaded_file: st.error("请先上传 TXT 文件")
            elif not title_input.strip(): st.error("书名不能为空")
            else:
                try:
                    now = get_ntp_time()
                    bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", (title_input, author_input, "导入生成", now, now))
                    _import_book_process(db_mgr, engine, uploaded_file, bid, title_input, author_input)
                    st.success("导入成功"); time.sleep(0.5); st.rerun()
                except Exception as e: st.error(f"导入错误: {e}")

def render_books(engine):
    db_mgr = st.session_state.db
    ensure_export_dir() 
    render_header("📚", "书籍管理")
    
    render_import_section(engine)
    
    if 'custom_genres_list' not in st.session_state:
        st.session_state.custom_genres_list = []

    with st.expander("✨ 手动创建新书 / AI 架构向导", expanded=False):
        with st.form("form_new_book"):
            col1, col2 = st.columns(2)
            b_title = col1.text_input("书名")
            b_author = col2.text_input("作者", "我")
            
            # 🔥 1. 水平对齐
            try: c3, c4 = st.columns([4, 1], vertical_alignment="bottom")
            except TypeError: c3, c4 = st.columns([4, 1])
            
            existing_cats_db = db_mgr.query("SELECT name FROM categories")
            db_cats = [c['name'] for c in existing_cats_db] if existing_cats_db else []
            all_options = sorted(list(set(FLAT_GENRE_LIST + db_cats + st.session_state.custom_genres_list)))
            
            default_idx = 0
            if 'new_genre_selection' in st.session_state and st.session_state.new_genre_selection in all_options:
                default_idx = all_options.index(st.session_state.new_genre_selection)
            elif "玄幻-东方玄幻" in all_options:
                default_idx = all_options.index("玄幻-东方玄幻")

            with c3:
                b_category = st.selectbox("流派/分类", all_options, index=default_idx)
            
            with c4:
                if st.form_submit_button("➕", help="添加自定义流派", type="secondary"):
                    dialog_add_custom_genre()

            b_intro = st.text_area("简介 / 大纲 (AI 生成结构将参考此内容)", height=100, placeholder="输入简介，AI 将自动生成分卷大纲和角色...")
            
            c_sub1, c_sub2 = st.columns([1, 4])
            btn_create = c_sub1.form_submit_button("🚀 仅创建", use_container_width=True)
            btn_create_jump = c_sub2.form_submit_button("💡 AI 生成结构与角色", type="primary", use_container_width=True)
            
            if btn_create or btn_create_jump:
                if not b_title.strip():
                    st.error("书名不能为空")
                else:
                    try:
                        now = get_ntp_time()
                        bid = db_mgr.execute(
                            "INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", 
                            (b_title, b_author, b_intro, now, now)
                        )
                        
                        if b_category:
                            cat_res = db_mgr.query("SELECT id FROM categories WHERE name=?", (b_category,))
                            if cat_res: cat_id = cat_res[0]['id']
                            else: cat_id = db_mgr.execute("INSERT INTO categories (name) VALUES (?)", (b_category,))
                            db_mgr.execute("INSERT INTO book_categories (book_id, category_id) VALUES (?,?)", (bid, cat_id))

                        if btn_create_jump:
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            try:
                                status_text.markdown(f"#### 🧠 正在基于【{b_category}】流派构思大纲 (约30-60秒)...")
                                progress_bar.progress(20)
                                ensure_log_file()
                                log_operation("AI架构", f"开始生成: 《{b_title}》")
                                
                                success, result_data, usage_info, _ = generate_structure_via_ai(engine, b_title, b_intro, genre=b_category)
                                
                                if success:
                                    status_text.markdown("#### 💾 正在写入数据库...")
                                    progress_bar.progress(50)
                                    
                                    # --- 角色写入逻辑 (含头像 & 关系映射) ---
                                    char_list = result_data.get('characters', [])
                                    relations_raw = result_data.get('relations', [])
                                    char_name_to_id = {}
                                    char_count = 0
                                    
                                    for ch in char_list:
                                        try:
                                            # 🔥 自动生成头像
                                            avatar_kw = ch.get('avatar_kw', f"{ch['name']} {b_category}")
                                            avatar_url = generate_bing_search_image(avatar_kw)
                                            # 兜底头像
                                            if not avatar_url: 
                                                avatar_url = f"https://api.dicebear.com/9.x/adventurer/svg?seed={ch['name']}"
                                            
                                            cid = db_mgr.execute(
                                                "INSERT INTO characters (book_id, name, role, gender, race, desc, is_major, avatar) VALUES (?,?,?,?,?,?,?,?)",
                                                (bid, ch.get('name'), ch.get('role','配角'), ch.get('gender','未知'), ch.get('race','人类'), ch.get('desc',''), True, avatar_url)
                                            )
                                            char_name_to_id[ch['name']] = cid
                                            char_count += 1
                                        except Exception as e_char:
                                            print(f"Char Insert Error: {e_char}")
                                    
                                    # --- 关系写入逻辑 ---
                                    relation_list = []
                                    for rel in relations_raw:
                                        c1 = rel.get('char1')
                                        c2 = rel.get('char2')
                                        desc = rel.get('desc', '相关')
                                        if c1 in char_name_to_id and c2 in char_name_to_id:
                                            relation_list.append({
                                                "source": char_name_to_id[c1],
                                                "target": char_name_to_id[c2],
                                                "label": desc,
                                                "weight": 1
                                            })
                                    if relation_list:
                                        save_relations_to_disk(bid, relation_list)
                                    
                                    # --- 结构写入 ---
                                    structure = result_data.get('structure', [])
                                    processed_count = 0
                                    if 'expanded_parts' not in st.session_state: st.session_state.expanded_parts = set()
                                    if 'expanded_volumes' not in st.session_state: st.session_state.expanded_volumes = set()

                                    for p_idx, part in enumerate(structure):
                                        p_name = part.get('part_name', f'第{p_idx+1}篇')
                                        pid = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, ?, ?)", (bid, p_name, (p_idx+1)*100))
                                        st.session_state.expanded_parts.add(pid)

                                        for v_idx, vol in enumerate(part.get('volumes', [])):
                                            v_name = vol.get('vol_name', f'第{v_idx+1}卷')
                                            vid = db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, ?, ?)", (bid, pid, v_name, (v_idx+1)*100))
                                            st.session_state.expanded_volumes.add(vid)

                                            raw_chapters = vol.get('chapters', [])
                                            for c_idx, chap_obj in enumerate(raw_chapters):
                                                c_title = chap_obj.get('title', f"第{c_idx+1}章") if isinstance(chap_obj, dict) else chap_obj
                                                c_summary = chap_obj.get('summary', "") if isinstance(chap_obj, dict) else ""
                                                db_mgr.execute("INSERT INTO chapters (volume_id, title, summary, content, sort_order) VALUES (?, ?, ?, ?, ?)", 
                                                               (vid, c_title, c_summary, "", (c_idx+1)))
                                                processed_count += 1
                                                status_text.markdown(f"**写入：{c_title}**")
                                                progress_bar.progress(min(50 + int(processed_count/60 * 45), 95))

                                    progress_bar.progress(100)
                                    status_text.success("✅ 完成！")
                                    time.sleep(0.5)
                                    dialog_gen_success(b_title, processed_count, char_count, len(relation_list), usage_info)
                                else:
                                    status_text.error(f"❌ AI 生成失败: {result_data}")
                                    pid = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, '第一篇', 100)", (bid,))
                                    db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, '第一卷', 100)", (bid, pid))
                                    time.sleep(1.5); st.rerun()
                            except Exception as e_ai: status_text.error(f"发生错误: {e_ai}")
                        else:
                            pid = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, '第一篇', 100)", (bid,))
                            db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, '第一卷', 100)", (bid, pid))
                            st.success("创建成功"); time.sleep(0.5); st.rerun()
                    except Exception as e:
                        st.error(f"创建失败: {str(e)}")
                        if 'bid' in locals() and bid: db_mgr.execute("DELETE FROM books WHERE id=?", (bid,))

    books = db_mgr.query("SELECT * FROM books ORDER BY updated_at DESC")
    if not books: st.info("暂无书籍。"); return

    def parse_time(t_str):
        if not t_str: return "N/A"
        try: 
            return datetime.strptime(str(t_str).split('.')[0], '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%d %H:%M')
        except: 
            try: return str(t_str).split(' ')[0]
            except: return str(t_str)

    def render_book_card(book):
        book = dict(book); book_id = book['id']
        cats = db_mgr.query("SELECT c.name FROM book_categories bc JOIN categories c ON bc.category_id = c.id WHERE bc.book_id = ?", (book_id,))
        genre_val = " / ".join([c['name'] for c in cats]) if cats else "未分类"
        file_path = get_cached_file_path(book_id, book['title'])
        
        with st.container(border=True):
            # 🔥 4. 修复：彻底解决[简介:...]问题，改用干净的布局
            # 只有标题和信息图标，没有多余的文本
            c_head_L, c_head_R = st.columns([8, 1]) 
            with c_head_L:
                # 标题旁边加个 emoji，Tooltip 在 emoji 上，保持标题纯净
                st.markdown(f"#### 📖 {book['title']} <span title='{book['intro'] or '暂无简介'}' style='font-size:0.8em; cursor:help;'>ℹ️</span>", unsafe_allow_html=True)
                st.caption(f"✍️ **{book['author']}** | 🏷️ {genre_val}")
                st.caption(f"🕒 创建: {parse_time(book['created_at'])} | 📝 修改: {parse_time(book['updated_at'])}")
            
            with c_head_R:
                if os.path.exists(file_path):
                    st.caption("📦 已打包")

            st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("✍️ 写作", key=f"ent_{book_id}", type="primary", use_container_width=True):
                st.session_state.current_book_id = book_id; st.session_state.current_menu = "write"; st.rerun()
            if c2.button("📑 预览", key=f"view_{book_id}", use_container_width=True):
                 st.session_state.current_book_id = book_id; st.session_state.current_menu = "chapters"; st.rerun()
            
            with c3:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        st.download_button(label="📥 下载", data=f, file_name=os.path.basename(file_path), mime="text/plain", key=f"dl_{book_id}", use_container_width=True)
                else:
                    if st.button("📦 打包", key=f"pack_{book_id}", use_container_width=True):
                        content = generate_book_content(db_mgr, book_id)
                        with open(file_path, "w", encoding='utf-8') as f: f.write(content)
                        st.rerun()
            if c4.button("🗑️ 删除", key=f"del_{book_id}", use_container_width=True):
                db_mgr.execute("DELETE FROM books WHERE id=?", (book_id,)); st.rerun()

    for i in range(0, len(books), 2):
        cols = st.columns(2)
        with cols[0]: render_book_card(books[i])
        if i+1 < len(books):
            with cols[1]:
                render_book_card(books[i+1])