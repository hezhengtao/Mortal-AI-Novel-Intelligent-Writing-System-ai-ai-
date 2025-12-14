
import streamlit as st
import re
import os
import time
from datetime import datetime
from utils import render_header, log_operation, generate_book_content, ensure_log_file
from logic import FEATURE_MODELS, get_ntp_time 

# ==============================================================================
# 🛠️ 缓存与文件管理工具
# ==============================================================================

def ensure_export_dir():
    """确保导出目录存在"""
    export_dir = "data/exports"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    return export_dir

def get_cached_file_path(book_id, book_title):
    """生成安全的文件路径"""
    safe_title = re.sub(r'[\\/*?:"<>|]', "", str(book_title)).strip()
    return os.path.join("data/exports", f"{book_id}_{safe_title}.txt")

# 🔥 新增：下载审计回调函数
def audit_download_callback(book_title, book_id):
    """当用户点击下载时触发此日志记录"""
    try:
        ensure_log_file()
        log_operation("数据导出", f"用户下载书籍TXT: 《{book_title}》 (ID:{book_id})")
    except Exception as e:
        print(f"Logging Error: {e}")


def robust_decode(data_bytes):
    encodings = ['utf-8', 'gb18030', 'gbk', 'big5', 'utf-16']
    for enc in encodings:
        try: 
            return data_bytes.decode(enc)
        except UnicodeDecodeError: 
            continue
    return data_bytes.decode('gb18030', errors='ignore')

