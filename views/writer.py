# mortal_write/views/writer.py

import streamlit as st
import streamlit.components.v1 as components
import time
import json
import pandas as pd
import os 
import re 
import csv
import uuid
import threading
from datetime import datetime
from utils import (
    render_header, 
    update_chapter_title_db, 
    update_chapter_summary_db,
    resequence_chapters,
    ensure_log_file     
)
from views.books import record_token_usage, get_beijing_time
from logic import FEATURE_MODELS, MODEL_MAPPING

# 🔥 核心修复：引入 OpenAI 用于手动构建客户端
try:
    from openai import OpenAI
except ImportError:
    class OpenAI: 
        def __init__(self, **kwargs): 
            pass

# ==============================================================================
# 🛠️ Helpers & Configuration
# ==============================================================================

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = "data"

MAX_SAFE_WORD_COUNT = 4096 

# ==============================================================================
# 🛡️ 严格审计日志系统 (Writer 集成版)
# ==============================================================================

SYSTEM_LOG_PATH = os.path.join(DATA_DIR, "logs", "system_audit.csv")
_log_lock = threading.Lock()

def get_session_id():
    if "session_trace_id" not in st.session_state:
        st.session_state.session_trace_id = str(uuid.uuid4())[:8]
    return st.session_state.session_trace_id

def log_audit_event(category, action, details, status="SUCCESS", module="WRITER"):
    try:
        os.makedirs(os.path.dirname(SYSTEM_LOG_PATH), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_id = get_session_id()
        
        status_map = {"SUCCESS": "成功", "WARNING": "警告", "ERROR": "错误"}
        status_cn = status_map.get(status, status)
        
        module_map = {"WRITER": "写作终端", "SETTINGS": "系统设置"}
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

def delete_book_cache(book_id, book_title):
    try:
        safe_title = re.sub(r'[\\/*?:"<>|]', "", str(book_title)).strip()
        cache_file = os.path.join(DATA_DIR, "exports", f"{book_id}_{safe_title}.txt")
        if os.path.exists(cache_file):
            os.remove(cache_file)
    except Exception as e:
        print(f"⚠️ 删除缓存文件失败: {e}")

def force_update_book_time(db_mgr, book_id):
    try:
        current_time = get_beijing_time()
        db_mgr.execute("UPDATE books SET updated_at=? WHERE id=?", (current_time, book_id))
        try:
            book_info = db_mgr.query("SELECT title FROM books WHERE id=?", (book_id,))
            if book_info:
                book_title = book_info[0]['title']
                delete_book_cache(book_id, book_title)
        except Exception as e:
            print(f"⚠️ 删除缓存失败: {e}")
    except Exception as e:
        print(f"Update time failed: {e}")

def get_safe_model_default(feature_key, hard_coded_default):
    if feature_key in FEATURE_MODELS:
        return FEATURE_MODELS[feature_key].get('default', hard_coded_default)
    return hard_coded_default

def safe_get_content(chunk):
    try:
        if isinstance(chunk, str): return chunk
        if hasattr(chunk, 'choices') and chunk.choices:
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content'): return delta.content
        if isinstance(chunk, dict):
            return chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
        return None
    except Exception: return None

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
        force_update_book_time(db_mgr, st.session_state.current_book_id)
        st.session_state.chapter_title_cache[chap_id] = new_title
        log_audit_event("章节管理", "重命名章节", {"章节ID": chap_id, "新标题": new_title})
        st.session_state.rerun_flag = True

def _update_chapter_summary_db_logged(chap_id, new_summary_key):
    new_summary = st.session_state[new_summary_key]
    db_mgr = st.session_state.db
    db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (new_summary, chap_id))
    force_update_book_time(db_mgr, st.session_state.current_book_id)
    log_audit_event("章节管理", "更新大纲", {"章节ID": chap_id, "大纲长度": len(new_summary)})
    st.session_state.rerun_flag = True

# ==============================================================================
# 🔥 [NEW] 直连数据库读取配置 (绕过 Engine 缓存)
# ==============================================================================
def get_config_direct_from_db(key_name, default_value=None):
    """直接查询 SQLite，确保配置百分百实时"""
    try:
        db_mgr = st.session_state.db
        rows = db_mgr.query("SELECT value FROM configs WHERE key=?", (key_name,))
        if rows and len(rows) > 0:
            val_str = rows[0]['value']
            try:
                return json.loads(val_str)
            except:
                return val_str
    except Exception as e:
        print(f"Direct Config Read Error: {e}")
    return default_value

# ==============================================================================
# 🧠 Logic: Plot Continuity
# ==============================================================================

class PlotContinuityTracker:
    def __init__(self, db_mgr, book_id):
        self.db_mgr = db_mgr
        self.book_id = book_id
        
    def extract_plot_nodes(self, chapter_content, chapter_title=""):
        if not chapter_content: return []
        time_patterns = [
            r'([一二三四五六七八九十]+天后)', r'([0-9]+天后)',
            r'次日', r'第二天', r'第三天', r'一周后', r'一个月后',
            r'清晨', r'正午', r'傍晚', r'深夜',
            r'春天', r'夏天', r'秋天', r'冬天'
        ]
        location_patterns = [
            r'来到([^，。！？]{2,10})', r'进入([^，。！？]{2,10})',
            r'在([^，。！？]{2,10})里', r'从([^，。！？]{2,10})出发',
            r'抵达([^，。！？]{2,10})', r'离开([^，。！？]{2,10})'
        ]
        content = chapter_content[:2000]
        event_keywords = ["突然", "就在这时", "没想到", "意外的是", "终于", "决定", "开始", "结束"]
        events = []
        for keyword in event_keywords:
            if keyword in content:
                positions = [m.start() for m in re.finditer(keyword, content)]
                for pos in positions[:3]:
                    start = max(0, pos - 100)
                    end = min(len(content), pos + 100)
                    context = content[start:end]
                    events.append(f"事件: {context.strip()}")
        return {
            'chapter': chapter_title,
            'time_markers': self._extract_by_patterns(content, time_patterns),
            'locations': self._extract_by_patterns(content, location_patterns),
            'events': events[:5],
            'character_status': self._extract_character_status(content)
        }
    
    def _extract_by_patterns(self, content, patterns):
        results = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    for m in match:
                        if m and len(m) > 1: results.add(m.strip())
                elif match and len(match) > 1:
                    results.add(match.strip())
        return list(results)
    
    def _extract_character_status(self, content):
        status_changes = []
        status_words = ["受伤", "死亡", "觉醒", "突破", "获得", "失去", "成为", "晋升"]
        for word in status_words:
            if word in content:
                pattern = rf'([^，。！？]{2,6}?){word}'
                matches = re.findall(pattern, content)
                for match in matches[:3]:
                    if match and len(match) > 1:
                        status_changes.append(f"{match}{word}")
        return status_changes
    
    def get_chapter_continuity_report(self, prev_chap_id, current_chap_id):
        try:
            prev_chap = self.db_mgr.query("SELECT id, title, content FROM chapters WHERE id=?", (prev_chap_id,))
            curr_chap = self.db_mgr.query("SELECT id, title, content FROM chapters WHERE id=?", (current_chap_id,))
            if not prev_chap or not curr_chap: return "无法获取章节信息"
            prev_data = prev_chap[0]
            curr_data = curr_chap[0]
            prev_content = prev_data['content'] or ""
            prev_end = prev_content[-500:] if len(prev_content) > 500 else prev_content
            curr_content = curr_data['content'] or ""
            curr_start = curr_content[:500] if len(curr_content) > 500 else curr_content
            prev_nodes = self.extract_plot_nodes(prev_end, f"《{prev_data['title']}》结尾")
            curr_nodes = self.extract_plot_nodes(curr_start, f"《{curr_data['title']}》开头")
            report = []
            report.append(f"## 📊 章节连贯性分析报告")
            report.append(f"**前一章**: {prev_data['title']} → **当前章**: {curr_data['title']}")
            report.append("---")
            if prev_nodes.get('time_markers') and curr_nodes.get('time_markers'):
                report.append(f"⏰ **时间线检查**:")
                report.append(f"- 前一章时间: {', '.join(prev_nodes['time_markers'][:3])}")
                report.append(f"- 当前章时间: {', '.join(curr_nodes['time_markers'][:3])}")
            if prev_nodes.get('locations') and curr_nodes.get('locations'):
                report.append(f"📍 **场景检查**:")
                report.append(f"- 前一章地点: {', '.join(prev_nodes['locations'][:3])}")
                report.append(f"- 当前章地点: {', '.join(curr_nodes['locations'][:3])}")
            if prev_nodes.get('events') and curr_nodes.get('events'):
                report.append(f"🎭 **事件连续性**:")
                report.append(f"- 前一章结尾事件: {prev_nodes['events'][0] if prev_nodes['events'] else '无'}")
                report.append(f"- 当前章开头事件: {curr_nodes['events'][0] if curr_nodes['events'] else '无'}")
            report.append(f"📖 **直接文本对比**:")
            report.append(f"```\n前一章结尾: {prev_end[-100:].replace(chr(10), ' ')}\n当前章开头: {curr_start[:100].replace(chr(10), ' ')}\n```")
            return "\n".join(report)
        except Exception as e:
            return f"分析出错: {str(e)}"

