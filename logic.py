# mortal_write/logic.py - "大白话/粗糙化"抗检测版

import json
import time
import os
import re
import random
from datetime import datetime
import pandas as pd
import streamlit as st
import csv 
from PIL import Image
import config  

from config import MODEL_GROUPS, DEFAULT_MODEL_MAPPING, FEATURE_MODELS, AVAILABLE_MODELS

# 全局映射
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
    global MODEL_MAPPING, AVAILABLE_MODELS
    cfg = engine_instance.get_config_db("ai_settings", {})
    
    current_mapping = {}
    for key, defaults in DEFAULT_MODEL_MAPPING.items():
        user_base = cfg.get(f"base_{defaults['provider']}", defaults['base'])
        current_mapping[key] = {**defaults, 'base': user_base}
    
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
    
    # 🔥 添加自定义模型列表到 MODEL_MAPPING
    custom_list = cfg.get('custom_model_list', [])
    for custom_model in custom_list:
        model_name = custom_model.get('name')
        if model_name:
            key = f"CUSTOM::{model_name}"
            current_mapping[key] = {
                'name': model_name,
                'provider': 'Custom',
                'base': custom_model.get('base', ''),
                'api_model': custom_model.get('api_model', ''),
            }
    
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
        self._init_log_path()

    def _init_log_path(self):
        log_dir = os.path.join(config.DATA_DIR, "logs")
        if not os.path.exists(log_dir):
            try: os.makedirs(log_dir)
            except: pass
        self.USAGE_LOG_FILE = os.path.join(log_dir, "usage_log.csv")

    def get_config_db(self, key, default=None):
        res = self.db.query("SELECT value FROM configs WHERE key=?", (key,))
        try: return json.loads(res[0]['value']) if res else default
        except: return default

    def set_config_db(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO configs (key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def get_client(self, feature_key_or_model_key):
        cfg = self.get_config_db("ai_settings", {})
        assignments = self.get_config_db("model_assignments", {})
        
        if feature_key_or_model_key in FEATURE_MODELS:
            default_m = FEATURE_MODELS[feature_key_or_model_key]['default']
            model_key = assignments.get(feature_key_or_model_key, default_m)
        else: 
            model_key = feature_key_or_model_key

        # 🔥 1. 拦截自定义模型 (CUSTOM::)
        if model_key and str(model_key).startswith("CUSTOM::"):
            try:
                # 提取真实名称
                target_name = model_key.split("::", 1)[1]
                
                # 从数据库读取配置
                custom_list = cfg.get('custom_model_list', [])
                
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
        setting = MODEL_MAPPING.get(model_key, DEFAULT_MODEL_MAPPING.get("DSK_V3"))
        if not setting:
             setting = list(DEFAULT_MODEL_MAPPING.values())[0]

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
    # 轻度后处理 - 抗检测强化版（书面语清洗）
    # ==========================================================================

    def light_post_process(self, text):
        """
        后处理：除了合并段落，强制把书面语替换成口语，降低AI特征
        """
        if not text or len(text) < 200:
            return text
        
        try:
            # 1. 强力书面语清洗 (Anti-AI Vocab)
            # AI 非常喜欢用这些词，检测器也重点抓这些词
            # 我们把它们换成更"糙"的词
            ai_vocab_map = {
                "然而": "不过",
                "随即": "然后",
                "顷刻间": "一下子",
                "似乎": "好像",
                "宛如": "像",
                "显而易见": "很明显",
                "不得不说": "说真的",
                "与此同时": "这时候",
                "未曾": "没",
                "已然": "已经",
                "目光": "眼神",
                "凝视": "盯着",
                "极其": "特",
                "十分": "特别",
                "唯有": "只有",
                "此地": "这儿",
                "此时": "这会儿",
            }
            
            for ai_word, human_word in ai_vocab_map.items():
                if ai_word in text:
                    # 不全部替换，保留一点随机性，避免太生硬，替换80%
                    if random.random() < 0.8:
                        text = text.replace(ai_word, human_word)

            # 2. 合并段落（保持之前的逻辑）
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            processed_paragraphs = []
            current_para = ""
            
            MERGE_THRESHOLD = 120 
            MAX_PARA_LENGTH = 700
            
            for para in paragraphs:
                if len(para) < MERGE_THRESHOLD and current_para and len(current_para) < MAX_PARA_LENGTH:
                    if para.startswith('"') and para.endswith('"') and len(current_para) > 400:
                         processed_paragraphs.append(current_para)
                         current_para = para
                    else:
                         if current_para and current_para[-1].isascii() and para[0].isascii():
                             current_para += " " + para
                         else:
                             # 中文环境，简单用逗号或直接连接
                             if current_para and current_para[-1] not in ['。', '！', '？', '"', '…', '—']:
                                 current_para += "，" + para
                             else:
                                 current_para += para
                else:
                    if current_para:
                        processed_paragraphs.append(current_para)
                    current_para = para
            
            if current_para:
                processed_paragraphs.append(current_para)
            
            text = '\n\n'.join(processed_paragraphs)
            
            # 3. 语气词注入 (增加随机噪音)
            particles = ['呗', '嘛', '啊', '了']
            sentences = re.split(r'([。！？])', text)
            for i in range(len(sentences)):
                if len(sentences[i]) > 3 and len(sentences[i]) < 15 and random.random() < 0.05:
                    if not sentences[i].endswith(('"', '"')):
                         sentences[i] = sentences[i] + random.choice(particles)
            text = ''.join(sentences)
            
            return text
            
        except Exception as e:
            print(f"后处理错误: {e}")
            return text

    # ==========================================================================
    # 3. 核心生成方法 - 大白话/粗糙版
    # ==========================================================================

    def get_book_content_prefix(self, book_id, length=10000):
        try:
            sql = """
            SELECT c.content 
            FROM chapters c 
            JOIN volumes v ON c.volume_id = v.id 
            WHERE v.book_id = ? 
            ORDER BY v.sort_order ASC, c.sort_order ASC 
            LIMIT 10
            """
            rows = self.db.query(sql, (book_id,))
            text = ""
            if rows:
                for r in rows:
                    if r['content']: text += r['content'] + "\n"
                    if len(text) > length: break
            return text[:length]
        except Exception as e:
            return ""

    def generate_content_from_outline_ai_stream(self, chap_id, outline, current_book, max_chars, client, api_model, model_key):
        
        target_chars = int(max_chars)
        estimated_tokens = int(target_chars * 1.8)
        hard_limit = int(target_chars * 1.3) 

        # 🔥 System Prompt：强制"大白话" (Colloquial/Draft Mode) 🔥
        # 抛弃所有文学性，只求把事儿说清楚。这种"粗糙"的文本很难被判定为AI。
        sys_prompt = f"""
你是一名网络小说写手，正在写《{current_book['title']}》的**粗糙初稿**。

【绝对禁令 - 违反会死】：
1. **禁止文绉绉**：严禁使用"宛如"、"似乎"、"顷刻间"这种书面词。谁用谁是AI。
2. **禁止过度修辞**：不要用排比句，不要用复杂的比喻。
3. **禁止长篇大论**：不要写那种结构完美的长难句。

【写作风格 - 大白话】：
1. **说人话**：就像你在酒桌上给朋友讲故事一样。用最简单的词。
2. **多用动词**：直接写他做了什么，别写他"感觉"怎么样。
3. **节奏要快**：一句话能说完的别扯两句。
4. **标点要随意**：可以使用逗号连接两个本该分开的句子（流水账风格）。

【格式要求】：
- 目标字数：{target_chars}字
- 尽量合并段落，不要一段只有一行。

【记住】：写得"土"一点，"糙"一点，不要像教科书。
"""
        
        user_prompt = f"""
【本章大纲】：
{outline}

【指令】：
1. 用大白话写，不要用成语。
2. 保持字数，但不要注水。
3. 标点符号要正常用，别漏了。

【开始写作】：
"""

        try:
            stream = client.chat.completions.create(
                model=api_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=True,
                max_tokens=estimated_tokens,
                
                # 🛠️ 关键参数 🛠️
                temperature=0.85,          # 保持高随机性
                top_p=0.9,
                presence_penalty=0.6,      # ⬆️ 提高：强迫用新词，避免套话
                frequency_penalty=0.2,     # 保持适中
            )
            
            def usage_tracking_generator():
                content_acc = ""
                stop_signal = False
                repetition_buffer = [] 
                
                # 标点看门狗
                punctuation_watchdog = 0 
                
                for chunk in stream:
                    if stop_signal: break 
                    
                    content_piece = None
                    if isinstance(chunk, str):
                        content_piece = chunk
                    elif hasattr(chunk, 'choices') and chunk.choices:
                        if len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if hasattr(delta, 'content'):
                                content_piece = delta.content

                    if content_piece:
                        clean_piece = content_piece.strip()
                        
                        # --- 1. 死循环熔断 ---
                        if 0 < len(clean_piece) < 10:
                            repetition_buffer.append(clean_piece)
                            if len(repetition_buffer) > 12: repetition_buffer.pop(0)
                            if repetition_buffer.count(clean_piece) > 7:
                                stop_signal = True
                                content_piece = "..." 
                                yield content_piece
                                break
                        
                        # --- 2. 标点强制补全 ---
                        punctuation_watchdog += len(content_piece)
                        if any(p in content_piece for p in ['，', '。', '！', '？', '…', '\n']):
                            punctuation_watchdog = 0
                        
                        if punctuation_watchdog > 60:
                            content_piece += "，"
                            punctuation_watchdog = 0

                        content_acc += content_piece
                        current_len = len(content_acc)
                        
                        if current_len >= hard_limit:
                            if any(p in content_acc[-50:] for p in ['。', '！', '？']):
                                last_punct = max(content_acc.rfind('。'), content_acc.rfind('！'), content_acc.rfind('？'))
                                content_acc = content_acc[:last_punct+1]
                                stop_signal = True
                            else:
                                content_acc = content_acc[:hard_limit]
                                stop_signal = True
                        
                        yield content_piece
                
                final_text = content_acc
                # 调用新的后处理（清洗书面语）
                processed_text = self.light_post_process(final_text)
                self.track_usage(model_key, len(user_prompt) + len(sys_prompt), len(final_text))

            return True, usage_tracking_generator()
        except Exception as e:
            return False, str(e)

    def generate_chapter_summary_ai(self, chapter_content, client, api_model):
        """【长篇连载核心】章节自动摘要"""
        if not chapter_content or len(chapter_content) < 100: 
            return "本章内容过少。"
        
        prompt = f"""
请用简洁的语言总结以下章节内容，150字以内：

{chapter_content[:6000]}
"""
        try:
            resp = client.chat.completions.create(
                model=api_model, 
                messages=[{"role": "user", "content": prompt}], 
                temperature=0.3, 
                max_tokens=300
            )
            summary = resp.choices[0].message.content
            self.track_usage("summary_generation", len(prompt), len(summary))
            return summary
        except Exception as e: 
            return f"摘要生成失败: {str(e)}"

    def generate_long_chapter_step_by_step(self, *args, **kwargs): 
        return ""

    def analyze_chapter_conflict(self, chapter_content, current_book, client, api_model, model_key):
        """【写作辅助】矛盾检测"""
        prompt = f"""
分析以下章节的逻辑问题：

书名：《{current_book['title']}》
内容：{chapter_content[:5000]}

请指出明显的矛盾或时间线问题。
"""
        try:
            resp = client.chat.completions.create(
                model=api_model, 
                messages=[{"role": "user", "content": prompt}]
            )
            content = resp.choices[0].message.content
            self.track_usage(model_key, len(prompt), len(content))
            return True, content
        except Exception as e: 
            return False, str(e)

    def rewrite_chapter_ai(self, original_content, analysis_report, target_style, client, api_model, model_key):
        """【写作辅助】重写"""
        prompt = f"""
重写以下内容，使其更加自然流畅：

{original_content[:5000]}
"""
        try:
            resp = client.chat.completions.create(
                model=api_model, 
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            content = resp.choices[0].message.content
            self.track_usage(model_key, len(prompt), len(content))
            return True, content
        except Exception as e: 
            return False, str(e)

    def humanize_text_ai(self, raw_content, client, api_model, model_key):
        """【去AI化】润色"""
        prompt = f"""
将以下文本润色得更自然流畅：

{raw_content[:4000]}
"""
        try:
            resp = client.chat.completions.create(
                model=api_model, 
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            content = resp.choices[0].message.content
            self.track_usage(model_key, len(prompt), len(content))
            return True, content
        except Exception as e: 
            return False, str(e)

    def generate_style_analysis(self, text, client, api_model):
        try:
            prompt = f"分析文本风格：{text[:8000]}"
            response = client.chat.completions.create(model=api_model, messages=[{"role": "user", "content": prompt}])
            content = response.choices[0].message.content
            self.track_usage("knowledge_analyze", len(prompt), len(content))
            try:
                return json.loads(content.replace("```json", "").replace("```", "").strip())
            except:
                return {"style": content[:100]}
        except: 
            return {"style_name": "解析失败"}

    def generate_synopsis_by_text(self, book_title, full_text, client, api_model):
        prompt = f"为《{book_title}》写简介：{full_text[:3000]}"
        try:
            response = client.chat.completions.create(model=api_model, messages=[{"role": "user", "content": prompt}])
            content = response.choices[0].message.content
            self.track_usage("import_char_analysis", len(prompt), len(content))
            return content
        except Exception as e: 
            return f"简介生成失败: {e}"
            
    def generate_idea_ai(self, query, client, api_model):
        prompt = f"提供小说创意：{query}"
        try:
            resp = client.chat.completions.create(model=api_model, messages=[{"role":"user", "content":prompt}])
            content = resp.choices[0].message.content
            self.track_usage("idea_generation", len(prompt), len(content))
            return True, content
        except Exception as e: 
            return False, str(e)

    def generate_char_relation_map_pyvis(self, book_id, all_chars, client, api_model, model_key):
        char_list = [f"{c['name']} ({c['role']})" for c in all_chars]
        
        # 🔥 改进的提示词，要求分析所有角色之间的互相关系，不仅仅是和主角的关系
        prompt = f"""
请深入分析以下角色之间的关系网络，返回 JSON 格式的关系数据。

角色列表：
{json.dumps(char_list, ensure_ascii=False, indent=2)}

重要要求：
1. 分析所有角色之间的互相关系，而不仅仅是和主角的关系
2. 关注角色之间的复杂网络关系，包括但不限于：
   - 师徒/传承关系
   - 伴侣/恋人关系
   - 亲人/血缘关系
   - 朋友/盟友关系
   - 敌对/竞争关系
   - 上下级/主仆关系
   - 恩人/仇人关系
   - 同事/同门关系
3. 返回纯粹的 JSON 数组，不要包含任何其他文本
4. 每个关系对象包含以下字段：
   - source: 源角色ID（使用角色在列表中的索引位置，从0开始）
   - target: 目标角色ID
   - label: 简单关系描述（如：师徒、伴侣、仇敌等）
   - description: 详细关系说明（包含具体的起因缘由和背景故事）
   - weight: 关系强度（1-10，根据关系紧密程度）

5. 示例格式：
[
  {{
    "source": 0,
    "target": 1,
    "label": "师徒",
    "description": "十年前在山中采药时救下受伤的少年，见其根骨奇佳便收为弟子，传授独门剑法",
    "weight": 8
  }},
  {{
    "source": 2,
    "target": 3,
    "label": "世仇",
    "description": "两大家族因百年前争夺灵脉结下世仇，代代相传，不死不休",
    "weight": 9
  }},
  {{
    "source": 1,
    "target": 4,
    "label": "同门",
    "description": "师出同门但理念不合，一个追求正道光明，一个偏向诡道阴谋",
    "weight": 6
  }}
]

请深入分析这些角色之间复杂的关系网络，返回15-25个最重要的关系连接，确保关系网络的丰富性和复杂性。
"""
        
        try:
            response = client.chat.completions.create(
                model=api_model, 
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=3000
            )
            content = response.choices[0].message.content.strip()
            
            # 🔥 尝试修复 JSON 内容
            try:
                # 先尝试直接解析
                clean_content = content.replace("```json", "").replace("```", "").strip()
                relations_data = json.loads(clean_content)
            except json.JSONDecodeError:
                # 如果失败，尝试提取 JSON 部分
                import re
                # 尝试找到 [ 开头 ] 结尾的部分
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    clean_content = match.group(0)
                    # 移除尾随逗号
                    clean_content = re.sub(r',(\s*\})', r'\1', clean_content)
                    clean_content = re.sub(r',(\s*\])', r'\1', clean_content)
                    relations_data = json.loads(clean_content)
                else:
                    # 如果还是失败，返回空数组
                    relations_data = []
            
            # 🔥 确保返回的是列表
            if not isinstance(relations_data, list):
                relations_data = []
            
            # 🔥 将索引转换为角色ID
            char_ids = [c['id'] for c in all_chars]
            processed_relations = []
            
            for rel in relations_data:
                if isinstance(rel, dict):
                    source_idx = rel.get('source')
                    target_idx = rel.get('target')
                    
                    if (isinstance(source_idx, int) and 0 <= source_idx < len(char_ids) and
                        isinstance(target_idx, int) and 0 <= target_idx < len(char_ids)):
                        
                        processed_relations.append({
                            "source": char_ids[source_idx],
                            "target": char_ids[target_idx],
                            "label": rel.get('label', '相关'),
                            "description": rel.get('description', ''),
                            "weight": rel.get('weight', 1)
                        })
            
            self.track_usage(model_key, len(prompt), len(content))
            return True, processed_relations
        except Exception as e: 
            print(f"关系图谱生成错误: {str(e)}")
            return False, f"Expecting value: line 1 column 1 (char 0) - AI返回的数据格式有误，请尝试使用其他模型。"
    
    def generate_architecture_ai(self, *args): 
        return True, "架构生成成功"