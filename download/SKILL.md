# download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright 操控浏览器，自动搜索并下载学术文献。支持 10 个数据库源：Springer Link、CNKI 知网、IEEE Xplore、IEEE Xplore (VPN)、EBSCOhost、Sci-Hub、**Wiley Online Library**、**OpenAlex**、**Semantic Scholar**、**Crossref**。

## 快速启动 Chrome

在执行任何操作前，确认 Chrome CDP 已就绪：

```bash
# 方式A：一键启动（检测+自动启动）
python scripts/chrome.py

# 方式B：仅检测状态
python scripts/chrome.py check

# 方式C：手动启动
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="C:\chrome-profile"
```

## 快速开始

### 1. 启动 Chrome 调试模式

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="C:\chrome-profile"
```

### 2. 安装依赖

```bash
pip install playwright websocket-client scihub requests
```

### 3. 使用

```bash
# Springer Link — 自动识别 OA，下载 PDF
python scripts/main.py sl "reinforcement learning | 2024 2026 | relevance | 10"

# CNKI 知网 — 筛选SCI/CSSCI后下载
python scripts/main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20"

# IEEE Xplore — 被引量排序，Sci-Hub 回退
python scripts/main.py ieee "transformer | 2022 2025 | citations | 15"

# IEEE Xplore (VPN) — 通过浏览器 VPN 获取 PDF（三种策略：嵌入/Stamp/onclick）
python scripts/main.py ieee-vpn "refined petroleum scheduling | 2020 2026 | citations | 10"

# EBSCOhost — 通过学校 VPN
python scripts/main.py ebsco "FinTech | 2016 2026 | 20 | ./papers | webvpn.upc.edu.cn"

# Sci-Hub — 无需浏览器
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"

# Wiley Online Library — OA + pdfdirect 下载（需学校 VPN）
python scripts/main.py wiley "fintech prediction | 10"

# OpenAlex — API搜索 → 浏览器3层PDF下载 → 失败自动记录
python scripts/main.py openalex "fintech prediction | 2025-2026 | Business, Management and Accounting | 5 | D:/md"

# Semantic Scholar — 浏览器搜索+OA筛选+PDF下载+期刊优先级排序+失败Excel
python scripts/main.py semantic "fintech prediction | 2025 2026 | 5 | D:/md"

# Crossref — 元数据搜索+DOI解析+OA PDF下载+失败Excel
python scripts/main.py crossref "fintech prediction | 2025 2026 | 5 | D:/md"
```

## 结构

```
download/
├── SKILL.md              # Claude Code Skill 定义
├── README.md             # 说明文档
├── requirements.txt      # Python 依赖
├── .gitignore
└── scripts/
    ├── main.py           # 统一 CLI 入口
    ├── utils.py          # 共享工具函数
    ├── chrome.py         # Chrome CDP 启动/检测工具
    ├── sl.py             # Springer Link
    ├── cnki.py           # CNKI 知网
    ├── ieee.py           # IEEE Xplore (直接 HTTP)
    ├── ieee_vpn.py       # IEEE Xplore (浏览器 VPN 管道)
    ├── ebsco.py          # EBSCOhost
    ├── scihub.py         # Sci-Hub
    ├── wiley.py          # Wiley Online Library
    ├── openalex.py       # OpenAlex (API + 浏览器3层PDF下载)
    ├── semantic.py       # Semantic Scholar (浏览器搜索+OA筛选+PDF下载)
    └── crossref.py       # Crossref (元数据搜索+DOI解析+OA PDF下载)
