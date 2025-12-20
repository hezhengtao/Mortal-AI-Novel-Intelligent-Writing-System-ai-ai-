# mortal_write/views/books.py

import streamlit as st
import re
import os
import json
import csv
import urllib.parse
import random
import time
import html
from datetime import datetime, timezone, timedelta

# 引入格式处理库
try:
    import PyPDF2
    import docx
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    pass 

# 尝试导入 ntplib
try:
    import ntplib
except ImportError:
    ntplib = None

# 从 utils 导入
from utils import (
    render_header, 
    log_operation, 
    generate_book_content, 
    ensure_log_file,
    save_file_locally,
    show_export_success_modal
)
from logic import FEATURE_MODELS, MODEL_MAPPING, OpenAI 

# 确保 DATA_DIR 可用
try: 
    from config import DATA_DIR
except ImportError:
    DATA_DIR = "data"

# ==============================================================================
# 1. 基础配置
# ==============================================================================
NOVEL_GENRES = {
    "玄幻奇幻": ["东方玄幻", "异世大陆", "王朝争霸", "高武世界", "西方奇幻", "领主种田", "魔法校园", "黑暗幻想"],
    "仙侠修真": ["凡人流", "古典仙侠", "修真文明", "幻想修仙", "洪荒封神", "无敌流", "家族修仙"],
    "都市现实": ["都市异能", "都市修仙", "神医赘婿", "文娱明星", "商战职场", "校花贴身", "鉴宝捡漏", "年代文"],
    "科幻末世": ["末世危机", "星际文明", "赛博朋克", "时空穿梭", "进化变异", "古武机甲", "无限流", "废土重建"],
    "历史军事": ["架空历史", "穿越重生", "秦汉三国", "两宋元明", "外国历史", "谍战特工", "军旅生涯", "大国崛起"],
    "游戏竞技": ["虚拟网游", "电子竞技", "游戏异界", "体育竞技", "卡牌游戏", "桌游棋牌", "全民领主"],
    "悬疑灵异": ["侦探推理", "诡异修仙", "盗墓探险", "风水秘术", "克苏鲁", "神秘复苏", "惊悚乐园"],
    "轻小说/二次元": ["原生幻想", "恋爱日常", "综漫同人", "变身入替", "搞笑吐槽", "系统流", "乙女向"],
    "诸天无限": ["诸天万界", "无限流", "综漫", "主神建设", "位面交易"],
    "脑洞创意": ["反套路", "迪化流", "聊天群", "幕后黑手", "灵气复苏"]
}

FLAT_GENRE_LIST = []
for main, subs in NOVEL_GENRES.items():
    for sub in subs:
        FLAT_GENRE_LIST.append(f"{main}-{sub}")

if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
else:
    dialog_decorator = st.experimental_dialog

# ==============================================================================
# 2. 底层工具函数
# ==============================================================================

USAGE_LOG_PATH = os.path.join(DATA_DIR, "logs", "usage_log.csv")

def get_beijing_time():
    """获取北京时间 (UTC+8)"""
    try:
        utc_now = datetime.now(timezone.utc)
        beijing_time = utc_now.astimezone(timezone(timedelta(hours=8)))
        return beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")

def ensure_export_dir():
    export_dir = os.path.join(DATA_DIR, "exports")
    if not os.path.exists(export_dir): os.makedirs(export_dir)
    return export_dir

def get_cached_file_path(book_id, book_title):
    safe_title = re.sub(r'[\\/*?:"<>|]', "", str(book_title)).strip()
    return os.path.join(DATA_DIR, "exports", f"{book_id}_{safe_title}.txt")

def get_relation_dir():
    d = os.path.join(DATA_DIR, "relations")
    if not os.path.exists(d):
        try: os.makedirs(d)
        except: pass
    return d

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

def record_token_usage(provider, model, tokens, action_name, book_title=None):
    try:
        final_book_title = book_title
        if not final_book_title or final_book_title == "未知书籍":
            if 'current_book_id' in st.session_state and st.session_state.current_book_id:
                try:
                    if 'db' in st.session_state:
                        res = st.session_state.db.query("SELECT title FROM books WHERE id=?", (st.session_state.current_book_id,))
                        if res: final_book_title = res[0]['title']
                except: pass
        if not final_book_title: final_book_title = "未知书籍"

        price_per_1k = 0.03 
        model_str = str(model).lower()
        if "gpt-4" in model_str: price_per_1k = 0.2
        elif "mini" in model_str: price_per_1k = 0.01
        elif "deepseek" in model_str: price_per_1k = 0.005 
        
        cost = (tokens / 1000.0) * price_per_1k
        timestamp = get_beijing_time()
        log_dir = os.path.dirname(USAGE_LOG_PATH)
        if not os.path.exists(log_dir): os.makedirs(log_dir)
        
        file_exists = os.path.exists(USAGE_LOG_PATH)
        header = ['timestamp', 'provider', 'model', 'chars', 'cost', 'book_title']
        
        if file_exists:
            with open(USAGE_LOG_PATH, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            if 'book_title' not in first_line:
                with open(USAGE_LOG_PATH, 'r', encoding='utf-8') as old_f: lines = old_f.readlines()
                with open(USAGE_LOG_PATH, 'w', newline='', encoding='utf-8') as new_f:
                    writer = csv.writer(new_f)
                    writer.writerow(header)
                    for line in lines[1:]:
                        parts = line.strip().split(',')
                        if len(parts) >= 5: writer.writerow(parts[:5] + ["历史记录"])
        
        with open(USAGE_LOG_PATH, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not os.path.exists(USAGE_LOG_PATH) or os.path.getsize(USAGE_LOG_PATH) == 0:
                writer.writerow(header)
            writer.writerow([timestamp, provider, model, tokens, cost, final_book_title])
            
        print(f"💰 [计费] {action_name}: {tokens} tokens, ¥{cost:.4f} (书: {final_book_title})")
    except Exception as e:
        print(f"❌ 计费日志写入失败: {e}")

def process_and_save_tags(db_mgr, book_id, tags_list):
    if not tags_list: return []
    if isinstance(tags_list, str): tags_list = [tags_list]
    clean_tags = sorted(list(set([str(t).strip() for t in tags_list if str(t).strip()])))
    if not clean_tags: return []
    db_mgr.execute("DELETE FROM book_categories WHERE book_id=?", (book_id,))
    for tag in clean_tags:
        c_res = db_mgr.query("SELECT id FROM categories WHERE name=?", (tag,))
        if c_res: cid = c_res[0]['id']
        else: cid = db_mgr.execute("INSERT INTO categories (name) VALUES (?)", (tag,))
        db_mgr.execute("INSERT INTO book_categories (book_id, category_id) VALUES (?,?)", (book_id, cid))
    return clean_tags

def generate_bing_search_image(keyword):
    if not keyword: return ""
    encoded = urllib.parse.quote(keyword)
    return f"https://tse2.mm.bing.net/th?q={encoded}&w=300&h=300&c=7&rs=1&p=0"

def audit_download_callback(book_title, book_id):
    try:
        ensure_log_file()
        log_operation("数据导出", f"用户下载书籍TXT: 《{book_title}》 (ID:{book_id})")
    except Exception as e: print(f"Logging Error: {e}")

def robust_decode(data_bytes):
    encodings = ['utf-8', 'gb18030', 'gbk', 'big5', 'utf-16']
    for enc in encodings:
        try: return data_bytes.decode(enc)
        except UnicodeDecodeError: continue
    return data_bytes.decode('gb18030', errors='ignore')

def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.name.split('.')[-1].lower()
    try:
        uploaded_file.seek(0) 
        if file_type == 'txt':
            return robust_decode(uploaded_file.getvalue())
        elif file_type == 'pdf':
            reader = PyPDF2.PdfReader(uploaded_file)
            text = []
            for page in reader.pages: text.append(page.extract_text() or "")
            return "\n".join(text)
        elif file_type == 'docx':
            doc = docx.Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs])
        elif file_type == 'epub':
            temp_path = f"temp_{int(time.time())}.epub"
            with open(temp_path, "wb") as f: f.write(uploaded_file.getvalue())
            book = epub.read_epub(temp_path)
            text = []
            for item in book.get_items():
                if item.get_type() == epub.EpubItemType.EBOOK_HTML:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text.append(soup.get_text())
            if os.path.exists(temp_path): os.remove(temp_path)
            return "\n".join(text)
        else:
            return f"文件解析失败: 不支持的文件格式: {file_type}"
    except Exception as e:
        return f"文件解析失败 ({file_type}): {str(e)}"

