---
name: download
description: 学术文献批量检索下载工具集 — 支持 14 个数据库源（Springer/CNKI/IEEE/EBSCO/WoS/Wiley/Sci-Hub/OpenAlex/Crossref/Semantic Scholar/ScienceDirect），统一 CLI 管道入口
---

# download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright 操控浏览器，自动搜索并下载学术文献。支持以下数据库源：
Springer Link、CNKI 知网、IEEE Xplore、EBSCOhost、Web of Science、Wiley、Sci-Hub、OpenAlex、Crossref、Semantic Scholar、ScienceDirect。

## 快速开始（新用户）

### 1. 配置环境

```bash
# 复制 VPN 配置模板并编辑
cp .env.example .env
# 编辑 .env: VPN_DOMAIN=你的学校WebVPN域名

# 安装依赖
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动 Chrome 调试模式

```bash
python scripts/chrome.py
```

### 3. 使用

```bash
# 不需要 VPN
python scripts/main.py openalex "machine learning | 2024 2026 | Computer Science | 5"

# 需要 VPN（需先登录）
python scripts/main.py sd "fintech prediction | 2025 2026 | 5"
```

## 需要 VPN 的源（CNKI / EBSCO / WoS / ScienceDirect）工作流程

这些数据库需要通过学校 WebVPN 访问，**必须用户手动登录**：

1. Claude 打开 Chrome 并导航到 VPN 登录页面
2. **停止操作**，通知用户去浏览器中登录 VPN
3. 用户登录完成后，告诉 Claude "已登录 + 筛选条件"
4. Claude 收到确认后再继续搜索 → 筛选 → 下载

**关键：** 用户登录期间 Claude 不会操控浏览器任何页面。

## 不需要 VPN 的源（Springer / IEEE / Sci-Hub / OpenAlex / Crossref / Semantic Scholar）

全自动执行，无需用户干预。

## 使用示例

```bash
# Springer Link
python scripts/main.py sl "reinforcement learning | 2024 2026 | relevance | 10"

# CNKI 知网
python scripts/main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20"

# IEEE Xplore
python scripts/main.py ieee "transformer | 2022 2025 | citations | 15"

# EBSCOhost（VPN）
python scripts/main.py ebsco "FinTech | 2016 2026 | 20 | ./papers | webvpn.upc.edu.cn"

# Web of Science（VPN）
python scripts/main.py wos "fintech | 2022 2025 | 10"

# Wiley（VPN）
python scripts/main.py wiley "machine learning | 5"

# ScienceDirect（VPN）
python scripts/main.py sd "fintech prediction | 2025 2026 | 5"

# OpenAlex
python scripts/main.py openalex "large language models | 2024 2026 | Computer Science | 5"

# Crossref
python scripts/main.py crossref "large language models | 2024 2026 | 5 | ./papers"

# Semantic Scholar
python scripts/main.py semantic "large language models | 2024 2026 | 5 | ./papers"

# Sci-Hub
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"
```

## 结构

```
download/
├── SKILL.md              # Skill 定义（含 YAML frontmatter）
├── README.md             # 说明文档
├── requirements.txt      # Python 依赖
├── .env.example          # VPN 配置模板
├── .gitignore
└── scripts/
    ├── main.py           # 统一 CLI 入口（17 个别名 → 14 个 source）
    ├── utils.py          # 共享工具（FailedRecord + validate_pdf + .env 加载）
    ├── chrome.py         # Chrome CDP 启动/检测
    ├── sl.py             # Springer Link
    ├── cnki.py           # CNKI 知网
    ├── ieee.py           # IEEE Xplore
    ├── ebsco.py          # EBSCOhost
    ├── wos.py            # Web of Science
    ├── wiley.py          # Wiley Online Library
    ├── scihub_dl.py      # Sci-Hub（直连 + Playwright，无 PyPI 依赖）
    ├── sciencedirect.py  # ScienceDirect（OA + printToPDF 回退）
    ├── openalex.py       # OpenAlex（API 搜索）
    ├── crossref.py       # Crossref（API 搜索）
    └── semantic.py       # Semantic Scholar（浏览器搜索）
```

## 各源对比

| 源 | 技术方案 | 需浏览器 | 需VPN/机构 | 回退机制 |
|----|----------|----------|------------|----------|
| Springer Link | Playwright CDP (async) | 是 | 部分OA无需 | — |
| CNKI 知网 | Playwright CDP (sync) | 是 | **必须** (VPN) | CAJ下载 |
| IEEE Xplore | Playwright CDP (async) | 是 | 建议 | Sci-Hub |
| EBSCOhost | WebSocket CDP | 是 | **必须** (VPN) | printToPDF |
| Web of Science | Playwright CDP (async) | 是 | 建议 | Sci-Hub |
| Wiley | Playwright CDP (async) | 是 | 建议 | — |
| ScienceDirect | Playwright CDP + printToPDF | 是 | **必须** (VPN) | printToPDF |
| Sci-Hub | 直连 HTTP + Playwright CDP | 可选 | 否 | — |
| OpenAlex | REST API (requests) | 否 | 否 | — |
| Crossref | REST API (requests) | 否 | 否 | — |
| Semantic Scholar | Playwright CDP (async) | 是 | 否 | — |
