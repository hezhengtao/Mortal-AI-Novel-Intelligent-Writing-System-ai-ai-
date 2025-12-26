# mortal_write/views/idea.py

import streamlit as st
import os
import time
import json
import csv
import uuid
import threading
from datetime import datetime
from utils import render_header # log_operation 已废弃

# 🔥 导入 OpenAI 类，以便在自定义模型解析中实例化
from logic import FEATURE_MODELS, OpenAI

# 🛠️ 修正导入：从 config 导入 DATA_DIR
from config import DATA_DIR

# ==============================================================================
# 🛡️ 严格审计日志系统 (Idea 集成版)
# ==============================================================================

SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_audit.csv")
_log_lock = threading.Lock()

def get_session_id():
    """获取或生成当前会话的唯一追踪ID"""
    if "session_trace_id" not in st.session_state:
        st.session_state.session_trace_id = str(uuid.uuid4())[:8]
    return st.session_state.session_trace_id

def log_audit_event(category, action, details, status="SUCCESS", module="IDEA"):
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
            "IDEA": "灵感风暴",
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
        # 🔥 修复：使用支持自定义模型的解析器
        # 原代码: client, model_name, model_key = engine.get_client(assigned_model_key_idea)
        client, model_name, model_key = _resolve_ai_client(engine, assigned_model_key_idea)
        
        if not client:
             st.error(f"❌ 无法初始化 AI 客户端。")
             st.info(f"当前功能【灵感生成】分配的模型 Key 是：**{assigned_model_key_idea}**。")
             st.info(f"请前往【系统设置】->【模型配置】检查该模型对应的厂商 API Key 是否已填写并保存。")
             
             # 🔥 审计：生成失败
             log_audit_event("AI创意", "生成失败", {"原因": "Key 未配置"}, status="ERROR")
             st.stop()
        
        if not keywords.strip():
             st.warning("⚠️ 请输入一些关键词或描述，给 AI 一点提示吧！")
             return
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
            
            # 🔥 审计：生成启动
            log_audit_event("AI创意", "启动生成", {
                "目标": final_type, 
                "流派": final_genre, 
                "基调": final_tone,
                "关键词": keywords[:50] + "..."
            })

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
                        
                        # 🔥 审计：生成成功
                        log_audit_event("AI创意", "生成完成", {"内容长度": len(result)})
                        
                    else:
                        st.error(f"生成失败: {result}")
                        
                        # 🔥 审计：生成失败
                        log_audit_event("AI创意", "生成失败", {"API错误": str(result)}, status="ERROR")
                        
                except Exception as e:
                    st.error(f"发生异常: {e}")
                    log_audit_event("AI创意", "生成异常", {"错误": str(e)}, status="ERROR")

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
                        
                    # 🔥 审计：保存文档
                    log_audit_event("档案管理", "保存文档", {"文件名": filename})
                    
                    st.toast(f"✅ 已保存版本：{filename}")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"保存失败: {e}")
                    log_audit_event("档案管理", "保存失败", {"错误": str(e)}, status="ERROR")

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
                            
                            # 🔥 审计：删除文档
                            log_audit_event("档案管理", "删除文档", {"文件名": f}, status="WARNING")
                            
                            st.toast(f"已删除: {f}")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"删除失败: {e}")
                    
                    if st.button("✏️ 加载", key=f"load_{f}", help="加载此文档内容到上方编辑台", use_container_width=True):
                        try:
                            with open(os.path.join(IDEA_DIR, f), "r", encoding="utf-8") as file:
                                content = file.read()
                                st.session_state["last_idea_result"] = content
                                st.session_state["last_idea_meta"] = {"type": "加载文档", "genre": "-", "tone": "-"}
                                
                                # 🔥 审计：加载文档
                                log_audit_event("档案管理", "加载文档", {"文件名": f})
                                
                                st.toast("已加载到上方编辑台")
                                st.rerun()
                        except Exception as e:
                            st.error("加载失败")
                            log_audit_event("档案管理", "加载失败", {"错误": str(e)}, status="ERROR")

                with col_content:
                    try:
                        with open(os.path.join(IDEA_DIR, f), "r", encoding="utf-8") as file:
                            content = file.read()
                            st.markdown(content)
                    except Exception as e:
                        st.error("无法读取文件 content")