def analyze_plot_momentum(content):
    if not content or len(content) < 200: return None
    last_paragraphs = content.split('\n\n')[-3:]
    momentum_points = []
    for para in last_paragraphs:
        para = para.strip()
        if not para: continue
        if ("说道" in para or "问道" in para or "回答" in para) and ("。" not in para or para.count("「") > para.count("」")):
            momentum_points.append("有未完成的对话需要继续")
        action_words = ["开始", "正在", "准备", "打算", "决定", "冲向", "拔出", "施展"]
        for word in action_words:
            if word in para and "。" not in para:
                momentum_points.append(f"有进行中的动作: {word}...")
                break
        question_words = ["?", "？", "为何", "怎么", "难道", "究竟"]
        for word in question_words:
            if word in para:
                momentum_points.append("存在未解答的疑问或悬念")
                break
    if momentum_points:
        return "⚠️ **前一章遗留的剧情动量**: " + " | ".join(set(momentum_points[:3]))
    return None

def generate_smart_summary(content, title):
    if not content or len(content) < 300: return "内容过短，无法提取关键剧情"
    sentences = []
    for delimiter in ['。', '！', '？', '.', '!', '?']:
        if delimiter in content:
            parts = content.split(delimiter)
            sentences.extend([s.strip() + delimiter for s in parts if len(s.strip()) > 20])
    key_indicators = ["突然", "就在这时", "没想到", "决定", "开始", "结束", "发现", "意识到", "承诺", "约定"]
    key_sentences = []
    for sentence in sentences[-10:]:
        for indicator in key_indicators:
            if indicator in sentence and sentence not in key_sentences:
                key_sentences.append(sentence)
                break
        if len(key_sentences) >= 3: break
    if key_sentences: return "\n".join(key_sentences[:3])
    else:
        last_sentences = sentences[-3:] if len(sentences) >= 3 else sentences
        return "\n".join(last_sentences)

def extract_narrative_ending(content):
    if not content: return None
    paragraphs = content.split('\n\n')
    if not paragraphs: return None
    for i in range(len(paragraphs)-1, max(-1, len(paragraphs)-5), -1):
        para = paragraphs[i].strip()
        if len(para) > 50:
            if para[-1] in ['。', '！', '？', '.', '!', '?', '」']: return para
    return content[-300:] if len(content) > 300 else content

def generate_transition_suggestion(prev_content):
    if not prev_content: return "从故事的自然起点开始"
    last_part = prev_content[-200:] if len(prev_content) > 200 else prev_content
    if "说道" in last_part or "问道" in last_part: return "建议从对话的回应或对话引发的行动开始"
    elif "睡着" in last_part or "休息" in last_part: return "建议从醒来后的早晨或继续休息后的时间开始"
    elif "离开" in last_part or "出发" in last_part: return "建议从旅程中的新场景或抵达目的地开始"
    elif "决定" in last_part or "计划" in last_part: return "建议从执行决定或计划的第一步开始"
    elif "突然" in last_part or "意外" in last_part: return "建议从突发事件的结果或应对开始"
    else: return "建议从时间推移后的合理延续开始"

