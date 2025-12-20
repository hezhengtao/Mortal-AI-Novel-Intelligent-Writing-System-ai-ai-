import os
import pandas as pd

# ================= 0. 全局配置 & 常量 =================

# 🚨 修正：根据文件结构图，修正 DB 文件名
DB_FILE = "novels.db"

# 🛠️ 修正：新增 DATA_DIR 供 views/dashboard.py 和其他模块使用
DATA_DIR = "data"

# --- 主题定义 ---
THEMES = {
    "翡翠森林": {
        "nav_bg": "#f1f8e9", 
        "primary": "#42b983",       
        "primary_light": "#e8f5e9", 
        "text_h": "#1b5e20",
        "grad_a": "#42e695", 
        "grad_b": "#3bb2b8", 
        "btn_text": "#1b5e20",      
        "bg_body": "#f9fbf7", 
        "input_bg": "#ffffff", 
        "text_body": "#1b5e20",     
        "border": "#c8e6c9"
    },
    "紫气东来": {
        "nav_bg": "#f8f9fa", 
        "primary": "#7e57c2",       
        "primary_light": "#e3f2fd", 
        "text_h": "#5e35b1",
        "grad_a": "#9575cd", 
        "grad_b": "#7e57c2", 
        "btn_text": "#ffffff",      
        "bg_body": "#ffffff", 
        "input_bg": "#ffffff", 
        "text_body": "#333333", 
        "border": "#d1c4e9"
    },
    "深海幽蓝": {
        "nav_bg": "#f0f8ff", 
        "primary": "#29b6f6",       
        "primary_light": "#e1f5fe", 
        "text_h": "#0277bd",
        "grad_a": "#4fc3f7", 
        "grad_b": "#29b6f6", 
        "btn_text": "#ffffff",      
        "bg_body": "#faffff", 
        "input_bg": "#ffffff", 
        "text_body": "#006064", 
        "border": "#b3e5fc"
    },
    "水墨黑白": {
        "nav_bg": "#ffffff", 
        "primary": "#616161",       
        "primary_light": "#f5f5f5", 
        "text_h": "#424242",
        "grad_a": "#9e9e9e", 
        "grad_b": "#616161", 
        "btn_text": "#ffffff",      
        "bg_body": "#ffffff", 
        "input_bg": "#fafafa", 
        "text_body": "#212121", 
        "border": "#e0e0e0"
    },
    "🌃 永夜极光 (黑夜)": {
        "nav_bg": "#1e1e1e", 
        "primary": "#ce93d8",       
        "primary_light": "#333333", 
        "text_h": "#ce93d8",
        "grad_a": "#e1bee7", 
        "grad_b": "#ce93d8", 
        "btn_text": "#ffffff",      
        "bg_body": "#121212", 
        "input_bg": "#2d2d2d", 
        "text_body": "#e0e0e0", 
        "border": "#444444"
    },
    "古韵墨香": {
        "nav_bg": "#fcf8f3", 
        "primary": "#8d6e63",       
        "primary_light": "#efebe9", 
        "text_h": "#5d4037",
        "grad_a": "#a1887f", 
        "grad_b": "#8d6e63", 
        "btn_text": "#ffffff",      
        "bg_body": "#fffdfa", 
        "input_bg": "#ffffff", 
        "text_body": "#4e342e", 
        "border": "#d7ccc8"
    },
    "科技青柠": {
        "nav_bg": "#e6ffe6", 
        "primary": "#9ccc65",       
        "primary_light": "#f1f8e9", 
        "text_h": "#558b2f",
        "grad_a": "#c5e1a5", 
        "grad_b": "#9ccc65", 
        "btn_text": "#ffffff",      
        "bg_body": "#f9fff9", 
        "input_bg": "#ffffff", 
        "text_body": "#33691e", 
        "border": "#dcedc8"
    },
    "热带日落": {
        "nav_bg": "#fff3e0", 
        "primary": "#ffa726",       
        "primary_light": "#ffe0b2", 
        "text_h": "#ef6c00",
        "grad_a": "#ffcc80", 
        "grad_b": "#ffa726", 
        "btn_text": "#ffffff",      
        "bg_body": "#fff8e1", 
        "input_bg": "#ffffff", 
        "text_body": "#e65100", 
        "border": "#ffe0b2"
    }
}