```

## 各源对比

| 源 | 技术方案 | 需浏览器 | 需VPN/机构 | 回退机制 |
|----|----------|----------|------------|----------|
| Springer Link | Playwright CDP (async) | 是 | 部分OA无需 | — |
| CNKI 知网 | Playwright CDP (sync) | 是 | 是 (WebVPN) | CAJ下载 |
| IEEE Xplore | Playwright CDP (async) | 是 | 建议 | Sci-Hub |
| IEEE Xplore (VPN) | Playwright CDP + 浏览器内 fetch | 是 | **必须** (VPN) | 嵌入/Stamp/onclick 三策略 |
| EBSCOhost | WebSocket CDP (自定义) | 是 | 是 (WebVPN) | printToPDF |
| Sci-Hub | 直接 HTTP (scihub库) | 否 | 否 | — |
| Wiley Online Library | Playwright CDP + 浏览器内 fetch | 是 | **必须** (VPN) | pdfdirect 管道 |
| **OpenAlex** | API搜索 + 浏览器3层PDF管道 | 是 | 否 | fetch→download→article(PrintToPDF) |
| **Semantic Scholar** | Playwright CDP 浏览器操控 + fetch | 是 | 否 | — |
| **Crossref** | 表单搜索+DOI解析+expect_download | 是 | 否 | Crossref API 回退 |

## OpenAlex 搜索下载说明

OpenAlex 是一个完全开放（CC0）的学术元数据目录，收录 3.17亿+ 学术著作。本工具通过 OpenAlex REST API 实现无需手动操作浏览器的检索，然后利用 Chrome CDP 自动下载 OA PDF。

### 技术特点
- **OpenAlex API** 直接查询（无需浏览器搜索），支持关键词/年份/领域筛选
- **3层PDF下载管道**（浏览器 fetch → download 事件 → 文章页回退），最大化成功率
- **失败自动记录** CSV + Excel 双格式

### 领域映射
支持的筛选领域：Business Management Accounting, Computer Science, Economics Econometrics Finance, Decision Sciences, Engineering, Social Sciences 等。

### 典型提示词

**完整指令：**
> 操控我的chrome浏览器，帮我用OpenAlex搜索xxx相关论文，筛选OA+近两年+管理学好期刊，下载前5篇到md文件夹，下载不了的记录到csv

**简化指令（已整理为脚本）：**
> /openalex fintech prediction | 2025-2026 | Business, Management and Accounting | 5 | D:/md

### Chrome 启动策略
```bash
# 第一步：确保 Chrome CDP 运行
python scripts/chrome.py

