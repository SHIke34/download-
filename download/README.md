# Download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright 操控浏览器，自动搜索并下载学术文献。支持 14 个数据库源。

## 支持的数据库

| 源 | 子命令 | 说明 | 技术方案 |
|----|--------|------|----------|
| **Springer Link** | `sl` | 搜索 + OA 识别 + PDF 下载 | Playwright CDP (async), fetch→base64 |
| **CNKI 知网** | `cnki` | 搜索 + 年份/来源筛选 + PDF/CAJ 下载 | Playwright CDP (sync) |
| **IEEE Xplore** | `ieee` | 搜索 + 被引排序 + PDF 下载 (含 Sci-Hub 回退) | Playwright CDP (async) |
| **EBSCOhost** | `ebsco` | VPN 搜索 + 同行评审筛选 + PDF 下载 | WebSocket CDP |
| **Web of Science** | `wos` | 高级检索 + 期刊/OA 筛选 + PDF 下载 | Playwright CDP (async) |
| **Wiley** | `wiley` | 搜索 + OA PDF 下载 | Playwright CDP (async) |
| **ScienceDirect** | `sd` | OA 搜索 + PDF 下载（推荐 VPN） | Playwright CDP (async) + printToPDF |
| **Sci-Hub** | `scihub` | DOI/标题/关键词搜索 + PDF 下载 | 直连 HTTP + Playwright CDP |
| **OpenAlex** | `openalex` / `oa` | API 搜索 + OA PDF 下载 | REST API (requests) |
| **Crossref** | `crossref` / `cr` | 元数据搜索 + OA PDF 下载 | REST API (requests) |
| **Semantic Scholar** | `semantic` / `ss` | 浏览器搜索 + OA 筛选 + PDF 下载 | Playwright CDP |

## 快速开始（新用户）

### 1. 配置 VPN（需要学校 VPN 的源）

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，将 VPN 域名改为你学校的 WebVPN 域名
# VPN_DOMAIN=webvpn.your-university.edu.cn
```

### 2. 启动 Chrome 调试模式

```bash
# 方式 A：自动检测并启动
python scripts/chrome.py

# 方式 B：手动启动
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --remote-allow-origins=* ^
  --user-data-dir="C:\chrome-profile"
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
# 安装 Playwright 浏览器
playwright install chromium
```

### 4. 使用

```bash
# 不依赖 VPN 的源（开箱即用）
python scripts/main.py openalex "machine learning | 2024 2026 | Computer Science | 5"
python scripts/main.py crossref "deep learning | 2024 2026 | 5 | ./papers"
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"

# 依赖 VPN 的源（需先登录 VPN）
python scripts/main.py sd "fintech prediction | 2025 2026 | 5 | ./SD_Results"
python scripts/main.py sl "reinforcement learning | 2024 2026 | relevance | 10"
```

## 参数格式

所有子命令使用 **管道符分隔** 的统一参数格式：

```bash
python scripts/main.py <源> "<关键词> | <起始年 结束年> | <数量> | <输出目录>"
```

不同源的位置可能有微调（如 ebsco 末尾多一个 vpn_domain），详见各源 docstring。

## VPN 工作流程

CNKI / EBSCO / WoS / ScienceDirect 需要通过学校 WebVPN 访问：

1. 运行脚本，Claude 导航到 VPN 登录页
2. **用户手动登录**
3. 用户确认"已登录"后，Claude 继续搜索下载

## 文件结构

```
download/
├── SKILL.md                  # Skill 定义（Claude Code 集成）
├── README.md                 # 本文件
├── requirements.txt          # Python 依赖
├── .env.example              # 环境配置模板（复制为 .env 后编辑）
├── .gitignore
└── scripts/
    ├── main.py               # 统一 CLI 入口
    ├── utils.py              # 共享工具函数
    ├── chrome.py             # Chrome CDP 启动/检测工具
    ├── sl.py                 # Springer Link
    ├── cnki.py               # CNKI 知网
    ├── ieee.py               # IEEE Xplore
    ├── ebsco.py              # EBSCOhost
    ├── wos.py                # Web of Science
    ├── wiley.py              # Wiley Online Library
    ├── sciencedirect.py      # ScienceDirect
    ├── scihub_dl.py          # Sci-Hub
    ├── openalex.py           # OpenAlex
    ├── crossref.py           # Crossref
    └── semantic.py           # Semantic Scholar
```

## License

MIT
