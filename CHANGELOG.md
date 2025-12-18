# 🛠️ Mortal Write 系统更新日志

### ✨ 新增功能 (New Features)

#### 1. 📖 书籍深度导入与 AI 识别系统 (`books.py`)

* **三级回退识别策略**：新增了智能识别逻辑，导入书籍时按以下优先级执行：
1. **名著检索**：优先识别知识库中已知的网文名著（如《斗破苍穹》），直接调用已有设定。
2. **采样深度分析**：若非名著，截取前 25,000 字进行文本特征分析。
3. **分步补全**：针对超长文本进行分段处理。


* **网文专属角色画像**：AI 现在会强制提取网文核心设定字段，写入数据库：
* **出身**（穿越者/重生者/家族弃子等）
* **金手指/核心能力**（系统/伴生宝物/老爷爷）
* **实力等级**（如：斗之力三段、炼气期）
* **恩仇录**（详细记录债务关系与血仇对象，作为剧情钩子）
* **代价与限制**（能力的副作用）



#### 2. 🛡️ 全链路严格审计系统 (`settings.py`, `utils.py`)

* **配置变更审计**：在 `settings.py` 中增加了 Diff 比对逻辑。修改配置时，系统会对比“旧值”与“新值”，并生成详细的审计日志（例如：`模型: GPT-4 -> DeepSeek`，`API Key: [密钥已更新]`）。
* **统一日志接口**：重写了 `utils.py` 中的 `log_operation`，现在所有操作（写作、导入、设置）都会**强制实时写入**磁盘上的 `system_log.csv`，不再依赖不稳定的内存缓存，确保日志绝对不丢失。

---

### ⚡ 优化与改进 (Optimizations)

#### 1. 🧶 复杂网文结构解析 (`books.py`)

* **正则引擎重构**：针对《斗破苍穹》等经典网文的松散排版进行了针对性优化。
* 现在完美支持 `正文 第一章`、`卷一 第10章`、`Chapter 1` 以及无卷名直接分章的结构。
* 解决了之前“只识别到 3 章”或“章节遗漏”的严重 Bug。


* **编码自动容错**：在 `extract_text_from_file` 中增加了对 `GB18030`, `GBK`, `UTF-8` 的自动尝试，彻底解决中文 TXT 乱码问题。

#### 2. 📊 数据看板精准化 (`dashboard.py`)

* **服务商名称修正**：修复了使用兼容 API（如 OneAPI）时，DeepSeek 等模型被错误显示为 "OpenAI" 的问题。现在系统会根据模型名（如 `deepseek-v3`）强制修正厂商显示。
* **日志关联增强**：在 `books.py` 和 `writer.py` 的计费埋点中，增加了**自动抓取书名**的逻辑。现在的 Token 消耗记录会自动关联当前正在操作的书籍，解决了看板中“按书筛选”无数据的问题。

---

### 🐛 问题修复 (Bug Fixes)

* **修复日志不显示问题**：解决了 `settings.py` 底部“全局系统日志”一直空白的问题（原因是旧版日志函数未落盘）。
* **修复时间时区错误**：全系统（包括数据库 `created_at/updated_at` 和日志时间戳）统一强制使用 **北京时间 (UTC+8)**，修复了云服务器上时间显示偏差的问题。
* **修复 AI 导入流程中断**：修复了在 AI 分析长文本时可能因 Token 超限导致整个导入流程崩溃的 Bug，增加了异常捕获与回退机制。

---

### 📝 数据库变更 (Schema Changes)

* **Characters 表**：逻辑上兼容了新增的深度字段（`origin`, `profession`, `cheat_ability`, `debts_and_feuds` 等）。如果数据库结构未更新，系统会自动将这些信息合并存入 `desc` 字段，保证数据不丢失。





🛠️ Mortal Write System Update Log
✨ New Features
1. 📖 Deep Book Import & AI Recognition System (books.py)
Three-Tier Fallback Recognition Strategy: Added intelligent identification logic. When importing books, the system executes the following priority order:

Classic Masterpiece Retrieval: Prioritizes identifying known web novel masterpieces in the knowledge base (e.g., Battle Through the Heavens) and directly applies existing settings.

Sampling Deep Analysis: If it is not a known masterpiece, the system captures the first 25,000 words for text feature analysis.

Step-by-Step Completion: Handles extra-long texts by processing them in segments.

Web Novel Specific Character Profiling: The AI now strictly extracts core web novel setting fields and writes them to the database:

Origin (Transmigrator / Reincarnator / Family Outcast, etc.)

Golden Finger / Core Ability (System / Companion Artifact / "Grandpa in the Ring")

Power Level (e.g., Dou Qi Stage 3, Qi Refining Stage)

Record of Grudges & Favors (Detailed records of debt relationships and blood feuds to serve as plot hooks)

Costs & Limitations (Side effects of abilities)

2. 🛡️ Full-Link Strict Audit System (settings.py, utils.py)
Configuration Change Audit: Added Diff comparison logic in settings.py. When modifying configurations, the system compares "Old Value" vs. "New Value" and generates a detailed audit log (e.g., Model: GPT-4 -> DeepSeek, API Key: [Key Updated]).

Unified Log Interface: Rewrote log_operation in utils.py. All operations (Writing, Importing, Settings) are now mandatorily written to disk (system_log.csv) in real-time, no longer relying on unstable memory caching, ensuring zero log loss.

⚡ Optimizations
1. 🧶 Complex Web Novel Structure Parsing (books.py)
Regex Engine Refactoring: Optimized specifically for the loose formatting of classic web novels like Battle Through the Heavens.

Now perfectly supports Main Text Chapter 1, Vol 1 Chapter 10, Chapter 1, and structureless chapter divisions.

Resolved severe bugs where the system "only identified 3 chapters" or "skipped chapters."

Automatic Encoding Fault Tolerance: Added automatic attempts for GB18030, GBK, and UTF-8 in extract_text_from_file, completely solving the issue of garbled text in Chinese TXT files.

2. 📊 Precision Dashboard Data (dashboard.py)
Provider Name Correction: Fixed the issue where models like DeepSeek were incorrectly displayed as "OpenAI" when using compatible APIs (e.g., OneAPI). The system now forces the vendor display based on the model name (e.g., deepseek-v3).

Enhanced Log Association: Added automatic book title scraping logic to the billing tracking in books.py and writer.py. Token consumption records now automatically associate with the book currently being operated on, fixing the issue where "Filter by Book" showed no data on the dashboard.

🐛 Bug Fixes
Fixed Log Display Issue: Resolved the issue where the "Global System Log" at the bottom of settings.py remained blank (caused by the old log function not persisting to disk).

Fixed Timezone Errors: Unified the entire system (including Database created_at/updated_at and log timestamps) to force the use of Beijing Time (UTC+8), fixing time deviation issues on cloud servers.

Fixed AI Import Process Interruption: Fixed a bug where the entire import process would crash due to Token limits when the AI analyzed long texts; added exception capturing and fallback mechanisms.

📝 Database Changes (Schema Changes)
Characters Table: Logically compatible with the new deep fields (origin, profession, cheat_ability, debts_and_feuds, etc.). If the database structure has not been updated, the system will automatically merge this information into the desc field to ensure no data is lost.