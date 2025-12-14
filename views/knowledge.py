

import streamlit as st
import json
import os
import time
from datetime import datetime
from utils import render_header, ensure_log_file, log_operation
from logic import FEATURE_MODELS, MODEL_MAPPING

# ==============================================================================
#  CSS 样式注入 (汉化上传组件 & 隐藏按钮)
# ==============================================================================
def inject_custom_css():
    st.markdown("""
    <style>
        /* 1. 隐藏上传组件内部的默认英文文本 */
        [data-testid="stFileUploaderDropzone"] > div > div > span { display: none; }
        [data-testid="stFileUploaderDropzone"] > div > div > small { display: none; }
        [data-testid="stFileUploaderDropzone"] button { display: none; }

        /* 2. 中文提示 */
        [data-testid="stFileUploaderDropzone"]::before {
            content: "☁️ 将经典章节文件 (TXT/PDF) 拖放到此处";
            position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%);
            font-size: 16px; font-weight: bold; color: #555; pointer-events: none;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            content: "限 200MB • 支持拖拽上传";
            position: absolute; top: 60%; left: 50%; transform: translate(-50%, -50%);
            font-size: 12px; color: #888; pointer-events: none;
        }
        [data-testid="stFileUploaderDropzone"] {
            min-height: 120px; text-align: center; position: relative;
            background-color: #f8f9fa; border: 1px dashed #ccc;
        }
    </style>
    """, unsafe_allow_html=True)

# --- 辅助函数：更新书籍时间戳 ---
def update_book_timestamp_by_book_id(book_id):
    if book_id:
        st.session_state.db.update_book_timestamp(book_id)

# ==============================================================================
# 核心渲染逻辑
# ==============================================================================