def get_current_chapter_characters(content):
    if not content or len(content) < 100: return set()
    characters = set()
    patterns = [
        r'["「]([^"「」]+?)["」]\s*[,，]?\s*([^,，。！？!?]{2,8}?)说道',
        r'([^,，。！？!?\s]{2,8}?)说道[:：]',
        r'["「]([^"「」]+?)["」]\s*[,，]?\s*([^,，。！？!?]{2,8}?)想道',
        r'([^,，。！？!?\s]{2,8}?)想道[:：]',
        r'([^,，。！？!?\s]{2,8}?)问道[:：]',
        r'["「]([^"「」]+?)["」]\s*[,，]?\s*([^,，。！？!?]{2,8}?)问道'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if isinstance(match, tuple):
                for name in match:
                    if name and len(name) >= 2: characters.add(name.strip())
            elif match: characters.add(match.strip())
    possessive_pattern = r'([^,，。！？!?\s]{2,6}?)的[^的]{1,8}'
    matches = re.findall(possessive_pattern, content)
    for name in matches:
        if len(name) >= 2: characters.add(name.strip())
    return characters

def get_previous_chapter_characters(db_mgr, book_id, current_chap_id):
    try:
        all_chaps = db_mgr.query("""
            SELECT c.id, c.title, c.content 
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            JOIN parts p ON v.part_id = p.id
            WHERE p.book_id = ?
            ORDER BY p.sort_order, v.sort_order, c.sort_order
        """, (book_id,))
        if not all_chaps: return set()
        current_idx = -1
        for idx, chap in enumerate(all_chaps):
            if chap['id'] == current_chap_id:
                current_idx = idx; break
        prev_characters = set()
        for i in range(1, 3): 
            check_idx = current_idx - i
            if check_idx >= 0:
                prev_content = all_chaps[check_idx]['content'] or ""
                if prev_content:
                    prev_characters.update(get_current_chapter_characters(prev_content))
        return prev_characters
    except Exception as e:
        return set()

def get_enhanced_writing_prompt(context, outline, target_words):
    prompt_parts = []
    prompt_parts.append("【小说创作AI - 智能剧情衔接模式】")
    prompt_parts.append("你是一个专业的网络小说作家，擅长创作连贯、引人入胜的章节。")
    prompt_parts.append("")
    prompt_parts.append(context)
    prompt_parts.append("")
    prompt_parts.append("【本章创作指令】")
    prompt_parts.append(f"1. 章节字数: {target_words} 字左右，严格控制篇幅")
    prompt_parts.append("2. **首要任务**: 确保与上一章完美衔接，不能有任何断档")
    prompt_parts.append("3. **剧情连续性**: 仔细阅读【智能前情提要】，特别是上一章结尾，从中找到本章的起点")
    prompt_parts.append("4. **角色一致性**: 角色的行为、对话、心理活动必须与前文保持一致")
    prompt_parts.append("5. **场景过渡**: 如果场景变化，必须有合理的过渡描述")
    prompt_parts.append("6. **时间流动**: 明确时间如何从前一章延续到本章")
    prompt_parts.append("7. **动量继承**: 继承上一章的剧情动量，继续推进故事")
    prompt_parts.append("")
    prompt_parts.append("【本章大纲与具体指令】")
    prompt_parts.append(outline)
    prompt_parts.append("")
    prompt_parts.append("【写作质量要求】")
    prompt_parts.append("- 禁止重复描述已交代过的信息")
    prompt_parts.append("- 新登场人物需有合理理由")
    prompt_parts.append("- 已登场人物不应重新介绍")
    prompt_parts.append("- 章节结尾要为下一章埋下合理伏笔")
    prompt_parts.append("- 保持紧张感与阅读流畅性")
    return "\n".join(prompt_parts)

# ==============================================================================
# 🧠 Context Manager
# ==============================================================================

def get_next_chapter_context(db_mgr, book_id, current_chap_id=None):
    try:
        all_chaps = db_mgr.query("""
            SELECT c.id, c.title, c.summary 
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            JOIN parts p ON v.part_id = p.id
            WHERE p.book_id = ?
            ORDER BY p.sort_order, v.sort_order, c.sort_order
        """, (book_id,))
        if not all_chaps: return ""
        curr_idx = -1
        if current_chap_id:
            for idx, item in enumerate(all_chaps):
                if item['id'] == current_chap_id:
                    curr_idx = idx; break
        if curr_idx != -1 and curr_idx + 1 < len(all_chaps):
            next_chap = all_chaps[curr_idx + 1]
            summary = next_chap['summary'] if 'summary' in next_chap.keys() else ""
            if summary:
                return f"【后续剧情提示】下一章《{next_chap['title']}》的规划：{summary}"
    except Exception as e: pass
    return ""

def get_full_context(db_mgr, book_id, current_chap_id=None, current_outline=""):
    context_parts = []
    context_parts.append("【重要写作要求 - 必须严格遵守】")
    context_parts.append("1. **强制衔接要求**: 必须与上一章结尾自然衔接，时间、地点、人物状态必须连续")
    context_parts.append("2. **人物登场管理**: 如果人物在前一章已经登场，本章不应再次介绍登场，应直接延续其行动")
    context_parts.append("3. **避免重复描述**: 相同的人物特征、能力在前文已描述过的，本章不应重复描述")
    context_parts.append("4. **逻辑连续性**: 剧情发展必须有合理的因果链条，避免突兀跳跃")
    context_parts.append("5. **章节过渡**: 章节结尾要为下一章提供自然的过渡，可以设置悬念或阶段总结")
    if current_chap_id:
        prev_characters = get_previous_chapter_characters(db_mgr, book_id, current_chap_id)
        if prev_characters:
            context_parts.append(f"【已登场人物名单】以下人物已在前面章节登场，请勿重新介绍登场:")
            context_parts.append(", ".join(sorted(list(prev_characters))))
            context_parts.append("如果需要在对话或行动中提及这些人物，请直接使用，无需再次介绍背景。")
            
    try:
        all_chaps = db_mgr.query("""
            SELECT c.id, c.title, c.content, c.summary 
            FROM chapters c
            JOIN volumes v ON c.volume_id = v.id
            JOIN parts p ON v.part_id = p.id
            WHERE p.book_id = ?
            ORDER BY p.sort_order, v.sort_order, c.sort_order
        """, (book_id,))
        curr_idx = -1
        if current_chap_id:
            for idx, chap in enumerate(all_chaps):
                if chap['id'] == current_chap_id:
                    curr_idx = idx; break
        if curr_idx > 0:
            prev_chap = all_chaps[curr_idx - 1]
            prev_content = prev_chap['content'] or ""
            if prev_content:
                momentum_analysis = analyze_plot_momentum(prev_content)
                if momentum_analysis:
                    context_parts.append(f"【剧情动量分析 - 必须承接】")
                    context_parts.append(momentum_analysis)
    except Exception as e: pass
    try:
        settings = db_mgr.query("SELECT content FROM plots WHERE book_id=? AND status LIKE 'Setting_%'", (book_id,))
        if settings:
            s_text = "\n".join([f"- {s['content']}" for s in settings])
            context_parts.append(f"【世界观与设定】\n{s_text}")
    except: pass
    try:
        all_chars = db_mgr.query("SELECT name, role, gender, desc, cheat_ability, is_major FROM characters WHERE book_id=?", (book_id,))
        if all_chars:
            relevant_chars = []
            seen_names = set()
            for c in all_chars:
                should_include = False
                c_name = c['name'].strip()
                if c['is_major']: should_include = True
                elif current_outline and c_name in current_outline: should_include = True
                if should_include and c_name not in seen_names:
                    gender_str = c['gender'] if c['gender'] else "未知性别"
                    info = f"{c_name} ({gender_str} | {c['role']}): {c['desc']}"
                    if c['cheat_ability']: info += f" | 金手指: {c['cheat_ability']}"
                    relevant_chars.append(info)
                    seen_names.add(c_name)
            if relevant_chars:
                context_parts.append(f"【本章相关角色档案】\n" + "\n".join(relevant_chars))
    except Exception as e: pass
    try:
        target_idx = curr_idx if curr_idx != -1 else len(all_chaps)
        if target_idx == 0:
            context_parts.append("【前情回顾】\n这是故事的开篇章节，请建立世界观和主要人物。")
        else:
            start_idx = max(0, target_idx - 3)
            prev_chaps = all_chaps[start_idx:target_idx]
            if prev_chaps:
                context_parts.append(f"【智能前情提要】")
                for i, pc in enumerate(prev_chaps):
                    is_last_prev = (i == len(prev_chaps) - 1)
                    if is_last_prev: 
                        pc_content = pc['content'] or ""
                        smart_summary = generate_smart_summary(pc_content, pc['title'])
                        context_parts.append(f"📖 **上一章《{pc['title']}》关键剧情**:")
                        context_parts.append(smart_summary)
                        raw_cont = pc_content
                        if raw_cont:
                            end_part = raw_cont[-800:] if len(raw_cont) > 800 else raw_cont
                            paragraphs = end_part.split('\n\n')
                            last_paragraphs = paragraphs[-3:] if len(paragraphs) > 3 else paragraphs
                            last_content = "\n\n".join([p.strip() for p in last_paragraphs if p.strip()])
                            if last_content:
                                context_parts.append(f"🔚 **上一章《{pc['title']}》结尾实录（必须从这继续）**:\n{last_content}")
                                transition_suggestion = generate_transition_suggestion(pc_content)
                                context_parts.append(f"💡 **智能衔接建议**: {transition_suggestion}")
                        else:
                            context_parts.append(f"📝 上一章《{pc['title']}》概要: {pc['summary'] or '暂无详细内容'}")
                    else:
                        summary = pc['summary'] if pc['summary'] else ""
                        context_parts.append(f"📝 《{pc['title']}》: {summary[:100]}...")
    except Exception as e: pass
    next_context = get_next_chapter_context(db_mgr, book_id, current_chap_id)
    if next_context:
        context_parts.append(next_context)
    return "\n\n".join(context_parts)

# ==============================================================================
# 🪟 Dialogs
# ==============================================================================
if hasattr(st, "dialog"): dialog_decorator = st.dialog
else: dialog_decorator = st.experimental_dialog

@dialog_decorator("💾 保存确认")
def dialog_save_chapter_content(db_mgr, chapter_id, new_content, book_id, chapter_title):
    st.markdown(f"### 正在保存：{chapter_title}")
    st.metric(label="当前文档字数", value=f"{len(new_content)}", delta="准备写入数据库", delta_color="off")
    st.divider()
    col_cancel, col_confirm = st.columns([1, 1], gap="medium")
    with col_cancel:
        if st.button("🚫 取消", type="secondary", width="stretch"): st.rerun()
    with col_confirm:
        if st.button("💾 确认覆盖", type="primary", width="stretch"):
            try:
                db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (new_content, chapter_id)) 
                force_update_book_time(db_mgr, book_id)
                log_audit_event("内容编辑", "保存正文", {"章节": chapter_title, "ID": chapter_id, "字数": len(new_content)})
                st.session_state.rerun_flag = True; st.toast("✅ 已保存"); time.sleep(0.5); st.rerun()
            except Exception as e: st.error(f"保存失败: {e}")