def extract_and_parse_json(content):
    """
    解析 JSON 内容，支持对象和数组格式，增强对截断 JSON 的修复能力
    """
    try:
        # 清理代码块标记
        content = re.sub(r'```json\s*', '', content, flags=re.IGNORECASE)
        content = re.sub(r'```\s*', '', content)
        
        # 寻找 JSON 边界
        start = content.find('{')
        end = content.rfind('}')
        
        if start == -1:
            start = content.find('[')
            end = content.rfind(']')
        
        if start != -1:
            # 如果没找到结束符，说明被截断了
            if end == -1 or end < start:
                 json_str = content[start:].strip()
            else:
                 json_str = content[start:end+1].strip()
            
            try:
                return json.loads(json_str, strict=False)
            except json.JSONDecodeError:
                # 🚑 【抢救模式】尝试修复截断的 JSON
                try:
                    # 1. 极其暴力的补全
                    fixed_str = json_str.rstrip(',')
                    if fixed_str.count('"') % 2 != 0: fixed_str += '"'
                    if fixed_str.count('{') > fixed_str.count('}'): fixed_str += '}' * (fixed_str.count('{') - fixed_str.count('}'))
                    if fixed_str.count('[') > fixed_str.count(']'): fixed_str += ']' * (fixed_str.count('[') - fixed_str.count(']'))
                    return json.loads(fixed_str, strict=False)
                except:
                    # 2. 正则提取兜底 (针对列表结构)
                    try:
                        print("⚠️ JSON 严重损坏，尝试正则提取对象...")
                        # 尝试匹配完整的对象 {...}
                        matches = re.findall(r'\{[^{}]*\}', json_str)
                        valid_objs = []
                        for m in matches:
                            try: valid_objs.append(json.loads(m))
                            except: pass
                        if valid_objs:
                            # 猜测这可能是 characters 或 chapters
                            if "name" in valid_objs[0]: return {"characters": valid_objs}
                            if "title" in valid_objs[0]: return {"chapters": valid_objs}
                            return valid_objs
                    except:
                        pass
                        
        print(f"JSON Parse Failed. Raw content start: {content[:100]}")
        return None

    except Exception as e:
        print(f"General Parse Error: {e}")
        return None

# ==============================================================================
# 3. 核心逻辑
# ==============================================================================

def _write_detailed_world_settings(db_mgr, book_id, settings_list):
    """写入世界观，映射到 Status 字段"""
    if not settings_list: return 0
    saved_count = 0
    
    type_map = {
        "PowerSystem": "PowerSystem", 
        "Geography": "Geography",     
        "History": "TimeHistory",     
        "Culture": "CultureLife",     
        "RuleSystem": "RuleSystem",   
        "Organization": "Organization", 
        "Universe": "Universe",       
        "Other": "Other"
    }
    
    if isinstance(settings_list, list):
        for item in settings_list:
            if not isinstance(item, dict): continue
            
            title = item.get("title", "未命名设定")
            content = item.get("content", "")
            category = item.get("category", "Other")
            
            if category in ["History", "Myth"]: category = "History"
            if category in ["Rules", "Laws"]: category = "RuleSystem"
            if category in ["Culture", "Customs"]: category = "Culture"
            
            mapped_cat = type_map.get(category, 'Other')
            
            # 🔥 修改处：去掉了 【{category}】 前缀，只保留标题和内容，解决显示英文标签问题
            full_content = f"{title}\n{content}"
            
            db_status = f"Setting_{mapped_cat}"
            try:
                db_mgr.execute(
                    "INSERT INTO plots (book_id, content, status, importance) VALUES (?, ?, ?, 10)",
                    (book_id, full_content, db_status)
                )
                saved_count += 1
            except Exception as e:
                print(f"Setting insert error: {e}")
    return saved_count

def analyze_book_metadata_deep_ai(engine, book_title, full_text):
    assigned_key = FEATURE_MODELS.get("import_char_analysis", {}).get('default', 'DSK_V3')
    client, model_name, _ = engine.get_client(assigned_key)
    if not client: return None, 0

    log_operation("AI分析", f"开始深度分析书籍: {book_title}")
    
    sample = full_text[:25000] # 增加采样长度
    
    prompt = f"""
    你是一位资深网文主编。用户上传了小说《{book_title}》。
    
    请执行以下逻辑：
    1. **知识检索**：如果你非常确信自己阅览过《{book_title}》（且作者匹配），请直接根据你的知识库生成该书的详细数据。
    2. **文本分析**：如果你不认识这本书，或者书名太通用，请必须基于我提供的【文本前2.5万字】进行分析。
    
    【任务目标】
    请返回一个**纯 JSON 对象**，不要包含任何 Markdown 标记，严格遵守以下结构：
    
    {{
        "synopsis": "200字以内的剧情梗概",
        "tags": ["流派1", "关键词"],
        "characters": [
            {{
                "name": "姓名",
                "role": "主角/配角",
                "gender": "男/女",
                "desc": "人物简介",
                "origin": "出身",
                "profession": "职业",
                "cheat_ability": "金手指/能力",
                "power_level": "实力等级",
                "appearance_features": "外貌特征",
                "debts_and_feuds": "恩怨情仇"
            }}
        ],
        "relations": [
            {{ "char1": "角色A", "char2": "角色B", "desc": "关系描述" }}
        ],
        "world_settings": [
            {{ "category": "PowerSystem", "title": "境界划分", "content": "详细内容" }}
        ]
    }}

    【文本前2.5万字】：
    {sample}
    """
    
    try:
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 4000 # 增加 Token 限制，防止截断
        }
        # 尝试启用 JSON mode
        try:
            if "deepseek" in model_name.lower() or "gpt" in model_name.lower():
                kwargs["response_format"] = {"type": "json_object"}
        except:
            pass

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content.strip()
        usage = response.usage.total_tokens if response.usage else 0
        
        print(f"DEBUG - AI Response Length: {len(content)}") 

        parsed_data = extract_and_parse_json(content)
        
        if not parsed_data:
            print(f"❌ JSON 解析失败，完整内容前500字符: {content[:500]}")

        record_token_usage("OpenAI", model_name, usage, f"导入分析(智能版)-《{book_title}》", book_title)
        return parsed_data, usage
    except Exception as e:
        log_operation("AI分析", f"分析失败：{e}")
        print(f"AI Error: {e}")
        return None, 0