def render_knowledge(engine, current_book, current_chapter):
    """渲染拆书知识库页面"""
    inject_custom_css()
    db_mgr = st.session_state.db
    
    render_header("🧠", "拆书知识库")
    
    tab_extract, tab_transform = st.tabs(["🧬 风格提炼 (知识库构建)", "🖋️ 风格改造"])
    
    # --------------------------------------------------------------------------
    # Tab 1: 风格提炼
    # --------------------------------------------------------------------------
    with tab_extract:
        st.markdown("#### 📖 上传经典小说章节，培养AI作家")
        
        up_file_extract = st.file_uploader(
            "file_uploader_hidden_label", 
            type=["txt", "docx", "pdf"], 
            key="up_extract",
            label_visibility="collapsed"
        )
        
        col_btn_start, _ = st.columns([1, 4])
        
        if col_btn_start.button("🚀 开始风格拆解", type="primary"):
            if up_file_extract:
                client, model, model_key = engine.get_client("knowledge_analyze")
                if not client:
                    st.error("请先在【系统设置】配置分配给 [拆书知识 - 风格/设定分析] 的模型 Key")
                    ensure_log_file()
                    log_operation("AI生成失败", "风格拆解失败: 模型 Key 未配置")
                else:
                    ensure_log_file()
                    log_operation("AI生成", f"开始分析文件: {up_file_extract.name}")
                    
                    with st.spinner("AI 正在深度解析文本，提炼写作风格..."):
                        try:
                            if up_file_extract.type == "text/plain":
                                text = up_file_extract.read().decode('utf-8', errors='ignore')[:10000] 
                            else:
                                st.warning(f"目前 AI 深度解析建议使用 TXT 格式。")
                                text = up_file_extract.read().decode('utf-8', errors='ignore')[:5000]

                            analysis_result = engine.generate_style_analysis(text, client, model)
                            style_name = analysis_result.get('style_name', f'未命名风格_{int(time.time())}')
                            
                            book_id_to_save = current_book['id'] if current_book else 0
                            db_mgr.execute(
                                "INSERT INTO plots (book_id, content, status, importance) VALUES (?, ?, ?, ?)",
                                (book_id_to_save, style_name, "StyleDNA", 5)
                            )
                            update_book_timestamp_by_book_id(book_id_to_save)
                            
                            st.success("风格提炼完成，已保存到知识库！")
                            ensure_log_file()
                            log_operation("AI生成", f"风格提炼成功并保存: {style_name}") 
                            
                            with st.expander("查看分析详情 JSON", expanded=False):
                                st.json(analysis_result)
                            time.sleep(1)
                            st.rerun() 
                        except Exception as e:
                            st.error(f"AI 分析失败: {e}")
                            ensure_log_file()
                            log_operation("AI生成失败", f"风格提炼异常: {e}") 
            else:
                st.error("请先上传文件。")
        
        # 修改：已移除横线 st.divider()
        
        with st.expander("📚 已提炼风格列表 (知识库历史)", expanded=True):
            all_styles = db_mgr.query("SELECT id, content, created_at FROM plots WHERE status='StyleDNA' ORDER BY id DESC")
            if all_styles:
                for s in all_styles:
                    col_s1, col_s2 = st.columns([4, 1])
                    with col_s1:
                        st.markdown(f"**🧬 {s['content']}**")
                        try:
                            dt_obj = datetime.strptime(str(s['created_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
                            date_str = dt_obj.strftime('%Y-%m-%d %H:%M')
                        except: date_str = "时间未知"
                        st.caption(f"创建时间: {date_str}")
                    with col_s2:
                        if st.button("❌", key=f"del_style_{s['id']}", help="删除该风格"):
                            db_mgr.execute("DELETE FROM plots WHERE id=?", (s['id'],))
                            if current_book: update_book_timestamp_by_book_id(current_book['id'])
                            ensure_log_file()
                            log_operation("删除数据", f"删除风格知识库: {s['content']}") 
                            st.rerun()
            else:
                st.info("暂无提炼的风格历史记录。")

    # --------------------------------------------------------------------------
    # Tab 2: 风格改造
    # --------------------------------------------------------------------------
    with tab_transform:
        st.markdown("#### 💡 改造你的章节")
        
        # --- 1. 获取所有书籍 ---
        all_books = db_mgr.query("SELECT id, title FROM books ORDER BY updated_at DESC")
        if not all_books:
            st.warning("暂无书籍，请先去【书籍管理】创建或导入书籍。")
            st.stop()
            
        book_map = {b['title']: b['id'] for b in all_books}
        
        # 确定当前选中的书
        default_book_idx = 0
        if current_book and current_book['title'] in book_map:
            default_book_idx = list(book_map.keys()).index(current_book['title'])
            
        col_sel_book, col_sel_chap = st.columns([1, 1.5])
        
        with col_sel_book:
            selected_book_title = st.selectbox("1. 选择书籍", list(book_map.keys()), index=default_book_idx, key="know_sel_book")
            selected_book_id = book_map[selected_book_title]

        # --- 2. 获取选中书籍的所有章节 ---
        parts = db_mgr.query("SELECT id FROM parts WHERE book_id=?", (selected_book_id,))
        chapter_options = {} 
        
        for p in parts:
            vols = db_mgr.query("SELECT id, name FROM volumes WHERE part_id=?", (p['id'],))
            for v in vols:
                chaps = db_mgr.query("SELECT id, title, content FROM chapters WHERE volume_id=? ORDER BY sort_order", (v['id'],))
                for c in chaps:
                    label = f"【{v['name']}】{c['title']}"
                    chapter_options[label] = {"id": c['id'], "content": c['content']}
        
        with col_sel_chap:
            if not chapter_options:
                st.selectbox("2. 选择目标章节", ["(该书暂无章节)"], disabled=True)
                target_chap_content = ""
                target_chap_id = None
            else:
                default_chap_label = list(chapter_options.keys())[0]
                if current_chapter and current_book and current_book['id'] == selected_book_id:
                     for lbl, data in chapter_options.items():
                         if data['id'] == current_chapter['id']:
                             default_chap_label = lbl
                             break
                
                selected_chap_label = st.selectbox("2. 选择目标章节", list(chapter_options.keys()), index=list(chapter_options.keys()).index(default_chap_label))
                target_chap_id = chapter_options[selected_chap_label]['id']
                target_chap_content = chapter_options[selected_chap_label]['content']

        # --- 3. 风格选择 ---
        available_styles = db_mgr.query("SELECT DISTINCT content FROM plots WHERE status='StyleDNA' AND content IS NOT NULL AND content != ''")
        style_options = sorted(list(set([s['content'] for s in available_styles])))
        style_options.insert(0, "（AI自由发挥 - 大神优化）")
        
        st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)
        selected_style = st.selectbox("3. 选择参考的经典风格", style_options)
        
        # --- 4. 内容编辑区 ---
        input_key = f"trans_input_{target_chap_id}" if target_chap_id else "trans_input_empty"
        chapter_to_transform = st.text_area("待改造内容 (自动加载选中章节，可手动微调)", value=target_chap_content, height=300, key=input_key)

        col_btn_run, _ = st.columns([1, 2])
        
        if col_btn_run.button("🤖 AI 自动生成改造版本", type="primary"):
            if not chapter_to_transform.strip():
                st.error("内容为空，无法改造")
                st.stop()
            
            client, model, model_key = engine.get_client("knowledge_style_gen")
            if not client: 
                st.error("API Key 未配置")
                st.stop()
                
            if selected_style == "（AI自由发挥 - 大神优化）":
                style_prompt = "请你以资深网文主编的身份，优化以下章节的文笔、节奏和画面感，使其更具吸引力。"
            else:
                style_prompt = f"请严格参照并模仿【{selected_style}】的写作风格（包括其用词习惯、句式节奏、描写侧重），重新改写以下章节。"

            user_msg = f"{style_prompt}\n\n【原始文本】：\n{chapter_to_transform}\n\n【改写要求】：\n1. 保持原剧情走向不变\n2. 显著提升文笔和风格契合度\n3. 输出完整的改写后正文，不要包含解释性语言。"
            
            ensure_log_file()
            log_operation("AI辅助", f"开始风格改造: {selected_style} (BookID:{selected_book_id})")

            with st.spinner("AI 正在挥毫泼墨进行改写..."):
                try:
                    stream = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": user_msg}],
                        stream=True,
                        max_tokens=4000
                    )
                    
                    st.markdown("##### 🖋️ 改造结果预览：")
                    result_area = st.empty()
                    full_content = ""
                    
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            full_content += chunk.choices[0].delta.content
                            result_area.markdown(full_content + "▌")
                    
                    result_area.markdown(full_content)
                    st.session_state['last_transform_result'] = full_content
                    
                    ensure_log_file()
                    log_operation("AI辅助", f"风格改造完成 (约{len(full_content)}字)")
                    
                except Exception as e:
                    st.error(f"生成出错: {e}")
                    ensure_log_file()
                    log_operation("AI生成失败", f"改造过程出错: {e}")

        # --- 5. 保存区 ---
        if 'last_transform_result' in st.session_state and st.session_state['last_transform_result']:
            st.success("生成完成！")
            
            if target_chap_id:
                if st.button(f"💾 覆盖保存到：{selected_chap_label}", type="primary", use_container_width=True):
                    new_content = st.session_state['last_transform_result']
                    db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (new_content, target_chap_id))
                    update_book_timestamp_by_book_id(selected_book_id)
                    
                    ensure_log_file()
                    log_operation("更新章节", f"应用风格改造结果覆盖章节 ID:{target_chap_id} ({selected_chap_label})")
                    
                    st.toast("✅ 已覆盖保存")
                    time.sleep(1)
                    del st.session_state['last_transform_result']
                    st.rerun()
            else:
                st.warning("未检测到有效章节 ID，请手动复制上方内容。")