# 第二步：搜索下载
python scripts/main.py openalex "关键词 | 年份范围 | 领域 | 数量 | 下载目录"
```

## Semantic Scholar 说明

Semantic Scholar 是一个 AI 驱动的学术搜索引擎，收录全学科论文元数据。本工具通过 Playwright CDP 操控浏览器实现搜索→筛选→PDF全流程。

### 技术特点
- **浏览器操控**：Playwright CDP 直接操控 Chrome，完全模拟用户操作
- **URL 参数年份筛选**：通过 URL 参数精准筛选发表年份
- **逐篇 OA 检查**：进入每篇文章详情页验证是否为 Open Access
- **管理学期刊优先**：内置 UTD24、ABS 3*+、中文管理顶刊的期刊识别库
- **管理学期刊排序**：自动对管理学期刊文章优先下载
- **浏览器内 fetch 下载**：通过浏览器 fetch API 下载 PDF，绕过 SSL/CORS 问题
- **失败自动记录**：记录到 Excel，含文章名称、期刊、DOI、链接、失败原因

### 期刊优先级
脚本内置管理学期刊识别库，优先下载匹配文章：
- **UTD24**：Management Science, Operations Research, MSOM, POM, JOM, Organization Science, AMJ, AMR, ASQ, SMJ, JIBS, ISR, MISQ 等
- **ABS 3\*+**：Decision Sciences, DSS, EJOR, Omega, TFSC, IJF, JoF, Research Policy, Technovation 等
- **中文顶刊**：中国管理科学、管理世界、系统工程理论与实践、管理科学学报、管理工程学报等

### 典型提示词

**完整指令：**
> 操控我的chrome浏览器，帮我用Semantic Scholar搜索金融科技预测相关论文，筛选2025、2026年，管理学好期刊，OA论文，下载前5篇到md文件夹，下载不了的记录到excel

**简化指令（已整理为脚本）：**
> python scripts/main.py semantic "fintech prediction | 2025 2026 | 5 | D:/md"

### 参数格式

| 位置 | 说明 | 默认值 |
|------|------|--------|
| 1st | 搜索关键词 | "fintech prediction" |
| 2nd | 年份范围 "start end" | "2025 2026" |
| 3rd | 下载数量 | 5 |
| 4th | 下载目录 | D:/md |

## Crossref 说明

Crossref 是全球学术元数据注册中心，收录 1.5亿+ 学术作品的 DOIs。本工具通过 Crossref Metadata Search 进行搜索，再经由 DOI 解析获取 OA PDF 链接，通过浏览器 expect_download 事件下载 PDF。

### 技术特点
- **搜索方式**：自动在 search.crossref.org 填写表单并提交，解析结果文本
- **DOI 解析**：对每篇论文优先导航到 DOI 详情页，提取真实 PDF 下载链接（如 MDPI 的 `/pdf?version=` 链接）
- **API 回退**：DOI 页无法提取 PDF 时，通过 Crossref REST API 查询 link/URL 字段
- **expect_download 下载**：Playwright 的 download 事件捕获 PDF，支持各种下载触发机制
- **管理学期刊优先**：同样内置 UTD24/ABS 3*+/中文顶刊优先级排序
- **失败自动记录**：Excel 格式记录

### 适用场景
- 搜索元数据最全（Crossref 是 DOI 注册中心）
- 部分出版社（MDPI、Bonview、Sciendo 等）的 OA PDF 可以直接下载
- **不适用于**需要通过复杂认证的出版商（World Scientific、ACM、SSRN 等）

### 典型提示词

**完整指令：**
> 操控我的chrome浏览器，在Crossref搜索金融科技预测相关论文，筛选2025/2026年，OA论文，下载前5篇到md文件夹，下载不了的记录到excel

**简化指令（已整理为脚本）：**
> python scripts/main.py crossref "fintech prediction | 2025 2026 | 5 | D:/md"

### 参数格式

| 位置 | 说明 | 默认值 |
|------|------|--------|
| 1st | 搜索关键词 | "fintech prediction" |
| 2nd | 年份范围 "start end" | "2025 2026" |
| 3rd | 下载数量 | 5 |
| 4th | 下载目录 | D:/md |

## Wiley Online Library 说明

Wiley 的特殊性：
- PDF 下载链接须使用 **`/doi/pdfdirect/`** 路径（而非 `/doi/pdf/`），后者在 VPN 下只返回占位 HTML
- 浏览器内 `fetch()` 走 VPN 代理通道，可直接获取 `/doi/pdfdirect/` 的真实 PDF 内容
- 搜索时通过侧栏 radio button 触发筛选（Journals + 时间 + Open Access）
- 时间筛选选项：Last 3 Months / Last 6 Months / Last 12 Months / Last 2 Years

PDF 获取流程：
1. 用户已通过学校 VPN 登录 Wiley
2. 从文章页提取 DOI
3. 构造 `https://onlinelibrary-wiley-com-443.webvpn.upc.edu.cn/doi/pdfdirect/{DOI}` 链接
4. 浏览器内 `fetch()` 获取 PDF → base64 → Python 解码保存

## 典型提示词（Prompt Templates）

以下为经过验证的提示词模板，每次调用时可参考使用。

### Wiley 检索下载

**完整指令：**
> 操控我的chrome浏览器，搜索xxx相关论文，筛选过去一年发表，OA，管理学比较好的期刊，并为我下载前五篇到md文件夹下。如果有文章是OA但你无法下载，那么你需要为我返回一个记录的excel，包括文章题目、期刊、链接等内容

**简化指令（已登录VPN+Wiley）：**
> /wiley 帮我搜 fintech prediction，OA+近一年，下载5篇

**增强指令（带失败记录）：**
> 帮我下载xxx，要下载OA的，下载不了的帮我记录到一个csv里，包括文章题目、期刊、DOI、链接和原因

### Crossref 检索下载

**完整指令：**
> 操控chrome浏览器，在Crossref搜索金融科技预测相关论文，筛选2025和2026年发表，OA论文，下载前5篇到md文件夹，下载不了的记录到excel

**简化指令（已整理为脚本）：**
> /crossref 帮我搜 fintech prediction，2025 2026，下载5篇

