

import json
import time
import os
from datetime import datetime
import pandas as pd
import streamlit as st
import csv 
from PIL import Image


from config import MODEL_GROUPS, DEFAULT_MODEL_MAPPING, FEATURE_MODELS, AVAILABLE_MODELS


HAS_NTP = False
HAS_SEARCH = False

def get_ntp_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 全局映射 (运行时会更新)
MODEL_MAPPING = DEFAULT_MODEL_MAPPING.copy()


try:
    from openai import OpenAI
except ImportError:
    class MockStream:
        def __iter__(self): yield type('C',(),{'choices':[type('C',(),{'delta':type('C',(),{'content':'Mock Data...'})})]})
    class MockChat:
        def completions(self, *args, **kwargs):
            if kwargs.get('stream'): return MockStream()
            return type('R',(),{'choices':[type('C',(),{'message':type('M',(),{'content':'Mock Response'})})]})
    class MockOpenAIClient:
        def __init__(self, *args, **kwargs): self.chat = MockChat()
        @property
        def api_key(self): return "mock_key"
    OpenAI = MockOpenAIClient

# ==============================================================================
# 1. 逻辑引擎与配置
# ==============================================================================

def load_and_update_model_config(engine_instance):
    """供 Settings 和 Writer 调用，刷新内存中的配置"""
    global MODEL_MAPPING, AVAILABLE_MODELS
    cfg = engine_instance.get_config_db("ai_settings", {})
    
    # 1. 从数据库更新 Base URL / Key
    current_mapping = {}
    for key, defaults in DEFAULT_MODEL_MAPPING.items():
        user_base = cfg.get(f"base_{defaults['provider']}", defaults['base'])
        current_mapping[key] = {**defaults, 'base': user_base}
    
    # 2. 注入自定义模型 (如果开启)
    try:
        if st.session_state.get('custom_model_enabled') or cfg.get('custom_model_enabled'):
            c_name = st.session_state.get('custom_model_name') or cfg.get('custom_model_name', 'Custom')
            c_base = st.session_state.get('custom_model_base') or cfg.get('custom_model_base', '')
            c_model = st.session_state.get('custom_api_model') or cfg.get('custom_api_model', '')
            
            current_mapping["CUSTOM_MODEL"] = {
                'name': c_name,
                'provider': "Custom",
                'base': c_base,
                'api_model': c_model
            }
    except Exception: pass
    
    # 3. 更新全局变量
    MODEL_MAPPING.update(current_mapping)
    AVAILABLE_MODELS.clear()
    AVAILABLE_MODELS.extend(list(MODEL_MAPPING.keys()))
    
    return cfg

def test_model_connection(client, model_name):
    try:
        if not client or not model_name: return False, "配置不完整"
        client.chat.completions.create(model=model_name, messages=[{"role":"user", "content":"Hi"}], max_tokens=5)
        return True, "连接成功"
    except Exception as e: return False, str(e)

# ================= 2. 引擎类 =================