def generate_structure_via_ai_v2(engine, title, intro, genre_list, status_callback=None, target_chapter_count=50):
    """
    生成书籍结构 (新增 target_chapter_count 参数)
    """
    if isinstance(genre_list, list): 
        genre_str = ", ".join(genre_list)
    else: 
        genre_str = str(genre_list)

    assignments = engine.get_config_db("model_assignments", {})
    assigned_key = assignments.get("novel_structure_gen") or assignments.get("books_arch_gen") or "GPT_4o"
    client, model_name, _ = engine.get_client(assigned_key)
    
    if not client: 
        return False, f"⚠️ 未配置 AI 模型 (Key: {assigned_key})", {}, None

    # 🔥 【核心配置】针对 DeepSeek 开启 8k 上下文
    base_max_tokens = 4000
    if "deepseek" in model_name.lower():
        base_max_tokens = 8000

    final_data = { 
        "characters": [], 
        "relations": [], 
        "world_settings": [], 
        "structure": [] 
    }
    total_tokens = 0

    try:
        # ======================================================================
        # Step 1: 力量体系 (独立生成，避免干扰)
        # ======================================================================
        if status_callback: 
            status_callback(f"⚔️ Step 1/6: 构建独创的力量/科技体系...", 5)
        
        prompt_power = f"""
        你是一位【{genre_str}】网文主编。请为《{title}》设计**核心升级体系**。
        简介："{intro}"
        要求：
        1. 设定要有新意，包含具体的等级名称、晋升条件、核心资源。
        2. 必须包含“代价”或“风险”设定。
        
        返回 JSON：
        {{ "world_settings": [ {{ "category": "PowerSystem", "title": "...", "content": "..." }} ] }}
        """
        
        power_context_str = ""
        try:
            res_p = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt_power}], 
                temperature=0.7, max_tokens=2500
            )
            if hasattr(res_p, 'usage'): total_tokens += res_p.usage.total_tokens
            data_p = extract_and_parse_json(res_p.choices[0].message.content)
            
            settings = []
            if isinstance(data_p, dict): settings = data_p.get("world_settings", [])
            elif isinstance(data_p, list): settings = data_p
            
            if settings:
                final_data["world_settings"].extend(settings)
                power_context_str = json.dumps(settings, ensure_ascii=False)
        except Exception as e:
            print(f"Power step error: {e}")

        # ======================================================================
        # Step 2: 地理与势力 (基于力量体系)
        # ======================================================================
        if status_callback: 
            status_callback(f"🌍 Step 2/6: 完善世界格局与势力斗争...", 15)
        
        prompt_geo = f"""
        基于力量体系：{power_context_str[:1000]}
        简介："{intro}"
        请完善世界观：
        1. **Geography (地理)**: 核心地图板块。
        2. **Organization (势力)**: 设计 3-4 个互相制衡或敌对的势力（正邪、朝堂、公会）。
        
        返回 JSON：
        {{ "world_settings": [ ... ] }}
        """
        
        world_context_str = power_context_str
        try:
            res_g = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt_geo}], 
                temperature=0.8, max_tokens=3000
            )
            if hasattr(res_g, 'usage'): total_tokens += res_g.usage.total_tokens
            data_g = extract_and_parse_json(res_g.choices[0].message.content)
            
            settings = []
            if isinstance(data_g, dict): settings = data_g.get("world_settings", [])
            elif isinstance(data_g, list): settings = data_g
            
            if settings:
                final_data["world_settings"].extend(settings)
                world_context_str = json.dumps(final_data["world_settings"], ensure_ascii=False)
        except Exception as e:
            print(f"World step error: {e}")

        # ======================================================================
        # Step 3: 核心双雄 (主角与宿敌 - 深度刻画)
        # ======================================================================
        if status_callback: 
            status_callback(f"👤 Step 3/6: 深度刻画主角与宿敌 (注入人性灰度)...", 30)
        
        char_schema = """
        字段要求：
        - name: 姓名
        - role: "主角" 或 "最终反派/宿敌"
        - gender: 性别
        - origin: 出身 (家族/宗门/过去)
        - profession: 表面身份
        - cheat_ability: 金手指/核心能力 (具体机制 + 代价)
        - personality_flaw: **性格缺陷** (如贪婪、傲慢、社恐、偏执)
        - hidden_agenda: **隐藏目的/秘密** (剧情钩子)
        - speech_style: 说话风格 (如"冷嘲热讽", "文绉绉")
        - avatar_kw: 英文绘画关键词
        """
        
        prompt_core_chars = f"""
        基于世界观：{world_context_str[:1200]}
        简介："{intro}"
        
        请设计 **2 名核心角色** (主角 + 核心反派/宿敌)。
        要求：
        1. 两人必须有**深层的利益冲突或理念分歧**。
        2. 拒绝脸谱化，反派要有魅力，主角要有阴暗面或弱点。
        
        {char_schema}
        
        返回 JSON：{{ "characters": [ ... ] }}
        """
        
        core_chars = []
        try:
            res_c1 = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt_core_chars}], 
                temperature=0.85, max_tokens=base_max_tokens # 8k tokens
            )
            if hasattr(res_c1, 'usage'): total_tokens += res_c1.usage.total_tokens
            data_c1 = extract_and_parse_json(res_c1.choices[0].message.content)
            
            if isinstance(data_c1, dict): core_chars = data_c1.get("characters", [])
            elif isinstance(data_c1, list): core_chars = data_c1
            
            if core_chars: final_data["characters"].extend(core_chars)
        except Exception as e:
            print(f"Core Char error: {e}")

        # ======================================================================
        # Step 4: 重要配角 (扩展角色库)
        # ======================================================================
        if status_callback: 
            status_callback(f"👥 Step 4/6: 补充 4-6 名关键配角 (丰富群像)...", 50)
        
        existing_names = [c['name'] for c in final_data["characters"] if 'name' in c]
        
        prompt_sub_chars = f"""
        基于主角与反派：{", ".join(existing_names)}
        请额外设计 **4-6 名重要配角** (如：主角的引路人、反派的军师、亦敌亦友的竞争者、关键道具持有者)。
        
        要求：
        1. 每个角色都必须与主角或反派有直接关联。
        2. 包含字段：name, role, origin, profession, cheat_ability, personality_flaw, debts_and_feuds (恩怨), avatar_kw.
        
        返回 JSON：{{ "characters": [ ... ] }}
        """
        
        try:
            res_c2 = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt_sub_chars}], 
                temperature=0.85, max_tokens=base_max_tokens
            )
            if hasattr(res_c2, 'usage'): total_tokens += res_c2.usage.total_tokens
            data_c2 = extract_and_parse_json(res_c2.choices[0].message.content)
            
            sub_chars = []
            if isinstance(data_c2, dict): sub_chars = data_c2.get("characters", [])
            elif isinstance(data_c2, list): sub_chars = data_c2
            
            if sub_chars: final_data["characters"].extend(sub_chars)
        except Exception as e:
            print(f"Sub Char error: {e}")

        # ======================================================================
        # Step 5: 人物关系网
        # ======================================================================
        if status_callback: 
            status_callback(f"🕸️ Step 5/6: 编织复杂的人物关系网...", 65)
        
        all_names = [c['name'] for c in final_data["characters"] if 'name' in c]
        
        prompt_rel = f"""
        角色列表：{", ".join(all_names)}
        请生成 **10-15 组** 人物关系。
        要求：不要只写“朋友/敌人”，要具体。例如“表面师徒实则利用”、“因争夺某物结仇”。
        格式：{{ "relations": [ {{ "char1": "A", "char2": "B", "desc": "..." }} ] }}
        """
        
        try:
            res_r = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt_rel}], 
                temperature=0.7, max_tokens=2000
            )
            if hasattr(res_r, 'usage'): total_tokens += res_r.usage.total_tokens
            data_r = extract_and_parse_json(res_r.choices[0].message.content)
            
            if isinstance(data_r, dict):
                final_data["relations"] = data_r.get("relations", [])
        except: pass

        # ======================================================================
        # Step 6: 分批生成大纲 (支持手动指定数量，每10章一切)
        # ======================================================================
        all_chapters = []
        prev_summary = "故事开始。"
        
        # 简化上下文，只传名字和简介，防止 Token 爆炸
        lite_char_context = ", ".join(all_names[:6])
        
        # 计算需要循环多少次 (向上取整)
        num_batches = (target_chapter_count + 9) // 10
        
        for i in range(num_batches): 
            start_c = i * 10 + 1
            # 确保结束章节不超过目标总数
            end_c = min((i + 1) * 10, target_chapter_count)
            
            if status_callback: 
                # 动态计算进度百分比：基础70% + (当前批次 / 总批次) * 剩余25%
                current_batch_progress = (i / num_batches) * 25
                status_callback(f"📝 Step 6/6: 正在构思第 {start_c}-{end_c} 章 (进度 {i+1}/{num_batches})...", 70 + int(current_batch_progress))
            
            prompt_outline = f"""
            小说：《{title}》
            类型：{genre_str}
            核心角色：{lite_char_context}
            前情概要：{prev_summary}
            
            任务：请生成 **第 {start_c} 章 到 第 {end_c} 章** 的大纲。
            要求：
            1. 剧情紧凑，包含冲突和反转。
            2. 必须体现主角的金手指运用和性格弱点带来的麻烦。
            3. 每章 title (标题), summary (80-100字内容)。
            
            返回 JSON：
            {{ "chapters": [ {{ "title": "...", "summary": "..." }}, ... ] }}
            """
            
            try:
                res_out = client.chat.completions.create(
                    model=model_name, messages=[{"role": "user", "content": prompt_outline}], 
                    temperature=0.8, max_tokens=base_max_tokens # 8k for DeepSeek
                )
                if hasattr(res_out, 'usage'): total_tokens += res_out.usage.total_tokens
                data_out = extract_and_parse_json(res_out.choices[0].message.content)
                
                new_chaps = []
                if isinstance(data_out, dict): new_chaps = data_out.get("chapters", [])
                elif isinstance(data_out, list): new_chaps = data_out
                
                if new_chaps:
                    all_chapters.extend(new_chaps)
                    # 更新前情摘要，只取最后 2 章的摘要作为下一轮的输入
                    last_sums = [c.get('summary','') for c in new_chaps[-2:]]
                    prev_summary = f"第{end_c}章结束。近期剧情：{' '.join(last_sums)}"
                
                time.sleep(0.5) # 避免触发 API 速率限制
                
            except Exception as e:
                print(f"Outline batch {i} error: {e}")

        # 构建最终结构
        if all_chapters:
            final_data["structure"] = [{ 
                "part_name": "第一卷：风起萍末", 
                "volumes": [{ 
                    "vol_name": "正文", 
                    "chapters": all_chapters 
                }] 
            }]
        
        if status_callback: 
            status_callback("✅ 架构生成完毕，写入数据库...", 98)
        
        record_token_usage("OpenAI", model_name, total_tokens, f"架构生成-《{title}》", title)
        
        return True, final_data, {'total_tokens': total_tokens}, assigned_key

    except Exception as e:
        return False, f"AI 调用失败: {str(e)}", {}, None