# 中文数字映射
CN_NUM = {'零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '百':100, '千':1000, '万':10000}

def parse_volume_number(num_str):
    if not num_str: return 0
    if num_str.isdigit(): return int(num_str)
    try:
        val = 0
        current_val = 0
        if num_str.startswith('十'): num_str = '一' + num_str 
        
        for char in num_str:
            if char in CN_NUM:
                digit = CN_NUM[char]
                if digit >= 10:
                    if current_val == 0: current_val = 1
                    current_val *= digit
                    val += current_val
                    current_val = 0
                else:
                    current_val = digit
        val += current_val
        return val if val > 0 else 0
    except:
        return 0

def _parse_book_structure(full_text):
    lines = full_text.splitlines()
    
    parts_list = []
    part_index_map = {} 
    
    # --- 1. 初始化默认容器 ---
    default_part = {
        'idx': 1,
        'name': '第一篇',
        'vol_map': {}, 
        'vol_list': []
    }
    parts_list.append(default_part)
    part_index_map[1] = default_part
    
    default_vol = {
        'idx': 1,
        'name': '第一卷',
        'chapters': []
    }
    default_part['vol_list'].append(default_vol)
    default_part['vol_map'][1] = default_vol
    
    current_part = default_part
    current_vol = default_vol
    
    current_chap_title = None
    current_chap_content = []

    # --- 正则表达式 ---
    combined_pattern = re.compile(
        r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[卷部篇集]|Volume\s*(\d+))\s*(.*?)\s*(第[0-9零一二三四五六七八九十百千万]+[章节回]|Chapter\s*\d+|序章|楔子|前言|尾声|后记)(.*)$', re.IGNORECASE
    )
    part_pattern = re.compile(r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[篇部]|Part\s*(\d+))(.*)$', re.IGNORECASE)
    vol_pattern = re.compile(r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[卷集]|Volume\s*(\d+))(.*)$', re.IGNORECASE)
    chap_pattern = re.compile(r'^\s*(第[0-9零一二三四五六七八九十百千万]+[章节回]|Chapter\s*\d+|序章|楔子|前言|尾声|后记)(.*)$', re.IGNORECASE)

    def save_current_chapter():
        if current_chap_title and current_chap_content:
            content_str = "\n".join(current_chap_content).strip()
            if content_str:
                current_vol['chapters'].append({'title': current_chap_title, 'content': content_str})

    def process_volume_switch(num_str, title_str):
        nonlocal current_vol
        
        v_idx = parse_volume_number(num_str)
        if v_idx == 0: v_idx = len(current_part['vol_list']) + 1
        
        prefix = f"第{num_str}卷" if not num_str.isdigit() else f"Volume {num_str}"
        if title_str and title_str.startswith(prefix):
             full_v_name = title_str
        else:
             full_v_name = f"{prefix} {title_str}".strip()

        if v_idx in current_part['vol_map']:
            current_vol = current_part['vol_map'][v_idx]
            if len(full_v_name) > len(current_vol['name']):
                current_vol['name'] = full_v_name
        else:
            is_curr_vol_empty = (len(current_vol['chapters']) == 0 and current_vol['name'] == '第一卷')
            if is_curr_vol_empty and v_idx == 1:
                current_vol['name'] = full_v_name
                current_part['vol_map'][1] = current_vol 
            else:
                new_vol = {
                    'idx': v_idx,
                    'name': full_v_name,
                    'chapters': []
                }
                current_part['vol_list'].append(new_vol)
                current_part['vol_map'][v_idx] = new_vol
                current_vol = new_vol

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_chap_title and current_chap_content: current_chap_content.append(line)
            continue

        combined_match = combined_pattern.match(stripped)
        part_match = part_pattern.match(stripped) if not combined_match else None
        vol_match = vol_pattern.match(stripped) if not combined_match else None
        chap_match = chap_pattern.match(stripped) if not combined_match else None

        if combined_match:
            save_current_chapter() 
            v_num = combined_match.group(1) or combined_match.group(2)
            v_title_part = combined_match.group(3).strip()
            process_volume_switch(v_num, v_title_part)
            c_marker = combined_match.group(4).strip()
            c_title_part = combined_match.group(5).strip()
            current_chap_title = f"{c_marker} {c_title_part}".strip()
            current_chap_content = []
            continue

        if part_match:
            save_current_chapter()
            num_str = part_match.group(1) or part_match.group(2)
            p_idx = parse_volume_number(num_str)
            if p_idx == 0: p_idx = len(parts_list) + 1
            p_title = part_match.group(3).strip()
            full_p_name = f"第{num_str}篇 {p_title}".strip()

            if p_idx in part_index_map:
                current_part = part_index_map[p_idx]
                if len(full_p_name) > len(current_part['name']):
                    current_part['name'] = full_p_name
            else:
                is_default_pure = (current_part == default_part and 
                                   len(current_part['vol_list']) == 1 and 
                                   len(current_part['vol_list'][0]['chapters']) == 0 and
                                   current_part['name'] == '第一篇')
                if is_default_pure and p_idx == 1:
                    current_part['name'] = full_p_name
                else:
                    new_part = {
                        'idx': p_idx,
                        'name': full_p_name,
                        'vol_map': {},
                        'vol_list': []
                    }
                    parts_list.append(new_part)
                    part_index_map[p_idx] = new_part
                    current_part = new_part
            
            if not current_part['vol_list']:
                 vol = { 'idx': 1, 'name': '第一卷', 'chapters': [] }
                 current_part['vol_list'].append(vol)
                 current_part['vol_map'][1] = vol
                 current_vol = vol
            else:
                 current_vol = current_part['vol_list'][-1]
            current_chap_title = None
            current_chap_content = []
            continue

        if vol_match:
            save_current_chapter()
            num = vol_match.group(1) or vol_match.group(2)
            title = vol_match.group(3).strip()
            process_volume_switch(num, title)
            current_chap_title = None
            current_chap_content = []
            continue

        if chap_match:
            raw_title = f"{chap_match.group(1).strip()} {chap_match.group(2).strip()}".strip()
            if raw_title == current_chap_title:
                continue
            save_current_chapter()
            current_chap_title = raw_title
            current_chap_content = []
            continue

        if current_chap_title:
            current_chap_content.append(line)
        else:
            if stripped:
                current_chap_title = "序言/引子"
                current_chap_content.append(line)
    
    save_current_chapter()

    final_structure = []
    for p in parts_list:
        valid_vols = []
        for v in p['vol_list']:
            if v['chapters']:
                valid_vols.append({
                    'vol_name': v['name'],
                    'chapters': v['chapters']
                })
        if valid_vols:
            final_structure.append({
                'part_name': p['name'],
                'volumes': valid_vols
            })
            
    return final_structure

# ==============================================================================
# 🚀 核心导入逻辑
# ==============================================================================

