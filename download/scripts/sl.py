"""Springer Link — 搜索 + OA识别 + 批量下载

支持关键词搜索、期刊限定、年份筛选、自动识别 Open Access、
浏览器内 fetch → base64 → Python 解码 管道下载 PDF。

用法:
  python main.py sl "keyword | startYear endYear | sortBy | count | outputDir"
"""

import asyncio
import json
import base64
import os
import re
import urllib.parse

from utils import sp, log, safe_filename, ensure_output_dir, connect_playwright_async, FailedRecord


DEFAULT_SORT = "relevance"
DEFAULT_COUNT = 10
DEFAULT_OUTPUT = "./SL_Results"


def parse_args(args_text: str) -> dict:
    """解析 SL 专有参数

    格式: keyword | startYear endYear | sortBy | count | outputDir
    sortBy: relevance (默认) / date
    """
    params = {
        "keyword": "",
        "start_year": None,
        "end_year": None,
        "sort_by": DEFAULT_SORT,
        "count": DEFAULT_COUNT,
        "output_dir": DEFAULT_OUTPUT,
    }
    if not args_text or not args_text.strip():
        return params

    parts = [p.strip() for p in args_text.split("|")]

    if len(parts) >= 1 and parts[0]:
        params["keyword"] = parts[0]
    if len(parts) >= 2 and parts[1]:
        years = parts[1].split()
        if len(years) >= 1 and years[0].isdigit():
            params["start_year"] = int(years[0])
        if len(years) >= 2 and years[1].isdigit():
            params["end_year"] = int(years[1])
    if len(parts) >= 3 and parts[2]:
        sort_map = {"relevance": "relevance", "date": "date", "相关性": "relevance", "时间": "date", "newest": "date"}
        params["sort_by"] = sort_map.get(parts[2].lower(), DEFAULT_SORT)
    if len(parts) >= 4 and parts[3] and parts[3].isdigit():
        params["count"] = int(parts[3])
    if len(parts) >= 5 and parts[4]:
        params["output_dir"] = parts[4]

    return params


async def get_oa_articles(page, seen_links):
    """扫描当前页面的 OA 文章"""
    articles_raw = await page.evaluate("""() => {
        const cards = document.querySelectorAll('.app-card-open');
        const results = [];
        cards.forEach(card => {
            const text = card.textContent;
            const hasOA = text.includes('Open access') || text.includes('open access');
            const linkEl = card.querySelector('.app-card-open__heading a, .app-card-open__link a');
            const title = linkEl ? linkEl.textContent.trim() : 'Unknown';
            const link = linkEl ? linkEl.href : '';
            const dateEl = card.querySelector('[data-test="published"]');
            const date = dateEl ? dateEl.textContent.trim() : '';
            results.push({
                title: title.substring(0, 150), link,
                hasOA, date, download: hasOA
            });
        });
        return JSON.stringify(results);
    }""")
    arts = json.loads(articles_raw)
    new_articles = []
    for a in arts:
        if a["download"] and a["link"] and "/article/" in a["link"] and a["link"] not in seen_links:
            seen_links.add(a["link"])
            new_articles.append(a)
    return new_articles