def _write_ai_characters(db_mgr, book_id, chars):
    if not chars: return 0
    n_chars = 0
    dicebear_base = "https://api.dicebear.com/9.x/adventurer/svg?seed="
    
    for char in chars:
        if not isinstance(char, dict): continue
        
        name = char.get('name', '未命名')
        if not name: continue
        
        role = char.get('role', '配角')
        gender = char.get('gender', '未知')
        race = char.get('race', '人族')
        desc = char.get('desc', '')
        
        avatar_kw = char.get('avatar_kw', '') or f"{name} fantasy style"
        if name in avatar_kw: search_query = avatar_kw
        else: search_query = f"{name} {avatar_kw}"
        avatar_url = generate_bing_search_image(search_query) 
        if not avatar_url: avatar_url = f"{dicebear_base}{urllib.parse.quote(name)}&flip=true"

        origin = char.get('origin', '未知')
        profession = char.get('profession', '无')
        cheat_ability = char.get('cheat_ability', '无')
        power_level = char.get('power_level', '未知')
        ability_limitations = char.get('ability_limitations', '无')
        appearance_features = char.get('appearance_features', '')
        signature_sign = char.get('signature_sign', '')
        relationship_to_protagonist = char.get('relationship_to_protagonist', '未知')
        social_role = char.get('social_role', '')
        debts_and_feuds = char.get('debts_and_feuds', '')

        if not desc:
            desc = f"【身份】{origin}，{profession}。\n【外貌】{appearance_features}。\n【能力】{cheat_ability}（{power_level}）。"

        try:
            db_mgr.execute(
                """INSERT INTO characters (
                    book_id, name, role, gender, race, desc, is_major, avatar,
                    origin, profession, cheat_ability, power_level, ability_limitations,
                    appearance_features, signature_sign, relationship_to_protagonist, social_role, debts_and_feuds
                ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)""",
                (
                    book_id, name, role, gender, race, desc, True, avatar_url,
                    origin, profession, cheat_ability, power_level, ability_limitations,
                    appearance_features, signature_sign, relationship_to_protagonist, social_role, debts_and_feuds
                )
            )
            n_chars += 1
        except Exception as e:
            try:
                db_mgr.execute(
                    "INSERT INTO characters (book_id, name, role, gender, race, desc, is_major, avatar) VALUES (?,?,?,?,?,?,?,?)",
                    (book_id, name, role, gender, race, desc, True, avatar_url)
                )
                n_chars += 1
            except Exception as e2:
                print(f"Char insert failed completely: {e2}")

    return n_chars

def _write_ai_relations(db_mgr, book_id, relations, char_map):
    if not relations: return 0
    n_rels = 0
    clean_relations = []
    
    normalized_map = {}
    for name, cid in char_map.items():
        norm_name = name.strip().lower()
        normalized_map[norm_name] = cid
        if "(" in norm_name: normalized_map[norm_name.split('(')[0]] = cid
    
    for rel in relations:
        if not isinstance(rel, dict): continue
        char1 = rel.get('char1', '').strip()
        char2 = rel.get('char2', '').strip()
        desc = rel.get('desc', '关联')
        if not char1 or not char2: continue

        c1_id = normalized_map.get(char1.lower())
        c2_id = normalized_map.get(char2.lower())
        
        if not c1_id:
            for k, v in normalized_map.items(): 
                if char1.lower() in k or k in char1.lower(): c1_id = v; break
        if not c2_id:
            for k, v in normalized_map.items():
                if char2.lower() in k or k in char2.lower(): c2_id = v; break

        if c1_id and c2_id and c1_id != c2_id:
            clean_relations.append({"source": c1_id, "target": c2_id, "label": desc, "weight": 3})
            n_rels += 1
            
    save_relations_to_disk(book_id, clean_relations)
    return n_rels

