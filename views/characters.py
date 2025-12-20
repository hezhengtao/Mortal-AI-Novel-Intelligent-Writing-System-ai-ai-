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
import re

from database import save_avatar_file
from config import FEATURE_MODELS
from logic import MODEL_MAPPING, OpenAI 
from utils import log_operation

# 🔥 导入 DATA_DIR 以解决路径问题
try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = "data"

# --- 0. 基础配置 ---
THEME_COLOR = "#2e7d32" 
THEME_LIGHT = "#e8f5e9"
RELATION_DIR = os.path.join(DATA_DIR, "relations") 
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
TEMP_GRAPH_FILE = os.path.join(DATA_DIR, "temp_graph.html")

# --- 角色排序优先级 ---
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

# --- 🛠️ 本地工具函数 ---
def render_header(icon, title):
    """渲染页面标题"""
    st.markdown(f"## {icon} {title}")

# --- 1. 初始化 Session State ---
def init_option_state():
    defaults = {
        "role_options": ["主角", "女主角", "双主角", "主要配角", "次要配角", "反派BOSS", "小反派/炮灰", "导师/师父", "挚友/死党", "宿敌", "暗恋者/伴侣", "亲属(父母/兄妹)", "金手指/系统化身", "宠物/坐骑", "路人"],
        "gender_options": ["男", "女", "无性", "双性", "流体性别", "未知/神秘"],
        "race_options": ["人族", "精灵", "矮人", "兽人/半兽人", "龙族", "亡灵/丧尸", "魔族", "妖族", "仙/神族", "机械/仿生人/AI", "灵体/鬼魂", "异虫/怪兽", "吸血鬼", "狼人", "混血", "未知生物"]
    }
    for key, val in defaults.items():
        if key not in st.session_state: st.session_state[key] = val

def update_book_timestamp_by_book_id(book_id):
    if book_id: 
        try: st.session_state.db.update_book_timestamp(book_id)
        except: pass

# --------------------------------------------------------------------------
# 智能排序逻辑
# --------------------------------------------------------------------------
def get_role_priority(role_name):
    if not role_name: return 99
    r = role_name.strip()
    
    # 精确匹配优先
    if r in ROLE_PRIORITY:
        return ROLE_PRIORITY[r]
        
    # 模糊匹配
    if "男主" in r or r == "主角": return 0
    if any(k in r for k in ["女主", "双主角", "妻", "道侣", "伴侣", "红颜"]): return 1
    if any(k in r for k in ["反派", "BOSS", "魔尊", "始祖"]): return 2
    if any(k in r for k in ["主要配角", "导师", "师父", "挚友", "死党", "兄弟"]): return 3
    if any(k in r for k in ["宿敌", "亲属", "金手指", "系统"]): return 4
    if any(k in r for k in ["次要", "宠物", "坐骑"]): return 5
    if any(k in r for k in ["炮灰", "路人", "龙套"]): return 6
    
    return 99

# --------------------------------------------------------------------------
#  核心交互：自定义选项模态弹窗
# --------------------------------------------------------------------------
@dialog_decorator("✨ 添加自定义选项")
def custom_option_dialog(list_key, widget_key):
    st.write("请输入新的选项名称：")
    new_val = st.text_input("输入内容", key=f"input_new_{list_key}")
    col_sub, col_can = st.columns([1, 1])
    
    if col_sub.button("✅ 确认并选中", type="primary", width="stretch"):
        if new_val and new_val.strip():
            if new_val not in st.session_state[list_key]:
                st.session_state[list_key].append(new_val)
            st.session_state[widget_key] = new_val
            log_operation('角色', f'添加自定义选项 {new_val} 到 {list_key}')
            st.rerun()
        else: st.warning("内容不能为空")

    if col_can.button("取消", width="stretch"):
        st.session_state[widget_key] = st.session_state[list_key][0]
        st.rerun()

def check_and_trigger_custom(selection, list_key, widget_key):
    if selection == "自定义...": custom_option_dialog(list_key, widget_key)

# --------------------------------------------------------------------------
# 核心交互：头像编辑模态弹窗
# --------------------------------------------------------------------------
@dialog_decorator("🖼️ 编辑角色头像")
def edit_avatar_dialog(char_id, current_avatar, char_name, current_book_id):
    st.caption(f"正在修改 **{char_name}** 的头像")
    
    col_prev, col_input = st.columns([1, 2.5], gap="medium", vertical_alignment="center")
    
    with col_prev:
        img_content = get_node_image_content(current_avatar)
        if img_content:
            st.image(img_content, width=110)
        else:
            st.info("无图")
            
    with col_input:
        new_file = st.file_uploader("上传新图片 (JPG/PNG)", type=['jpg', 'png'])
        new_url = st.text_input("输入图片 URL", value=current_avatar if isinstance(current_avatar, str) and current_avatar.startswith("http") else "")

    if st.button("💾 保存更改", type="primary", width="stretch"):
        final_path = current_avatar
        
        if new_file:
            saved_path = save_avatar_file(new_file, char_id)
            if saved_path:
                final_path = saved_path
        elif new_url and new_url != current_avatar:
            final_path = new_url
            
        if final_path != current_avatar:
            st.session_state.db.execute("UPDATE characters SET avatar=? WHERE id=?", (final_path, char_id))
            update_book_timestamp_by_book_id(current_book_id)
            log_operation('角色', f'更新头像：{char_name} (ID: {char_id})')
            st.toast("✅ 头像已更新！")
            time.sleep(0.5)
            st.rerun()
        else:
            st.warning("未检测到更改")

# --------------------------------------------------------------------------
# 🔥 修复版：图片处理 & URL 生成 (增强版头像获取)
# --------------------------------------------------------------------------