class LogicEngine:
    def __init__(self, db_mgr):
        self.db = db_mgr
        self.pricing_map = {
            "DSK_V3": 0.001, "GPT_4o": 0.03, "GPT_4o_Mini": 0.01, 
            "CLA_3_5_Sonnet": 0.015, "QWN_Max": 0.004, "GEM_2_5_Pro": 0.015
        }
        self.USAGE_LOG_FILE = "logs/usage_log.csv"
        # 初始化时加载
        load_and_update_model_config(self)

    def get_config_db(self, key, default=None):
        res = self.db.query("SELECT value FROM configs WHERE key=?", (key,))
        try: return json.loads(res[0]['value']) if res else default
        except: return default

    def set_config_db(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO configs (key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def get_client(self, feature_key_or_model_key):
        """
        核心方法：获取 AI Client。
        参数可以是 'GPT_4o' (模型Key)，也可以是 'write_logic_assist' (功能Key)。
        """
        cfg = self.get_config_db("ai_settings", {})
        assignments = self.get_config_db("model_assignments", {})
        
        # 1. 自动解析 Key
        if feature_key_or_model_key in FEATURE_MODELS:
           
            default_m = FEATURE_MODELS[feature_key_or_model_key]['default']
            model_key = assignments.get(feature_key_or_model_key, default_m)
        else: 
            # 已经是模型 Key
            model_key = feature_key_or_model_key

        # 2. 获取模型详情
        setting = MODEL_MAPPING.get(model_key, DEFAULT_MODEL_MAPPING.get("DSK_V3"))
        if not setting:
             setting = list(DEFAULT_MODEL_MAPPING.values())[0]

        # 3. 构建 Client
        try:
            if model_key == "CUSTOM_MODEL":
                api_key = st.session_state.get('custom_model_key') or cfg.get('custom_model_key', '')
                base_url = setting['base']
            else:
                p = setting['provider']
                api_key = cfg.get(f"key_{p}", "")
                base_url = cfg.get(f"base_{p}", setting['base'])
        except: return None, None, model_key
        
        api_model = setting.get('api_model', 'gpt-3.5-turbo')
        if not api_key: return None, None, model_key 
        return OpenAI(api_key=api_key, base_url=base_url), api_model, model_key
    
    def get_remaining_funds(self, provider="All"):
        total_recharged = sum(self.get_config_db("ai_settings", {}).get(f"recharge_{p}", 0.0) for p in MODEL_GROUPS.keys())
        total_spent = 0.0
        try:
            if os.path.exists(self.USAGE_LOG_FILE):
                df = pd.read_csv(self.USAGE_LOG_FILE)
                if 'cost' in df.columns:
                    total_spent = df['cost'].sum()
        except: pass
        
        remaining = max(0, total_recharged - total_spent)
        return remaining, total_recharged

    def track_usage(self, model_key, input_len, output_len):
        in_tok = input_len 
        out_tok = output_len
        price = self.pricing_map.get(model_key, 0.002)
        cost = (in_tok + out_tok) / 1000 * price 
        
        if 'token_tracker' not in st.session_state: st.session_state.token_tracker = {"cost": 0.0}
        
        st.session_state.token_tracker["cost"] += cost
        
        provider = MODEL_MAPPING.get(model_key, {}).get('provider', 'Custom')
        try:
            log_dir = os.path.dirname(self.USAGE_LOG_FILE)
            if not os.path.exists(log_dir): os.makedirs(log_dir)
            file_exists = os.path.exists(self.USAGE_LOG_FILE)
            with open(self.USAGE_LOG_FILE, "a", encoding="utf-8", newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "provider", "model", "chars", "cost"])
                writer.writerow([datetime.now(), provider, model_key, input_len + output_len, f"{cost:.6f}"])
        except: pass

    # ==========================================================================
    # 3. 核心生成方法 (Writer, Knowledge, Books, Characters)
    # ==========================================================================

   
    def get_book_content_prefix(self, book_id, length=10000):
        """获取书籍前文片段用于上下文分析"""
        try:
            
            rows = self.db.query(
                "SELECT content FROM chapters WHERE book_id=? ORDER BY id ASC LIMIT 10", 
                (book_id,)
            )
            text = ""
            if rows:
                for r in rows:
                    if r.get('content'):
                        text += r['content'] + "\n"
                    if len(text) > length: break
            return text[:length]
        except Exception:
            return ""

    def generate_content_from_outline_ai_stream(self, chap_id, outline, current_book, max_chars, client, api_model, model_key):
        """【沉浸写作】流式生成正文"""
        prompt = f"""
你是一个专业的小说家。请根据以下信息撰写小说正文。
书名：《{current_book['title']}》
本章要求/大纲：
{outline}

要求：
1. 字数控制在 {max_chars} 字左右。
2. 风格要契合书名，文笔流畅，描写生动。
3. 直接输出正文内容，不要包含"好的"、"正文如下"等前缀。
"""
        try:
            stream = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=4000
            )
            def usage_tracking_generator():
                content_acc = ""
                for chunk in stream:
                    yield chunk
                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                        content_acc += chunk.choices[0].delta.content
                self.track_usage(model_key, len(prompt), len(content_acc))

            return True, usage_tracking_generator()
        except Exception as e:
            return False, str(e)

    def analyze_chapter_conflict(self, chapter_content, current_book, client, api_model, model_key):
        """【写作辅助】矛盾检测"""
        prompt = f"""
请分析以下小说章节内容，检查是否存在逻辑矛盾、时间线错误或角色行为OOC（不符合人设）。
书名：《{current_book['title']}》
章节内容：
{chapter_content[:5000]}... (截取部分)

请输出一份简短的分析报告，指出具体问题（如有）。
"""
        try:
            resp = client.chat.completions.create(model=api_model, messages=[{"role": "user", "content": prompt}])
            content = resp.choices[0].message.content
            self.track_usage(model_key, len(prompt), len(content))
            return True, content
        except Exception as e:
            return False, str(e)

    def rewrite_chapter_ai(self, original_content, analysis_report, client, api_model, model_key):
        """【写作辅助】一键重写"""
        prompt = f"""
请根据以下的分析建议，重写或优化该小说章节。
分析建议：
{analysis_report}

原章节内容：
{original_content[:4000]}...

要求：
1. 修复逻辑漏洞。
2. 润色文笔。
3. 直接输出重写后的正文。
"""
        try:
            resp = client.chat.completions.create(model=api_model, messages=[{"role": "user", "content": prompt}])
            content = resp.choices[0].message.content
            self.track_usage(model_key, len(prompt), len(content))
            return True, content
        except Exception as e:
            return False, str(e)

    def generate_style_analysis(self, text, client, api_model):
        """【拆书知识库】文本风格分析"""
        prompt = f"""
请作为一位资深文学评论家，对以下文本片段进行深度风格分析。

【待分析文本】：
{text[:8000]} 

请提炼出该作者的“文笔DNA”，并严格按照下方 JSON 格式返回分析结果（不要包含 Markdown 代码块标记，直接返回 JSON 字符串）：

{{
    "style_name": "用4-8个字概括这种风格 (如：古龙式冷峻浪子风)",
    "keywords": ["关键词1", "关键词2", "关键词3", "关键词4"],
    "sentence_structure": "分析其句式特征（长短句搭配、节奏感、特殊句式等）",
    "diction": "分析其遣词造句习惯（用词华丽度、成语使用、感官描写等）",
    "mood": "分析其营造的氛围和情感基调",
    "rhetoric": "常用的修辞手法（比喻、夸张、白描等）",
    "pacing": "叙事节奏（快慢、详略等）",
    "suggestion": "如果模仿这种风格写作，有什么核心建议"
}}
"""
        try:
            response = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
            content = content.replace("```json", "").replace("```", "").strip()
            
            # 记录消耗 (使用通用 Key 记录)
            self.track_usage("knowledge_analyze", len(prompt), len(content))
            
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "style_name": "解析失败的风格",
                "keywords": ["解析错误"],
                "sentence_structure": "AI 返回的内容不是合法的 JSON 格式",
                "diction": "未知", 
                "mood": "未知", 
                "rhetoric": "未知", 
                "pacing": "未知", 
                "suggestion": f"原始返回: {content[:100]}..."
            }
        except Exception as e:
            raise e

    def generate_synopsis_by_text(self, book_title, full_text, client, api_model):
        """【书籍导入】自动生成简介"""
        prompt = f"""
请阅读以下小说《{book_title}》的节选内容，为其撰写一段吸引人的简介（200字以内）。

【节选内容】：
{full_text[:3000]}
"""
        try:
            response = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )
            content = response.choices[0].message.content
            self.track_usage("import_char_analysis", len(prompt), len(content))
            return content
        except Exception as e:
            return f"简介生成失败: {e}"
            
    def generate_idea_ai(self, query, client, api_model):
        """【灵感模式】生成点子"""
        prompt = f"请根据以下关键词或思路，提供3个独特的小说创意/点子：\n关键词：{query}"
        try:
            resp = client.chat.completions.create(model=api_model, messages=[{"role":"user", "content":prompt}])
            content = resp.choices[0].message.content
            self.track_usage("idea_generation", len(prompt), len(content))
            return True, content
        except Exception as e:
            return False, str(e)

    
    def generate_char_relation_map_pyvis(self, book_id, all_chars, client, api_model, model_key):
        """【角色管理】AI 生成人物关系图谱数据"""
        char_list = [f"{c['name']} ({c['role']}, ID:{c['id']})" for c in all_chars]
        
        prompt = f"""
请基于以下小说角色列表，分析他们之间的主要关系和联系。
你需要严格按照指定的 JSON 格式返回一个关系列表。

角色列表 (注意角色ID)：
{char_list}

返回格式要求 (必须是 JSON 列表)：
[
  {{ "source": <角色ID_A>, "target": <角色ID_B>, "label": "关系描述，如：师徒、父子、对立", "weight": <关系强度，整数1-5> }},
  ...
]
"""
        try:
            response = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4
            )
            
            content = response.choices[0].message.content
            content = content.replace("```json", "").replace("```", "").strip()
            
            self.track_usage(model_key, len(prompt), len(content))
            
            relations = json.loads(content)
            if not isinstance(relations, list):
                 return False, "AI 返回的数据不是有效的 JSON 列表。"
                 
            return True, relations
        
        except json.JSONDecodeError:
             return False, f"AI 返回格式错误，请检查模型输出是否为 JSON: {content[:100]}..."
        except Exception as e:
            return False, str(e)


    
    def generate_architecture_ai(self, *args): return True, "架构生成成功"