def _write_ai_structure(db_mgr, book_id, structure):
    n_chaps = 0
    if not structure: return 0
    if not isinstance(structure, list): return 0

    for p_idx, part in enumerate(structure):
        if not isinstance(part, dict): continue
        p_name = part.get('part_name', f'第{p_idx+1}篇')
        part_id = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?,?,?)", (book_id, p_name, (p_idx+1)*100))
        
        volumes = part.get('volumes', [])
        for v_idx, vol in enumerate(volumes):
            if not isinstance(vol, dict): continue
            v_name = vol.get('vol_name', f'第{v_idx+1}卷')
            vol_id = db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?,?,?,?)", (book_id, part_id, v_name, (v_idx+1)*100))
            raw_chapters = vol.get('chapters', [])
            for c_idx, chap in enumerate(raw_chapters):
                c_title = chap.get('title', f"第{c_idx+1}章") if isinstance(chap, dict) else str(chap)
                c_summary = chap.get('summary', "") if isinstance(chap, dict) else ""
                db_mgr.execute("INSERT INTO chapters (volume_id, title, content, summary, sort_order) VALUES (?,?,?,?,?)",
                    (vol_id, c_title, "", c_summary, c_idx+1))
                n_chaps += 1
    return n_chaps

def _process_ai_generated_data(db_mgr, engine, book_id, res_data, book_title, book_category):
    """
    处理AI生成的数据，增强容错性
    """
    # 🛡️ 容错核心：确保 res_data 是字典
    if isinstance(res_data, list):
        if len(res_data) > 0 and isinstance(res_data[0], dict):
             # 尝试合并列表中的字典
             merged = {}
             for item in res_data:
                 if isinstance(item, dict): merged.update(item)
             res_data = merged
        else:
             res_data = {}
    
    if not isinstance(res_data, dict):
        print(f"Warning: res_data is not a dict, got {type(res_data)}")
        res_data = {}
    
    # 辅助函数，用于模糊匹配键名
    def get_robust_list(data, possible_keys):
        for k in possible_keys:
            if k in data and isinstance(data[k], list):
                return data[k]
        return []

    # 处理角色数据 (支持多种键名)
    char_keys = ['characters', 'Characters', 'roles', 'chars', '角色列表', '人物']
    characters = get_robust_list(res_data, char_keys)
    
    if not characters:
        print(f"⚠️ 未提取到角色数据，当前Keys: {res_data.keys()}")
    
    n_chars = _write_ai_characters(db_mgr, book_id, characters)
    
    # 获取角色映射
    char_map_res = db_mgr.query("SELECT name, id FROM characters WHERE book_id=?", (book_id,))
    char_map = {r['name']: r['id'] for r in char_map_res}
    
    # 处理关系数据
    rel_keys = ['relations', 'Relations', 'relationships', 'relationship', '人物关系', '关系']
    relations = get_robust_list(res_data, rel_keys)
    
    n_rels = _write_ai_relations(db_mgr, book_id, relations, char_map)
    
    # 处理世界观设定
    setting_keys = ['world_settings', 'WorldSettings', 'settings', 'world', '世界观', '设定']
    world_settings = get_robust_list(res_data, setting_keys)
    
    n_settings = _write_detailed_world_settings(db_mgr, book_id, world_settings)
    
    return n_chars, n_rels, n_settings