def _import_book_process(db_mgr, engine, uploaded_file, book_id, book_title, book_author):
    content_bytes = uploaded_file.getvalue()
    with st.status("🚀 正在导入书籍...", expanded=True) as status:
        status.write("📂 正在解析 篇-卷-章 结构 (智能分割模式)...")
        full_text = robust_decode(content_bytes)
        
        structure = _parse_book_structure(full_text)
        
        total_parts = len(structure)
        total_vols = sum(len(p['volumes']) for p in structure)
        total_chaps = sum(sum(len(v['chapters']) for v in p['volumes']) for p in structure)

        if total_chaps == 0:
             structure = [{
                 'part_name': '正文', 
                 'volumes': [{
                     'vol_name': '全书', 
                     'chapters': [{'title': '全文内容', 'content': full_text}]
                 }]
             }]
             total_chaps = 1
             
        status.write(f"✅ 解析完成：共 {len(full_text)} 字，{total_parts} 篇，{total_vols} 卷，{total_chaps} 章")
        status.write("📝 正在AI阅读正文生成简介...")
        
        synopsis = "暂无简介"
        assigned_key = engine.get_config_db("model_assignments", {}).get("import_char_analysis", FEATURE_MODELS["import_char_analysis"]['default'])
        client, model_name, _ = engine.get_client(assigned_key)
        
        if client and hasattr(engine, 'generate_synopsis_by_text'):
             try:
                 synopsis = engine.generate_synopsis_by_text(book_title, full_text, client, model_name)
                 if not synopsis or "功能已禁用" in synopsis: synopsis = "暂无简介 (AI未生成)"
             except Exception as e: synopsis = f"简介生成出错: {e}"
        
        db_mgr.execute("UPDATE books SET intro=? WHERE id=?", (synopsis, book_id))
        
        status.write("💾 正在写入数据库...")
        prog = st.progress(0)
        curr = 0
        
        for p_idx, part in enumerate(structure):
            part_id = db_mgr.execute(
                "INSERT INTO parts (book_id, name, sort_order) VALUES (?,?,?)", 
                (book_id, part['part_name'], (p_idx+1)*100)
            )
            
            for v_idx, vol in enumerate(part['volumes']):
                vol_id = db_mgr.execute(
                    "INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?,?,?,?)", 
                    (book_id, part_id, vol['vol_name'], (v_idx+1)*100)
                )
                
                for c_idx, chap in enumerate(vol['chapters']):
                    summary_text = f"字数:{len(chap['content'])}"
                    db_mgr.execute(
                        "INSERT INTO chapters (volume_id, title, content, summary, sort_order) VALUES (?,?,?,?,?)",
                        (vol_id, chap['title'], chap['content'], summary_text, c_idx+1)
                    )
                    curr += 1
                    if curr % 50 == 0 or curr == total_chaps: 
                        prog.progress(curr/total_chaps)
        
        prog.empty()
        ntp_time = get_ntp_time()
        db_mgr.execute("UPDATE books SET updated_at=? WHERE id=?", (ntp_time, book_id))
        
        status.update(label=f"🎉 导入成功！共 {total_chaps} 章", state="complete", expanded=False)
        
        # 🔥 日志记录：导入成功
        ensure_log_file()
        log_operation("书籍导入", f"成功导入《{book_title}》，共 {total_chaps} 章")
        
        st.success("书籍导入完成！")
        
        if 'char_data_cache' in st.session_state: del st.session_state['char_data_cache']
        if 'last_loaded_file' in st.session_state: del st.session_state['last_loaded_file']

    return 0, total_chaps

# ==============================================================================
# 🎨 UI 渲染
# ==============================================================================