# --- 模型定义 ---
MODEL_GROUPS = {
    "OpenAI": {
        "models": {
            "GPT_4o": {"name": "GPT-4o", "api_model": "gpt-4o", "base": "https://api.openai.com/v1"},
            "GPT_4o_Mini": {"name": "GPT-4o Mini", "api_model": "gpt-4o-mini", "base": "https://api.openai.com/v1"},
            "GPT_4_Turbo": {"name": "GPT-4 Turbo", "api_model": "gpt-4-turbo", "base": "https://api.openai.com/v1"},
        },
        "default_key": "GPT_4o"
    },
    "Anthropic": {
        "models": {
            "CLA_3_5_Sonnet": {"name": "Claude 3.5 Sonnet", "api_model": "claude-3-5-sonnet-20240620", "base": "https://api.anthropic.com/v1"},
            "CLA_3_Opus": {"name": "Claude 3 Opus", "api_model": "claude-3-opus-20240229", "base": "https://api.anthropic.com/v1"},
        },
        "default_key": "CLA_3_5_Sonnet"
    },
    "DeepSeek": {
        "models": {
            "DSK_V3": {"name": "DeepSeek 3.0", "api_model": "deepseek-chat", "base": "https://api.deepseek.com/v1"},
            "DSK_V2": {"name": "DeepSeek 2.0", "api_model": "deepseek-v2", "base": "https://api.deepseek.com/v1"},
        },
        "default_key": "DSK_V3"
    },
    "阿里云 (Aliyun)": {
        "models": {
            "QWN_Max": {"name": "通义千问 Max", "api_model": "qwen-max", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
            "QWN_Turbo": {"name": "通义千问 Turbo", "api_model": "qwen-turbo", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        },
        "default_key": "QWN_Max"
    },
    "谷歌 (Google)": {
        "models": {
            "GEM_2_5_Pro": {"name": "Gemini 2.5 Pro", "api_model": "gemini-2.5-pro", "base": "https://api.google.com/v1"},
            "GEM_2_5_Flash": {"name": "Gemini 2.5 Flash", "api_model": "gemini-2.5-flash", "base": "https://api.google.com/v1"},
        },
        "default_key": "GEM_2_5_Pro"
    },
    "百度 (Baidu)": {
        "models": {
            "ERNIE_4": {"name": "文心一言 4.0", "api_model": "ernie-4.0-8k", "base": "https://aip.baiduce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"},
            "ERNIE_3_5": {"name": "文心一言 3.5", "api_model": "ernie-3.5-8k", "base": "https://aip.baiduce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"},
        },
        "default_key": "ERNIE_4"
    },
    "月之暗面 (Moonshot)": {
        "models": {
            "Kimi_Moonshot_V1": {"name": "Kimi Moonshot-v1", "api_model": "moonshot-v1-8k", "base": "https://api.moonshot.cn/v1"},
            "Kimi_Moonshot_V1_32k": {"name": "Kimi Moonshot-v1-32k", "api_model": "moonshot-v1-32k", "base": "https://api.moonshot.cn/v1"},
        },
        "default_key": "Kimi_Moonshot_V1_32k"
    },
    "豆包 (Doubao)": {
        "models": {
            "Doubao_Pro": {"name": "豆包 Pro", "api_model": "doubao-pro-4k", "base": "https://ark.cn-beijing.volces.com/api/v3"},
            "Doubao_Lite": {"name": "豆包 Lite", "api_model": "doubao-lite-4k", "base": "https://ark.cn-beijing.volces.com/api/v3"},
        },
        "default_key": "Doubao_Pro"
    },
    "硅基流动 (SiliconFlow)": {
        "models": {
            "SF_Qwen_Turbo": {"name": "SF-Qwen-Turbo", "api_model": "qwen-turbo", "base": "https://api.siliconflow.cn/v1"},
            "SF_DeepSeek_V2": {"name": "SF-DeepSeek-V2", "api_model": "deepseek-v2", "base": "https://api.siliconflow.cn/v1"},
        },
        "default_key": "SF_Qwen_Turbo"
    },
}

# 扁平化映射
DEFAULT_MODEL_MAPPING = {}
for provider, group in MODEL_GROUPS.items():
    for key, model_info in group['models'].items():
        DEFAULT_MODEL_MAPPING[key] = {**model_info, "provider": provider}

MODEL_MAPPING = DEFAULT_MODEL_MAPPING.copy() # 全局变量，运行时更新
AVAILABLE_MODELS = list(DEFAULT_MODEL_MAPPING.keys())

# --- 功能键定义 (单一真理源) ---
FEATURE_MODELS = {
    "write_quick_gen": {"name": "沉浸写作 - 快速生成/重写", "default": "DSK_V3"},
    "write_batch_gen": {"name": "沉浸写作 - 批量生成", "default": "GPT_4o"},
    "write_logic_assist": {"name": "沉浸写作 - 逻辑/设定辅助", "default": "GPT_4o_Mini"},
    "write_re_write": {"name": "写作辅助 - 一键重写", "default": "GPT_4o"}, 
    "knowledge_style_gen": {"name": "拆书知识 - 风格改造", "default": "CLA_3_5_Sonnet"},
    "knowledge_analyze": {"name": "拆书知识 - 风格/设定分析", "default": "GPT_4o_Mini"},
    "books_arch_gen": {"name": "书籍管理 - 架构/图谱生成", "default": "DSK_V3"},
    "import_char_analysis": {"name": "书籍导入 - 简介/分析", "default": "DSK_V3"}, 
    "character_extract": {"name": "角色管理 - 智能提取", "default": "GPT_4o"}, 
    "idea_generation": {"name": "灵感模式 - 点子生成", "default": "GPT_4o_Mini"},
}

# === Session State 默认值 ===
defaults = {
    'nav_expanded': True, 
    'current_menu': "dashboard",
    'current_book_id': None,
    'current_chapter_id': None,
    'analysis_tasks': [],
    'current_theme': "翡翠森林",
    'token_tracker': {"cost": 0.0},
    'reading_chapter_id': None, 
    'chapter_title_cache': {}, 
    'rerun_flag': False, 
    'model_usage_stats': {},
    'custom_model_base': "",
    'custom_model_key': "",
    'custom_api_model': "",
    'custom_model_name': "自定义模型",
    'selected_provider': "OpenAI",
    'custom_model_enabled': False,
    'generation_running': False,
    'batch_input_data': pd.DataFrame([
        {'序号': 1, '章节标题': '新章节标题 1', '大纲/摘要': '本章主要剧情点...'},
        {'序号': 2, '章节标题': '新章节标题 2', '大纲/摘要': '本章主要剧情点...'}
    ]),
    'batch_start_index': 1
}