# ==============================================================================
# 解析逻辑
# ==============================================================================
CN_NUM = {'零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10, '百':100, '千':1000, '万':10000}
def parse_volume_number(num_str):
    if not num_str: return 0
    if num_str.isdigit(): return int(num_str)
    try:
        val = 0; current_val = 0
        if num_str.startswith('十'): num_str = '一' + num_str 
        for char in num_str:
            if char in CN_NUM:
                digit = CN_NUM[char]
                if digit >= 10:
                    if current_val == 0: current_val = 1; current_val *= digit; val += current_val; current_val = 0
                else: current_val = digit
        val += current_val
        return val if val > 0 else 0
    except: return 0

def _parse_book_structure(full_text):
    lines = full_text.splitlines()
    parts_list = []
    part_index_map = {} 
    
    default_part = {'idx': 1, 'name': '正文', 'vol_map': {}, 'vol_list': []}
    parts_list.append(default_part)
    part_index_map[1] = default_part
    
    default_vol = {'idx': 1, 'name': '默认卷', 'chapters': []}
    default_part['vol_list'].append(default_vol)
    default_part['vol_map'][1] = default_vol
    
    current_part = default_part
    current_vol = default_vol
    current_chap_title = None
    current_chap_content = []

    combined_pattern = re.compile(r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[卷部篇集]|Volume\s*(\d+))\s*(.*?)\s*(第\s*|)([0-9零一二三四五六七八九十百千万]+[章节回]|Chapter\s*\d+|序章|楔子|前言|尾声|后记)(.*)$', re.IGNORECASE)
    part_pattern = re.compile(r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[篇部]|Part\s*(\d+))(.*)$', re.IGNORECASE)
    vol_pattern = re.compile(r'^\s*(?:第\s*([0-9零一二三四五六七八九十百千万]+)\s*[卷集]|Volume\s*(\d+))(.*)$', re.IGNORECASE)
    chap_pattern = re.compile(r'^\s*(?:正文\s*)?(第\s*|)([0-9零一二三四五六七八九十百千万]+[章节回]|Chapter\s*\d+|序章|楔子|前言|尾声|后记)(.*)$', re.IGNORECASE)

    def save_current_chapter():
        if current_chap_title and current_chap_content:
            content_str = "\n".join(current_chap_content).strip()
            if content_str: current_vol['chapters'].append({'title': current_chap_title, 'content': content_str})

    def process_volume_switch(num_str, title_str):
        nonlocal current_vol
        v_idx = parse_volume_number(num_str)
        if v_idx == 0: v_idx = len(current_part['vol_list']) + 1
        prefix = f"第{num_str}卷" if not num_str.isdigit() else f"Volume {num_str}"
        full_v_name = title_str if title_str and title_str.startswith(prefix) else f"{prefix} {title_str}".strip()

        if v_idx in current_part['vol_map']:
            current_vol = current_part['vol_map'][v_idx]
            if len(full_v_name) > len(current_vol['name']): current_vol['name'] = full_v_name
        else:
            is_curr_vol_empty = (len(current_vol['chapters']) == 0 and current_vol['name'] == '默认卷')
            if is_curr_vol_empty and v_idx == 1:
                current_vol['name'] = full_v_name; current_part['vol_map'][1] = current_vol 
            else:
                new_vol = {'idx': v_idx, 'name': full_v_name, 'chapters': []}
                current_part['vol_list'].append(new_vol); current_part['vol_map'][v_idx] = new_vol; current_vol = new_vol

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_chap_title: current_chap_content.append(line)
            continue

        combined_match = combined_pattern.match(stripped)
        part_match = part_pattern.match(stripped) if not combined_match else None
        vol_match = vol_pattern.match(stripped) if not combined_match else None
        chap_match = chap_pattern.match(stripped) if not combined_match and not part_match and not vol_match else None

        if combined_match:
            save_current_chapter() 
            v_num = combined_match.group(1) or combined_match.group(2)
            v_title_part = combined_match.group(3).strip()
            process_volume_switch(v_num, v_title_part)
            c_marker = combined_match.group(4).strip() + combined_match.group(5).strip()
            c_title_part = combined_match.group(6).strip()
            current_chap_title = f"{c_marker} {c_title_part}".strip()
            current_chap_content = []
            continue

        if part_match:
            save_current_chapter()
            num_str = part_match.group(1) or part_match.group(2)
            p_idx = parse_volume_number(num_str)
            if p_idx == 0: p_idx = len(parts_list) + 1
            p_title = part_match.group(3).strip()
            
            new_part = {'idx': p_idx, 'name': f"第{num_str}篇 {p_title}".strip(), 'vol_map': {}, 'vol_list': []}
            parts_list.append(new_part); part_index_map[p_idx] = new_part; current_part = new_part
            vol = { 'idx': 1, 'name': '默认卷', 'chapters': [] }; current_part['vol_list'].append(vol); current_part['vol_map'][1] = vol; current_vol = vol
            current_chap_title = None; current_chap_content = []
            continue

        if vol_match:
            save_current_chapter()
            num = vol_match.group(1) or vol_match.group(2)
            title = vol_match.group(3).strip()
            process_volume_switch(num, title)
            current_chap_title = None; current_chap_content = []
            continue

        if chap_match:
            save_current_chapter()
            raw_title = f"{chap_match.group(1).strip()}{chap_match.group(2).strip()} {chap_match.group(3).strip() or ''}".strip()
            current_chap_title = raw_title
            current_chap_content = []
            continue

        if current_chap_title: current_chap_content.append(line)
        else:
            if stripped and len(stripped) < 50: 
                 if not current_chap_content: 
                     current_chap_title = "序言/引子"; current_chap_content.append(line)
                 else: current_chap_content.append(line)
            elif stripped:
                 current_chap_content.append(line)
    
    save_current_chapter()
    
    total_chaps = sum(len(v['chapters']) for p in parts_list for v in p['vol_list'])

    if total_chaps < 5 and len(full_text) > 50000:
        print("⚠️ 触发暴力分章模式...")
        log_operation("解析", "触发暴力分章模式")
        
        fallback_structure = [{'part_name': '正文', 'volumes': [{'vol_name': '全书', 'chapters': []}]}]
        target_vol = fallback_structure[0]['volumes'][0]
        
        force_chap_pattern = re.compile(r'^\s*(?:正文\s*)?(第\s*[0-9零一二三四五六七八九十百千万]+\s*[章节回]|Chapter\s*\d+)(.*)$', re.MULTILINE)
        split_res = force_chap_pattern.split(full_text)
        
        if split_res[0].strip():
            target_vol['chapters'].append({'title': '序章', 'content': split_res[0].strip()})
            
        i = 1
        while i < len(split_res) - 1:
            title_key = split_res[i] 
            title_suffix = split_res[i+1] 
            content = split_res[i+2] if i+2 < len(split_res) else ""
            full_title = f"{title_key} {title_suffix}".strip()
            target_vol['chapters'].append({'title': full_title, 'content': content.strip()})
            i += 3
            
        return fallback_structure

    final_structure = []
    for p in parts_list:
        valid_vols = []
        for v in p['vol_list']:
            if v['chapters']: valid_vols.append({'vol_name': v['name'], 'chapters': v['chapters']})
        if valid_vols: final_structure.append({'part_name': p['name'], 'volumes': valid_vols})
        
    return final_structure

def _import_book_process(db_mgr, engine, uploaded_file, book_id, book_title, book_author, genre_hint=""):
    progress_bar = st.progress(0)
    n_chaps, n_chars, n_rels, n_settings, detected_tags, usage_info = 0, 0, 0, 0, [], {}
    
    try:
        with st.status("🚀 正在导入书籍...", expanded=True) as status:
            status.write(f"📂 正在读取 {uploaded_file.name} ...")
            uploaded_file.seek(0) 
            full_text = extract_text_from_file(uploaded_file)
            progress_bar.progress(10)
            if "文件解析失败" in full_text: st.error(full_text); return 0, 0, 0, 0, 0, [], {}

            if "-" in uploaded_file.name:
                parts = uploaded_file.name.rsplit('.', 1)[0].split('-')
                if len(parts) >= 2:
                    book_title = parts[0]
                    book_author = parts[1]
                    db_mgr.execute("UPDATE books SET title=?, author=? WHERE id=?", (book_title, book_author, book_id))
            
            status.write("📂 正在解析章节结构 (双模式扫描)...")
            structure = _parse_book_structure(full_text)
            progress_bar.progress(25)
            
            total_chaps = sum(sum(len(v['chapters']) for v in p['volumes']) for p in structure)
            if total_chaps == 0:
                 structure = [{'part_name': '正文', 'volumes': [{'vol_name': '全书', 'chapters': [{'title': '全文内容', 'content': full_text}]}]}]
                 total_chaps = 1
            status.write(f"✅ 解析完成：共 {len(full_text)} 字，{total_chaps} 章")

            status.write("🧠 正在 AI 深度分析 (知识检索 + 文本分析)...")
            progress_bar.progress(40)
            
            ai_data, tokens = analyze_book_metadata_deep_ai(engine, book_title, full_text)
            usage_info = {'total_tokens': tokens}
            
            if ai_data and "error" not in ai_data:
                synopsis = ai_data.get('synopsis', '暂无简介')
                detected_tags = ai_data.get('tags', [genre_hint or "未分类"])
                
                db_mgr.execute("UPDATE books SET intro=? WHERE id=?", (synopsis, book_id))
                
                n_chars, n_rels, n_settings = _process_ai_generated_data(db_mgr, engine, book_id, ai_data, book_title, detected_tags[0])
                process_and_save_tags(db_mgr, book_id, detected_tags)
                status.write(f"✅ 档案建立：{n_chars} 名角色，{n_rels} 条关系")
            else:
                detected_tags = [genre_hint or "未分类"]

            progress_bar.progress(60)

            status.write("💾 正在写入数据库...")
            curr = 0; current_prog = 60.0
            for p_idx, part in enumerate(structure):
                # 🛠️ 修复核心：INSERT INTO parts 只接受3个参数 (book_id, name, sort_order)
                part_id = db_mgr.execute("INSERT INTO parts (book_id, name, sort_order) VALUES (?,?,?)", (book_id, part['part_name'], (p_idx+1)*100))

                for v_idx, vol in enumerate(part['volumes']):
                    vol_id = db_mgr.execute("INSERT INTO volumes (book_id, part_id, name, sort_order) VALUES (?,?,?,?)", (book_id, part_id, vol['vol_name'], (v_idx+1)*100))
                    for c_idx, chap in enumerate(vol['chapters']):
                        db_mgr.execute("INSERT INTO chapters (volume_id, title, content, summary, sort_order) VALUES (?,?,?,?,?)",
                            (vol_id, chap['title'], chap['content'], f"字数:{len(chap['content'])}", c_idx+1))
                        curr += 1
                        if curr % 50 == 0:
                            current_prog = min(99, current_prog + 0.5)
                            progress_bar.progress(int(current_prog))
            
            n_chaps = total_chaps
            progress_bar.progress(100)
            db_mgr.execute("UPDATE books SET updated_at=? WHERE id=?", (get_beijing_time(), book_id))
            
            status.update(label=f"🎉 导入成功！共 {n_chaps} 章", state="complete", expanded=False)
            log_operation("书籍导入", f"成功导入《{book_title}》，共 {n_chaps} 章")
            return n_chaps, n_chars, n_rels, n_settings, detected_tags, usage_info

    except Exception as e:
        log_operation("书籍导入", f"导入致命错误: {e}")
        st.error(f"导入出错: {e}")
        return 0, 0, 0, 0, [], {}

# ==============================================================================
# 4. 弹窗组件
# ==============================================================================

@dialog_decorator("➕ 添加自定义流派")
def dialog_add_custom_genre():
    st.markdown("请输入新的流派名称：")
    db_mgr = st.session_state.db
    
    new_genre = st.text_input("流派名称", key="input_custom_genre_modal")
    
    if st.button("确认添加", type="primary", use_container_width=True):
        val = new_genre.strip()
        if val:
            # 1. 查重
            existing = db_mgr.query("SELECT id FROM categories WHERE name=?", (val,))
            
            if not existing:
                try:
                    # 2. 写入数据库
                    db_mgr.execute("INSERT INTO categories (name) VALUES (?)", (val,))
                    
                    # 🔥 3. 【核心修复】强制更新 Session State (使用列表拼接赋值，触发重绘)
                    ms_key = "new_book_selected_genres"
                    
                    # 确保Key存在
                    current_selection = st.session_state.get(ms_key, [])
                    if not isinstance(current_selection, list):
                        current_selection = []
                    
                    # 如果当前未选中，则添加并重新赋值
                    if val not in current_selection:
                        st.session_state[ms_key] = current_selection + [val]
                        print(f"DEBUG: Updated session state {ms_key} to {st.session_state[ms_key]}")
                    
                    st.success(f"✅ 已添加并选中：{val}")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"添加失败: {e}")
            else:
                st.warning("⚠️ 该流派已存在")
        else:
            st.warning("名称不能为空")

