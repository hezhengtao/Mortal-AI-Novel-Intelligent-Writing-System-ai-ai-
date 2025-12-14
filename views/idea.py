

import streamlit as st
import os
import time
from utils import render_header
from logic import FEATURE_MODELS, MODEL_MAPPING
from utils import log_operation 

# --- 0. 基础配置 (用于样式联动) ---
THEME_COLOR = "#2e7d32" 
THEME_LIGHT = "#e8f5e9"

# --- 配置灵感保存目录 ---
IDEA_DIR = "data/ideas"
if not os.path.exists(IDEA_DIR):
    os.makedirs(IDEA_DIR)

def render_idea(engine):
    """渲染灵感模式页面 (主题色联动版)"""
    render_header("💡", "灵感风暴 - 创意生成")
    
    # 注入 CSS：优化标签样式 + 选中颜色联动
    st.markdown(f"""
    <style>
    /* 让 Radio 选项更紧凑，像标签一样 */
    div[role="radiogroup"] {{
        gap: 8px;
    }}
    div[role="radiogroup"] label {{
        background-color: #f0f2f6;
        padding: 4px 12px;
        border-radius: 16px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s;
    }}
    div[role="radiogroup"] label:hover {{
        border-color: {THEME_COLOR};
        background-color: {THEME_LIGHT};
    }}
    
    /* 🔥 核心修复：强制选中状态的小圆点颜色跟随主题 */
    div[role="radiogroup"] label > div:first-child[aria-checked="true"] {{
        background-color: {THEME_COLOR} !important;
        border-color: {THEME_COLOR} !important;
    }}
    /* 未选中时的边框颜色微调 */
    div[role="radiogroup"] label > div:first-child {{
        border-color: #bbbbbb;
    }}
    
    div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        margin-right: 6px;
    }}
    </style>
    """, unsafe_allow_html=True)
    
    # --- 1. 灵感配置区 ---
    with st.container():
        st.markdown("##### 🎛️ 灵感参数配置")
        
        # 1. 生成目标
        st.caption("🎯 **生成目标**")
        type_options = [
            "⚡ 核心脑洞", "📜 开篇大纲", "💍 金手指设计", 
            "😈 反派设定", "🔄 剧情反转", "🌏 世界观", 
            "✨ 自定义"
        ]
        gen_type_sel = st.radio("生成目标_hidden", type_options, horizontal=True, label_visibility="collapsed", key="radio_type")
        
        if gen_type_sel == "✨ 自定义":
            gen_type = st.text_input("请输入自定义目标", placeholder="例如：功法体系、武器进化路线...", key="cust_type")
        else:
            gen_type = gen_type_sel
            
        st.markdown("") # 间距

        # 2. 题材流派
        st.caption("📚 **题材流派**")
        genre_options = [
            "玄幻", "仙侠", "都市", "科幻", "悬疑", 
            "历史", "网游", "古言", "无限流", "克苏鲁", 
            "✨ 自定义"
        ]
        genre_sel = st.radio("题材流派_hidden", genre_options, horizontal=True, index=0, label_visibility="collapsed", key="radio_genre")
        
        if genre_sel == "✨ 自定义":
            genre = st.text_input("请输入自定义流派", placeholder="例如：赛博朋克、蒸汽魔法...", key="cust_genre")
        else:
            genre = genre_sel

        st.markdown("") # 间距
            
        # 3. 风格基调
        st.caption("🎨 **风格基调**")
        tone_options = [
            "热血", "搞笑", "黑暗", "正剧", 
            "虐心", "智斗", "甜宠", "杀伐", 
            "✨ 自定义"
        ]
        tone_sel = st.radio("风格基调_hidden", tone_options, horizontal=True, index=0, label_visibility="collapsed", key="radio_tone")
        
        if tone_sel == "✨ 自定义":
            tone = st.text_input("请输入自定义基调", placeholder="例如：意识流、荒诞...", key="cust_tone")
        else:
            tone = tone_sel

        st.markdown("---") # 分割线

        keywords = st.text_area(
            "🔑 核心关键词 / 困境描述 (必填)", 
            height=100, 
            placeholder="在此输入您的核心元素、主角设定，或者当前遇到的卡文困境。\n例如：主角是炼丹师但没有火灵根，必须靠吞噬妖火升级..."
        )

    # --- 2. 生成操作区 ---
    assigned_model_key_idea = engine.get_config_db("model_assignments", {}).get("idea_generation", FEATURE_MODELS["idea_generation"]['default'])
    
    col_btn, col_info = st.columns([1, 3])
    
    with col_btn:
        start_gen = st.button("✨ 立即生成灵感", type="primary", use_container_width=True)
    
    if start_gen:
        client, model_name, model_key = engine.get_client(assigned_model_key_idea)
        
        if not client:
             st.error(f"请先在【系统设置】配置分配给 [灵感模式 - 点子生成] 的模型 Key")
             
             log_operation("AI生成失败", "灵感点子生成中断: 模型 Key 未配置")
             st.stop()
        
        if not keywords.strip():
             st.warning("⚠️ 请输入一些关键词或描述，给 AI 一点提示吧！")
            
             log_operation("输入错误", "灵感点子生成中断: 关键词为空")
             st.stop()
        else:
            # 确保自定义字段不为空
            final_type = gen_type if gen_type else "未指定"
            final_genre = genre if genre else "未指定"
            final_tone = tone if tone else "未指定"

            full_prompt = f"""
            【题材流派】：{final_genre}
            【风格基调】：{final_tone}
            【生成目标】：{final_type}
            【核心需求】：{keywords}
            
            请根据以上要求，发挥最大的想象力，生成具有创意、网文感强、且逻辑自洽的创作灵感。
            如果是“核心梗”，请提供3个不同的创意方向。
            请直接输出内容，格式清晰，便于阅读。
            """
            
            
            log_operation("AI生成", f"开始生成灵感: Type={final_type}, Genre={final_genre}")

            with st.spinner(f"AI ({model_name}) 正在进行头脑风暴..."):
                try:
                    ok, result = engine.generate_idea_ai(full_prompt, client, model_name)
                    
                    if ok:
                        st.session_state["last_idea_result"] = result
                        st.session_state["last_idea_meta"] = {
                            "type": final_type,
                            "genre": final_genre,
                            "tone": final_tone
                        }
                        st.success("灵感生成成功！")
                       
                        log_operation("AI生成成功", f"灵感生成完成 (长度:{len(result)})")
                    else:
                        st.error(f"生成失败: {result}")
                       
                        log_operation("AI生成失败", f"API返回错误: {result}")
                except Exception as e:
                    st.error(f"发生异常: {e}")
                   
                    log_operation("系统异常", f"灵感生成抛出异常: {str(e)}")

    # --- 3. 结果编辑与版本保存区 ---
    if "last_idea_result" in st.session_state:
        st.divider()
        st.subheader("💡 灵感编辑台")
        
        edited_content = st.text_area(
            "您可以直接在此处修改内容，修改后点击保存即可存为新版本：",
            value=st.session_state["last_idea_result"],
            height=400
        )
        st.session_state["last_idea_result"] = edited_content
        
        meta = st.session_state.get("last_idea_meta", {})
        
        c_name, c_save = st.columns([3, 1], vertical_alignment="bottom")
        with c_name:
            version_note = st.text_input("版本备注 (可选)", placeholder="例如：增加了反派背景 V2...")
        
        with c_save:
            if st.button("💾 保存此版本", type="primary", use_container_width=True, help="将当前文本框内容保存为一个新的独立文档"):
                try:
                    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
                    safe_type = meta.get('type', '灵感').split(' ')[0].replace('/', '').replace('\\', '')
                    
                    filename = f"{safe_type}_{timestamp_str}.md"
                    filepath = os.path.join(IDEA_DIR, filename)
                    
                    file_content = f"# 灵感记录: {meta.get('type')}\n"
                    file_content += f"- **保存时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    file_content += f"- **流派风格**: {meta.get('genre')} / {meta.get('tone')}\n"
                    if version_note:
                        file_content += f"- **版本备注**: {version_note}\n"
                    file_content += "-" * 30 + "\n\n"
                    file_content += edited_content
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(file_content)
                        
                   
                    log_operation("数据保存", f"保存灵感文档: {filename}")
                    
                    st.toast(f"✅ 已保存版本：{filename}")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"保存失败: {e}")
                    log_operation("保存失败", f"保存灵感文档出错: {str(e)}")

    # --- 4. 灵感档案柜 ---
    st.markdown("### 📂 灵感档案柜")
    
    files = [f for f in os.listdir(IDEA_DIR) if f.endswith('.md') or f.endswith('.txt')]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(IDEA_DIR, x)), reverse=True)
    
    if not files:
        st.info("暂无保存的灵感文档。")
    else:
        for f in files:
            mtime = os.path.getmtime(os.path.join(IDEA_DIR, f))
            dt_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
            
            with st.expander(f"📄 {f} ({dt_str})", expanded=False):
                col_act, col_content = st.columns([1, 6])
                
                with col_act:
                    if st.button("🗑️ 删除", key=f"del_{f}", type="secondary", use_container_width=True):
                        try:
                            os.remove(os.path.join(IDEA_DIR, f))
                            # 🔥 审计：删除文件
                            log_operation("删除数据", f"删除灵感文档: {f}")
                            st.toast(f"已删除: {f}")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
                            log_operation("删除失败", f"删除文档出错: {str(e)}")
                    
                    if st.button("✏️ 加载", key=f"load_{f}", help="加载此文档内容到上方编辑台", use_container_width=True):
                        try:
                            with open(os.path.join(IDEA_DIR, f), "r", encoding="utf-8") as file:
                                content = file.read()
                                st.session_state["last_idea_result"] = content
                                st.session_state["last_idea_meta"] = {"type": "加载文档", "genre": "-", "tone": "-"}
                                
                                
                                log_operation("加载数据", f"加载灵感文档到编辑台: {f}")
                                
                                st.toast("已加载到上方编辑台")
                                st.rerun()
                        except Exception as e:
                            st.error("加载失败")
                            log_operation("加载失败", f"读取文档出错: {str(e)}")

                with col_content:
                    try:
                        with open(os.path.join(IDEA_DIR, f), "r", encoding="utf-8") as file:
                            content = file.read()
                            st.markdown(content)
                    except Exception as e:
                        st.error("无法读取文件 content")