def render_import_section(engine):
    db_mgr = st.session_state.db
    
    st.markdown("""
    <style>
    [data-testid="stFileUploaderDropzone"] { position: relative; text-align: center; }
    [data-testid="stFileUploaderDropzone"] > * { visibility: hidden !important; height: 0 !important; padding: 0 !important; margin: 0 !important; }
    [data-testid="stFileUploaderDropzone"]::before { content: "将 TXT 文件拖放到此处"; visibility: visible; position: absolute; top: 30%; left: 50%; transform: translate(-50%, -50%); color: #888; font-size: 14px; line-height: 1.5; z-index: 1; }
    [data-testid="stFileUploaderDropzone"]::after { content: "限 TXT 文件 (最大 200MB)"; visibility: visible; position: absolute; top: 70%; left: 50%; transform: translate(-50%, -50%); color: #aaa; font-size: 12px; z-index: 1; }
    </style>
    """, unsafe_allow_html=True)
    
    with st.expander("📥 导入书籍"):
        st.caption("支持 txt 格式，自动识别 篇-卷-章 结构。")
        uploaded_file = st.file_uploader(
            "TXT文件上传区", 
            type=["txt"], 
            key="import_file_real", 
            label_visibility="collapsed"
        )
        
        if uploaded_file:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.get('last_loaded_file') != file_id:
                new_title = os.path.splitext(uploaded_file.name)[0]
                st.session_state['import_book_title_ui'] = new_title
                st.session_state['last_loaded_file'] = file_id
                st.rerun()

        with st.form("form_import_action"):
            c1, c2 = st.columns(2)
            title_input = c1.text_input("书名 (必填)", key="import_book_title_ui")
            author_input = c2.text_input("作者", value="未知", key="import_book_author_ui")
            submitted = st.form_submit_button("🚀 开始导入", type="primary", use_container_width=True)
        
        if submitted:
            if not uploaded_file: st.error("请先上传 TXT 文件")
            elif not title_input.strip(): st.error("书名不能为空")
            else:
                bid = None 
                try:
                    now_str = get_ntp_time()
                    bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", 
                                         (title_input, author_input, "导入生成", now_str, now_str))
                    st.session_state.current_book_id = bid
                    _, total_chaps = _import_book_process(db_mgr, engine, uploaded_file, bid, title_input, author_input)
                    st.session_state['show_success_actions'] = True 
                except Exception as e:
                    if bid: db_mgr.execute("DELETE FROM books WHERE id=?", (bid,))
                    st.error(f"导入错误: {e}")
                    ensure_log_file()
                    log_operation("导入失败", str(e))
        
        if st.session_state.get('show_success_actions', False):
            st.session_state['show_success_actions'] = False

# ==============================================================================
# 📚 书籍管理主界面
# ==============================================================================

