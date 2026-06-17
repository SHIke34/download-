# Download — 学术文献批量检索下载工具集

通过 Chrome CDP / Playwright 操控浏览器，自动搜索并下载学术文献。支持多个数据库源。

## 支持的数据库

| 源 | 子命令 | 说明 | 技术方案 |
|----|--------|------|----------|
| **Springer Link** | `sl` | 搜索 + OA 识别 + PDF 下载 | Playwright CDP (async), fetch→base64 |
| **Springer Link** | `springer` | 搜索 + 期刊限定 + PDF 下载 (同步版) | Playwright CDP (sync), expect_download |
| **CNKI 知网** | `cnki` | 搜索 + 年份/来源筛选 + PDF/CAJ 下载 | Playwright CDP (sync), Browser.setDownloadBehavior |
| **IEEE Xplore** | `ieee` | 搜索 + 被引排序 + PDF 下载 (含 Sci-Hub 回退) | Playwright CDP (async), stamp endpoint + Sci-Hub |
| **EBSCOhost** | `ebsco` | VPN 搜索 + 同行评审筛选 + PDF 下载 | WebSocket CDP (自定义), Page.printToPDF |
| **Web of Science** | `wos` | 高级检索 + 期刊/OA 筛选 + PDF 下载 | Playwright CDP (async), fetch→base64 + Sci-Hub |
| **Sci-Hub** | `scihub` | DOI/标题/关键词搜索 + PDF 下载 | 直接 HTTP (scihub 库), 无需浏览器 |

## 统一参数格式

所有子命令均使用 **管道符分隔** 的参数格式：

```
python scripts/main.py <源> "<关键词> | <起始年 结束年> | <排序> | <数量> | <输出目录>"
```

## 前置条件

1. **Chrome 调试模式启动**（sl, cnki, ieee, ebsco, wos 需要，scihub 不需要）：
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="C:\chrome-profile"
   ```

2. **安装依赖**：
   ```
   pip install -r requirements.txt
   ```

## 使用

```bash
# Springer Link (async)
python scripts/main.py sl "reinforcement learning | 2024 2026 | relevance | 10 | D:/papers"

# Springer Link (sync, 期刊限定)
python scripts/main.py springer "mass spectrometry | 40543 | 2024 2026 | 15 | D:/papers"

# CNKI 知网
python scripts/main.py cnki "深度学习 | 2024 2026 | CSSCI,SCI | 被引 | 20 | D:/papers"

# IEEE Xplore
python scripts/main.py ieee "reinforcement learning | 2022 2025 | citations | 10 | D:/papers"

# EBSCOhost
python scripts/main.py ebsco "FinTech | 2016 2026 | 20 | D:/papers | webvpn.upc.edu.cn"

# Web of Science
python scripts/main.py wos "fintech | 2022 2025 | 10 | D:/papers"

# Sci-Hub
python scripts/main.py scihub "10.1109/ACCESS.2023.3312345"
python scripts/main.py scihub --doi "10.1109/ACCESS.2023.3312345"
python scripts/main.py scihub --title "deep learning review"
python scripts/main.py scihub --keyword "machine learning" --results 10
```

## 文件结构

```
download/
├── SKILL.md                  # Skill 定义
├── README.md                 # 本文件
├── requirements.txt          # Python 依赖
├── .gitignore
└── scripts/
    ├── main.py               # 统一 CLI 启动入口
    ├── utils.py              # 共享工具函数
    ├── sl.py                 # Springer Link (async, OA识别)
    ├── springer.py           # Springer Link (sync, 期刊限定)
    ├── cnki.py               # CNKI 知网下载
    ├── ieee.py               # IEEE Xplore 下载
    ├── ebsco.py              # EBSCOhost 下载
    ├── wos.py                # Web of Science 下载
    └── scihub.py             # Sci-Hub 下载
```


## License

MIT
