#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenAlex 学术搜索 + OA筛选 + PDF下载工具

功能：
  1. 通过 OpenAlex Web UI 搜索、筛选（OA/年份/领域）
  2. 3 层 PDF 下载管道：browser fetch → download event → article page fallback
  3. 失败自动记录 CSV/Excel

用法：
  python openalex.py "<关键词> | <年份范围> | <领域> | <数量> | <下载目录>"

示例：
  python openalex.py "fintech prediction | 2025-2026 | Business, Management and Accounting | 5 | D:/md"
  python openalex.py "machine learning | 2024-2026 | Computer Science | 10 | ./papers"
"""

import asyncio
import base64
import csv
import os
import sys
import re
import json

DOWNLOAD_DIR = "D:/md"


# ============================================================
#  第1层：浏览器 fetch（适用于同源或CORS允许的PDF）
# ============================================================
async def try_fetch(page, url, timeout=15):
    """在页面上下文中 fetch PDF → base64"""
    try:
        result = await page.evaluate("""
        async (url) => {
            try {
                var resp = await fetch(url, {credentials: 'include'});
                if (!resp.ok) return {error: 'HTTP ' + resp.status};
                var ct = resp.headers.get('content-type') || '';
                var blob = await resp.arrayBuffer();
                var bytes = new Uint8Array(blob);
                var binary = '';
                for (var i = 0; i < bytes.length; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return {data: btoa(binary), size: bytes.length, type: ct};
            } catch(e) {
                return {error: e.toString()};
            }
        }
        """, url)
        if result and not result.get('error'):
            data = base64.b64decode(result['data'])
            if len(data) > 5000:
                return data
    except Exception:
        pass
    return None


# ============================================================
#  第2层：download 事件捕获（适用于自动触发下载的网站）
# ============================================================
async def try_download_event(page, browser, url, timeout=20):
    """导航到 URL 并捕获 download 事件"""
    dl = None
    def on_download(dl_obj):
        nonlocal dl
        dl = dl_obj
    page.on("download", on_download)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    except Exception:
        pass

    await page.wait_for_timeout(3000)

    if dl:
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "openalex_tmp.pdf")
        await dl.save_as(tmp)
        with open(tmp, 'rb') as f:
            data = f.read()
        os.remove(tmp)
        if len(data) > 5000:
            return data
    return None


# ============================================================
#  第3层：导航到文章页 → 找PDF链接 → 下载
# ============================================================
async def try_article_page(page, browser, article_url, title=""):
    """进入文章页，寻找并下载PDF"""
    try:
        await page.goto(article_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)
    except Exception:
        return None

    # 1) 找 PDF 链接
    pdf_links = await page.evaluate("""
    () => {
        var links = document.querySelectorAll('a');
        var pdfs = [];
        for (var i=0; i<links.length; i++) {
            var href = links[i].href || '';
            var text = links[i].innerText.toLowerCase().trim();
            if (href && (href.includes('.pdf') || href.includes('/pdf/') || text.includes('pdf') || text.includes('download') || text.includes('full text'))) {
                pdfs.push(href);
            }
        }
        return pdfs.slice(0, 5);
    }
    """)

    for link in pdf_links:
        # 尝试fetch
        data = await try_fetch(page, link)
        if data:
            return data

        # 尝试download事件
        dl = None
        def on_dl(d):
            nonlocal dl
            dl = d
        page.on("download", on_dl)
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)
        if dl:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), "openalex_tmp.pdf")
            await dl.save_as(tmp)
            with open(tmp, 'rb') as f:
                data = f.read()
            os.remove(tmp)
            if len(data) > 5000:
                return data

    return None


# ============================================================
#  下载入口：3层管道
# ============================================================
async def download_pdf(page, browser, pdf_url, article_url, title, filepath):
    """3 层 PDF 下载管道"""
    if os.path.exists(filepath) and os.path.getsize(filepath) > 5000:
        return True

    # 第1层：fetch
    data = await try_fetch(page, pdf_url)
    if data:
        with open(filepath, 'wb') as f:
            f.write(data)
        return True

    # 第2层：download event
    data = await try_download_event(page, browser, pdf_url)
    if data:
        with open(filepath, 'wb') as f:
            f.write(data)
        return True

    # 第3层：文章页
    if article_url and article_url != pdf_url:
        data = await try_article_page(page, browser, article_url, title)
        if data:
            with open(filepath, 'wb') as f:
                f.write(data)
            return True

    return False


# ============================================================
#  失败记录到 CSV
# ============================================================
FAILED_FILE = "failed_articles.csv"

def record_failed(title, journal, doi, link, reason, download_dir):
    """追加一条失败记录到 CSV"""
    path = os.path.join(download_dir, FAILED_FILE)
    exists = os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["title", "journal", "doi", "link", "reason"])
        writer.writerow([title, journal, doi, link, reason])
    print(f"  [FAIL] {title[:50]}... | {reason}")


# ============================================================
#  领域名称 → OpenAlex field.id 映射
# ============================================================
FIELD_IDS = {
    "business, management and accounting": 14,
    "decision sciences": 19,
    "computer science": 20,
    "economics, econometrics and finance": 21,
    "social sciences": 23,
    "engineering": 22,
    "agricultural and biological sciences": 1,
    "arts and humanities": 2,
    "biochemistry, genetics and molecular biology": 3,
    "chemistry": 4,
    "energy": 6,
    "environmental science": 7,
    "materials science": 11,
    "mathematics": 12,
    "medicine": 13,
    "neuroscience": 15,
    "pharmacology, toxicology and pharmaceutics": 16,
    "physics and astronomy": 17,
    "psychology": 18,
}


def parse_field(field_str):
    """解析领域名称或ID"""
    field_str = field_str.strip().lower()
    if field_str in FIELD_IDS:
        return FIELD_IDS[field_str]
    try:
        return int(field_str)
    except ValueError:
        return None


def sanitize_filename(name):
    """文件名净化"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name[:100]


# ============================================================
#  主流程
# ============================================================
async def async_main(args_text):
    global DOWNLOAD_DIR
    sp = print  # safe_print wrapper

    # 解析参数：关键词 | 年份范围 | 领域 | 数量 | 下载目录
    parts = [p.strip() for p in args_text.split("|")]
    keyword = parts[0] if len(parts) > 0 else ""
    year_range = parts[1] if len(parts) > 1 else "2025-2026"
    field_name = parts[2] if len(parts) > 2 else "Business, Management and Accounting"
    count = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 5
    if len(parts) > 4 and parts[4]:
        DOWNLOAD_DIR = parts[4]

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    sp("=" * 60)
    sp("OpenAlex 学术搜索与PDF下载")
    sp(f"  关键词: {keyword}")
    sp(f"  年份: {year_range}")
    sp(f"  领域: {field_name}")
    sp(f"  数量: {count}")
    sp(f"  下载到: {DOWNLOAD_DIR}")
    sp("=" * 60)

    # 解析年份
    years = year_range.replace(" ", "").split("-")
    year_from = years[0] if years[0] else ""
    year_to = years[1] if len(years) > 1 else ""

    # 解析领域
    field_id = parse_field(field_name)

    # 构建OpenAlex API查询
    filters = ["open_access.is_oa:true"]
    if year_from:
        filters.append(f"publication_year:{year_from}-")
    if year_to and year_to != year_from:
        filters[-1] = f"publication_year:{year_from}-{year_to}"
    if field_id:
        filters.append(f"primary_topic.field.id:{field_id}")

    api_url = "https://api.openalex.org/works"
    params = {
        "search": keyword,
        "filter": ",".join(filters),
        "sort": "relevance_score:desc",
        "per_page": count,
        "select": "id,doi,title,primary_location,open_access,publication_year,cited_by_count,authorships,primary_topic",
    }

    sp("\n[1/4] 查询 OpenAlex API...")
    import requests
    try:
        resp = requests.get(api_url, params=params, timeout=30)
        data = resp.json()
    except Exception as e:
        sp(f"  API请求失败: {e}")
        return

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)
    sp(f"  找到 {total} 篇论文（OA+年份+领域筛选后）")
    sp(f"  获取前 {len(results)} 篇")

    if not results:
        sp("  无结果，结束。")
        return

    # 打印结果概览
    sp("\n[2/4] 论文列表:")
    for i, work in enumerate(results):
        title = work.get("title", "N/A")
        year = work.get("publication_year", "?")
        doi = work.get("doi", "")
        doi_short = doi.replace("https://doi.org/", "") if doi else "—"
        loc = work.get("primary_location", {}) or {}
        source = loc.get("source", {}) or {}
        journal = source.get("display_name", "—") if source else "—"
        cited = work.get("cited_by_count", 0)
        sp(f"  [{i+1}] ({year}) {title[:70]}...")
        sp(f"      期刊: {journal} | 引用: {cited} | DOI: {doi_short}")

    # 连接 Chrome
    sp("\n[3/4] 连接 Chrome CDP...")
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = await browser.new_page()

        success_count = 0
        fail_count = 0

        for i, work in enumerate(results):
            title = work.get("title", "Untitled")
            doi = work.get("doi", "")
            doi_short = doi.replace("https://doi.org/", "") if doi else ""
            loc = work.get("primary_location", {}) or {}
            source = loc.get("source", {}) or {}
            journal = source.get("display_name", "—") if source else "—"

            oa = work.get("open_access", {}) or {}
            oa_url = oa.get("oa_url", "")
            pdf_url = loc.get("pdf_url", "") if loc else ""
            landing_url = loc.get("landing_page_url", "") if loc else ""

            # 确定PDF URL和文章URL
            pdf_url = pdf_url or oa_url
            article_url = landing_url or (f"https://doi.org/{doi_short}" if doi_short else "")

            fn = f"{i+1:02d}_{sanitize_filename(title[:60])}.pdf"
            fp = os.path.join(DOWNLOAD_DIR, fn)

            sp(f"\n  [{i+1}/{len(results)}] {title[:60]}...")

            if not pdf_url:
                sp(f"    无 PDF 链接，跳过")
                record_failed(title, journal, doi_short, article_url, "OpenAlex 记录中无可用 PDF 链接", DOWNLOAD_DIR)
                fail_count += 1
                continue

            sp(f"    PDF: {pdf_url[:100]}")

            ok = await download_pdf(page, browser, pdf_url, article_url, title, fp)

            if ok:
                size = os.path.getsize(fp)
                sp(f"    ✅ 下载成功 ({size:,} bytes) → {fn}")
                success_count += 1
            else:
                sp(f"    ❌ 3层管道均失败")
                record_failed(title, journal, doi_short, article_url, "3层PDF管道均无法获取", DOWNLOAD_DIR)
                fail_count += 1

        await page.close()

    # 总结
    sp("\n" + "=" * 60)
    sp(f"下载完成: ✅ {success_count} 成功 | ❌ {fail_count} 失败")
    if fail_count > 0:
        failed_path = os.path.join(DOWNLOAD_DIR, FAILED_FILE)
        sp(f"失败记录保存在: {failed_path}")
        # 尝试生成 xlsx
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Failed Downloads"
            ws.append(["文章标题", "期刊", "DOI", "链接", "失败原因"])
            with open(failed_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                for row in reader:
                    ws.append(row)
            ws.column_dimensions['A'].width = 60
            ws.column_dimensions['B'].width = 35
            ws.column_dimensions['C'].width = 40
            ws.column_dimensions['D'].width = 60
            ws.column_dimensions['E'].width = 55
            xlsx_path = failed_path.replace('.csv', '.xlsx')
            wb.save(xlsx_path)
            sp(f"Excel版本: {xlsx_path}")
        except ImportError:
            pass
    sp(f"成功PDF保存在: {DOWNLOAD_DIR}")
    sp("=" * 60)


def main(args_text):
    asyncio.run(async_main(args_text))


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