@dialog_decorator("🎉 AI 创作完成")
def show_import_report_modal(data):
    db_mgr = st.session_state.db
    book_title = data.get('title', '新书')
    book_id = data.get('book_id')
    
    st.success(f"《{book_title}》架构已生成！")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("章节", data.get('chapters', 0))
    c2.metric("角色", data.get('chars', 0))
    c3.metric("关系", data.get('relations', 0))
    c4.metric("设定", data.get('settings', 0))
    st.divider()
    usage_info = data.get('usage', {})
    if usage_info and 'total_tokens' in usage_info:
        st.caption(f"Tokens 消耗: {usage_info.get('total_tokens', 0)}")
    
    if st.button("开始写作", type="primary", use_container_width=True):
        if 'import_report_data' in st.session_state: del st.session_state['import_report_data']
        st.session_state.current_book_id = book_id
        st.session_state.current_menu = "write"
        st.rerun()
    if st.button("关闭", type="secondary", use_container_width=True):
        if 'import_report_data' in st.session_state: del st.session_state['import_report_data']
        st.rerun()

# ==============================================================================
# 5. UI 渲染函数
# ==============================================================================

def render_import_section(engine):
    """书籍导入文件拖拽区"""
    db_mgr = st.session_state.db
    
    st.markdown("""
    <style>
    [data-testid="stFileUploaderDropzone"] {
        position: relative;
        padding: 30px 10px;
        border: 2px dashed #4CAF50;
        background-color: #f9f9f9;
        min-height: 120px;
    }
    [data-testid="stFileUploaderDropzone"] div div::before { display: none; }
    [data-testid="stFileUploaderDropzone"] div div span { display: none; }
    [data-testid="stFileUploaderDropzone"] div div small { display: none; }
    [data-testid="stFileUploaderDropzone"] button { display: none; }
    
    [data-testid="stFileUploaderDropzone"]::after { 
        content: "点击或将文件拖拽至此上传"; 
        visibility: visible; 
        display: block;
        position: absolute; 
        top: 40%; 
        left: 50%; 
        transform: translate(-50%, -50%);
        color: #333; 
        font-weight: bold; 
        font-size: 16px; 
        pointer-events: none;
    }
    [data-testid="stFileUploaderDropzone"]::before { 
        content: "支持 TXT / PDF / EPUB / DOCX (最大 200MB)"; 
        visibility: visible; 
        display: block;
        position: absolute; 
        top: 60%; 
        left: 50%; 
        transform: translate(-50%, -50%);
        color: #666; 
        font-size: 12px; 
        pointer-events: none;
    }
    </style>
    """, unsafe_allow_html=True)
    
    with st.expander("📥 导入书籍", expanded=False):
        uploaded_file = st.file_uploader("文件上传区", type=["txt", "pdf", "epub", "docx"], key="import_file_real", label_visibility="collapsed")
        
        if uploaded_file:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.get('last_loaded_file') != file_id:
                new_title = os.path.splitext(uploaded_file.name)[0]
                if "-" in new_title: new_title = new_title.split('-')[0]
                st.session_state['import_book_title_ui'] = new_title
                st.session_state['last_loaded_file'] = file_id
                st.rerun()

        with st.form("form_import_action"):
            c1, c2 = st.columns(2)
            default_title = st.session_state.get('import_book_title_ui', "")
            title_input = c1.text_input("书名", value=default_title)
            author_input = c2.text_input("作者", value="未知")
            genre_hint = st.text_input("📚 辅助关键词 (让 AI 更懂这本小说)", placeholder="例如：玄幻, 退婚流, 斗气")
            submitted = st.form_submit_button("🚀 开始导入", type="primary", use_container_width=True)
        
        if submitted:
            if not uploaded_file: st.error("请先上传文件")
            elif not title_input.strip(): st.error("书名不能为空")
            else:
                bid = None 
                try:
                    now_str = get_beijing_time()
                    bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", 
                                         (title_input, author_input, "导入中...", now_str, now_str))
                    
                    n_chaps, n_chars, n_rels, n_settings, detected_tags, usage = _import_book_process(db_mgr, engine, uploaded_file, bid, title_input, author_input, genre_hint)
                    
                    st.session_state['import_report_data'] = {
                        'title': title_input, 'chapters': n_chaps, 'chars': n_chars, 'relations': n_rels, 'settings': n_settings, 'tags': detected_tags, 'book_id': bid, 'usage': usage
                    }
                    st.rerun()
                except Exception as e:
                    if bid: db_mgr.execute("DELETE FROM books WHERE id=?", (bid,))
                    st.error(f"导入错误: {e}")

