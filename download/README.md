# Download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright 操控浏览器，自动搜索并下载学术文献。支持 10 个数据库源。

## 支持的数据库

| # | 源 | 子命令 | 技术方案 | 需VPN |
|---|------|--------|----------|------|
| 1 | **Springer Link** | `sl` | Playwright CDP, fetch→base64 | 部分OA无需 |
| 2 | **CNKI 知网** | `cnki` | Playwright CDP, Browser.setDownloadBehavior | 是 (WebVPN) |
| 3 | **IEEE Xplore** | `ieee` | Playwright CDP, Sci-Hub 回退 | 建议 |
| 4 | **IEEE Xplore (VPN)** | `ieee-vpn` | Playwright CDP + 浏览器内 fetch | **必须** |
| 5 | **EBSCOhost** | `ebsco` | WebSocket CDP, Page.printToPDF | **必须** |
| 6 | **Sci-Hub** | `scihub` | 直接 HTTP (scihub 库), 无需浏览器 | 否 |
| 7 | **Wiley Online Library** | `wiley` | Playwright CDP + pdfdirect 管道 | **必须** |
| 8 | **OpenAlex** | `openalex` | API 搜索 + 浏览器 3 层 PDF 管道 | 否 |
| 9 | **Semantic Scholar** | `semantic` | 浏览器搜索 + OA 筛选 + 期刊优先级排序 | 否 |
| 10 | **Crossref** | `crossref` | 表单搜索 + DOI 解析 + expect_download | 否 |

## 快速启动

```bash
# 启动 Chrome CDP
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="C:\chrome-profile"

# 安装依赖
pip install playwright websocket-client scihub requests openpyxl
```

## 使用

所有子命令均使用 **管道符分隔** 的统一参数格式：

```bash
# Springer Link
python scripts/main.py sl "reinforcement learning | 2024 2026 | relevance | 10"

# CNKI 知网
python scripts/main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20"

# IEEE Xplore
python scripts/main.py ieee "transformer | 2022 2025 | citations | 15"

# IEEE Xplore (VPN)
python scripts/main.py ieee-vpn "refined petroleum scheduling | 2020 2026 | citations | 10"

# EBSCOhost
python scripts/main.py ebsco "FinTech | 2016 2026 | 20 | ./papers | webvpn.upc.edu.cn"

# Sci-Hub
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"

# Wiley Online Library（需 VPN）
python scripts/main.py wiley "fintech prediction | 10"

# OpenAlex（无需 VPN）
python scripts/main.py openalex "fintech prediction | 2025-2026 | Business, Management and Accounting | 5 | D:/md"

# Semantic Scholar（无需 VPN，期刊优先级排序）
python scripts/main.py semantic "fintech prediction | 2025 2026 | 5 | D:/md"

# Crossref（无需 VPN）
python scripts/main.py crossref "fintech prediction | 2025 2026 | 5 | D:/md"
```

## 文件结构

```
download/
├── SKILL.md                  # Skill 定义
├── README.md                 # 本文件
├── requirements.txt          # Python 依赖
├── .gitignore
└── scripts/
    ├── main.py               # 统一 CLI 入口
    ├── utils.py              # 共享工具函数
    ├── chrome.py             # Chrome CDP 启动/检测
    ├── sl.py                 # Springer Link
    ├── cnki.py               # CNKI 知网
    ├── ieee.py               # IEEE Xplore
    ├── ieee_vpn.py           # IEEE Xplore (VPN)
    ├── ebsco.py              # EBSCOhost
    ├── scihub.py             # Sci-Hub
    ├── wiley.py              # Wiley Online Library
    ├── openalex.py           # OpenAlex
    ├── semantic.py           # Semantic Scholar
    └── crossref.py           # Crossref
```

## PDF 下载管道

所有数据库统一采用浏览器内管道下载 PDF，绕过 Windows SSL / 证书问题：

```
浏览器内 fetch(PDF_URL) → ArrayBuffer → base64 → Python 解码 → 写 .pdf 文件
```

部分源（Crossref）使用 Playwright `expect_download` 事件捕获 PDF。

## 失败记录机制

自动记录无法下载的 OA 文章到 Excel 文件，包含：文章名称、期刊、DOI、链接、失败原因。

## License

MIT
