# download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright / WebSocket 操控浏览器，自动搜索并下载学术文献。支持 7 种方式覆盖 6 个数据库源：Springer Link (async/sync)、CNKI 知网、IEEE Xplore、EBSCOhost、Web of Science、Sci-Hub。

## 需要 VPN 的源（CNKI / EBSCO / WoS）工作流程

这些数据库需要通过学校 WebVPN 访问，**必须用户手动登录**，流程如下：

1. Claude 打开 Chrome 并导航到 VPN 登录页面 / 数据库页面
2. **停止操作**，通知用户去浏览器中登录 VPN
3. 用户登录完成后，告诉 Claude "已登录 + 筛选条件"
4. Claude 收到确认后再执行搜索 → 筛选 → 下载

**关键：** 用户登录期间 Claude 不会操控浏览器任何页面，避免干扰登录会话。

## 不需要 VPN 的源（Springer / IEEE / Sci-Hub）

全自动执行，无需用户干预。

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

# Springer Link — 期刊限定 (同步版)
python scripts/main.py springer "mass spectrometry | 40543 | 2024 2026 | 15"

# CNKI 知网 — 筛选SCI/CSSCI后下载
python scripts/main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20"

# IEEE Xplore — 被引量排序，Sci-Hub 回退
python scripts/main.py ieee "transformer | 2022 2025 | citations | 15"

# EBSCOhost — 通过学校 VPN
python scripts/main.py ebsco "FinTech | 2016 2026 | 20 | ./papers | webvpn.upc.edu.cn"

# Web of Science — 期刊/OA筛选，逐篇获取Free Full Text
python scripts/main.py wos "fintech | 2022 2025 | 10"

# Sci-Hub — 无需浏览器
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"
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
    ├── sl.py             # Springer Link (async, OA识别)
    ├── springer.py       # Springer Link (sync, 期刊限定)
    ├── cnki.py           # CNKI 知网
    ├── ieee.py           # IEEE Xplore
    ├── ebsco.py          # EBSCOhost
    ├── wos.py            # Web of Science
    └── scihub.py         # Sci-Hub
```

## 各源对比

| 源 | 技术方案 | 需浏览器 | 需VPN/机构 | 回退机制 |
|----|----------|----------|------------|----------|
| Springer Link | Playwright CDP (async) | 是 | 部分OA无需 | — |
| Springer Link (sync) | Playwright CDP (sync) | 是 | 部分OA无需 | printToPDF回退 |
| CNKI 知网 | Playwright CDP (sync) | 是 | 是 (WebVPN) | CAJ下载 |
| IEEE Xplore | Playwright CDP (async) | 是 | 建议 | Sci-Hub |
| EBSCOhost | WebSocket CDP (自定义) | 是 | 是 (WebVPN) | printToPDF |
| Web of Science | Playwright CDP (async) | 是 | 建议 | Sci-Hub |
| Sci-Hub | 直接 HTTP (scihub库) | 否 | 否 | — |
