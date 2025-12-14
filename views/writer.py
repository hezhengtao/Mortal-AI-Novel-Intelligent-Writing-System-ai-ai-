# mortal_write/views/writer.py

import streamlit as st
import time
import pandas as pd
from utils import (
    render_header, 
    update_chapter_title_db, 
    update_chapter_summary_db,
    resequence_chapters,
    log_operation,      
    ensure_log_file     
)

from logic import FEATURE_MODELS, MODEL_MAPPING

# ==============================================================================
# Helpers
# ==============================================================================
def get_safe_model_default(feature_key, hard_coded_default):
    if feature_key in FEATURE_MODELS:
        return FEATURE_MODELS[feature_key].get('default', hard_coded_default)
    return hard_coded_default

def _ensure_part_volume_schema(db_mgr):
    if st.session_state.get('schema_checked', False): return
    try:
        db_mgr.execute("""
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                book_id INTEGER, name TEXT, summary TEXT, sort_order INTEGER
            )
        """)
        try: db_mgr.query("SELECT part_id FROM volumes LIMIT 1")
        except: 
            try: db_mgr.execute("ALTER TABLE volumes ADD COLUMN part_id INTEGER")
            except: pass
        st.session_state.schema_checked = True
    except Exception: pass

def _update_chapter_title_db_logged(chap_id, new_title_key):
    new_title = st.session_state[new_title_key]
    db_mgr = st.session_state.db
    if new_title:
        db_mgr.execute("UPDATE chapters SET title=? WHERE id=?", (new_title, chap_id))
        db_mgr.update_book_timestamp(st.session_state.current_book_id)
        st.session_state.chapter_title_cache[chap_id] = new_title
        ensure_log_file()
        log_operation("章节管理", f"重命名章节 ID:{chap_id} 为 {new_title}")
        st.session_state.rerun_flag = True

def _update_chapter_summary_db_logged(chap_id, new_summary_key):
    new_summary = st.session_state[new_summary_key]
    db_mgr = st.session_state.db
    db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (new_summary, chap_id))
    db_mgr.update_book_timestamp(st.session_state.current_book_id)
    ensure_log_file()
    log_operation("章节管理", f"更新章节大纲 ID:{chap_id}")
    st.session_state.rerun_flag = True


if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