def get_node_image_content(path_or_url):
    """
    🔥 增强版头像获取函数
    支持多种路径格式：
    1. HTTP/HTTPS URL
    2. Data URI (base64)
    3. 绝对路径
    4. 相对路径 (相对于 DATA_DIR/avatars/)
    5. 数据库存储的相对路径
    """
    if not path_or_url:
        return None
    
    path_or_url = str(path_or_url).strip()
    
    # 1. 如果是 HTTP URL 或 Data URI，直接返回
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    
    # 2. 尝试直接路径
    if os.path.exists(path_or_url):
        try:
            return local_file_to_data_uri(path_or_url)
        except:
            pass
    
    # 3. 尝试在 avatar 目录下查找
    avatar_filename = os.path.basename(path_or_url)
    avatar_path = os.path.join(AVATAR_DIR, avatar_filename)
    if os.path.exists(avatar_path):
        try:
            return local_file_to_data_uri(avatar_path)
        except:
            pass
    
    # 4. 尝试原始路径（可能数据库存储的是相对路径）
    if not os.path.isabs(path_or_url):
        # 尝试在 data 目录下
        data_path = os.path.join(DATA_DIR, path_or_url)
        if os.path.exists(data_path):
            try:
                return local_file_to_data_uri(data_path)
            except:
                pass
        
        # 尝试在项目根目录下
        root_path = os.path.join(os.getcwd(), path_or_url)
        if os.path.exists(root_path):
            try:
                return local_file_to_data_uri(root_path)
            except:
                pass
    
    # 5. 如果所有尝试都失败，返回 None
    return None

def local_file_to_data_uri(file_path):
    """将本地文件转换为 data URI"""
    try:
        with open(file_path, "rb") as img_file:
            b64_string = base64.b64encode(img_file.read()).decode('utf-8')
            ext = file_path.split('.')[-1].lower() if '.' in file_path else 'jpg'
            mime_type = "image/png" if ext == "png" else "image/jpeg"
            return f"data:{mime_type};base64,{b64_string}"
    except Exception as e:
        print(f"转换图片失败 {file_path}: {e}")
        return None

def generate_bing_search_image(keyword):
    """生成 Bing 搜索图片 URL"""
    if not keyword: 
        return ""
    encoded = urllib.parse.quote(keyword)
    return f"https://tse2.mm.bing.net/th?q={encoded}&w=300&h=300&c=7&rs=1&p=0"

def generate_pollinations_url(desc, name):
    if not desc: 
        return ""
    safe_desc = desc[:80].replace("\n", " ")
    prompt = f"portrait of {name}, {safe_desc}, fantasy art, high quality"
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true&seed={random.randint(0,999)}"

def get_default_avatar(name):
    """获取默认头像（当没有头像时）"""
    if not name:
        return "https://api.dicebear.com/9.x/adventurer/svg?seed=Unknown&flip=true"
    return f"https://api.dicebear.com/9.x/adventurer/svg?seed={urllib.parse.quote(name)}&flip=true"

