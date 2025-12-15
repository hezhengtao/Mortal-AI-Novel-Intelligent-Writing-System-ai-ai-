# mortal_write/path_utils.py

import os
import sys
import json
import tkinter as tk
from tkinter import filedialog

def get_executable_dir():
    """
    获取软件所在的真实目录。
    - 如果是打包后的 EXE，返回 EXE 所在文件夹。
    - 如果是代码运行，返回 main.py 所在文件夹。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

# 配置文件路径 (固定存放在软件旁边，用于记住用户的选择)
CONFIG_FILE = os.path.join(get_executable_dir(), "mortal_write_config.json")

def load_workspace_config():
    """读取工作区配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                path = data.get("data_dir")
                if path and os.path.exists(path):
                    return path
        except:
            return None
    return None

def save_workspace_config(path):
    """保存工作区配置"""
    config = {"data_dir": path}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def reset_workspace_config():
    """重置配置 (用于切换工作区)"""
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

def select_folder_dialog():
    """弹出系统原生文件夹选择框"""
    try:
        # 创建一个隐藏的 tk 主窗口
        root = tk.Tk()
        root.withdraw() 
        # 强制置顶，防止被浏览器窗口遮挡
        root.attributes('-topmost', True) 
        
        folder_path = filedialog.askdirectory(title="请选择数据存储目录 (Mortal Write)")
        
        root.destroy()
        return folder_path
    except Exception as e:
        print(f"Dialog Error: {e}")
        return None