@dialog_decorator("➕ 新建")
def dialog_add_node(type_label, parent_id, book_id=None):
    st.caption(f"正在创建新的 **{type_label}**")
    name_input = st.text_input("名称", key="dialog_name_input")
    if st.button("确认创建", type="primary"):
        if not name_input.strip(): st.error("名称不能为空"); return
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
            cid = db_mgr.execute("INSERT INTO chapters (volume_id, title, summary, content, sort_order) VALUES (?,?,?,?,?)", (parent_id, name_input, "", "", mx+1))
            st.session_state.current_chapter_id = cid
            if 'expanded_volumes' not in st.session_state: st.session_state.expanded_volumes = set()
            st.session_state.expanded_volumes.add(parent_id)
        log_audit_event("结构管理", f"新建{type_label}", {"名称": name_input, "父级ID": parent_id})
        st.session_state.rerun_flag = True; st.rerun()

@dialog_decorator("⚙️ 管理")
def dialog_manage_node(type_label, node_id, current_name):
    st.caption(f"正在管理 {type_label}: **{current_name}**")
    new_name = st.text_input("重命名", value=current_name)
    c1, c2 = st.columns(2)
    if c1.button("💾 保存修改", type="primary"):
        db_mgr = st.session_state.db
        table = "parts" if type_label == "篇" else "volumes"
        db_mgr.execute(f"UPDATE {table} SET name=? WHERE id=?", (new_name, node_id))
        st.rerun()
    if c2.button("🗑️ 删除", type="secondary"):
        db_mgr = st.session_state.db
        table = "parts" if type_label == "篇" else "volumes"
        db_mgr.execute(f"DELETE FROM {table} WHERE id=?", (node_id,))
        st.rerun()

# ==============================================================================
# 🎨 Explorer Logic
# ==============================================================================
def toggle_state(key, item_id):
    if key not in st.session_state: st.session_state[key] = set()
    if item_id in st.session_state[key]: st.session_state[key].remove(item_id)
    else: st.session_state[key].add(item_id)

def render_explorer_node_part(db_mgr, part, current_book_id):
    if 'expanded_parts' not in st.session_state: st.session_state.expanded_parts = set()
    is_expanded = part['id'] in st.session_state.expanded_parts
    icon = "📂" if not is_expanded else "📖"
    if st.button(f"{icon} {part['name']}", key=f"p_btn_{part['id']}", width="stretch"):
        toggle_state('expanded_parts', part['id']); st.rerun()
    if is_expanded:
        st.markdown("""<div style="margin-top: -12px; margin-bottom: 5px;"></div>""", unsafe_allow_html=True)
        c_i, c_act1, c_act2 = st.columns([0.1, 1, 1])
        with c_act1:
            if st.button("➕ 加卷", key=f"add_v_{part['id']}", width="stretch"): dialog_add_node("卷", part['id'])
        with c_act2:
            if st.button("⚙️ 管理", key=f"mng_p_{part['id']}", width="stretch"): dialog_manage_node("篇", part['id'], part['name'])
        vols = db_mgr.query("SELECT id, name, part_id FROM volumes WHERE part_id=? ORDER BY sort_order", (part['id'],))
        if not vols: st.markdown("<div style='padding-left: 15px; color: gray; font-size: 12px; margin-bottom: 10px;'>└─ (暂无卷)</div>", unsafe_allow_html=True)
        else:
            for vol in vols: render_explorer_node_volume(db_mgr, vol)
        st.markdown("""<div style="margin-bottom: 10px;"></div>""", unsafe_allow_html=True)

def render_explorer_node_volume(db_mgr, vol):
    if 'expanded_volumes' not in st.session_state: st.session_state.expanded_volumes = set()
    is_expanded = vol['id'] in st.session_state.expanded_volumes
    icon = "📁" if not is_expanded else "📂"
    c_indent, c_main = st.columns([0.2, 5.8])
    with c_main:
        if st.button(f"{icon} {vol['name']}", key=f"v_btn_{vol['id']}", width="stretch"):
            toggle_state('expanded_volumes', vol['id']); st.rerun()
    if is_expanded:
        st.markdown("""<div style="margin-top: -12px; margin-bottom: 5px;"></div>""", unsafe_allow_html=True)
        c_i, c_act1, c_act2 = st.columns([0.3, 1, 1])
        with c_act1:
            if st.button("➕ 加章", key=f"add_c_{vol['id']}", width="stretch"): dialog_add_node("章", vol['id'])
        with c_act2:
            if st.button("⚙️ 管理", key=f"mng_v_{vol['id']}", width="stretch"): dialog_manage_node("卷", vol['id'], vol['name'])
        chaps = db_mgr.query("SELECT id, title FROM chapters WHERE volume_id=? ORDER BY sort_order", (vol['id'],))
        if not chaps: st.markdown("<div style='padding-left: 35px; color: gray; font-size: 12px;'>└─ (暂无章节)</div>", unsafe_allow_html=True)
        else:
            st.markdown("""<style>div[data-testid="stVerticalBlock"] > div > button.chap-btn { text-align: left; padding-left: 35px !important; border: none; font-size: 14px; }</style>""", unsafe_allow_html=True)
            with st.container():
                for chap in chaps:
                    is_active = (st.session_state.get('current_chapter_id') == chap['id'])
                    display_title = st.session_state.chapter_title_cache.get(chap['id'], chap['title'])
                    b_type = "primary" if is_active else "secondary"
                    if st.button(f"　　{display_title}", key=f"c_{chap['id']}", width="stretch", type=b_type):
                        ensure_log_file()
                        log_audit_event("阅读行为", "切换章节", {"章节": display_title, "ID": chap['id']})
                        st.session_state.current_chapter_id = chap['id']
                        st.session_state.current_part_id = vol['part_id']
                        st.rerun()
        st.markdown("""<div style="margin-bottom: 8px;"></div>""", unsafe_allow_html=True)