def save_relations_to_disk(book_id, relations_data):
    if not os.path.exists(RELATION_DIR): 
        os.makedirs(RELATION_DIR)
    file_path = os.path.join(RELATION_DIR, f"book_{book_id}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(relations_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

def load_relations_from_disk(book_id):
    file_path = os.path.join(RELATION_DIR, f"book_{book_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception as e:
            print(f"Load Error: {e}")
            return []
    return []

# --------------------------------------------------------------------------
# 数据库 & AI 提取逻辑
# --------------------------------------------------------------------------
def ensure_schema_compatibility(db_mgr):
    new_cols = [
        "race", "desc", "avatar", "is_major",
        "origin", "profession", "cheat_ability", "power_level", 
        "ability_limitations", "appearance_features", "signature_sign",
        "relationship_to_protagonist", "social_role", "debts_and_feuds"
    ]
    for col in new_cols:
        try: 
            db_mgr.query(f"SELECT {col} FROM characters LIMIT 1")
        except: 
            try: 
                db_mgr.execute(f"ALTER TABLE characters ADD COLUMN {col} TEXT")
            except: 
                pass

def repair_json_content(content):
    """
    🔥 强力修复 JSON 字符串
    """
    if not content: 
        return "[]"
    
    # 1. 移除 Markdown 代码块标记
    content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'^```\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
    
    # 2. 尝试提取最外层的列表 [ ... ]
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        content = match.group(0)
    
    # 3. 移除尾随逗号 (Trailing Commas)
    content = re.sub(r',(\s*\})', r'\1', content)
    content = re.sub(r',(\s*\])', r'\1', content)
    
    return content.strip()

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

    if progress_callback: 
        progress_callback(10, "STEP 1/6: 正在扫描现有角色库...")
    existing_res = db_mgr.query("SELECT name FROM characters WHERE book_id=?", (current_book_id,))
    existing_names = {r['name'] for r in existing_res} if existing_res else set()

    if progress_callback: 
        progress_callback(20, "STEP 2/6: 正在读取小说内容...")
    content_snippet = ""
    if hasattr(engine, 'get_book_content_prefix'):
        content_snippet = engine.get_book_content_prefix(current_book_id, length=15000)
    
    if progress_callback: 
        progress_callback(40, f"STEP 3/6: 正在调用 {display_model_name} 深度分析 (这可能需要十几秒)...")
    
    prompt = f"""
    请深入分析小说《{current_book['title']}》。
    {f"参考小说前文片段：{content_snippet[:3500]}..." if content_snippet else "请基于你的知识库。"}
    
    任务：提取该小说中最重要的 5-10 个角色，并补充详细的网文设定属性。
    
    要求：
    1. 必须返回纯粹的 JSON 数组格式。
    2. 不要包含 markdown 标记。
    3. 严禁使用尾随逗号（trailing commas）。
    4. 排除已存在的角色：{list(existing_names)}
    
    返回 JSON 结构示例：
    [
        {{
            "name": "角色名", "gender": "男/女", "race": "种族", "role": "主角/反派...",
            "desc": "基础外貌和性格描述",
            "is_major": true,
            "origin": "家族弃子",
            "profession": "炼药师",
            "cheat_ability": "骨灵冷火",
            "power_level": "斗之气三段",
            "relationships": [
                 {{"target": "另一个角色名", "label": "义父"}},
                 {{"target": "另一个角色名", "label": "宿敌"}}
            ]
        }}
    ]
    """
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        if progress_callback: 
            progress_callback(70, "STEP 4/6: 解析数据结构与关系...")
        
        raw_content = response.choices[0].message.content.strip()
        cleaned_json = repair_json_content(raw_content)

        try:
            char_list = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e} | Content: {raw_content}")
            return False, f"AI 返回格式有误，自动修复失败。请重试。(Error: {e})"

        final_list = []
        total_items = len(char_list)
        
        for i, c in enumerate(char_list):
            if not c.get('name'): 
                continue
            
            # 动态更新进度
            current_progress = 70 + int((i / total_items) * 25)
            if progress_callback: 
                progress_callback(current_progress, f"STEP 5/6: 准备 {c['name']} 的数据...")
            
            avatar_url = c.get('avatar', '').strip()
            if not avatar_url or not avatar_url.startswith("http"):
                search_query = f"{current_book['title']} {c['name']} 插画"
                avatar_url = generate_bing_search_image(search_query)
            
            c['avatar'] = avatar_url
            final_list.append(c)
        
        if progress_callback: 
            progress_callback(100, "✅ 分析完成！")
        log_operation('角色', f'提取成功：AI 发现了 {len(final_list)} 个角色。')
        return True, final_list
        
    except Exception as e:
        log_operation('角色', f'提取异常：{str(e)}')
        return False, f"提取失败: {str(e)}"

# --------------------------------------------------------------------------
# 🔥 修复版：核心渲染逻辑
# --------------------------------------------------------------------------

def generate_graph_html(nodes, edges, height="600px"):
    
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    
    # 使用 CDN 链接
    vis_js_url = "https://lib.baomitu.com/vis/4.21.0/vis.min.js"
    vis_css_url = "https://lib.baomitu.com/vis/4.21.0/vis.min.css"

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script type="text/javascript" src="{vis_js_url}"></script>
        <link href="{vis_css_url}" rel="stylesheet" type="text/css" />
        <style type="text/css">
            #mynetwork {{
                width: 100%;
                height: {height};
                border: 1px solid #eee;
                background-color: #ffffff;
            }}
            div.vis-network div.vis-manipulation {{ display: none !important; }}
            div.vis-tooltip {{
                position: absolute;
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                padding: 12px;
                font-family: "Microsoft YaHei", sans-serif;
                font-size: 13px;
                line-height: 1.6;
                color: #333;
                width: auto;
                max-width: 320px; 
                white-space: normal; 
                word-wrap: break-word; 
                z-index: 9999;
                visibility: visible;
                pointer-events: none;
            }}
            div.vis-tooltip strong {{ color: #2e7d32; font-size: 15px; display: block; margin-bottom: 4px; }}
            div.vis-tooltip span.meta {{ color: #888; font-size: 12px; display: block; margin-bottom: 8px; border-bottom: 1px dashed #eee; padding-bottom: 4px; }}
        </style>
    </head>
    <body>
    <div id="mynetwork"></div>
    <script type="text/javascript">
        var nodes = new vis.DataSet({nodes_json});
        var edges = new vis.DataSet({edges_json});
        var container = document.getElementById('mynetwork');
        var data = {{ nodes: nodes, edges: edges }};
        
        var options = {{
            locale: 'cn',
            nodes: {{
                shape: 'dot', 
                size: 30,
                font: {{ 
                    size: 15, 
                    color: '#333333', 
                    strokeWidth: 4, 
                    strokeColor: '#ffffff', 
                    vadjust: 6 
                }},
                borderWidth: 4, 
                borderWidthSelected: 6,
                shadow: {{ 
                    enabled: true, 
                    color: 'rgba(0,0,0,0.15)', 
                    size: 10, 
                    x: 2, 
                    y: 4 
                }},
                shapeProperties: {{ 
                    useBorderWithImage: true,
                    useImageSize: false
                }}
            }},
            edges: {{
                width: 2, 
                color: {{ color: '#bbbbbb', highlight: '#2e7d32' }},
                smooth: {{ type: 'continuous', roundness: 0.5 }}, 
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }},
                font: {{ 
                    align: 'middle', 
                    strokeWidth: 3, 
                    strokeColor: '#ffffff', 
                    size: 12, 
                    background: 'white' 
                }}
            }},
            physics: {{
                enabled: true,
                forceAtlas2Based: {{ 
                    gravitationalConstant: -100, 
                    centralGravity: 0.015, 
                    springLength: 120, 
                    springConstant: 0.08, 
                    damping: 0.4, 
                    avoidOverlap: 0.8 
                }},
                maxVelocity: 50, 
                minVelocity: 0.1, 
                solver: 'forceAtlas2Based'
            }},
            manipulation: {{ enabled: false }},
            interaction: {{ 
                navigationButtons: true, 
                keyboard: true, 
                hover: true, 
                zoomView: true, 
                dragView: true,
                hoverConnectedEdges: true
            }}
        }};
        
        var network = new vis.Network(container, data, options);
        
        // 延迟调整视图，确保图片加载完成
        setTimeout(function() {{ 
            network.fit({{
                animation: {{ 
                    duration: 1000, 
                    easingFunction: 'easeInOutQuad' 
                }}
            }}); 
        }}, 2000);

        network.on("doubleClick", function (params) {{
            if (params.nodes.length > 0) {{ 
                network.focus(params.nodes[0], {{ 
                    scale: 1.5, 
                    animation: true 
                }}); 
            }} else {{ 
                network.fit({{ animation: true }}); 
            }}
        }});
        
        // 处理图片加载失败的情况
        network.on("afterDrawing", function() {{
            var canvas = container.getElementsByTagName('canvas')[0];
            if (canvas) {{
                var ctx = canvas.getContext('2d');
                // 这里可以添加图片加载失败的处理逻辑
            }}
        }});
    </script>
    </body>
    </html>
    """
    return html_template

# --------------------------------------------------------------------------
# 主渲染函数
# --------------------------------------------------------------------------

def render_characters(engine, current_book_arg=None):
    """Render character profile page"""
    db_mgr = st.session_state.db
    ensure_schema_compatibility(db_mgr)
    init_option_state() 
    
    render_header("👥", "角色档案")
    
    # CSS 样式优化
    st.markdown(f"""
    <style>
    input[type="checkbox"] {{ accent-color: {THEME_COLOR} !important; }}
    
    [data-testid="StyledFullScreenButton"] {{ display: none !important; }}
    button[kind="header"] {{ display: none !important; }}

    [data-testid='stFileUploaderDropzone'] {{ 
        border: 1px dashed #bbb !important; 
        background-color: #fafafa !important; 
        border-radius: 4px !important; 
        padding: 0 !important; 
        min-height: 40px !important; 
        height: 40px !important;
        display: flex !important; 
        align-items: center !important; 
        justify-content: center !important;
        cursor: pointer;
    }}
    [data-testid='stFileUploaderDropzone']:hover {{
        border-color: {THEME_COLOR} !important;
        background-color: #f1f8e9 !important;
    }}
    [data-testid='stFileUploaderDropzone'] > div > div > svg, 
    [data-testid='stFileUploaderDropzone'] > div > div > small, 
    [data-testid='stFileUploaderDropzone'] span {{ display: none !important; }}
    
    [data-testid='stFileUploaderDropzone']::after {{ 
        content: "📷 点击更换"; 
        display: block !important;
        color: #666; font-size: 13px; font-weight: 500; visibility: visible !important;
    }}
    [data-testid='stFileUploader'] button[kind="secondary"] {{ display: none !important; }}
    
    .char-card-title {{ margin: -15px 0 0 0 !important; font-weight: bold; }}
    
    /* 🔥 修复头像和文本框垂直对齐问题 */
    .avatar-container {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        height: 100% !important;
        margin-top: -8px !important;  /* 向上移动一点 */
    }}
    
    .name-input-container {{
        display: flex !important;
        align-items: center !important;
        height: 100% !important;
        margin-top: -4px !important;  /* 微调文本框位置 */
    }}
    
    .name-input-container input {{
        margin-top: 0 !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    
    all_books_res = db_mgr.query("SELECT id, title FROM books")
    all_books = {r['title']: int(r['id']) for r in all_books_res} if all_books_res else {}
    book_titles = list(all_books.keys())
    
    if not all_books:
        st.warning("数据库中没有书籍，请先在 [书籍管理] 中添加书籍。")
        return

    current_book_id = st.session_state.get('current_book_id')
    if not current_book_id:
        last_viewed = engine.get_config_db("last_viewed_book_id", None)
        if last_viewed and int(last_viewed) in all_books.values():
            current_book_id = int(last_viewed)
            st.session_state['current_book_id'] = current_book_id
    
    default_idx = 0
    if current_book_id:
        for idx, t in enumerate(book_titles):
            if all_books[t] == current_book_id:
                default_idx = idx
                break
    
    def on_book_change():
        new_title = st.session_state.character_manager_book_selector
        new_id = all_books[new_title]
        st.session_state['current_book_id'] = new_id
        engine.set_config_db("last_viewed_book_id", new_id)
        
    selected_title = st.selectbox(
        "📚 **选择要管理的角色书籍：**", 
        book_titles, 
        index=default_idx, 
        key="character_manager_book_selector",
        on_change=on_book_change
    )
    
    selected_book_id = int(all_books.get(selected_title))
    if selected_book_id != st.session_state.get('current_book_id'):
        st.session_state['current_book_id'] = selected_book_id
        engine.set_config_db("last_viewed_book_id", selected_book_id)
    
    current_book_id = selected_book_id
    current_book = None
    if current_book_id:
        res = db_mgr.query("SELECT * FROM books WHERE id=?", (current_book_id,))
        if res: current_book = res[0]
    if not current_book: return
    st.info(f"当前管理书籍：《{current_book['title']}》")
    
    col_graph, col_edit = st.columns([2, 1]) 

    # =================================================================
    # 左侧：人物关系图谱
    # =================================================================
    with col_graph:
        st.subheader("🕸️ 人物关系图谱")
        
        chars_graph_rows = db_mgr.query("SELECT * FROM characters WHERE book_id=?", (current_book_id,))
        
        if not chars_graph_rows:
            st.info("暂无角色，请在右侧添加。")
        else:
            chars_graph = [dict(r) for r in chars_graph_rows]
            saved_relations = load_relations_from_disk(current_book_id)
            has_cache = saved_relations is not None and len(saved_relations) > 0
            
            c_tools_1, c_tools_2 = st.columns([1, 1])
            with c_tools_1:
                btn_label = "🔄 重新生成图谱" if has_cache else "🤖 AI 生成图谱"
                if st.button(btn_label, key="gen_chart_btn", type="primary", width="stretch"):
                    assignments = engine.get_config_db("model_assignments", {})
                    assigned_key = assignments.get("books_arch_gen")
                    if not assigned_key: assigned_key = assignments.get("novel_structure_gen")
                    if not assigned_key: assigned_key = "GPT_4o"

                    client, model_name, model_key = engine.get_client(assigned_key)
                    
                    if not client: 
                        st.error(f"请先配置图谱生成模型")
                    else:
                        log_operation('角色', f'开始生成关系图谱: {current_book["title"]}')
                        with st.spinner("AI 正在阅读分析人物关系..."):
                            ok, res = engine.generate_char_relation_map_pyvis(current_book_id, chars_graph, client, model_name, model_key)
                            if ok and isinstance(res, list):
                                save_relations_to_disk(current_book_id, res)
                                saved_relations = res
                                log_operation('角色', f'图谱生成成功并保存 ({len(res)} 条关系)。')
                                st.rerun()
                            else:
                                st.error(f"生成失败: {res}")
            
            relations_data = saved_relations if saved_relations else []
            try:
                role_colors = {
                    "主角": "#d32f2f", "双主角": "#d32f2f", "反派BOSS": "#212121",
                    "主要配角": "#1976d2", "次要配角": "#64b5f6", "挚友/死党": "#388e3c",
                    "暗恋者/伴侣": "#e91e63", "导师/师父": "#fbc02d", "default": "#9e9e9e"
                }

                nodes = []
                node_ids = set()
                
                for char in chars_graph:
                    char_id = char['id']
                    node_ids.add(char_id)
                    
                    color = role_colors.get(char.get('role'), role_colors["default"])
                    size = 35 if char.get('is_major') else 20
                    
                    # 🔥 获取头像内容
                    avatar_path = char.get('avatar', '')
                    image_url = get_node_image_content(avatar_path)
                    
                    # 如果获取不到头像，使用默认头像
                    if not image_url:
                        image_url = get_default_avatar(char['name'])
                    
                    shape = 'circularImage' if image_url else 'dot'
                    
                    desc_raw = (char.get('desc') or "暂无描述").replace('\n', ' ')
                    
                    extra_info = ""
                    if char.get('power_level'): 
                        extra_info += f"[{char.get('power_level')}] "
                    if char.get('profession'): 
                        extra_info += f"{char.get('profession')}"
                    
                    tooltip_html = f"""
                        <strong>{html.escape(char['name'])}</strong>
                        <span class="meta">{char.get('role', '未知')} | {char.get('race', '未知')}</span>
                        <div style="font-size:11px;color:#666;margin:2px 0;">{html.escape(extra_info)}</div>
                        <hr style="margin:5px 0;border:0;border-top:1px solid #eee;">
                        <div style="font-size:12px;">{html.escape(desc_raw)}</div>
                    """
                    
                    nodes.append({
                        "id": char_id,
                        "label": char['name'],
                        "title": tooltip_html, 
                        "shape": shape,
                        "image": image_url if image_url else None,
                        "size": size,
                        "borderWidth": 4, 
                        "borderWidthSelected": 6,
                        "color": { 
                            "border": color, 
                            "background": "#ffffff",
                            "highlight": {
                                "border": color,
                                "background": "#f0f0f0"
                            }
                        }
                    })
                    
                edges = []
                seen_edges = set()
                
                for rel in relations_data:
                    source_id = rel.get('source')
                    target_id = rel.get('target')
                    
                    if source_id in node_ids and target_id in node_ids:
                        edge_key = tuple(sorted([source_id, target_id]))
                        
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)
                        
                        full_label = rel.get('label', '')
                        display_label = full_label[:5] + ".." if len(full_label) > 5 else full_label
                        
                        edges.append({
                            "from": source_id,
                            "to": target_id,
                            "label": display_label, 
                            "title": full_label,    
                            "width": max(1, rel.get('weight', 1) * 0.8)
                        })
                
                if nodes:
                    html_code = generate_graph_html(nodes, edges, height="600px")
                    components.html(html_code, height=620, scrolling=False)
                else:
                    st.info("没有可显示的节点")
                
            except Exception as e:
                st.error(f"渲染构建错误: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

    # =================================================================
    # 右侧：编辑与列表
    # =================================================================
    with col_edit:
        tab_add, tab_rels, tab_list, tab_ai = st.tabs(["➕ 添加角色", "🔗 关系管理", "📋 列表管理", "🤖 AI 提取"])
        
        # --- Tab 1: 手动添加 ---
        with tab_add:
            st.caption("添加新角色并可直接绑定关系。")
            name = st.text_input("姓名", key="manual_name")
            
            r_list = st.session_state.role_options + ["自定义..."]
            g_list = st.session_state.gender_options + ["自定义..."]
            rc_list = st.session_state.race_options + ["自定义..."]
            
            kp_man = "man" 
            role_sel = st.selectbox("定位", r_list, key=f"{kp_man}_role")
            gen_sel = st.selectbox("性别", g_list, key=f"{kp_man}_gen")
            race_sel = st.selectbox("种族", rc_list, key=f"{kp_man}_race")
            
            up_new_add = st.file_uploader("上传头像", type=['jpg','png'], key="man_up", label_visibility="collapsed")
            av_url = st.text_input("或 头像 URL", key="manual_av")
            
            with st.expander("📝 详细设定 (身份/能力/关系...)", expanded=False):
                st.caption("以下内容将存入数据库，供 AI 写作参考")
                c_d1, c_d2 = st.columns(2)
                m_origin = c_d1.text_input("出身背景", placeholder="贵族/平民/穿越...", key="m_origin")
                m_prof = c_d2.text_input("职业/天赋", placeholder="剑士/炼药师...", key="m_prof")
                
                m_cheat = st.text_input("金手指/核心能力", placeholder="系统/神秘宝物", key="m_cheat")
                c_d3, c_d4 = st.columns(2)
                m_level = c_d3.text_input("当前境界", placeholder="斗之气三段", key="m_level")
                m_limit = c_d4.text_input("能力代价", placeholder="消耗寿命/冷却...", key="m_limit")
                
                m_face = st.text_input("外貌特征", placeholder="一道疤/异色瞳", key="m_face")
                m_sign = st.text_input("标志性物品/动作", placeholder="摸鼻子/如意棒", key="m_sign")
                
                m_rel_pro = st.text_input("与主角关系", placeholder="盟友/死敌", key="m_rel_pro")
                m_social = st.text_input("社会角色/恩仇", placeholder="家族族长/欠某人情", key="m_social")
            
            desc = st.text_area("综合简介", height=150, key="manual_desc")
            
            st.markdown("---")
            st.markdown("**🔗 初始关系绑定**")
            
            char_rows = db_mgr.query("SELECT id, name FROM characters WHERE book_id=?", (current_book_id,))
            char_options = {c['name']: c['id'] for c in char_rows}
            char_names = ["(无)"] + list(char_options.keys())
            
            rel_target_name = st.selectbox("关联对象", char_names, key="man_rel_target")
            rel_desc = st.text_input("关系描述 (如: 义妹)", key="man_rel_desc")

            if st.button("确认添加", type="primary", width="stretch"):
                if name:
                    # 🔥 手动添加的去重逻辑
                    exist_check = db_mgr.query("SELECT id FROM characters WHERE book_id=? AND name=?", (current_book_id, name))
                    if exist_check:
                        st.warning(f"角色 {name} 已存在，请勿重复添加。")
                    else:
                        final_av = av_url
                        if up_new_add:
                             temp_id = int(time.time())
                             saved_path = save_avatar_file(up_new_add, temp_id)
                             if saved_path: 
                                 final_av = saved_path
                        
                        if not final_av:
                             final_av = generate_bing_search_image(f"{current_book['title']} {name} 插画")
                             if not final_av:
                                final_av = get_default_avatar(name)

                        new_char_id = db_mgr.execute(
                            """INSERT INTO characters (
                                book_id, name, role, gender, race, desc, is_major, avatar,
                                origin, profession, cheat_ability, power_level, ability_limitations,
                                appearance_features, signature_sign, relationship_to_protagonist, social_role
                            ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?)""",
                            (
                                current_book_id, name, role_sel, gen_sel, race_sel, desc, True, final_av,
                                m_origin, m_prof, m_cheat, m_level, m_limit,
                                m_face, m_sign, m_rel_pro, m_social
                            )
                        )
                        
                        if rel_target_name != "(无)" and rel_desc:
                            target_id = char_options[rel_target_name]
                            current_relations = load_relations_from_disk(current_book_id) or []
                            current_relations.append({
                                "source": new_char_id,
                                "target": target_id,
                                "label": rel_desc,
                                "weight": 1
                            })
                            save_relations_to_disk(current_book_id, current_relations)

                        update_book_timestamp_by_book_id(current_book_id)
                        log_operation('角色', f'手动添加角色：{name}')
                        st.toast(f"✅ {name} 已添加！")
                        time.sleep(0.5)
                        st.rerun()

            check_and_trigger_custom(role_sel, "role_options", f"{kp_man}_role")
            check_and_trigger_custom(gen_sel, "gender_options", f"{kp_man}_gen")
            check_and_trigger_custom(race_sel, "race_options", f"{kp_man}_race")

        # --- Tab 2: 关系管理 ---
        with tab_rels:
            st.caption("管理角色间的连线。")
            char_rows = db_mgr.query("SELECT id, name FROM characters WHERE book_id=?", (current_book_id,))
            char_options = {c['name']: c['id'] for c in char_rows}
            char_names = list(char_options.keys())
            
            if not char_names:
                st.info("请先添加至少两个角色")
            else:
                c_src, c_tgt = st.columns([1, 1])
                with c_src:
                    src_name = st.selectbox("角色 A", char_names, key="rel_src")
                with c_tgt:
                    tgt_name = st.selectbox("角色 B", char_names, key="rel_tgt")
                    
                if src_name and tgt_name and src_name != tgt_name:
                    src_id = char_options[src_name]
                    tgt_id = char_options[tgt_name]
                    
                    current_relations = load_relations_from_disk(current_book_id) or []
                    existing_rel = None
                    existing_idx = -1
                    
                    for i, r in enumerate(current_relations):
                        if (r['source'] == src_id and r['target'] == tgt_id) or (r['source'] == tgt_id and r['target'] == src_id):
                            existing_rel = r
                            existing_idx = i
                            break
                    
                    rel_label = st.text_input("关系描述", value=existing_rel['label'] if existing_rel else "", key="rel_label_input")
                    
                    c_act_1, c_act_2 = st.columns([1, 1])
                    
                    if existing_rel:
                        with c_act_1:
                            if st.button("更新关系", type="primary", width="stretch"):
                                current_relations[existing_idx]['label'] = rel_label
                                save_relations_to_disk(current_book_id, current_relations)
                                log_operation('角色', f'更新关系：{src_name}-{tgt_name} ({rel_label})')
                                st.toast("✅ 关系已更新")
                                time.sleep(0.5)
                                st.rerun()
                        with c_act_2:
                            if st.button("删除连线", type="secondary", width="stretch"):
                                current_relations.pop(existing_idx)
                                save_relations_to_disk(current_book_id, current_relations)
                                log_operation('角色', f'删除关系：{src_name}-{tgt_name}')
                                st.toast("🗑️ 关系已删除")
                                time.sleep(0.5)
                                st.rerun()
                    else:
                        if st.button("➕ 建立新关系", type="primary", width="stretch"):
                            new_rel = {
                                "source": src_id,
                                "target": tgt_id,
                                "label": rel_label,
                                "weight": 1
                            }
                            current_relations.append(new_rel)
                            save_relations_to_disk(current_book_id, current_relations)
                            log_operation('角色', f'新建关系：{src_name}-{tgt_name} ({rel_label})')
                            st.toast("✅ 关系已建立")
                            time.sleep(0.5)
                            st.rerun()

        # --- Tab 3: 列表管理 ---
        with tab_list:
            c_count, c_view = st.columns([2, 1])
            with c_count:
                 rows = db_mgr.query("SELECT * FROM characters WHERE book_id=? ORDER BY is_major DESC, id DESC", (current_book_id,))
                 count = len(rows) if rows else 0
                 st.markdown(f"**共 {count} 名角色** <span style='color:grey;font-size:0.8em'>(已按重要性排序)</span>", unsafe_allow_html=True)
            with c_view:
                 avatar_shape = st.radio("头像形状", ["⚪ 圆形", "⬜ 方形"], index=0, horizontal=True, label_visibility="collapsed", key="shape_toggle")
            
            radius_style = "50%" if avatar_shape == "⚪ 圆形" else "6px"
            
            if not rows:
                st.info("暂无角色")
            else:
                all_chars_res = [dict(r) for r in rows]
                all_chars_res.sort(key=lambda x: get_role_priority(x.get('role')))

                for ch in all_chars_res:
                    with st.expander(f"{ch['name']} ({ch['role']})"):
                        
                        c_header, c_gear = st.columns([5, 1])
                        with c_header: 
                            st.caption("编辑信息")
                        with c_gear:
                            if st.button("⚙️", key=f"gear_{ch['id']}", help="编辑头像"):
                                edit_avatar_dialog(ch['id'], ch.get('avatar'), ch['name'], current_book_id)

                        kp = f"cedit_{ch['id']}"
                        
                        # 🔥 修复头像和文本框垂直对齐问题
                        c_thumb, c_name = st.columns([1, 4], vertical_alignment="center")
                        
                        with c_thumb:
                             img_src = get_node_image_content(ch.get('avatar'))
                             if not img_src:
                                 img_src = get_default_avatar(ch['name'])
                             
                             if img_src:
                                 # 使用自定义容器确保垂直居中
                                 st.markdown(f"""
                                 <div class="avatar-container">
                                     <img src="{img_src}" style="
                                         width: 60px; 
                                         height: 60px; 
                                         border-radius: {radius_style}; 
                                         object-fit: cover; 
                                         border: 1px solid #ddd; 
                                         box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                                     ">
                                 </div>
                                 """, unsafe_allow_html=True)
                             else:
                                 st.markdown(f"""
                                 <div class="avatar-container">
                                     <div style="
                                         width: 60px; 
                                         height: 60px; 
                                         border-radius: {radius_style}; 
                                         background-color: #f0f2f6; 
                                         color: #555; 
                                         font-size: 20px; 
                                         line-height: 60px; 
                                         text-align: center; 
                                         border: 1px solid #ddd;
                                         display: flex;
                                         align-items: center;
                                         justify-content: center;
                                     ">?</div>
                                 </div>
                                 """, unsafe_allow_html=True)
                        
                        with c_name:
                             # 使用自定义容器确保文本框垂直居中
                             st.markdown(f'<div class="name-input-container">', unsafe_allow_html=True)
                             n_new = st.text_input("姓名", ch['name'], key=f"{kp}_n", label_visibility="collapsed")
                             st.markdown('</div>', unsafe_allow_html=True)

                        with st.expander("📝 详细属性 (点击展开编辑)", expanded=False):
                            c_e1, c_e2 = st.columns(2)
                            e_orig = c_e1.text_input("出身", value=ch.get('origin') or "", key=f"{kp}_orig")
                            e_prof = c_e2.text_input("职业", value=ch.get('profession') or "", key=f"{kp}_prof")
                            
                            e_cheat = st.text_input("金手指", value=ch.get('cheat_ability') or "", key=f"{kp}_cheat")
                            
                            c_e3, c_e4 = st.columns(2)
                            e_lvl = c_e3.text_input("境界", value=ch.get('power_level') or "", key=f"{kp}_lvl")
                            e_lim = c_e4.text_input("代价", value=ch.get('ability_limitations') or "", key=f"{kp}_lim")
                            
                            e_sign = st.text_input("标志/外貌", value=ch.get('appearance_features') or "", key=f"{kp}_sign")
                            e_rel = st.text_input("关系/恩仇", value=ch.get('relationship_to_protagonist') or "", key=f"{kp}_rel")

                        d_new = st.text_area("描述", ch.get('desc', ''), height=100, key=f"{kp}_d")

                        c_del, c_save = st.columns([1, 1])
                        if c_del.button("删除", key=f"del_{ch['id']}", type="secondary", width="stretch"):
                             db_mgr.execute("DELETE FROM characters WHERE id=?", (ch['id'],))
                             update_book_timestamp_by_book_id(current_book_id)
                             st.rerun()
                             
                        if c_save.button("保存", key=f"save_{ch['id']}", type="primary", width="stretch"):
                             db_mgr.execute("""
                                UPDATE characters SET 
                                name=?, desc=?, origin=?, profession=?, cheat_ability=?, 
                                power_level=?, ability_limitations=?, appearance_features=?, relationship_to_protagonist=?
                                WHERE id=?
                             """, (n_new, d_new, e_orig, e_prof, e_cheat, e_lvl, e_lim, e_sign, e_rel, ch['id']))
                             
                             update_book_timestamp_by_book_id(current_book_id)
                             st.toast("✅ 保存成功")
                             st.rerun()

        # --- Tab 4: AI 提取 ---
        with tab_ai:
            st.caption("AI 将智能分析小说内容，自动提取角色并建立关系网。")
            if st.button("🚀 启动智能分析与提取", type="primary", width="stretch"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(p, text):
                    progress_bar.progress(p)
                    status_text.text(text)
                
                ok, result = ai_extract_characters(engine, db_mgr, current_book, current_book_id, update_progress)
                
                if ok:
                    st.session_state[f"extracted_chars_{current_book_id}"] = result
                    st.success(f"分析完成！共发现 {len(result)} 个新角色")
                    time.sleep(1) 
                    st.rerun()
                else:
                    st.error(result)

            extracted_data = st.session_state.get(f"extracted_chars_{current_book_id}", [])
            
            if extracted_data:
                st.divider()
                st.write(f"📊 **待确认导入角色：{len(extracted_data)} 人**")
                
                if st.button("📥 全部导入 (含角色关系)", type="primary", width="stretch"):
                    # 🔥 1. 批量插入角色 - 核心去重逻辑
                    name_id_map = {} 
                    
                    # 获取库里已有角色
                    existing_rows = db_mgr.query("SELECT id, name FROM characters WHERE book_id=?", (current_book_id,))
                    # 使用 strip() 防止空格导致的误判
                    for r in existing_rows: 
                        name_id_map[r['name'].strip()] = r['id']

                    pending_relations = []
                    new_char_count = 0

                    for char_data in extracted_data:
                        raw_name = char_data.get('name', '').strip()
                        if not raw_name: 
                            continue
                        
                        # 🔥 如果已存在，则记录 ID 并跳过插入
                        if raw_name in name_id_map:
                            print(f"角色 [{raw_name}] 已存在，跳过创建。")
                            # 仍需处理该角色的关系数据，所以不做 continue
                        else:
                            try:
                                cid = db_mgr.execute(
                                    """INSERT INTO characters (
                                        book_id, name, role, gender, race, desc, is_major, avatar,
                                        origin, profession, cheat_ability, power_level, ability_limitations,
                                        appearance_features, signature_sign, relationship_to_protagonist, social_role, debts_and_feuds
                                    ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)""",
                                    (
                                        current_book_id, 
                                        raw_name, 
                                        char_data.get('role', '路人'), 
                                        char_data.get('gender', '未知'), 
                                        char_data.get('race', '人族'), 
                                        char_data.get('desc', ''), 
                                        char_data.get('is_major', False), 
                                        char_data.get('avatar', ''),
                                        char_data.get('origin', ''),
                                        char_data.get('profession', ''),
                                        char_data.get('cheat_ability', ''),
                                        char_data.get('power_level', ''),
                                        char_data.get('ability_limitations', ''),
                                        char_data.get('appearance_features', ''),
                                        char_data.get('signature_sign', ''),
                                        char_data.get('relationship_to_protagonist', ''),
                                        char_data.get('social_role', ''),
                                        char_data.get('debts_and_feuds', '')
                                    )
                                )
                                name_id_map[raw_name] = cid
                                new_char_count += 1
                            except Exception as e: 
                                print(f"Insert Error: {e}")
                                pass
                        
                        # 收集该角色的关系数据
                        if 'relationships' in char_data and isinstance(char_data['relationships'], list):
                            for rel in char_data['relationships']:
                                pending_relations.append({
                                    "source_name": raw_name,
                                    "target_name": rel.get('target', '').strip(),
                                    "label": rel.get('label', '相关')
                                })
                    
                    # 🔥 2. 处理关系导入
                    current_rels = load_relations_from_disk(current_book_id) or []
                    new_rel_count = 0
                    
                    # 构建现有关系的指纹，防止重复添加
                    existing_rel_fingerprints = set()
                    for r in current_rels:
                        # 关系是无向的，排序后作为指纹
                        fp = tuple(sorted([str(r['source']), str(r['target'])]))
                        existing_rel_fingerprints.add(fp)

                    for pr in pending_relations:
                        s_id = name_id_map.get(pr['source_name'])
                        t_id = name_id_map.get(pr['target_name'])
                        
                        if s_id and t_id and s_id != t_id:
                            fp = tuple(sorted([str(s_id), str(t_id)]))
                            
                            if fp not in existing_rel_fingerprints:
                                current_rels.append({
                                    "source": s_id,
                                    "target": t_id,
                                    "label": pr['label'],
                                    "weight": 1
                                })
                                existing_rel_fingerprints.add(fp) # 立即加入指纹
                                new_rel_count += 1
                    
                    save_relations_to_disk(current_book_id, current_rels)

                    st.session_state[f"extracted_chars_{current_book_id}"] = []
                    update_book_timestamp_by_book_id(current_book_id)
                    st.toast(f"导入成功！新增角色 {new_char_count} 人，建立关系 {new_rel_count} 条。")
                    time.sleep(1)
                    st.rerun()
                    
                # 预览列表
                for idx, char_data in enumerate(extracted_data):
                    with st.expander(f"{idx+1}. {char_data['name']} ({char_data.get('role')})"):
                        c_p1, c_p2 = st.columns([1, 4], vertical_alignment="center")
                        with c_p1:
                            if char_data.get('avatar'):
                                st.image(char_data['avatar'], width=60)
                        with c_p2:
                            st.write(f"**简介**: {char_data.get('desc')}")
                            if char_data.get('relationships'):
                                rels = [f"{r['target']}({r['label']})" for r in char_data['relationships']]
                                st.caption(f"🔗 关系: {', '.join(rels)}")
                            if char_data.get('cheat_ability'):
                                st.caption(f"✨ 能力: {char_data.get('cheat_ability')}")