def render_books(engine):
    db_mgr = st.session_state.db
    ensure_export_dir() 
    
    render_header("📚", "书籍管理")
    render_import_section(engine) 
    
    with st.expander("✨ 手动创建新书", expanded=False):
        with st.form("form_new_book"):
            col1, col2 = st.columns(2)
            b_title = col1.text_input("书名")
            b_author = col2.text_input("作者", "我")
            b_intro = st.text_area("简介", height=100)
            c_sub1, c_sub2 = st.columns([1, 4])
            
            if c_sub1.form_submit_button("🚀 仅创建", use_container_width=True):
                if b_title:
                    now = get_ntp_time()
                    bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", (b_title, b_author, b_intro, now, now))
                    pid = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, '第一篇', 100)", (bid,))
                    db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, '第一卷', 100)", (bid, pid))
                    
                    # 🔥 日志记录：创建
                    ensure_log_file()
                    log_operation("书籍管理", f"手动创建新书: 《{b_title}》")
                    
                    st.success("创建成功")
                    st.rerun()
                else: st.error("书名不能为空")
            
            if c_sub2.form_submit_button("💡 创建并进入 AI 架构向导", type="secondary", use_container_width=True):
                if b_title:
                    now = get_ntp_time()
                    bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", (b_title, b_author, b_intro, now, now))
                    pid = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?, '第一篇', 100)", (bid,))
                    db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?, ?, '第一卷', 100)", (bid, pid))
                    
                    # 🔥 日志记录：创建并跳转
                    ensure_log_file()
                    log_operation("书籍管理", f"手动创建并跳转: 《{b_title}》")
                    
                    st.session_state.current_book_id = bid
                    st.success("创建成功，跳转中...")
                    st.session_state.current_menu = "structure"
                    st.rerun()
                else: st.error("书名不能为空")

    
    
    books = db_mgr.query("SELECT * FROM books ORDER BY updated_at DESC")
    if not books:
        st.info("暂无书籍。")
        return

    def parse_time(t_str):
        if not t_str: return "N/A"
        try: 
            t_str_clean = str(t_str).split('.')[0].replace('T', ' ')
            try:
                from datetime import datetime
                dt_obj = datetime.strptime(t_str_clean, '%Y-%m-%d %H:%M:%S')
                return dt_obj.strftime('%Y年%m月%d日 %H:%M')
            except ValueError: pass
            try:
                from datetime import datetime
                dt_obj = datetime.strptime(t_str_clean.split(' ')[0], '%Y-%m-%d')
                return dt_obj.strftime('%Y年%m月%d日')
            except ValueError: pass
            return str(t_str)
        except Exception: return str(t_str)

    def render_book_card(book):
        book = dict(book)
        book_id = book['id']
        book_title = book['title']
        
        book_categories = db_mgr.query("SELECT c.name FROM book_categories bc JOIN categories c ON bc.category_id = c.id WHERE bc.book_id = ?", (book_id,))
        genre_list = [c['name'] for c in book_categories]
        genre_value = " / ".join(genre_list) if genre_list else '未分类'
        
        created_time = parse_time(book.get('created_at'))
        updated_time = parse_time(book.get('updated_at'))
        
        file_path = get_cached_file_path(book_id, book['title'])
        size_label = None
        if os.path.exists(file_path):
            try:
                f_size = os.path.getsize(file_path) / 1024 
                size_label = f"{f_size:.1f}KB" if f_size < 1024 else f"{f_size/1024:.1f}MB"
            except: pass

        with st.container(border=True):
            c_head_L, c_head_R = st.columns([3, 1])
            with c_head_L:
                st.markdown(f"#### 📖 {book['title']}")
            with c_head_R:
                if size_label:
                    st.markdown(f"<div style='text-align: right; color: #888; font-size: 12px; margin-top: 5px;'>📦 {size_label}</div>", unsafe_allow_html=True)

            st.caption(f"作者: **{book['author']}** | 创建: {created_time} | 更新: {updated_time} | 分类: {genre_value}")
            
            if book['intro'] and book['intro'].strip():
                with st.popover("📄 查看简介", use_container_width=True):
                    st.write(book['intro'])
            else:
                st.button("暂无简介", key=f"no_intro_{book_id}", disabled=True, use_container_width=True)
            
            st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            
           
            if c1.button("✍️ 写作", key=f"ent_{book_id}", type="primary", use_container_width=True):
                ensure_log_file()
                log_operation("页面跳转", f"进入写作模式: 《{book_title}》 (ID:{book_id})")
                st.session_state.current_book_id = book_id
                st.session_state.current_menu = "write"
                st.rerun()
            
            
            if c2.button("📑 预览", key=f"view_{book_id}", use_container_width=True):
                 ensure_log_file()
                 log_operation("页面跳转", f"进入预览模式: 《{book_title}》 (ID:{book_id})")
                 st.session_state.current_book_id = book_id
                 st.session_state.current_menu = "chapters"
                 st.rerun()

            with c3:
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            
                            st.download_button(
                                label="📥 下载", 
                                data=f, 
                                file_name=os.path.basename(file_path), 
                                mime="text/plain", 
                                key=f"dl_final_{book_id}", 
                                use_container_width=True,
                                on_click=audit_download_callback,
                                args=(book_title, book_id)
                            )
                    except Exception:
                        if st.button("📦 重试", key=f"err_pack_{book_id}", use_container_width=True):
                            with st.spinner("修复中..."):
                                content = generate_book_content(db_mgr, book_id)
                                with open(file_path, "w", encoding='utf-8') as f: f.write(content)
                                # 🔥 日志记录：修复打包
                                ensure_log_file()
                                log_operation("数据打包", f"修复并重新打包: 《{book_title}》")
                            st.rerun()
                else:
                    if st.button("📦 打包", key=f"pack_{book_id}", use_container_width=True):
                        with st.spinner("生成中..."):
                            content = generate_book_content(db_mgr, book_id)
                            with open(file_path, "w", encoding='utf-8') as f: f.write(content)
                            # 🔥 日志记录：打包
                            ensure_log_file()
                            log_operation("数据打包", f"生成TXT包: 《{book_title}》")
                        st.rerun()

            if c4.button("🗑️ 删除", key=f"del_{book_id}", use_container_width=True):
                db_mgr.execute("DELETE FROM books WHERE id=?", (book_id,))
                if os.path.exists(file_path):
                    try: os.remove(file_path)
                    except: pass
                if f"dl_cache_{book_id}" in st.session_state: del st.session_state[f"dl_cache_{book_id}"]
                
                
                ensure_log_file()
                log_operation("书籍管理", f"删除书籍: 《{book_title}》 (ID:{book_id})")
                
                st.rerun()

    for i in range(0, len(books), 2):
        cols = st.columns(2)
        with cols[0]: render_book_card(books[i])
        if i+1 < len(books):
            with cols[1]: render_book_card(books[i+1])