**CLI 指令：**
```bash
python scripts/main.py crossref "关键词 | 年份范围 | 数量 | 下载目录"
```

### SpringerLink 检索下载

**完整指令：**
> /SL 操控我的chrome浏览器，打开SpringerLink网站并为我搜索xxx，选择last 24 months，下载标有"Open access"或"Full access"的前十篇文献下载到md文件夹里的SL文件夹内

### CNKI 知网检索下载

**完整指令：**
> 操控chrome浏览器，知网搜索xxx，筛选：学术期刊+SCI+北大核心+近5年+高被引，下载前20篇

**带VPN的流程（分步）：**
> 1. 先为我操控到vpn页面
> 2. [用户手动登录] → "已登录"
> 3. 继续搜索和下载

### Semantic Scholar 检索下载

**完整指令：**
> 操控我的chrome浏览器，帮我用Semantic Scholar搜索xxx相关论文，筛选近两年发表，OA论文，管理学好期刊，下载前5篇到md文件夹，下载不了的记录到excel

**简化指令（已整理为脚本）：**
> /semantic 帮我搜 fintech prediction，2025 2026，下载5篇，期刊优选管理学期刊

**CLI 指令：**
```bash
python scripts/main.py semantic "关键词 | 年份范围 | 数量 | 下载目录"
```

### IEEE Xplore 检索下载

**完整指令：**
> 在IEEE Xplore上搜索xxx，筛选近3年+OA，下载前10篇PDF

### EBSCOhost 检索下载

**完整指令：**
> 帮我通过VPN在EBSCOhost上搜索xxx，peer-reviewed+全文+近5年，下载前10篇

## 通用交互流程

所有数据库源都遵循类似的人机协作模式：

1. **你（Claude）**: 启动 Chrome CDP → 导航到目标网站 → 执行搜索 → 筛选条件 → 识别可下载文献

2. **用户（仅在涉及VPN时）**: 手动登录 VPN
   - Claude 导航到 VPN 登录页 → 用户输入凭证 → 用户说"已登录" → Claude 继续

3. **你（Claude）**: 逐篇处理每篇 OA 文章：
   - 进入文章详情页 → 验证是否为真实 OA（搜索结果标记有时不准确）
   - 若为真实 OA → 浏览器 fetch → base64 → Python 解码保存 PDF
   - 若非 OA 或 PDF 无法获取 → **记录到 CSV 文件**，包含：文章标题、期刊、DOI、链接、失败原因
   - 最终输出：成功下载的 PDF 列表 + `failed_articles.csv` 失败记录

### PDF 下载管道（统一方案）

所有数据库的 PDF 下载统一采用：
```
浏览器内 fetch(PDF_URL) → ArrayBuffer → base64 → 传回 Python → base64.b64decode → 写 .pdf 文件
```

此方案的优势：
- 绕过 Windows SChannel SSL 兼容性问题
- VPN 环境下自动走浏览器代理通道
- 不受 requests/urllib 的证书验证限制

### 失败记录机制（CSV 输出）

当文章标记为 OA 但实际无法下载时，必须创建 CSV 记录文件。输出默认路径为下载目录下的 `failed_articles.csv`。

**CSV 字段：**
| 字段 | 示例 |
|------|------|
| title | The Impact of FinTech on Environmental Sustainability |
| journal | Business Strategy and the Environment |
| doi | 10.1002/bse.70546 |
| link | https://.../doi/10.1002/bse.70546 |
| reason | 搜索结果标记为OA但文章页面无Open Access标识 |

**常见失败原因：**
- `搜索结果标记为OA但文章页面无Open Access标识` — Wiley 搜索筛选与文章页实际状态不一致
- `OA标识但PDF获取失败: HTML / ERR:403 / ERR:404` — 有 OA 标记但 pdfdirect 端点返回非 PDF 内容
- `处理异常: ...` — 网络或脚本执行异常

**输出要求：**
- 编码使用 `utf-8-sig`（Excel 可直接打开）
- 文件必须放到下载目录（`DOWNLOAD_DIR`）下
- 同时在终端打印每篇失败文章的简要摘要
