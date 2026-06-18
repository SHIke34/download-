"""download — 学术文献批量检索下载工具集

共享工具函数：Chrome连接、参数解析、文件操作、控制台输出
"""

import sys
import os
import re
import json
import time
import urllib.parse


# ── 控制台输出 ────────────────────────────────────────────────────────────
def sp(*args, sep=" ", end="\n", flush=True):
    """Safe print — 处理 Windows GBK 编码问题"""
    text = sep.join(str(a) for a in args)
    try:
        print(text, end=end, flush=flush)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode(), end=end, flush=flush)


def log(tag, msg):
    """带标签的日志输出，如 [ieee] xxx"""
    sp(f"[{tag}] {msg}")


# ── 参数解析 ──────────────────────────────────────────────────────────────
def parse_pipe_args(raw_args: str, defaults: dict) -> dict:
    """解析管道符分隔的参数，合并默认值

    格式: keyword | startYear endYear | [extra...]
    返回: {keyword, start_year, end_year, ...}
    """
    params = dict(defaults)
    if not raw_args or not raw_args.strip():
        return params

    parts = [p.strip() for p in raw_args.split("|")]

    if len(parts) >= 1 and parts[0]:
        params["keyword"] = parts[0]
    if len(parts) >= 2 and parts[1]:
        years = parts[1].split()
        if len(years) >= 1 and years[0].isdigit():
            params["start_year"] = int(years[0])
        if len(years) >= 2 and years[1].isdigit():
            params["end_year"] = int(years[1])
    if len(parts) >= 3 and parts[2]:
        params["extra"] = parts[2]
    if len(parts) >= 4 and parts[3]:
        try:
            params["count"] = int(parts[3])
        except ValueError:
            params["extra2"] = parts[3]
    if len(parts) >= 5 and parts[4]:
        params["output_dir"] = parts[4]
    if len(parts) >= 6 and parts[5]:
        params["vpn_domain"] = parts[5]

    return params


def safe_filename(text: str, max_len: int = 80) -> str:
    """将任意文本转为安全的文件名"""
    name = re.sub(r'[\\/*?:"<>|]', "_", text)
    return name.strip(". ")[:max_len] or "paper"


def extract_year(date_str: str) -> int:
    """从日期字符串中提取年份"""
    m = re.search(r"(20\d{2})", date_str or "")
    return int(m.group(1)) if m else 0


def save_json(data, filepath):
    """保存 JSON 文件"""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_list(articles, filepath, header_lines=None):
    """保存文献列表为文本文件"""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        if header_lines:
            for line in header_lines:
                f.write(line + "\n")
            f.write("=" * 60 + "\n\n")
        for i, art in enumerate(articles):
            f.write(f"{i+1}. {art.get('title', '')}\n")
            for k, v in art.items():
                if k != "title":
                    f.write(f"   {k}: {v}\n")
            f.write("\n")
    return filepath


def ensure_output_dir(path):
    """确保输出目录存在，返回路径"""
    if not path:
        return None
    os.makedirs(path, exist_ok=True)
    return path


# ── Chrome CDP 连接 (Playwright) ──────────────────────────────────────────

def connect_playwright(port=9222):
    """连接到已打开的 Chrome，返回 (playwright, browser, context, page)

    使用 Playwright sync_api，适用于 cnki, springer 等同步操作场景
    """
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
    context = browser.contexts[0]
    page = context.new_page()
    return p, browser, context, page


def connect_playwright_async(port=9222):
    """异步版本 connect_over_cdp

    适用于 ieee, sl 等异步操作场景
    """
    from playwright.async_api import async_playwright

    async def _connect():
        p = await async_playwright().start()
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        ctx = browser.contexts[0]
        pages = ctx.pages
        page = pages[0] if pages else await ctx.new_page()
        # close extra pages
        for pg in pages[1:]:
            await pg.close()
        return p, browser, page
    return _connect