def render_book_card(book):
    """
    书籍卡片渲染 (修复版)
    移除有缺陷的日期对比纠偏逻辑，直接显示时间。
    一旦使用新的 get_beijing_time 写入数据库，显示即会正常。
    """
    book = dict(book)
    bid = book['id']
    book_title = book['title']
    db_mgr = st.session_state.db
    
    book_categories = db_mgr.query("SELECT c.name FROM book_categories bc JOIN categories c ON bc.category_id = c.id WHERE bc.book_id = ?", (bid,))
    genre_list = [c['name'] for c in book_categories]
    genre_value = " / ".join(genre_list) if genre_list else '未分类'
    
    # 格式化时间字符串，去掉毫秒
    raw_c_time = str(book.get('created_at', '')).replace('T', ' ').split('.')[0]
    raw_u_time = str(book.get('updated_at', '')).replace('T', ' ').split('.')[0]
    
    # 截取文件名用于缓存检查
    file_path = get_cached_file_path(bid, book_title)
    size_label = None
    if os.path.exists(file_path):
        f_size = os.path.getsize(file_path) / 1024 
        size_label = f"{f_size:.1f}KB" if f_size < 1024 else f"{f_size/1024:.1f}MB"

    intro_full = html.escape(book.get('intro') or "暂无简介")

    with st.container(border=True):
        c_head_L, c_head_R = st.columns([3, 1])
        with c_head_L: 
            st.markdown(f"""
            <div title="{intro_full}" style='height: 48px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; cursor: help;'>
                <h4 style='margin:0; padding:0; line-height: 1.2;'>📖 {book['title']}</h4>
            </div>
            """, unsafe_allow_html=True)
        with c_head_R:
            if size_label: st.markdown(f"<div style='text-align: right; color: #888; font-size: 12px; margin-top: 5px;'>📦 {size_label}</div>", unsafe_allow_html=True)
        
        # 移除了 faulty 的自动纠偏逻辑，直接显示
        st.markdown(f"""
        <div style='height: 90px; overflow-y: hidden; font-size: 13px; color: #555; margin-bottom: 10px; border-bottom: 1px dashed #eee;'>
            <div style='margin-bottom: 2px;'><b>作者:</b> {book['author']}</div>
            <div style='margin-bottom: 2px;'><b>分类:</b> {genre_value}</div>
            <div style='margin-bottom: 2px; color:#888; font-size:12px;'>📅 创建: {raw_c_time}</div>
            <div style='margin-bottom: 2px; color:#2e7d32; font-size:12px;'>⏱️ 更新: <b>{raw_u_time}</b></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height: 4px'></div>", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("✍️ 写作", key=f"ent_{bid}", type="primary", use_container_width=True, help="进入写作模式"):
            # 🔥 点击写作时，使用新的 get_beijing_time() 强制修复数据库中的时间
            db_mgr.execute("UPDATE books SET updated_at=? WHERE id=?", (get_beijing_time(), bid))
            st.session_state.current_book_id = bid
            st.session_state.current_menu = "write"
            
            # 🔥 [关键修改]：只设置 Flag，不要在这里执行 JS，因为 st.rerun() 会打断它
            st.session_state.trigger_scroll_to_top = True 
            
            st.rerun()
            
        if c2.button("📑 预览", key=f"view_{bid}", use_container_width=True, help="查看章节列表"):
             st.session_state.current_book_id = bid; st.session_state.current_menu = "chapters"; st.rerun()
             
        with c3:
            # 🔥 修改：将"打包"和"导出"合并，直接生成最新内容
            if st.button("📥 导出", key=f"dl_{bid}", use_container_width=True, help="导出最新内容到本地文件夹"):
                try:
                    # 总是重新生成最新内容
                    content = generate_book_content(db_mgr, bid)
                    
                    # 同时更新缓存文件
                    with open(file_path, "w", encoding='utf-8') as f: 
                        f.write(content)
                    
                    # 保存到本地
                    success, saved_path = save_file_locally(f"{book_title}.txt", content)
                    if success:
                        audit_download_callback(book_title, bid)
                        show_export_success_modal(saved_path)
                except Exception as e:
                    st.error(f"导出失败: {e}")
                    
        if c4.button("🗑️ 删除", key=f"del_{bid}", use_container_width=True, help="永久删除"):
            db_mgr.execute("DELETE FROM books WHERE id=?", (bid,))
            if os.path.exists(file_path): os.remove(file_path)
            st.rerun()

def render_books(engine):
    """书籍管理主界面"""
    db_mgr = st.session_state.db
    ensure_export_dir() 
    
    if 'import_report_data' in st.session_state:
        show_import_report_modal(st.session_state['import_report_data'])

    render_header("📚", "书籍管理")
    render_import_section(engine) 
    
    # 🗑️ 移除旧的缓存 List，直接依赖 DB 和 Key
    
    # 🔥 [修改] expanded=False 默认折叠
    with st.expander("✨ AI 架构向导 (从零开始)", expanded=False):
        with st.form("form_new_book"):
            # 🔥 [UI 更新] 改为三列布局，增加“生成章节数”输入
            c_title, c_auth, c_num = st.columns([2, 1, 1])
            b_title = c_title.text_input("书名", placeholder="例如：诡秘之主")
            b_author = c_auth.text_input("作者", "我")
            b_target_chaps = c_num.number_input("生成章节数量", min_value=10, max_value=200, value=50, step=10, help="每10章为一个生成批次")
            
            # 🔥 [修复关键]：每次渲染时，从数据库实时拉取最新的 Categories
            existing_cats_db = db_mgr.query("SELECT name FROM categories")
            db_cats = [c['name'] for c in existing_cats_db] if existing_cats_db else []
            
            # 合并：默认流派 + 数据库流派 -> 去重 -> 排序
            all_options = sorted(list(set(FLAT_GENRE_LIST + db_cats)))
            
            # 🔥 [新增] 在渲染多选框前，确保 Session State 中 key 存在且类型正确
            ms_key = "new_book_selected_genres"
            if ms_key not in st.session_state:
                st.session_state[ms_key] = []
            
            # 🔥 [新增 key] 绑定 Session State，以便自动选中
            b_category = st.multiselect("流派", all_options, placeholder="选择流派...", key=ms_key)
            if st.form_submit_button("➕ 添加流派", type="secondary"): dialog_add_custom_genre()

            b_intro = st.text_area("简介 / 核心脑洞 (AI 生成依据)", height=150, placeholder="例如：穿越到异界，开局被退婚...")
            
            c_sub1, c_sub2 = st.columns([1, 4])
            btn_create = c_sub1.form_submit_button("仅创建", use_container_width=True)
            # 🔥 [UI 更新] 按钮文本动态显示章节数
            btn_create_gen = c_sub2.form_submit_button(f"🚀 启动 AI 架构师 (生成角色 + {b_target_chaps}章大纲)", type="primary", use_container_width=True)
            
            if btn_create or btn_create_gen:
                if not b_title.strip():
                    st.error("书名不能为空")
                elif btn_create_gen and not b_intro.strip():
                    st.error("AI 模式必须填写简介")
                else:
                    bid = None
                    try:
                        now_str = get_beijing_time()
                        bid = db_mgr.execute("INSERT INTO books (title, author, intro, created_at, updated_at) VALUES (?,?,?,?,?)", 
                                             (b_title, b_author, b_intro, now_str, now_str))
                        if b_category: process_and_save_tags(db_mgr, bid, b_category)

                        if btn_create_gen:
                            status_container = st.status("🧠 AI 正在构思...", expanded=True)
                            progress_bar = status_container.progress(5)
                            def update_status(msg, p):
                                status_container.write(msg)
                                progress_bar.progress(p)

                            # 🔥 [Logic 更新] 传入 target_chapter_count
                            ok, res_data, usage, _ = generate_structure_via_ai_v2(engine, b_title, b_intro, b_category, update_status, target_chapter_count=b_target_chaps)
                            
                            if ok:
                                progress_bar.progress(95)
                                status_container.write("💾 正在写入数据库...")
                                
                                # 🛡️ 容错处理：确保 AI 返回的是 Dict，如果是 List 则尝试恢复
                                if isinstance(res_data, list):
                                     if len(res_data) > 0 and isinstance(res_data[0], dict):
                                          merged_data = {}
                                          for item in res_data:
                                              if isinstance(item, dict): merged_data.update(item)
                                          res_data = merged_data
                                     else:
                                          res_data = {}
                                
                                if not isinstance(res_data, dict):
                                     res_data = {}

                                n_chars, n_rels, n_settings = _process_ai_generated_data(db_mgr, engine, bid, res_data, b_title, b_category)
                                
                                # 安全获取 structure
                                struct_data = res_data.get('structure', [])
                                n_chaps = _write_ai_structure(db_mgr, bid, struct_data)
                                
                                db_mgr.execute("UPDATE books SET updated_at=? WHERE id=?", (get_beijing_time(), bid))
                                status_container.update(label="✅ 完成！", state="complete")
                                
                                st.session_state['import_report_data'] = {
                                    'title': b_title, 'chapters': n_chaps, 'chars': n_chars, 'relations': n_rels, 'settings': n_settings, 'tags': b_category, 'book_id': bid, 'usage': usage
                                }
                                time.sleep(1); st.rerun()
                            else:
                                st.error(f"AI 生成失败: {res_data}")
                        else:
                            st.toast("✅ 书籍已创建"); time.sleep(0.5); st.rerun()
                    except Exception as e:
                        st.error(f"操作失败: {e}")
                        if bid: db_mgr.execute("DELETE FROM books WHERE id=?", (bid,))

    # 书籍列表
    books = db_mgr.query("SELECT * FROM books ORDER BY updated_at DESC")
    if books:
        for i in range(0, len(books), 2):
            cols = st.columns(2)
            with cols[0]: render_book_card(books[i])
            if i+1 < len(books):
                with cols[1]: render_book_card(books[i+1])
    else:
        st.info("暂无书籍。")