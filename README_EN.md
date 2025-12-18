<p align="right">
  <a href="./README.md">中文</a> | <strong>English</strong>
</p>

# ✒️ MortalWrite - Intelligent Writing Assistant


A desktop intelligent writing assistant designed for web novelists, screenwriters, and creators. It combines powerful AI capabilities with fully localized data management, allowing your inspiration to be safely and efficiently transformed into text.

<img width="2460" height="1410" alt="image" src="https://github.com/user-attachments/assets/ef97ac25-7833-4efc-91b0-8572fbe05ed5" />
<img width="2460" height="1410" alt="image" src="https://github.com/user-attachments/assets/6e7abacc-ffcc-47e7-bb45-d3762c2bcec0" />

## ✨ Project Introduction

In the wave of AI, numerous writing tools have emerged, but most rely on the cloud, causing creators to worry about their data privacy and long-term sustainability. **MortalWrite** was born to solve this problem. It is a desktop software that runs on your own computer, with AI functions comparable to online tools, while ensuring that every book, every character, and every inspiration belongs only to you.

This software is built with Python and Streamlit, and packaged into native desktop applications using PyWebView and PyInstaller, achieving a cross-platform, installation-free, and browser-free experience.

## 🚀 Main Features

*   📚 **Work Management**: With "books" as the core, easily manage volumes, chapters, and sections of multiple novels with a clear structure.
*   ✍️ **Immersive Writing**: Provides a clean writing interface, and can call AI at any time for continuation, polishing, and style imitation.
*   👥 **Character Profiles**: Create detailed character cards including background, personality, abilities, and avatars. **One-click AI to automatically generate character relationship graphs**, making complex relationships clear at a glance.
*   💡 **Inspiration Storm**: When you're stuck, input a few keywords, and AI will provide you with multiple creative directions, plot twists, or world-building ideas.
*   🧠 **Book Analysis Knowledge Base**: Import your favorite articles or novel excerpts, AI will automatically analyze their "writing DNA" to help you learn and imitate.
*   🎨 **Personalized Themes**: Built-in multiple UI themes, supporting high customization to create your writing environment.
*   💻 **Desktop Application**: No need to rely on a browser, runs like regular software, providing a complete experience with startup animations and independent icons.
*   🔒 **Data Localization**: **All your data is stored in a local folder of your choice**. Basic writing and management are possible without an internet connection.

## 🛠️ Technology Stack

*   **Core Framework**: Python 3.9+
*   **User Interface**: Streamlit
*   **Desktop Packaging**: PyWebView (packaging web interfaces into native windows)
*   **Application Packaging**: PyInstaller (generating executable files)
*   **Data Storage**: SQLite (local database)

## 🎯 Quick Start

### For Regular Users

You don't need to install Python or any complex environment.

1.  Go to this project's [**Releases**](https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-/releases) page.
2.  Download the latest version of the compressed package.
3.  After extraction, you'll get a `MortalWrite` folder.
4.  Double-click `MortalWrite.exe` in the folder to start using it.

> **Tip**: You can create a desktop shortcut for `MortalWrite.exe` for easy future startup.

### For Developers

If you want to run from source or develop further, follow these steps:

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-.git
    cd Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-
    ```

2.  **Create `requirements.txt`**
    If you don't have a dependency file yet, you can quickly generate one using `pipreqs` (it will only include libraries imported by the project):
    ```bash
    pip install pipreqs
    pipreqs . --encoding=utf8 --force
    ```

3.  **Install Dependencies**
    It's recommended to install in a virtual environment to avoid conflicts with the global environment.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run from Source**
    ```bash
    streamlit run main.py
    ```
    This will open the application in your browser.

## 📖 Usage Guide

When starting the software for the first time, the program will pop up a folder selection dialog, prompting you to **choose a "workspace"**.

This folder is the home for all your data. Every book you create, every character, all AI configurations, and logs will be safely stored in this folder. Be sure to choose a stable, secure location.

## 🤝 Contributing Code

All forms of contribution are welcome! If you have good ideas, find bugs, or want to optimize code, please:

1.  **Fork** this repository.
2.  Create a new feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4.  Push to your branch (`git push origin feature/AmazingFeature`).
5.  Create a **Pull Request**.

You can also directly submit [**Issues**](https://github.com/hezhengtao/Mortal-AI-Novel-Intelligent-Writing-System-ai-ai-/issues) to report problems or make suggestions.

## 📄 License

This project adopts the MIT license. For details, please see the `LICENSE` file.

## 🙏 Acknowledgements

*   Thanks to the developers of excellent open-source projects like Streamlit, PyWebView, etc.
*   Thanks to all users who provided inspiration and feedback for this project.