# ==============================================================================
# 🚀 Render Main Logic
# ==============================================================================
def render_writer(engine, current_book, current_chapter):
    if st.session_state.get("trigger_scroll_to_top"):
        components.html("""<script>window.parent.document.querySelector('section.main').scrollTo(0,0);</script>""", height=0)
        st.session_state.trigger_scroll_to_top = False 
        
    db_mgr = st.session_state.db
    _ensure_part_volume_schema(db_mgr)
    if 'generation_running' not in st.session_state: st.session_state.generation_running = False
    
    # 🔥🔥🔥 强制直连数据库读取配置 🔥🔥🔥
    st.session_state.model_assignments = get_config_direct_from_db("model_assignments", {})
    ai_settings = get_config_direct_from_db("ai_settings", {})
    custom_models = ai_settings.get("custom_model_list", [])
    
    def get_custom_model_data(assigned_key):
        search_name = assigned_key.replace("CUSTOM::", "").replace("CUSTOM:", "").strip()
        for m in custom_models:
            if m['name'] == search_name: return m
        return None

    if not current_book:
        st.warning("请先在 [书籍管理] 中选择一本书"); return
        
    render_header("✍️", current_book['title'])
    
    full_context_str = get_full_context(db_mgr, current_book['id'], current_chapter['id'] if current_chapter else None)
    
    st.markdown("""
    <style>
    div[data-testid="column"]:nth-of-type(1) button { border: 0px solid transparent !important; background: transparent !important; box-shadow: none !important; text-align: left !important; } 
    div[data-testid="column"]:nth-of-type(1) button:hover { background-color: rgba(150, 150, 150, 0.1) !important; color: #3eaf7c !important; } 
    div[data-testid="column"]:nth-of-type(1) button[kind="primary"] { background-color: rgba(62, 175, 124, 0.15) !important; border-left: 3px solid #3eaf7c !important; color: #3eaf7c !important; padding-left: 8px !important; }
    .custom-select-label { font-size: 14px; font-weight: 600; color: #444; margin-bottom: 4px; display: block; }
    textarea { font-size: 16px !important; line-height: 1.6 !important; font-family: 'PingFang SC', sans-serif; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-thumb { background: #888; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }
    </style>
    """, unsafe_allow_html=True)
    
    col_explorer, col_editor = st.columns([1.4, 2.6], gap="medium")
    
    with col_explorer:
        all_books = db_mgr.query("SELECT id, title FROM books")
        opts = {b['title']: b['id'] for b in all_books}
        idx = list(opts.values()).index(current_book['id']) if current_book['id'] in opts.values() else 0
        sel_title = st.selectbox("当前书籍", list(opts.keys()), index=idx, label_visibility="collapsed", key="write_book_selector")
        if opts[sel_title] != current_book['id']:
            log_audit_event("阅读行为", "切换书籍", {"书籍": sel_title, "ID": opts[sel_title]})
            st.session_state.current_book_id = opts[sel_title]
            st.session_state.current_chapter_id = None; st.session_state.current_part_id = None
            st.rerun()
        
        c_label, c_add = st.columns([4, 2])
        with c_label: st.caption("🗂️ 目录结构")
        with c_add:
            if st.button("➕ 新建篇", key="root_add_p_btn", width="stretch"): dialog_add_node("篇", None, current_book['id'])
        
        with st.container(height=700, border=False):
            parts = db_mgr.query("SELECT id, name FROM parts WHERE book_id=? ORDER BY sort_order", (current_book['id'],))
            if not parts: st.info('暂无内容，请点击上方"新建篇"')
            else:
                for part in parts: render_explorer_node_part(db_mgr, part, current_book['id'])

    with col_editor:
        tab_write, tab_outline, tab_assist = st.tabs(["📝 沉浸写作", "🧠 AI 批量生成", "✨ 写作辅助"])
        
        # TAB 1: 沉浸写作
        with tab_write:
            if not current_chapter: st.info("👈 请先从左侧选择一个章节。")
            else:
                title_key = f"chap_title_{current_chapter['id']}"
                st.text_input("章节标题", current_chapter['title'], key=title_key, on_change=_update_chapter_title_db_logged, args=(current_chapter['id'], title_key))
                
                st.markdown("##### 🤖 智能写作控制台")
                current_summary = current_chapter['summary'] or ""
                outline_key = f"ai_outline_input_{current_chapter['id']}"
                outline_input = st.text_area("本章大纲/提示词", current_summary, height=80, key=outline_key, 
                                           placeholder="在此输入剧情简述...（提到的配角会被自动识别并加入上下文）",
                                           on_change=_update_chapter_summary_db_logged, args=(current_chapter['id'], outline_key))
                
                c_m, c_l = st.columns([1.2, 1.8]) 
                with c_m:
                    def_write = get_safe_model_default("write_quick_gen", "DSK_V3")
                    assigned_write = st.session_state.model_assignments.get("write_quick_gen", def_write)
                    
                    model_display_name = ""
                    # 🔥 修复：如果检测到是自定义模型，直接显示其 API Model ID (如 mimo-v2-flash)
                    if "CUSTOM" in assigned_write:
                        c_data = get_custom_model_data(assigned_write)
                        if c_data:
                            model_display_name = f"🟢 {c_data.get('api_model', 'Unknown')}"
                        else:
                            clean_name = assigned_write.replace("CUSTOM::", "").replace("CUSTOM:", "")
                            model_display_name = f"🟢 {clean_name} (配置未找到)"
                    elif assigned_write in MODEL_MAPPING:
                        model_display_name = MODEL_MAPPING[assigned_write].get('name', assigned_write)
                    else:
                        model_display_name = assigned_write

                    st.caption(f"当前模型: {model_display_name}")
                    
                    # 允许自定义模型通过
                    if assigned_write in MODEL_MAPPING or "CUSTOM" in assigned_write:
                        model_pk = assigned_write
                    else:
                        model_pk = None

                with c_l: 
                    target_k = st.slider("本章预计字数 (k)", 1.0, 10.0, 3.0, 0.1, key="word_slider")
                    target_words_num = int(target_k * 1000)

                st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    btn_gen = st.button("✨ 开始生成", type="secondary", disabled=st.session_state.generation_running, width="stretch")
                with btn_col2:
                    btn_stop = st.button("⏹️ 停止生成", type="secondary", disabled=not st.session_state.generation_running, width="stretch")

                content_key = f"chapter_content_{current_chapter['id']}"
                if content_key not in st.session_state:
                    st.session_state[content_key] = current_chapter['content'] or ""

                if st.button("💾 保存当前正文", type="primary", width="stretch"):
                     content_to_save = st.session_state.get(content_key, current_chapter['content'] or "")
                     dialog_save_chapter_content(db_mgr, current_chapter['id'], content_to_save, current_book['id'], current_chapter['title'])

                st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

                current_text = st.session_state.get(content_key, "")
                current_len = len(current_text)
                len_color = "green" if current_len > 100 else "orange"
                
                c_head, c_status, c_count = st.columns([1.2, 2.5, 1.3])
                with c_head: st.caption("📖 正文编辑")
                ai_status_box = c_status.empty()
                with c_count: st.markdown(f"<div style='text-align:right; font-size:14px; padding-bottom:5px;'>字数: <span style='color:{len_color}; font-weight:bold'>{current_len}</span> / {target_words_num}</div>", unsafe_allow_html=True)

                editor_placeholder = st.empty()
                should_render_editor = True

                if btn_gen and model_pk:
                    should_render_editor = False 
                    
                    # 🔥🔥🔥 核心修复：如果是 Custom 模型，手动构建 Client 绕过 Engine 查找失败的问题
                    client = None; m_name = ""; m_key = ""
                    
                    if "CUSTOM" in model_pk:
                        c_data = get_custom_model_data(model_pk)
                        if c_data:
                            # 直接从数据库读配置，不依赖 engine.get_client
                            try:
                                client = OpenAI(api_key=c_data.get('key'), base_url=c_data.get('base'))
                                m_name = c_data.get('api_model', 'custom')
                                m_key = c_data.get('key')
                            except Exception as e:
                                st.error(f"❌ 客户端创建失败: {e}")
                        else:
                            st.error("❌ 自定义模型配置未找到，请检查设置。")
                    else:
                        # 标准模型继续走 Engine
                        client, m_name, m_key = engine.get_client(model_pk)

                    if not client: 
                        st.error("API Key 未配置或无效")
                    else:
                        db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (outline_input, current_chapter['id']))
                        st.session_state.generation_running = True
                        ensure_log_file()
                        
                        # 🔥 审计：AI生成开始
                        log_audit_event("AI创作", "单章生成启动", {"章节": current_chapter['title'], "模型": m_name, "目标字数": target_words_num})
                        
                        # 🔥🔥🔥 智能读取核心调用点：传入 outline_input 以激活配角读取 🔥🔥🔥
                        full_context_smart = get_full_context(
                            db_mgr, 
                            current_book['id'], 
                            current_chapter['id'], 
                            current_outline=outline_input
                        )
                        
                        final_prompt = get_enhanced_writing_prompt(full_context_smart, outline_input, target_words_num)
                        request_tokens = min(target_words_num, MAX_SAFE_WORD_COUNT)
                        if request_tokens != target_words_num: st.toast(f"⚠️ 自动限制字数为 {MAX_SAFE_WORD_COUNT}", icon="🛡️")

                        # 显示纯净的 API ID 用于状态栏
                        status_model_name = m_name if m_name else "AI"
                        ai_status_box.markdown(f":blue[⚡ AI 正在码字 ({status_model_name})...] <span style='font-size:12px'>Thinking...</span>", unsafe_allow_html=True)
                        
                        # 传入手动构建的 client
                        ok, stream = engine.generate_content_from_outline_ai_stream(current_chapter['id'], final_prompt, current_book, request_tokens, client, m_name, m_key)
                        if ok:
                            buf = ""
                            full_existing = (st.session_state[content_key] or "").strip()
                            full_existing = full_existing + "\n" if full_existing else ""
                            
                            for chunk in stream:
                                if not st.session_state.generation_running: break
                                content_text = safe_get_content(chunk)
                                if content_text:
                                    buf += content_text
                                    simulated_content = full_existing + buf
                                    editor_placeholder.markdown(f"""<div style="height: 600px; overflow-y: auto; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.25rem; padding: 1rem; font-family: 'Source Sans Pro', sans-serif; white-space: pre-wrap; background-color: transparent;">{simulated_content}</div>""", unsafe_allow_html=True)
                                    if len(buf) > int(target_words_num * 1.5): st.session_state.generation_running = False; st.toast("⚠️ 字数超限停止", icon="🛑"); break
                                     
                            full_new = full_existing + buf
                            db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (full_new, current_chapter['id']))
                            force_update_book_time(db_mgr, current_book['id'])
                            st.session_state[content_key] = full_new 
                            record_token_usage(provider="AI", model=m_name, tokens=len(buf), action_name="沉浸写作", book_title=current_book['title'])
                            
                            # 🔥 审计：AI生成完成
                            log_audit_event("AI创作", "单章生成完成", {"章节": current_chapter['title'], "生成字数": len(buf)})
                            
                            st.session_state.generation_running = False
                            ai_status_box.empty(); st.rerun() 
                        else:
                            ai_status_box.error("生成失败"); st.error(f"生成失败: {stream}"); st.session_state.generation_running = False
                
                if btn_stop:
                    ai_status_box.empty(); st.session_state.generation_running = False; st.rerun()

                if should_render_editor:
                    with editor_placeholder:
                        st.text_area(label="hidden_content", value=current_text, height=600, label_visibility="collapsed", key=content_key)

        # TAB 2: 批量生成
        with tab_outline:
             if not current_book: st.warning("请选择书籍")
             elif not parts: st.warning("无结构")
             else:
                st.subheader("✍️ 批量生成")
                default_p_idx = 0; default_v_idx = 0
                part_opts = {p['name']: p['id'] for p in parts}
                if current_chapter:
                    curr_vol = db_mgr.query("SELECT * FROM volumes WHERE id=?", (current_chapter['volume_id'],))[0]
                    if curr_vol['part_id'] in part_opts.values(): default_p_idx = list(part_opts.values()).index(curr_vol['part_id'])
                
                c_p, c_v = st.columns(2)
                sel_p_name = c_p.selectbox("选择篇", list(part_opts.keys()), index=default_p_idx, key="bg_p")
                sel_p_id = part_opts[sel_p_name]
                bg_vols = db_mgr.query("SELECT * FROM volumes WHERE part_id=? ORDER BY sort_order", (sel_p_id,))
                
                if not bg_vols: st.warning("该篇无卷")
                else:
                    bg_v_opts = {v['name']: v['id'] for v in bg_vols}
                    if current_chapter and current_chapter['volume_id'] in bg_v_opts.values(): default_v_idx = list(bg_v_opts.values()).index(current_chapter['volume_id'])
                    sel_v_name = c_v.selectbox("选择卷", list(bg_v_opts.keys()), index=default_v_idx, key="bg_v")
                    sel_v_id = bg_v_opts[sel_v_name]
                    bg_chaps = db_mgr.query("SELECT id, title, summary FROM chapters WHERE volume_id=? ORDER BY sort_order", (sel_v_id,))
                    
                    if not bg_chaps: st.info("该卷无章节")
                    else:
                        c_names = [c['title'] for c in bg_chaps]
                        c1, c2 = st.columns(2)
                        s_start = c1.selectbox("起始章", c_names, 0, key="bg_s"); s_idx = c_names.index(s_start)
                        s_end = c2.selectbox("结束章", c_names[s_idx:], len(c_names[s_idx:])-1, key="bg_e"); e_idx = c_names.index(s_end)
                        target_chaps = bg_chaps[s_idx:e_idx+1]
                        st.info(f"选中: {len(target_chaps)} 章")
                        gen_prompt = st.text_area("通用大纲/指令", height=100, placeholder="例如：主角在这一段剧情中...")
                        
                        cm1, cm2, cm3 = st.columns([1, 1, 1])
                        with cm1:
                            def_b = get_safe_model_default("write_batch_gen", "GPT_4o")
                            assigned_b = st.session_state.model_assignments.get("write_batch_gen", def_b)
                            model_display_name_b = ""
                            if "CUSTOM" in assigned_b:
                                c_data_b = get_custom_model_data(assigned_b)
                                model_display_name_b = f"🟢 {c_data_b.get('api_model', 'Unknown')}" if c_data_b else f"🟢 {assigned_b}"
                            elif assigned_b in MODEL_MAPPING:
                                model_display_name_b = MODEL_MAPPING[assigned_b].get('name', assigned_b)
                            else:
                                model_display_name_b = assigned_b

                            st.markdown(f"**模型**"); st.caption(f"🚀 {model_display_name_b}")
                            pk_b = assigned_b if (assigned_b in MODEL_MAPPING or "CUSTOM" in assigned_b) else None

                        with cm2: len_b = st.slider("单章字数(k)", 1, 10, 3, key="bg_l")
                        with cm3:
                            st.markdown('<div style="padding-top: 29px;"></div>', unsafe_allow_html=True)
                            c_bg_start, c_bg_stop = st.columns(2)
                            with c_bg_start:
                                btn_bg = st.button("🚀 开始", type="primary", width="stretch", disabled=st.session_state.generation_running)
                            with c_bg_stop:
                                if st.button("⏹️ 停止", type="secondary", width="stretch", disabled=not st.session_state.generation_running, key="btn_stop_batch"):
                                    st.session_state.generation_running = False; st.rerun()
                                    
                        if btn_bg and pk_b:
                            if not gen_prompt.strip(): st.error("请输入大纲")
                            else:
                                client = None; m_name = ""; m_key = ""
                                if "CUSTOM" in pk_b:
                                    c_data = get_custom_model_data(pk_b)
                                    if c_data:
                                        try:
                                            client = OpenAI(api_key=c_data.get('key'), base_url=c_data.get('base'))
                                            m_name = c_data.get('api_model', 'custom'); m_key = c_data.get('key')
                                        except Exception as e: st.error(f"❌ 客户端创建失败: {e}")
                                    else: st.error("❌ 自定义模型配置未找到")
                                else:
                                    client, m_name, m_key = engine.get_client(pk_b)

                                if not client: st.error("API Key 未配置")
                                else:
                                    st.session_state.generation_running = True
                                    ph = st.empty(); cnt = 0
                                    ensure_log_file()
                                    log_audit_event("AI创作", "批量生成启动", {"章节数": len(target_chaps), "模型": m_name})
                                    batch_hard_limit = len_b * 1000 * 1.5
                                    request_words_b = min(len_b * 1000, MAX_SAFE_WORD_COUNT)
                                    if request_words_b != len_b*1000: st.toast(f"⚠️ 自动限制为 {MAX_SAFE_WORD_COUNT}", icon="🛡️")

                                    try:
                                        prev_chap_title = "前一章" 
                                        for idx, ch in enumerate(target_chaps):
                                            if not st.session_state.generation_running: ph.warning("已停止"); break
                                            ph.info(f"⏳ ({idx+1}/{len(target_chaps)}) 生成：{ch['title']}...")
                                            combined_outline = f"{gen_prompt}\n{ch['summary'] or ''}"
                                            batch_context = get_full_context(
                                                db_mgr, 
                                                current_book['id'], 
                                                ch['id'],
                                                current_outline=combined_outline
                                            )
                                            final_batch_prompt = f"{batch_context}\n\n【批量生成连续性要求】\n**前一章是《{prev_chap_title}》**，请紧接其后。\n【本章大纲】\n{combined_outline}"
                                            db_mgr.execute("UPDATE chapters SET summary=? WHERE id=?", (combined_outline, ch['id']))
                                            full_c = ""
                                            ok, stream = engine.generate_content_from_outline_ai_stream(ch['id'], final_batch_prompt, current_book, request_words_b, client, m_name, m_key)
                                            if ok:
                                                for chunk in stream:
                                                    content_text = safe_get_content(chunk)
                                                    if content_text:
                                                        full_c += content_text
                                                        if len(full_c) > batch_hard_limit: break 
                                                db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (full_c, ch['id']))
                                                record_token_usage(provider="AI", model=m_name, tokens=len(full_c), action_name="批量生成", book_title=current_book['title'])
                                                cnt += 1; prev_chap_title = ch['title']
                                            else: st.error(f"失败: {ch['title']}")
                                        force_update_book_time(db_mgr, current_book['id'])
                                        ph.success(f"🎉 完成！共 {cnt} 章")
                                    except Exception as e: ph.error(f"错误: {e}")
                                    finally: st.session_state.generation_running = False; time.sleep(2); st.rerun()

        # TAB 3: 写作辅助
        with tab_assist:
            # 🔥 强制直连刷新，获取最新配置
            current_assignments = get_config_direct_from_db("model_assignments", {})
            
            all_chaps_in_book = db_mgr.query("SELECT c.id, c.title, c.content, c.summary FROM chapters c JOIN volumes v ON c.volume_id = v.id JOIN parts p ON v.part_id = p.id WHERE p.book_id = ? ORDER BY p.sort_order, v.sort_order, c.sort_order", (current_book['id'],))
            
            if not all_chaps_in_book: st.info("请先创建章节。")
            else:
                chap_options = {c['title']: c['id'] for c in all_chaps_in_book}
                default_idx = 0
                if current_chapter and current_chapter['title'] in chap_options:
                    default_idx = list(chap_options.keys()).index(current_chapter['title'])
                target_chap_title = st.selectbox("🎯 选择目标章节", list(chap_options.keys()), index=default_idx)
                target_chap_id = chap_options[target_chap_title]
                target_chap_data = next((c for c in all_chaps_in_book if c['id'] == target_chap_id), None)
                target_content = target_chap_data['content'] if target_chap_data else ""
                target_summary = target_chap_data['summary'] if target_chap_data else ""
                
                # 🔥 使用强制刷新的 assignments
                def_cf = get_safe_model_default("write_logic_assist", "GPT_4o_Mini")
                
                # 键名修正：write_re_write
                def_rw = get_safe_model_default("write_re_write", "DSK_V3") 
                as_cf = current_assignments.get("write_logic_assist", def_cf)
                as_rw = current_assignments.get("write_re_write", def_rw) 
                
                display_name_cf = as_cf
                if "CUSTOM" in as_cf:
                    c_data_cf = get_custom_model_data(as_cf)
                    if c_data_cf: display_name_cf = f"🟢 {c_data_cf.get('api_model', 'Unknown')}"
                    else: display_name_cf = f"🔴 配置失效 ({as_cf})"
                elif as_cf in MODEL_MAPPING:
                    display_name_cf = MODEL_MAPPING[as_cf].get('name', as_cf)

                st.subheader("🔎 矛盾检测")
                st.caption(f"模型: **{display_name_cf}**")
                
                if st.button("🚨 检测设定冲突", width="stretch"):
                    client = None; m_name = ""; m_key = ""
                    if "CUSTOM" in as_cf:
                        c_data = get_custom_model_data(as_cf)
                        if c_data:
                            client = OpenAI(api_key=c_data.get('key'), base_url=c_data.get('base'))
                            m_name = c_data.get('api_model'); m_key = c_data.get('key')
                    else: client, m_name, m_key = engine.get_client(as_cf)

                    if not client: st.error("API Key 未配置")
                    else:
                        with st.spinner("正在对比设定集与前文..."):
                            ensure_log_file()
                            log_audit_event("AI辅助", "矛盾检测", {"章节": target_chap_title, "模型": m_name})
                            assist_context = get_full_context(db_mgr, current_book['id'], target_chap_id, current_outline=target_summary)
                            final_input = f"{assist_context}\n\n【待检测正文】\n{target_content}"
                            rep = engine.analyze_chapter_conflict(final_input, current_book, client, m_name, m_key)
                            if isinstance(rep, tuple): rep = rep[1]
                            st.session_state[f"conflict_report_{target_chap_id}"] = rep
                        st.success("完成")
                rep_val = st.session_state.get(f"conflict_report_{target_chap_id}", "")
                if rep_val: st.info("检测报告："); st.text_area("report", rep_val, height=150, disabled=True, label_visibility="collapsed")
                
                st.subheader("📊 剧情节点与连贯性")
                c_pl1, c_pl2 = st.columns(2)
                with c_pl1:
                    if st.button("🔍 深度分析剧情连贯性", width="stretch"):
                        chap_idx = next((i for i, c in enumerate(all_chaps_in_book) if c['id'] == target_chap_id), -1)
                        if chap_idx > 0:
                            tracker = PlotContinuityTracker(db_mgr, current_book['id'])
                            st.session_state[f"plot_continuity_report_{target_chap_id}"] = tracker.get_chapter_continuity_report(all_chaps_in_book[chap_idx-1]['id'], target_chap_id)
                        else: st.session_state[f"plot_continuity_report_{target_chap_id}"] = "这是第一章"
                with c_pl2:
                    if st.button("👥 检测人物重复登场", width="stretch"):
                        chap_idx = next((i for i, c in enumerate(all_chaps_in_book) if c['id'] == target_chap_id), -1)
                        if chap_idx > 0:
                            prev_chars = get_current_chapter_characters(all_chaps_in_book[chap_idx-1]['content'] or "")
                            curr_chars = get_current_chapter_characters(target_content)
                            rep_chars = prev_chars.intersection(curr_chars)
                            st.session_state[f"character_repeat_report_{target_chap_id}"] = f"**重复登场**: {', '.join(rep_chars)}" if rep_chars else "✅ 无重复"
                        else: st.session_state[f"character_repeat_report_{target_chap_id}"] = "无需检测"

                if st.session_state.get(f"plot_continuity_report_{target_chap_id}"): st.markdown(st.session_state[f"plot_continuity_report_{target_chap_id}"])
                if st.session_state.get(f"character_repeat_report_{target_chap_id}"): st.info(st.session_state[f"character_repeat_report_{target_chap_id}"])

                st.subheader("🔄 一键重写")
                c_style_1, c_style_2 = st.columns([2, 1])
                with c_style_1:
                    style_rows = db_mgr.query("SELECT content FROM plots WHERE status='StyleDNA' AND book_id=?", (current_book['id'],))
                    settings = db_mgr.query("SELECT content FROM plots WHERE status LIKE 'Setting_%' AND book_id=?", (current_book['id'],))
                    all_opts = ["(不使用额外参考)"] + [f"🎨 风格: {s['content']}" for s in style_rows] + [f"🌍 设定: {s['content'][:20]}" for s in settings]
                    sel_opt = st.selectbox("参考风格/设定", all_opts, label_visibility="collapsed")
                    target_style_content = sel_opt if sel_opt != "(不使用额外参考)" else ""

                with c_style_2:
                    display_name_rw = as_rw
                    if "CUSTOM" in as_rw:
                         c_data_rw = get_custom_model_data(as_rw)
                         if c_data_rw: display_name_rw = f"🟢 {c_data_rw.get('api_model', 'Unknown')}"
                         else: display_name_rw = f"🔴 配置失效 ({as_rw})"
                    elif as_rw in MODEL_MAPPING:
                        display_name_rw = MODEL_MAPPING[as_rw].get('name', as_rw)
                    
                    st.markdown(f"**模型**: {display_name_rw}")
                    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True) 
                
                # 🔥 流式重写实现区
                if st.button("🚀 根据建议/设定重写本章", type="primary", width="stretch"):
                    if not target_content: st.error("章节内容为空")
                    else:
                        client = None; m_name = ""; m_key = ""
                        if "CUSTOM" in as_rw:
                            c_data = get_custom_model_data(as_rw)
                            if c_data:
                                client = OpenAI(api_key=c_data.get('key'), base_url=c_data.get('base'))
                                m_name = c_data.get('api_model'); m_key = c_data.get('key')
                        else: client, m_name, m_key = engine.get_client(as_rw)

                        if not client: st.error("API Key 未配置")
                        else:
                            st.session_state.generation_running = True
                            
                            # 构建 Prompt
                            report_context = st.session_state.get(f"conflict_report_{target_chap_id}", "无特殊报告")
                            prompt = "你是一个专业的网文写作助手。请根据以下要求重写提供的章节内容。\n\n"
                            if target_style_content:
                                prompt += f"【参考风格/设定】：\n{target_style_content}\n\n"
                            if report_context and report_context != "无特殊报告":
                                prompt += f"【需修正的逻辑/矛盾问题】：\n{report_context}\n\n"
                            prompt += f"【原文内容】：\n{target_content[:MAX_SAFE_WORD_COUNT]}\n\n"
                            prompt += "【重写要求】：\n1. 保持剧情核心不变，优化文笔。\n2. 解决上述提到的逻辑问题（如有）。\n3. 贴合参考风格（如有）。\n4. 直接输出重写后的正文，不要包含任何解释性语言。"

                            ensure_log_file()
                            log_audit_event("AI辅助", "章节重写", {"章节": target_chap_title, "模型": m_name})
                            
                            rewrite_placeholder = st.empty()
                            full_response = ""
                            
                            try:
                                stream = client.chat.completions.create(
                                    model=m_name,
                                    messages=[{"role": "user", "content": prompt}],
                                    stream=True,
                                    max_tokens=4096,
                                    temperature=0.7
                                )
                                
                                for chunk in stream:
                                    content = safe_get_content(chunk)
                                    if content:
                                        full_response += content
                                        rewrite_placeholder.markdown(f"##### ⏳ 正在重写...\n\n{full_response}")
                                
                                st.session_state[f"rewritten_content_{target_chap_id}"] = full_response
                                record_token_usage(provider="AI", model=m_name, tokens=len(full_response), action_name="章节重写", book_title=current_book['title'])
                                st.success("完成")
                                st.session_state.generation_running = False
                                time.sleep(0.5)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"重写失败: {e}")
                                st.session_state.generation_running = False
                
                rw_val = st.session_state.get(f"rewritten_content_{target_chap_id}", "")
                if rw_val:
                    st.markdown("##### 预览重写结果")
                    st.text_area("preview", rw_val, height=300, label_visibility="collapsed")
                    if st.button(f"✅ 覆盖【{target_chap_title}】原内容", width="stretch"):
                        db_mgr.execute("UPDATE chapters SET content=? WHERE id=?", (rw_val, target_chap_id))
                        force_update_book_time(db_mgr, current_book['id'])
                        if current_chapter and target_chap_id == current_chapter['id']: st.session_state[f"chapter_content_{target_chap_id}"] = rw_val
                        log_audit_event("内容编辑", "应用重写", {"章节": target_chap_title})
                        st.session_state.rerun_flag = True; st.rerun()