@dialog_decorator("💾 保存确认")
def dialog_save_chapter_content(db_mgr, chapter_id, new_content, book_id, chapter_title):
    st.markdown(f"""
    <div style="margin-bottom: 15px;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
            <span style="font-size: 1.1rem; font-weight: 600; color: #333;">{chapter_title}</span>
            <span style="background-color: #ffebee; color: #c62828; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; border: 1px solid #ffcdd2;">
                未保存
            </span>
        </div>
        <div style="color: #666; font-size: 0.9rem;">
            当前字数: <span style="font-family: monospace; font-weight: bold;">{len(new_content)}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.warning("⚠️ 确定要覆盖原有内容吗？此操作无法撤销。")
    
    col_cancel, col_confirm = st.columns([1, 1.5])
    
    with col_cancel:
        if st.button("取消", type="secondary", use_container_width=True):
            st.rerun()

    with col_confirm:
        if st.button("确认保存", type="primary", use_container_width=True):
            try:
                db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (new_content, chapter_id)) 
                db_mgr.update_book_timestamp(book_id)
                
                ensure_log_file()
                log_operation("更新章节", f"保存正文: {chapter_title}")
                
                st.session_state.rerun_flag = True
                st.toast("✅ 已保存")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"保存失败: {e}")

@dialog_decorator("➕ 新建")
def dialog_add_node(type_label, parent_id, book_id=None):
    st.caption(f"正在创建新的 **{type_label}**")
    name_input = st.text_input("名称", key="dialog_name_input")
    
    if st.button("确认创建", type="primary", use_container_width=True):
        if not name_input.strip():
            st.error("名称不能为空")
            return
        
        db_mgr = st.session_state.db
        if type_label == "篇":
            mx = db_mgr.query("SELECT MAX(sort_order) as m FROM parts WHERE book_id=?", (book_id,))[0]['m'] or 0
            db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?,?,?)", (book_id, name_input, mx+100))
        elif type_label == "卷":
            mx = db_mgr.query("SELECT MAX(sort_order) as m FROM volumes WHERE part_id=?", (parent_id,))[0]['m'] or 0
            db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?,?,?,?)", (st.session_state.current_book_id, parent_id, name_input, mx+100))
            if 'expanded_parts' not in st.session_state: st.session_state.expanded_parts = set()
            st.session_state.expanded_parts.add(parent_id)
        elif type_label == "章":
            mx = db_mgr.query("SELECT MAX(sort_order) as m FROM chapters WHERE volume_id=?", (parent_id,))[0]['m'] or 0
            cid = db_mgr.execute("INSERT INTO chapters (volume_id, title, summary, content, sort_order) VALUES (?,?,?,?,?)",
                           (parent_id, name_input, "", "", mx+1))
            st.session_state.current_chapter_id = cid
            if 'expanded_volumes' not in st.session_state: st.session_state.expanded_volumes = set()
            st.session_state.expanded_volumes.add(parent_id)
        
        ensure_log_file()
        log_operation("结构管理", f"新建{type_label}: {name_input}")
        st.session_state.rerun_flag = True
        st.rerun()

@dialog_decorator("⚙️ 管理")
def dialog_manage_node(type_label, node_id, current_name):
    st.caption(f"正在管理 {type_label}: **{current_name}**")
    new_name = st.text_input("重命名", value=current_name)
    
    c1, c2 = st.columns(2)
    if c1.button("💾 保存修改", type="primary", use_container_width=True):
        db_mgr = st.session_state.db
        table = "parts" if type_label == "篇" else "volumes"
        db_mgr.execute(f"UPDATE {table} SET name=? WHERE id=?", (new_name, node_id))
        log_operation("结构管理", f"重命名{type_label}: {current_name} -> {new_name}")
        st.rerun()
        
    if c2.button("🗑️ 删除", type="secondary", use_container_width=True):
        db_mgr = st.session_state.db
        table = "parts" if type_label == "篇" else "volumes"
        db_mgr.execute(f"DELETE FROM {table} WHERE id=?", (node_id,))
        if type_label == "篇" and node_id in st.session_state.get('expanded_parts', set()):
            st.session_state.expanded_parts.remove(node_id)
        if type_label == "卷" and node_id in st.session_state.get('expanded_volumes', set()):
            st.session_state.expanded_volumes.remove(node_id)
        log_operation("结构管理", f"删除{type_label}: {current_name}")
        st.rerun()


def toggle_state(key, item_id):
    if key not in st.session_state: st.session_state[key] = set()
    if item_id in st.session_state[key]:
        st.session_state[key].remove(item_id)
    else:
        st.session_state[key].add(item_id)

def render_explorer_node_part(db_mgr, part, current_book_id):
    if 'expanded_parts' not in st.session_state: st.session_state.expanded_parts = set()
    is_expanded = part['id'] in st.session_state.expanded_parts
    icon = "📂" if not is_expanded else "📖"
    if st.button(f"{icon} {part['name']}", key=f"p_btn_{part['id']}", use_container_width=True):
        toggle_state('expanded_parts', part['id'])
        st.rerun()
    if is_expanded:
        st.markdown("""<div style="margin-top: -12px; margin-bottom: 5px;"></div>""", unsafe_allow_html=True)
        c_i, c_act1, c_act2 = st.columns([0.1, 1, 1])
        with c_act1:
            if st.button("➕ 加卷", key=f"add_v_{part['id']}", help="在此篇下新建卷", use_container_width=True):
                dialog_add_node("卷", part['id'])
        with c_act2:
            if st.button("⚙️ 管理", key=f"mng_p_{part['id']}", help="重命名或删除此篇", use_container_width=True):
                dialog_manage_node("篇", part['id'], part['name'])
        vols = db_mgr.query("SELECT id, name, part_id FROM volumes WHERE part_id=? ORDER BY sort_order", (part['id'],))
        if not vols:
            st.markdown("<div style='padding-left: 15px; color: gray; font-size: 12px; margin-bottom: 10px;'>└─ (暂无卷)</div>", unsafe_allow_html=True)
        else:
            for vol in vols:
                render_explorer_node_volume(db_mgr, vol)
        st.markdown("""<div style="margin-bottom: 10px;"></div>""", unsafe_allow_html=True)

def render_explorer_node_volume(db_mgr, vol):
    if 'expanded_volumes' not in st.session_state: st.session_state.expanded_volumes = set()
    is_expanded = vol['id'] in st.session_state.expanded_volumes
    icon = "📁" if not is_expanded else "📂"
    c_indent, c_main = st.columns([0.2, 5.8])
    with c_main:
        if st.button(f"{icon} {vol['name']}", key=f"v_btn_{vol['id']}", use_container_width=True):
            toggle_state('expanded_volumes', vol['id'])
            st.rerun()
    if is_expanded:
        st.markdown("""<div style="margin-top: -12px; margin-bottom: 5px;"></div>""", unsafe_allow_html=True)
        c_i, c_act1, c_act2 = st.columns([0.3, 1, 1])
        with c_act1:
            if st.button("➕ 加章", key=f"add_c_{vol['id']}", use_container_width=True):
                dialog_add_node("章", vol['id'])
        with c_act2:
            if st.button("⚙️ 管理", key=f"mng_v_{vol['id']}", use_container_width=True):
                dialog_manage_node("卷", vol['id'], vol['name'])
        chaps = db_mgr.query("SELECT id, title FROM chapters WHERE volume_id=? ORDER BY sort_order", (vol['id'],))
        if not chaps:
            st.markdown("<div style='padding-left: 35px; color: gray; font-size: 12px;'>└─ (暂无章节)</div>", unsafe_allow_html=True)
        else:
            st.markdown("""
            <style>
            div[data-testid="stVerticalBlock"] > div > button.chap-btn {
                text-align: left; padding-left: 35px !important; border: none; font-size: 14px;
            }
            </style>
            """, unsafe_allow_html=True)
            with st.container():
                for chap in chaps:
                    is_active = (st.session_state.get('current_chapter_id') == chap['id'])
                    display_title = st.session_state.chapter_title_cache.get(chap['id'], chap['title'])
                    
                    label = f"　　{display_title}"
                    b_type = "primary" if is_active else "secondary"
                    
                    if st.button(label, key=f"c_{chap['id']}", use_container_width=True, type=b_type):
                        ensure_log_file()
                        log_operation("阅读章节", f"切换章节: {display_title} (ID:{chap['id']})")
                        
                        st.session_state.current_chapter_id = chap['id']
                        st.session_state.current_part_id = vol['part_id']
                        st.rerun()
        st.markdown("""<div style="margin-bottom: 8px;"></div>""", unsafe_allow_html=True)



def render_writer(engine, current_book, current_chapter):
    db_mgr = st.session_state.db
    _ensure_part_volume_schema(db_mgr)
    
    if 'generation_running' not in st.session_state: st.session_state.generation_running = False
    
    st.session_state.model_assignments = engine.get_config_db("model_assignments", {})

    if not current_book:
        st.warning("请先在 [书籍管理] 中选择一本书")
        return
        
    render_header("✍️", current_book['title'])
    
    st.markdown("""
    <style>
    div[data-testid="column"]:nth-of-type(1) button {
        border: 0px solid transparent !important; background: transparent !important; box-shadow: none !important; text-align: left !important;
    }
    div[data-testid="column"]:nth-of-type(1) button:hover {
        background-color: rgba(150, 150, 150, 0.1) !important; color: #3eaf7c !important;
    }
    div[data-testid="column"]:nth-of-type(1) button[kind="primary"] {
        background-color: rgba(62, 175, 124, 0.15) !important; border-left: 3px solid #3eaf7c !important; color: #3eaf7c !important; padding-left: 8px !important;
    }
    div[data-testid="column"]:nth-of-type(1) button[title="在此篇下新建卷"],
    div[data-testid="column"]:nth-of-type(1) button[title="在此卷下新建章"] {
        color: #888 !important; font-size: 12px !important; height: auto !important; padding: 2px 5px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col_explorer, col_editor = st.columns([1.4, 2.6], gap="medium")
    
    
    with col_explorer:
        all_books = db_mgr.query("SELECT id, title FROM books")
        opts = {b['title']: b['id'] for b in all_books}
        idx = list(opts.values()).index(current_book['id']) if current_book['id'] in opts.values() else 0
        sel_title = st.selectbox("当前书籍", list(opts.keys()), index=idx, label_visibility="collapsed", key="write_book_selector")
        
        if opts[sel_title] != current_book['id']:
            ensure_log_file()
            log_operation("页面跳转", f"在写作台切换书籍: 《{sel_title}》")
            
            st.session_state.current_book_id = opts[sel_title]
            st.session_state.current_chapter_id = None 
            st.session_state.current_part_id = None
            st.rerun()
        
        c_label, c_add = st.columns([4, 2])
        with c_label: st.caption("🗂️ 目录结构")
        with c_add:
            if st.button("➕ 新建篇", key="root_add_p_btn", use_container_width=True):
                dialog_add_node("篇", None, current_book['id'])
        parts = db_mgr.query("SELECT id, name FROM parts WHERE book_id=? ORDER BY sort_order", (current_book['id'],))
        if not parts: st.info("暂无内容，请点击上方“新建篇”")
        else:
            for part in parts: render_explorer_node_part(db_mgr, part, current_book['id'])

   
    with col_editor:
        tab_write, tab_outline, tab_assist = st.tabs(["📝 沉浸写作", "🧠 AI 批量生成", "✨ 写作辅助"])
        
     
        with tab_write:
            if not current_chapter:
                st.info("👈 请先从左侧选择一个章节。")
            else:
                title_key = f"chap_title_{current_chapter['id']}"
                st.text_input("章节标题", current_chapter['title'], key=title_key, on_change=_update_chapter_title_db_logged, args=(current_chapter['id'], title_key))
                
                st.markdown("##### 🤖 沉浸写作 (快速生成)")
                current_summary = current_chapter['summary'] or ""
                outline_key = f"ai_outline_input_{current_chapter['id']}"
                outline_input = st.text_area("本章大纲/提示词", current_summary, height=80, key=outline_key, on_change=_update_chapter_summary_db_logged, args=(current_chapter['id'], outline_key))
                
                c_m, c_l, c_b = st.columns([1.2, 1.2, 1.6]) 
                with c_m:
                    def_write = get_safe_model_default("write_quick_gen", "DSK_V3")
                    assigned_write = st.session_state.model_assignments.get("write_quick_gen", def_write)
                    
                    model_display_name = MODEL_MAPPING.get(assigned_write, {}).get('name', assigned_write)
                    
                    st.markdown(f"**模型**")
                    st.caption(f"🚀 {model_display_name}")
                    
                    model_pk = assigned_write if assigned_write in MODEL_MAPPING else None
                
                with c_l:
                    content_len = st.slider("字数(k)", 1, 10, 3)

                with c_b:
                    st.markdown('<div style="padding-top: 29px;"></div>', unsafe_allow_html=True)
                    b1, b2 = st.columns(2)
                    with b1:
                        btn_gen = st.button("🚀 生成", type="primary", disabled=st.session_state.generation_running, use_container_width=True)
                    with b2:
                        btn_stop = st.button("🛑 停止", type="secondary", disabled=not st.session_state.generation_running, use_container_width=True)

                if btn_gen and model_pk:
                    client, m_name, m_key = engine.get_client(model_pk)
                    if not client: st.error("API Key 未配置")
                    else:
                        db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (outline_input, current_chapter['id']))
                        st.session_state.generation_running = True
                        
                        ensure_log_file()
                        log_operation("AI生成", f"开始生成章节: {current_chapter['title']} (模型: {m_name})")
                        
                        with st.spinner("AI 正在运笔..."):
                            ok, stream = engine.generate_content_from_outline_ai_stream(current_chapter['id'], outline_input, current_book, content_len*1000, client, m_name, m_key)
                            if ok:
                                buf = ""
                                res_area = st.empty()
                                for chunk in stream:
                                    if not st.session_state.generation_running: break
                                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                                        buf += chunk.choices[0].delta.content
                                        res_area.markdown(f"_{buf}_")
                                full_new = (current_chapter['content'] or "") + "\n" + buf
                                db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (full_new, current_chapter['id']))
                                db_mgr.update_book_timestamp(current_book['id'])
                                
                                log_operation("AI生成", f"生成完成: {current_chapter['title']} (新增约 {len(buf)} 字)")
                                st.session_state.generation_running = False
                                st.rerun()
                            else:
                                st.error(f"生成失败: {stream}")
                                log_operation("AI错误", f"章节生成失败: {stream}")
                                st.session_state.generation_running = False
                
                if btn_stop:
                    st.session_state.generation_running = False
                    log_operation("AI生成", "用户手动停止生成")
                    st.rerun()

                content_key = f"chapter_content_{current_chapter['id']}"
                current_text_val = st.session_state.get(content_key, current_chapter['content'] or "")
                
                c_tool_1, c_tool_2 = st.columns([3, 1])
                with c_tool_1:
                    st.caption(f"✍️ 正文编辑 (当前字数: {len(current_text_val)})")
                with c_tool_2:
                    if st.button("💾 保存正文", use_container_width=True, help="点击保存当前正文内容"):
                        content_to_save = st.session_state.get(content_key, current_chapter['content'] or "")
                        dialog_save_chapter_content(db_mgr, current_chapter['id'], content_to_save, current_book['id'], current_chapter['title'])

                st.text_area(
                    "正文内容", 
                    value=current_chapter['content'] or "", 
                    height=600, 
                    label_visibility="collapsed", 
                    key=content_key
                )

       
        with tab_outline:
             if not current_book: st.warning("请选择书籍")
             elif not parts: st.warning("无结构")
             else:
                st.subheader("✍️ 批量生成")
                default_p_idx = 0
                default_v_idx = 0
                part_opts = {p['name']: p['id'] for p in parts}
                if current_chapter:
                    curr_vol = db_mgr.query("SELECT * FROM volumes WHERE id=?", (current_chapter['volume_id'],))[0]
                    if curr_vol['part_id'] in part_opts.values():
                        default_p_idx = list(part_opts.values()).index(curr_vol['part_id'])
                
                c_p, c_v = st.columns(2)
                sel_p_name = c_p.selectbox("选择篇", list(part_opts.keys()), index=default_p_idx, key="bg_p")
                sel_p_id = part_opts[sel_p_name]
                bg_vols = db_mgr.query("SELECT * FROM volumes WHERE part_id=? ORDER BY sort_order", (sel_p_id,))
                
                if not bg_vols: st.warning("该篇无卷")
                else:
                    bg_v_opts = {v['name']: v['id'] for v in bg_vols}
                    if current_chapter and current_chapter['volume_id'] in bg_v_opts.values():
                        default_v_idx = list(bg_v_opts.values()).index(current_chapter['volume_id'])
                    sel_v_name = c_v.selectbox("选择卷", list(bg_v_opts.keys()), index=default_v_idx, key="bg_v")
                    sel_v_id = bg_v_opts[sel_v_name]
                    bg_chaps = db_mgr.query("SELECT id, title FROM chapters WHERE volume_id=? ORDER BY sort_order", (sel_v_id,))
                    
                    if not bg_chaps: st.info("该卷无章节")
                    else:
                        c_names = [c['title'] for c in bg_chaps]
                        c1, c2 = st.columns(2)
                        s_start = c1.selectbox("起始章", c_names, 0, key="bg_s")
                        s_idx = c_names.index(s_start)
                        s_end = c2.selectbox("结束章", c_names[s_idx:], len(c_names[s_idx:])-1, key="bg_e")
                        e_idx = c_names.index(s_end)
                        target_chaps = bg_chaps[s_idx:e_idx+1]
                        
                        st.info(f"选中范围: {s_start} ~ {s_end} (共 {len(target_chaps)} 章)")
                        gen_prompt = st.text_area("通用大纲/指令", height=100, placeholder="例如：主角在这一段剧情中...")
                        
                        cm1, cm2, cm3 = st.columns([1, 1, 1])
                        with cm1:
                            def_b = get_safe_model_default("write_batch_gen", "GPT_4o")
                            assigned_b = st.session_state.model_assignments.get("write_batch_gen", def_b)
                            
                            model_display_name_b = MODEL_MAPPING.get(assigned_b, {}).get('name', assigned_b)
                            
                            st.markdown(f"**模型**")
                            st.caption(f"🚀 {model_display_name_b}")
                            
                            pk_b = assigned_b if assigned_b in MODEL_MAPPING else None

                        with cm2:
                            len_b = st.slider("单章字数(k)", 1, 10, 3, key="bg_l")
                        with cm3:
                            st.markdown('<div style="padding-top: 29px;"></div>', unsafe_allow_html=True)
                            btn_bg = st.button("🚀 开始批量", type="primary", use_container_width=True, disabled=st.session_state.generation_running)
                        
                        if btn_bg and pk_b:
                            if not gen_prompt.strip(): st.error("请输入大纲")
                            else:
                                client, m_name, m_key = engine.get_client(pk_b)
                                if not client: st.error("API Key 未配置")
                                else:
                                    st.session_state.generation_running = True
                                    ph = st.empty()
                                    cnt = 0
                                    
                                    ensure_log_file()
                                    log_operation("AI批量", f"开始批量生成 {len(target_chaps)} 章")
                                    
                                    try:
                                        for idx, ch in enumerate(target_chaps):
                                            if not st.session_state.generation_running: 
                                                ph.warning("已停止"); break
                                            ph.info(f"⏳ ({idx+1}/{len(target_chaps)}) 生成：{ch['title']}...")
                                            prompt = f"【批量指令】{gen_prompt}\n【章节】{ch['title']}"
                                            db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (prompt, ch['id']))
                                            
                                            full_c = ""
                                            ok, stream = engine.generate_content_from_outline_ai_stream(ch['id'], prompt, current_book, len_b*1000, client, m_name, m_key)
                                            if ok:
                                                for chunk in stream:
                                                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                                                        full_c += chunk.choices[0].delta.content
                                                db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (full_c, ch['id']))
                                                cnt += 1
                                            else: 
                                                st.error(f"失败: {ch['title']}")
                                                log_operation("AI错误", f"批量中 {ch['title']} 失败")
                                        
                                        db_mgr.update_book_timestamp(current_book['id'])
                                        ph.success(f"🎉 完成！共 {cnt} 章")
                                        log_operation("AI批量", f"批量任务结束，成功 {cnt} 章")
                                    except Exception as e: 
                                        ph.error(f"错误: {e}")
                                        log_operation("AI错误", f"批量致命错误: {e}")
                                    finally:
                                        st.session_state.generation_running = False
                                        time.sleep(2)
                                        st.rerun()

        
        with tab_assist:
            if not current_chapter:
                st.info("👈 请先从左侧选择一个章节。")
            else:
                def_cf = get_safe_model_default("write_logic_assist", "GPT_4o_Mini")
                def_rw = get_safe_model_default("write_rewrite", "DSK_V3")
                
                as_cf = st.session_state.model_assignments.get("write_logic_assist", def_cf)
                as_rw = st.session_state.model_assignments.get("write_rewrite", def_rw)
                
                st.subheader("🔎 矛盾检测", divider="gray")
                m_info = MODEL_MAPPING.get(as_cf, {'name': '未配置或无效'})
                st.caption(f"模型: **{m_info['name']}**")
                
                if st.button("🚨 检测设定冲突", use_container_width=True):
                    client, m_name, m_key = engine.get_client(as_cf)
                    if not client: st.error("API Key 未配置")
                    else:
                        with st.spinner("分析中..."):
                            time.sleep(1)
                            ensure_log_file()
                            log_operation("AI辅助", "开始矛盾检测")
                            rep = engine.analyze_chapter_conflict(current_chapter['content'], current_book, client, m_name, m_key)
                            if isinstance(rep, tuple): rep = rep[1]
                            st.session_state[f"conflict_report_{current_chapter['id']}"] = rep
                        st.success("完成")
                
                rep_val = st.session_state.get(f"conflict_report_{current_chapter['id']}", "")
                st.text_area("报告", rep_val, height=150, disabled=True)
                
                st.subheader("🔄 一键重写", divider="gray")
                m_info_rw = MODEL_MAPPING.get(as_rw, {'name': '未配置或无效'})
                st.caption(f"模型: **{m_info_rw['name']}**")
                
                if st.button("🚀 根据建议重写", type="primary", use_container_width=True):
                    if not current_chapter['content']: st.error("章节为空")
                    else:
                        client, m_name, m_key = engine.get_client(as_rw)
                        if not client: st.error("API Key 未配置")
                        else:
                            with st.spinner("重写中..."):
                                ensure_log_file()
                                log_operation("AI辅助", "开始一键重写")
                                report_context = st.session_state.get(f"conflict_report_{current_chapter['id']}", "无特殊报告")
                                res = engine.rewrite_chapter_ai(current_chapter['content'], report_context, client, m_name, m_key)
                                if isinstance(res, tuple): res = res[1]
                                st.session_state[f"rewritten_content_{current_chapter['id']}"] = res
                            st.success("完成")
                
                rw_val = st.session_state.get(f"rewritten_content_{current_chapter['id']}", "")
                if rw_val:
                    st.text_area("预览", rw_val, height=300)
                    if st.button("✅ 覆盖原内容", use_container_width=True):
                        db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (rw_val, current_chapter['id']))
                        db_mgr.update_book_timestamp(current_book['id'])
                        log_operation("更新章节", "应用重写内容覆盖原章节")
                        st.session_state.rerun_flag = True
                        st.rerun()