async def download_pdf(page, art, index, output_dir, failed):
    """浏览器 fetch 管道下载单篇 PDF"""
    log("SL", f"  [{index}] {art['title'][:60]}...")
    await page.goto(art["link"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    pdf_url = await page.evaluate("""() => {
        const links = document.querySelectorAll('a');
        for (const link of links) {
            if (link.textContent.trim().toLowerCase().includes('download pdf')) return link.href;
        }
        for (const link of links) {
            if (link.href && link.href.includes('content/pdf')) return link.href;
        }
        return null;
    }""")
    if not pdf_url:
        failed.add(title=art["title"], link=art["link"], source="SpringerLink", reason="No PDF download link found")
        log("SL", "  -> No PDF link, skip")
        return False

    pdf_b64 = await page.evaluate("""async (url) => {
        try {
            const resp = await fetch(url);
            if (!resp.ok) return 'FETCH_ERROR:' + resp.status;
            const blob = await resp.blob();
            const buffer = await blob.arrayBuffer();
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
            return btoa(binary);
        } catch(e) { return 'FETCH_ERROR:' + e.message; }
    }""", pdf_url)
    if pdf_b64.startswith("FETCH_ERROR"):
        failed.add(title=art["title"], link=pdf_url, source="SpringerLink", reason=f"Fetch failed: {pdf_b64[:60]}")
        log("SL", f"  -> Fetch failed: {pdf_b64[:60]}")
        return False

    title_short = safe_filename(art["title"], 80).replace(" ", "_")
    filename = f"{index:02d}_{title_short}.pdf"
    padding = 4 - len(pdf_b64) % 4
    if padding != 4:
        pdf_b64 += "=" * padding
    with open(os.path.join(output_dir, filename), "wb") as f:
        f.write(base64.b64decode(pdf_b64))
    log("SL", f"  -> Saved: {filename}")
    return True


async def main_async(args_text: str):
    """异步主入口"""
    params = parse_args(args_text)
    keyword = params["keyword"]
    output_dir = ensure_output_dir(params["output_dir"])

    # 默认搜索词
    if not keyword:
        keyword = "reinforcement learning"

    # 构建搜索 URL
    search_query = urllib.parse.quote(keyword)
    search_url = f"https://link.springer.com/search?query={search_query}&sortBy={params['sort_by']}"
    if params["start_year"]:
        search_url += f"&dateFrom={params['start_year']}-01-01&dateTo={params['end_year'] or params['start_year']}-12-31"

    log("SL", f"Query: {keyword}")
    log("SL", f"Sort: {params['sort_by']} | Count: {params['count']} | Output: {output_dir}")

    # 连接 Chrome
    connect_fn = connect_playwright_async()
    log("SL", "Connecting to Chrome...")
    try:
        p, browser, page = await connect_fn()
    except Exception as e:
        log("SL", f"ERROR: Cannot connect to Chrome: {e}")
        log("SL", "Ensure Chrome is running with --remote-debugging-port=9222")
        return
    log("SL", "Connected.")

    try:
        # 搜索
        log("SL", f"Searching: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # 翻页收集 OA 文章
        all_articles, seen_links = [], set()
        MAX_PAGES = 10
        for page_num in range(1, MAX_PAGES + 1):
            if len(all_articles) >= params["count"]:
                break
            new_arts = await get_oa_articles(page, seen_links)
            all_articles.extend(new_arts)
            log("SL", f"Page {page_num}: +{len(new_arts)} OA (total {len(all_articles)})")

            if len(all_articles) < params["count"]:
                next_url = f"{search_url}&page={page_num + 1}"
                await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

        log("SL", f"Total OA articles found: {len(all_articles)}")
        for i, a in enumerate(all_articles[: params["count"]]):
            sp(f"  {i+1:2d}. [{a.get('date','?')}] {a['title'][:70]}")

        if not all_articles:
            log("SL", "No OA articles found. Try broader keywords.")
            return

        # 下载
        log("SL", f"Downloading {min(params['count'], len(all_articles))} papers...")
        failed = FailedRecord()
        downloaded = 0
        for i, art in enumerate(all_articles[: params["count"]], 1):
            ok = await download_pdf(page, art, i, output_dir, failed)
            if ok:
                downloaded += 1

        log("SL", f"Done! {downloaded}/{min(params['count'], len(all_articles))} downloaded to {output_dir}")
        if failed.count > 0:
            xlsx = failed.save_xlsx(output_dir)
            log("SL", f"Failed records saved: {xlsx} ({failed.count} papers)")

    finally:
        await browser.close()
        await p.stop()


def main(args_text: str):
    """同步入口"""
    asyncio.run(main_async(args_text))


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
