# mortal_write/views/idea.py

import streamlit as st
import os
import time
from utils import render_header, log_operation
from logic import FEATURE_MODELS
# 🛠️ 修正导入：从 config 导入 DATA_DIR
from config import DATA_DIR

# --- 0. 基础配置 ---
THEME_COLOR = "#2e7d32" 
THEME_LIGHT = "#e8f5e9"

# --- 配置灵感保存目录 (基于动态数据目录) ---
def get_idea_dir():
    # 修正：直接使用导入的 DATA_DIR 常量
    d = os.path.join(DATA_DIR, "ideas")
    
    if not os.path.exists(d):
        try: os.makedirs(d)
        except: pass
    return d

def render_idea(engine):
    """渲染灵感模式页面 (最终增强版：标签交互 + 严格审计 + 版本管理)"""
    render_header("💡", "灵感风暴 - 创意生成")
    
    IDEA_DIR = get_idea_dir()
    
    # 🎨 注入 CSS：优化标签样式 + 选中颜色与主题联动
    st.markdown(f"""
    <style>
    /* 让 Radio 选项更紧凑，像标签一样水平排列 */
    div[role="radiogroup"] {{
        gap: 8px;
        flex-wrap: wrap;
    }}
    div[role="radiogroup"] label {{
        background-color: #f8f9fa;
        padding: 4px 16px;
        border-radius: 20px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s;
        margin-right: 0px !important;
    }}
    div[role="radiogroup"] label:hover {{
        border-color: {THEME_COLOR};
        background-color: {THEME_LIGHT};
        cursor: pointer;
    }}
    
    /* 🔥 核心修复：强制选中状态的小圆点颜色跟随主题 */
    div[role="radiogroup"] label > div:first-child[aria-checked="true"] {{
        background-color: {THEME_COLOR} !important;
        border-color: {THEME_COLOR} !important;
    }}
    
    /* 选中时的文字颜色增强 (可选) */
    div[role="radiogroup"] label:has(div[aria-checked="true"]) {{
        border-color: {THEME_COLOR};
        background-color: {THEME_LIGHT};
        color: {THEME_COLOR};
        font-weight: 500;
    }}

    /* 调整 Radio 内部文字间距 */
    div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {{
        margin-right: 8px;
    }}
    </style>
    """, unsafe_allow_html=True)
    
    # --- 1. 灵感配置区 (参数配置) ---
    with st.container():
        st.markdown("##### 🎛️ 灵感参数配置")
        
        # 1. 生成目标 (Tag Style)
        st.caption("🎯 **生成目标**")
        type_options = [
            "⚡ 核心脑洞", "📜 开篇大纲", "💍 金手指设计", 
            "😈 反派设定", "🔄 剧情反转", "🌏 世界观", 
            "✨ 自定义"
        ]
        # 使用 Radio 替代 Selectbox，避免下拉框搜索的 "No results" 问题
        gen_type_sel = st.radio("生成目标_hidden", type_options, horizontal=True, label_visibility="collapsed", key="radio_type")
        
        if gen_type_sel == "✨ 自定义":
            gen_type = st.text_input("请输入自定义目标", placeholder="例如：功法体系、武器进化路线...", key="cust_type")
        else:
            gen_type = gen_type_sel
            
        st.markdown("") # 垂直间距

        # 2. 题材流派 (Tag Style)
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

        st.markdown("") # 垂直间距
            
        # 3. 风格基调 (Tag Style)
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

    # --- 2. AI 生成操作区 ---
    assigned_model_key_idea = engine.get_config_db("model_assignments", {}).get("idea_generation", FEATURE_MODELS["idea_generation"]['default'])
    
    col_btn, col_info = st.columns([1, 3])
    
    with col_btn:
        start_gen = st.button("✨ 立即生成灵感", type="primary", use_container_width=True)
    
    if start_gen:
        client, model_name, model_key = engine.get_client(assigned_model_key_idea)
        
        if not client:
             st.error(f"❌ 无法初始化 AI 客户端。")
             st.info(f"当前功能【灵感生成】分配的模型是：**{model_key}**。")
             st.info(f"请前往【系统设置】->【模型配置】检查该模型对应的厂商 API Key 是否已填写并保存。")
             log_operation("AI生成失败", "Key 未配置")
             st.stop()
        
        if not keywords.strip():
             st.warning("⚠️ 请输入一些关键词或描述，给 AI 一点提示吧！")
             log_operation("输入错误", "灵感点子生成中断: 关键词为空")
             st.stop()
        else:
            # 确保字段不为空 (防御性处理)
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

    # --- 3. 结果编辑与保存区 (版本化存储) ---
    if "last_idea_result" in st.session_state:
        st.divider()
        st.subheader("💡 灵感编辑台")
        
        # 允许用户直接修改生成结果
        edited_content = st.text_area(
            "您可以直接在此处修改内容，点击下方保存为新版本：",
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
                    # 生成唯一文件名
                    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
                    safe_type = str(meta.get('type', '灵感')).split(' ')[0].replace('/', '').replace('\\', '')
                    filename = f"{safe_type}_{timestamp_str}.md"
                    filepath = os.path.join(IDEA_DIR, filename)
                    
                    # 构建文档内容
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

    # --- 4. 灵感档案柜 (历史记录) ---
    st.markdown("### 📂 灵感档案柜")
    
    # 读取并按时间倒序排列
    files = [f for f in os.listdir(IDEA_DIR) if f.endswith('.md') or f.endswith('.txt')]
    # 🛠️ 修正：使用 lambda 参数 x 代替外部作用域的 f
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