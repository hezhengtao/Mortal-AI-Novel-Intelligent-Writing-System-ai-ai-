# mortal_write/views/structure.py

import streamlit as st
import time
from utils import (
    render_header, 
    generate_export_content_from_ids,
    log_operation,
    ensure_log_file
)

# ==============================================================================
#  CSS 样式注入 (美化阅读器 & 界面微调)
# ==============================================================================
def inject_custom_css():
    st.markdown("""
    <style>
    /* 移除 Expander 边框 */
    div[data-testid="stExpander"] details {
        border: none;
        background-color: transparent;
    }
    div[data-testid="stExpander"] details > summary {
        padding-left: 0; 
    }
    
    /* 仿书页阅读器样式 - 滚动优化版 */
    .book-page-container {
        background-color: #fcf6e5; /* 米黄色羊皮纸背景 */
        padding: 50px 60px;        /* 宽敞的内边距 */
        border-radius: 4px;
        border: 1px solid #e0d8c0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08); 
        
        font-family: "Georgia", "Songti SC", "SimSun", serif; 
        color: #2c2c2c;
        line-height: 1.8;
        font-size: 18px;
        white-space: pre-wrap; 
        
        /* 🔥 核心修复：固定高度 + 内部滚动 */
        height: 72vh;              /* 固定高度，占据屏幕约 72% */
        overflow-y: auto;          /* 内容超长时显示内部滚动条 */
        
        max-width: 850px;          /* 限制最大宽度 */
        margin: 0 auto;            /* 水平居中 */
    }

    /* 美化阅读器内部滚动条 - 羊皮纸风格 */
    .book-page-container::-webkit-scrollbar {
        width: 10px;               /* 滚动条宽度 */
    }
    .book-page-container::-webkit-scrollbar-track {
        background: rgba(0,0,0,0.02);
        border-radius: 4px;
    }
    .book-page-container::-webkit-scrollbar-thumb {
        background-color: #d6cbb0; /* 淡米色滑块 */
        border-radius: 5px;
        border: 2px solid #fcf6e5; /* 增加边框产生间隙感 */
    }
    .book-page-container::-webkit-scrollbar-thumb:hover {
        background-color: #c4b9a0;
    }

    /* 调整按钮对齐 */
    div[data-testid="column"] button {
        text-align: left !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 核心辅助逻辑
# ==============================================================================

def _ensure_schema(db_mgr):
    if st.session_state.get('struct_schema_checked', False): return
    try:
        db_mgr.execute("CREATE TABLE IF NOT EXISTS parts (id INTEGER PRIMARY KEY AUTOINCREMENT, book_id INTEGER, name TEXT, summary TEXT, sort_order INTEGER)")
        try: db_mgr.execute("ALTER TABLE volumes ADD COLUMN part_id INTEGER")
        except: pass
        st.session_state.struct_schema_checked = True
    except: pass

# 🔥 新增：下载审计回调
def audit_export_callback(action_type, details):
    try:
        ensure_log_file()
        log_operation(action_type, details)
    except: pass

def move_item_struct(db_mgr, table, item_id, direction, context_col, context_id):
    item = db_mgr.query(f"SELECT * FROM {table} WHERE id=?", (item_id,))
    if not item: return
    item = item[0]
    curr_ord = item['sort_order']
    
    op = '<' if direction == 'up' else '>'
    order_dir = 'DESC' if direction == 'up' else 'ASC'
    
    target = db_mgr.query(f"SELECT id, sort_order FROM {table} WHERE {context_col}=? AND sort_order {op} ? ORDER BY sort_order {order_dir} LIMIT 1", (context_id, curr_ord))
    
    if target:
        target = target[0]
        db_mgr.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (target['sort_order'], item_id))
        db_mgr.execute(f"UPDATE {table} SET sort_order=? WHERE id=?", (curr_ord, target['id']))
        # 🔥 修改：确保日志文件存在
        ensure_log_file()
        log_operation("架构调整", f"{table} ID:{item_id} {direction}")

def set_selection(node_type, node_id):
    st.session_state.struct_sel_type = node_type
    st.session_state.struct_sel_id = node_id
    # 切换时清理临时状态
    keys_to_clear = [k for k in st.session_state.keys() if k.startswith('prop_') or k.startswith('temp_content_')]

# ==============================================================================
# Dialogs (模态弹窗)
# ==============================================================================

if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

@dialog_decorator("新建节点")
def dialog_add_struct_node(type_label, parent_id, book_id=None):
    st.caption(f"正在创建新的 **{type_label}**")
    name_input = st.text_input("名称", key="struct_new_name")
    
    if st.button("确认创建", type="primary", use_container_width=True):
        if not name_input.strip():
            st.error("名称不能为空")
            return
        
        db_mgr = st.session_state.db
        try:
            if type_label == "篇":
                mx = db_mgr.query("SELECT MAX(sort_order) as m FROM parts WHERE book_id=?", (book_id,))[0]['m'] or 0
                db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?,?,?)", (book_id, name_input, mx+100))
                
            elif type_label == "卷":
                mx = db_mgr.query("SELECT MAX(sort_order) as m FROM volumes WHERE part_id=?", (parent_id,))[0]['m'] or 0
                db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?,?,?,?)", (st.session_state.current_book_id, parent_id, name_input, mx+100))
                
            elif type_label == "章":
                mx = db_mgr.query("SELECT MAX(sort_order) as m FROM chapters WHERE volume_id=?", (parent_id,))[0]['m'] or 0
                db_mgr.execute("INSERT INTO chapters (volume_id, title, summary, content, sort_order) VALUES (?,?,?,?,?)",
                               (parent_id, name_input, "", "", mx+1))
            
            ensure_log_file()
            log_operation("架构新建", f"新建{type_label}: {name_input}")
            st.session_state.rerun_flag = True
            st.rerun()
        except Exception as e:
            st.error(f"创建失败: {e}")

@dialog_decorator("📚 全局导出")
def dialog_global_export(book_id, book_title):
    db_mgr = st.session_state.db
    st.caption(f"导出 **{book_title}** 的章节内容")
    
    parts = db_mgr.query("SELECT id, name FROM parts WHERE book_id=? ORDER BY sort_order", (book_id,))
    
    if not parts:
        st.warning("本书暂无内容")
        return

    all_chapters_ordered = [] 
    chapter_options = {}      
    
    for part in parts:
        vols = db_mgr.query("SELECT id, name FROM volumes WHERE part_id=? ORDER BY sort_order", (part['id'],))
        for vol in vols:
            chaps = db_mgr.query("SELECT id, title FROM chapters WHERE volume_id=? ORDER BY sort_order", (vol['id'],))
            for chap in chaps:
                display_label = f"【{vol['name']}】 {chap['title']}"
                chapter_options[display_label] = chap['id']
                all_chapters_ordered.append(display_label)

    if not all_chapters_ordered:
        st.warning("本书暂无章节可导出。")
        return

    c_all, c_none = st.columns([1, 1])
    if c_all.button("全选所有", key="btn_exp_all", use_container_width=True):
        st.session_state["ms_global_export"] = all_chapters_ordered
        st.rerun()
    if c_none.button("清空选择", key="btn_exp_none", use_container_width=True):
        st.session_state["ms_global_export"] = []
        st.rerun()
        
    selected_labels = st.multiselect(
        "勾选要导出的章节",
        options=all_chapters_ordered,
        default=st.session_state.get("ms_global_export", []), 
        key="ms_global_export",
        placeholder="请选择要导出的章节..."
    )
    
    st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
    
    if not selected_labels:
        st.button("请至少选择一章", disabled=True, use_container_width=True)
    else:
        target_ids = [chapter_options[label] for label in selected_labels]
        ordered_target_ids = []
        for label in all_chapters_ordered:
            if label in selected_labels:
                ordered_target_ids.append(chapter_options[label])
        
        txt_content = generate_export_content_from_ids(db_mgr, ordered_target_ids)
        
        col_dl, col_close = st.columns([2, 1])
        with col_dl:
            
            st.download_button(
                label=f"📥 下载 ({len(selected_labels)}章)",
                data=txt_content,
                file_name=f"{book_title}_导出.txt",
                mime="text/plain",
                type="primary",
                use_container_width=True,
                on_click=audit_export_callback,
                args=("数据导出", f"全局导出书籍: 《{book_title}》 (共{len(selected_labels)}章)")
            )
        with col_close:
             if st.button("关闭", use_container_width=True):
                 st.rerun()


@dialog_decorator("⚠️ 删除确认")
def dialog_delete_confirm(node_type, node_id, node_name):
    st.warning(f"确定要删除 {node_name} 吗？")
    
    if node_type == 'part':
        st.error("❌ 警告：此操作将删除该篇下的所有 卷 和 章节！")
    elif node_type == 'vol':
        st.error("❌ 警告：此操作将删除该卷下的所有 章节！")
    
    st.markdown("此操作 **无法撤销**，所有数据将从数据库中移除。")
    
    col_cancel, col_confirm = st.columns([1, 1])
    with col_cancel:
        if st.button("取消", use_container_width=True):
            st.rerun()
            
    with col_confirm:
        if st.button("确认删除", type="primary", use_container_width=True):
            db_mgr = st.session_state.db
            if node_type == 'part':
                vols = db_mgr.query("SELECT id FROM volumes WHERE part_id=?", (node_id,))
                for v in vols:
                    db_mgr.execute("DELETE FROM chapters WHERE volume_id=?", (v['id'],))
                db_mgr.execute("DELETE FROM volumes WHERE part_id=?", (node_id,))
                db_mgr.execute("DELETE FROM parts WHERE id=?", (node_id,))
            elif node_type == 'vol':
                db_mgr.execute("DELETE FROM chapters WHERE volume_id=?", (node_id,))
                db_mgr.execute("DELETE FROM volumes WHERE id=?", (node_id,))
            elif node_type == 'chap':
                db_mgr.execute("DELETE FROM chapters WHERE id=?", (node_id,))
            
           
            ensure_log_file()
            log_operation("架构删除", f"删除 {node_type} ID:{node_id}")
            st.session_state.struct_sel_id = None
            st.session_state.struct_sel_type = None
            st.rerun()


@dialog_decorator("💾 保存确认")
def dialog_save_confirm(node_type, node_id, new_data):
    st.markdown(f"**正在保存 {new_data['name']}**")
    
    if node_type == 'chap':
        content_len = len(new_data.get('content', ''))
        st.markdown(f"当前正文字数: `{content_len}`")
        if content_len > 0:
            st.caption("正文预览: " + (new_data['content'][:50] + "..." if new_data['content'] else ""))
            
    st.info("确定要应用修改吗？")
    
    col_c, col_s = st.columns([1, 1])
    with col_c:
        if st.button("取消", use_container_width=True):
            st.rerun()
    with col_s:
        if st.button("确认保存", type="primary", use_container_width=True):
            db_mgr = st.session_state.db
            try:
                if node_type == 'part':
                    db_mgr.execute("UPDATE parts SET name=?, summary=? WHERE id=?", (new_data['name'], new_data['summary'], node_id))
                elif node_type == 'vol':
                    db_mgr.execute("UPDATE volumes SET name=? WHERE id=?", (new_data['name'], node_id))
                elif node_type == 'chap':
                    db_mgr.execute("UPDATE chapters SET title=?, summary=?, content=? WHERE id=?", (new_data['name'], new_data['summary'], new_data['content'], node_id))
                
                # 🔥 修改：确保日志文件存在
                ensure_log_file()
                log_operation("架构更新", f"更新 {node_type} ID:{node_id}")
                st.toast("✅ 已保存")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"保存失败: {e}")

# ==============================================================================
# 左侧目录树渲染逻辑
# ==============================================================================

def render_tree_view(db_mgr, current_book_id):
    parts = db_mgr.query("SELECT * FROM parts WHERE book_id=? ORDER BY sort_order", (current_book_id,))
    
    if not parts:
        st.info("暂无内容，请新建篇章")
        return

    for part in parts:
        with st.expander(f"{part['name']}", expanded=False):
            c1, c2 = st.columns([1, 1])
            if c1.button("编辑信息", key=f"btn_ed_p_{part['id']}", use_container_width=True):
                # 修改：添加浏览日志
                ensure_log_file()
                log_operation("查看节点", f"查看篇信息: {part['name']}")
                set_selection('part', part['id'])
                st.rerun()
            if c2.button("新建卷", key=f"btn_add_v_{part['id']}", use_container_width=True):
                dialog_add_struct_node("卷", part['id'])
            
            st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

            vols = db_mgr.query("SELECT id, name FROM volumes WHERE part_id=? ORDER BY sort_order", (part['id'],))
            for vol in vols:
                with st.expander(f"{vol['name']}", expanded=False):
                    cv1, cv2 = st.columns([1, 1])
                    if cv1.button("编辑信息", key=f"btn_ed_v_{vol['id']}", use_container_width=True):
                        # 修改：添加浏览日志
                        ensure_log_file()
                        log_operation("查看节点", f"查看卷信息: {vol['name']}")
                        set_selection('vol', vol['id'])
                        st.rerun()
                    if cv2.button("新建章", key=f"btn_add_c_{vol['id']}", use_container_width=True):
                        dialog_add_struct_node("章", vol['id'])

                    st.markdown("<div style='height: 5px'></div>", unsafe_allow_html=True)

                    chaps = db_mgr.query("SELECT id, title FROM chapters WHERE volume_id=? ORDER BY sort_order", (vol['id'],))
                    if not chaps:
                        st.caption("  (暂无章节)")
                    else:
                        for chap in chaps:
                            is_active = (st.session_state.get('struct_sel_type') == 'chap' and st.session_state.get('struct_sel_id') == chap['id'])
                            type_ = "primary" if is_active else "secondary"
                            if st.button(f"{chap['title']}", key=f"btn_c_{chap['id']}", use_container_width=True, type=type_):
                                #  修改：添加阅读日志
                                ensure_log_file()
                                log_operation("阅读章节", f"在架构页阅读章节: {chap['title']}")
                                set_selection('chap', chap['id'])
                                st.rerun()
                st.markdown("<div style='height: 5px'></div>", unsafe_allow_html=True)

# ==============================================================================
# 📝右侧属性面板逻辑 (含顶部操作栏)
# ==============================================================================

def render_properties_panel(db_mgr, current_book_id):
    sel_type = st.session_state.get('struct_sel_type')
    sel_id = st.session_state.get('struct_sel_id')
    
    if not sel_type or not sel_id:
        st.info("👈 请从左侧目录选择一个节点进行编辑")
        return

    table_map = {'part': 'parts', 'vol': 'volumes', 'chap': 'chapters'}
    table = table_map.get(sel_type)
    data = None
    if table:
        res = db_mgr.query(f"SELECT * FROM {table} WHERE id=?", (sel_id,))
        if res: data = dict(res[0])

    if not data:
        st.warning("节点不存在")
        st.session_state.struct_sel_type = None
        st.rerun()
        return

    # --- 数据准备 ---
    db_name = data.get('name') or data.get('title')
    db_summary = data.get('summary', '')
    db_content = data.get('content', '') or ""
    
    # 构造 Session State Key
    key_name = f"prop_name_{sel_type}_{sel_id}"
    key_sum = f"prop_sum_{sel_type}_{sel_id}"
    key_cont = f"prop_content_{sel_id}"

    # --- 顶栏：标题 + 核心操作 ---
    type_name_map = {'part': '篇', 'vol': '卷', 'chap': '章节'}
    st.subheader(f"{type_name_map[sel_type]}详情")
    
    c_tools_1, c_tools_2, c_tools_3 = st.columns([1.5, 1, 1.5])
    
    with c_tools_1:
        # 保存按钮
        if st.button("💾 保存修改", type="primary", use_container_width=True, key="top_btn_save"):
            current_input_name = st.session_state.get(key_name, db_name)
            current_input_summary = st.session_state.get(key_sum, db_summary)
            current_input_content = st.session_state.get(key_cont, db_content)
            
            save_data = {
                'name': current_input_name,
                'summary': current_input_summary,
                'content': current_input_content if sel_type == 'chap' else None
            }
            dialog_save_confirm(sel_type, sel_id, save_data)

    with c_tools_2:
        # 删除按钮
        if st.button("🗑️ 删除", type="secondary", use_container_width=True, key="top_btn_del"):
            dialog_delete_confirm(sel_type, sel_id, db_name)
            
    with c_tools_3:
        if sel_type == 'chap':
            # 修改：绑定下载审计回调
            st.download_button(
                "📥 导出此章", 
                data=f"{db_name}\n\n{db_content}", 
                file_name=f"{db_name}.txt", 
                use_container_width=True,
                on_click=audit_export_callback,
                args=("数据导出", f"单章导出: {db_name}")
            )
            
    st.markdown("---")

    # --- 1. 基本信息编辑区 ---
    try:
        col_edit, col_sort = st.columns([3, 1], vertical_alignment="bottom")
    except TypeError:
        col_edit, col_sort = st.columns([3, 1])
        with col_sort: st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    
    with col_edit:
        st.text_input("标题 / 名称", value=db_name, key=key_name)
        
    with col_sort:
        b1, b2 = st.columns(2)
        context_map = {'part': ('book_id', data.get('book_id')), 
                       'vol': ('part_id', data.get('part_id')), 
                       'chap': ('volume_id', data.get('volume_id'))}
        with b1:
            if st.button("⬆", key="btn_mv_up", help="上移", use_container_width=True):
                ctx_col, ctx_id = context_map[sel_type]
                move_item_struct(db_mgr, table, sel_id, 'up', ctx_col, ctx_id)
                st.rerun()
        with b2:
            if st.button("⬇", key="btn_mv_down", help="下移", use_container_width=True):
                ctx_col, ctx_id = context_map[sel_type]
                move_item_struct(db_mgr, table, sel_id, 'down', ctx_col, ctx_id)
                st.rerun()

    if sel_type in ['part', 'chap']:
        st.text_area("简介 / 摘要", value=db_summary, height=80, key=key_sum)

    # --- 2. 章节正文 (阅读器优化：居中显示) ---
    if sel_type == 'chap':
        st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
        
        # 模式切换
        mode = st.radio("视图模式", ["👁️ 预览阅读", "✏️ 编辑模式"], horizontal=True, label_visibility="collapsed")
        
        if mode == "👁️ 预览阅读":
            # 渲染美化后、居中显示的书页
            display_text = db_content if db_content else "(暂无内容，请切换到编辑模式撰写)"
            st.markdown(f"""
            <div class="book-page-container">
            {display_text}
            </div>
            """, unsafe_allow_html=True)
            # 确保 key 存在，防止切换模式时报错
            if key_cont not in st.session_state: st.session_state[key_cont] = db_content
            
        else:
            # 编辑模式
            st.text_area(
                "正文内容", 
                value=db_content, 
                height=500, 
                key=key_cont,
                label_visibility="collapsed",
                placeholder="在此处撰写章节正文..."
            )

# ==============================================================================
# 主渲染入口
# ==============================================================================

def render_structure(engine, current_book):
    inject_custom_css()
    db_mgr = st.session_state.db
    _ensure_schema(db_mgr)
    
    render_header("架构管理", "") 

    all_books = db_mgr.query("SELECT id, title FROM books")
    if not all_books:
        st.warning("请先在书籍管理中创建书籍。")
        return
        
    col_tree, col_props = st.columns([1.5, 2.5], gap="medium")
    
    with col_tree:
        book_opts = {b['title']: b['id'] for b in all_books}
        default_idx = 0
        if st.session_state.current_book_id in book_opts.values():
             default_idx = list(book_opts.values()).index(st.session_state.current_book_id)
        
        selected_title = st.selectbox("当前书籍", list(book_opts.keys()), index=default_idx, label_visibility="collapsed", key="struct_book_sel")
        selected_book_id = book_opts[selected_title]
        
        # 修改：添加书籍切换日志
        if selected_book_id != st.session_state.current_book_id:
            ensure_log_file()
            log_operation("页面跳转", f"架构页切换书籍: 《{selected_title}》")
            
            st.session_state.current_book_id = selected_book_id
            st.session_state.struct_sel_id = None
            st.session_state.struct_sel_type = None
            st.rerun()
            
        c_add, c_exp = st.columns([1, 1])
        with c_add:
            if st.button("➕ 新建篇", key="root_add_p_btn", use_container_width=True):
                dialog_add_struct_node("篇", None, selected_book_id)
        with c_exp:
            if st.button("📤 导出", key="root_exp_btn", use_container_width=True):
                dialog_global_export(selected_book_id, selected_title)
                
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        render_tree_view(db_mgr, selected_book_id)

    with col_props:
        render_properties_panel(db_mgr, selected_book_id)