<p align="right">
  <a href="./README_EN.md">English</a> | <strong>中文</strong>
</p>

# ✒️ 凡人智能写作系统 (MortalWrite)

一款专为网络小说家、编剧和创作者设计的桌面智能写作助手，它将强大的AI能力与完全本地化的数据管理相结合，让您的灵感安全、高效地转化为文字。

<img width="2460" height="1410" alt="image" src="https://github.com/user-attachments/assets/ef97ac25-7833-4efc-91b0-8572fbe05ed5" />
<img width="2460" height="1410" alt="image" src="https://github.com/user-attachments/assets/6e7abacc-ffcc-47e7-bb45-d3762c2bcec0" />

## ✨ 项目简介

在 AI 浪潮下，写作工具层出不穷，但大多依赖云端，让创作者对自己的数据隐私和长期存续感到不安。**凡人** 的诞生就是为了解决这个问题。它是一个运行在您自己电脑上的桌面软件，拥有媲美在线工具的 AI 功能，同时确保您的每一本书、每一个角色、每一个灵感都只属于您自己。

本软件基于 Python 和 Streamlit 构建，并使用 PyWebView 和 PyInstaller 打包成原生桌面应用，实现了跨平台的免安装、免浏览器体验。

## 🚀 主要功能

*   📚 **作品管理**: 以"书籍"为核心，轻松管理多部小说的卷、章、节，结构清晰。
*   ✍️ **沉浸式写作**: 提供简洁的写作界面，并可随时调用 AI 进行续写、润色、风格模仿。
*   👥 **角色档案**: 建立详细的角色卡片，包括背景、性格、能力和头像。更可以**一键调用AI，自动生成人物关系图谱**，让复杂的人物关系一目了然。
*   💡 **灵感风暴**: 当您卡文时，输入几个关键词，AI 会为您提供多个创意方向、剧情转折或世界观设定。
*   🧠 **拆书知识库**: 导入您喜欢的文章或小说片段，AI 会自动分析其"文笔DNA"，帮助您学习和模仿。
*   🎨 **个性化主题**: 内置多种UI主题，并支持高度自定义，打造属于您的写作环境。
*   💻 **桌面端应用**: 无需依赖浏览器，像普通软件一样运行，提供开场动画、独立图标的完整体验。
*   🔒 **数据本地化**: **您的所有数据都存储在您自己选择的本地文件夹中**。无需联网，也能进行基础的写作和管理。

## 🛠️ 技术栈

*   **核心框架**: Python 3.9+
*   **用户界面**: Streamlit
*   **桌面封装**: PyWebView (将Web界面打包成原生窗口)
*   **程序打包**: PyInstaller (生成可执行文件)
*   **数据存储**: SQLite (本地数据库)

## 🎯 快速开始

### 面向普通用户

您无需安装Python或任何复杂的环境。

1.  前往本项目的 [**Releases**](https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-/releases) 页面。
2.  下载最新版本的压缩包。
3.  解压后，得到一个 `MortalWrite` 文件夹。
4.  双击运行文件夹内的 `MortalWrite.exe` 即可开始使用。

> **提示**：您可以为 `MortalWrite.exe` 创建一个桌面快捷方式，方便日后启动。

### 面向开发者

如果您想从源码运行或进行二次开发，请按以下步骤操作：

1.  **克隆仓库**
    ```bash
    git clone https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-.git
    cd Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-
    ```

2.  **创建 `requirements.txt`**
    如果您还没有依赖文件，可以使用 `pipreqs` 快速生成（它只会包含项目导入的库）：
    ```bash
    pip install pipreqs
    pipreqs . --encoding=utf8 --force
    ```

3.  **安装依赖**
    建议在虚拟环境中安装，以避免与全局环境冲突。
    ```bash
    pip install -r requirements.txt
    ```

4.  **从源码运行**
    ```bash
    streamlit run main.py
    ```
    这将在您的浏览器中打开应用。

## 📖 使用指南

首次启动软件时，程序会弹出一个文件夹选择框，提示您**选择一个"工作区"**。

这个文件夹是您所有数据的家。您创作的每一本书、每一个角色、所有的AI配置和日志，都将安全地存储在这个文件夹中。请务必选择一个稳定、安全的位置。

## 🤝 贡献代码

欢迎所有形式的贡献！如果您有好的想法、发现了BUG或想优化代码，请：

1.  **Fork** 本仓库。
2.  创建一个新的功能分支 (`git checkout -b feature/AmazingFeature`)。
3.  提交您的修改 (`git commit -m 'Add some AmazingFeature'`)。
4.  推送到您的分支 (`git push origin feature/AmazingFeature`)。
5.  创建一个 **Pull Request**。

您也可以直接提交 [**Issues**](https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-/issues) 来报告问题或提出建议。

## 📄 许可证

本项目采用 MIT 许可证。详情请见 `LICENSE` 文件。

## 🙏 致谢

*   感谢 Streamlit、PyWebView 等优秀开源项目的开发者。
*   感谢所有为本项目提供灵感和反馈的用户。