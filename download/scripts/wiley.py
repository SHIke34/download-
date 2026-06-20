"""Wiley Online Library — 搜索 + PDF 下载

通过 Playwright CDP 操作 Wiley Online Library，支持关键词搜索、
年份筛选、批量下载 PDF（含浏览器内 fetch→base64 管道）。

用法:
  python main.py wiley "keyword | startYear endYear | count | outputDir"

管道格式:
  第1段: 关键词
  第2段: 起止年份 (可选, 如 "2024 2026")
  第3段: 数量 (默认 5)
  第4段: 输出目录 (默认 ./Wiley_Results)
"""

import asyncio
import json
import os
import re
import sys
import base64
import urllib.parse

from utils import sp, log, safe_filename, ensure_output_dir, connect_playwright_async, FailedRecord


DEFAULT_COUNT = 5
DEFAULT_OUTPUT = "./Wiley_Results"


def parse_args(args_text: str) -> dict:
    """解析 Wiley 参数

    格式: keyword | startYear endYear | count | outputDir
    """
    params = {
        "keyword": "",
        "start_year": None,
        "end_year": None,
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
    if len(parts) >= 3 and parts[2] and parts[2].isdigit():
        params["count"] = int(parts[2])
    if len(parts) >= 4 and parts[3]:
        params["output_dir"] = parts[3]

    return params


async def main_async(args_text: str):
    """异步主入口"""
    params = parse_args(args_text)
    keyword = params["keyword"]
    count = params["count"]
    output_dir = ensure_output_dir(params["output_dir"])

    if not keyword:
        log("WILEY", "Keyword required.")
        return

    log("WILEY", f"Query: {keyword} | Count: {count} | Output: {output_dir}")

    connect_fn = connect_playwright_async()
    try:
        p, browser, page = await connect_fn()
    except Exception as e:
        log("WILEY", f"Cannot connect to Chrome: {e}")
        return

    try:
        # Build search URL
        search_url = ("https://onlinelibrary.wiley.com/action/doSearch?"
                      f"ConceptID=&target=default&ContribAuthorRaw=&"
                      f"startPage=&pageSize={min(count * 2, 50)}&"
                      f"AllField={urllib.parse.quote(keyword)}&"
                      "content=articlesSearch&sortBy=relevance")
        if params["start_year"]:
            search_url += f"&PubDate={params['start_year']}%20-%20{params['end_year'] or params['start_year']}"

        log("WILEY", f"Searching: {search_url[:120]}...")
        await page.goto(search_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)

        # Extract articles
        articles = await page.evaluate("""
        () => {
            const results = [];
            const items = document.querySelectorAll('.search__item, article[data-doi], .item-card');
            if (items.length === 0) {
                // Alternative: look for h2/h3 links
                document.querySelectorAll('h2 a, h3 a, a[href*="/doi/"]').forEach(a => {
                    const href = a.href || '';
                    if (href.includes('/doi/') && !results.some(r => r.link === href)) {
                        results.push({
                            title: (a.textContent || '').trim(),
                            link: href,
                        });
                    }
                });
            } else {
                items.forEach(item => {
                    const titleEl = item.querySelector('a[href*="/doi/"], h2 a, h3 a');
                    if (!titleEl) return;
                    const title = (titleEl.textContent || '').trim();
                    const link = titleEl.href || '';
                    if (link && title.length > 5 && !results.some(r => r.link === link)) {
                        results.push({ title: title.substring(0, 150), link });
                    }
                });
            }
            return results;
        }
        """)

        if not articles:
            log("WILEY", "No articles found.")
            return

        articles = articles[:count]
        log("WILEY", f"Found {len(articles)} articles:")
        for i, a in enumerate(articles, 1):
            sp(f"  {i:2d}. {a['title'][:70]}")

        # Download PDFs
        log("WILEY", f"Downloading {len(articles)} papers...")
        failed = FailedRecord()
        downloaded = 0

        for i, a in enumerate(articles, 1):
            log("WILEY", f"  [{i}/{len(articles)}] {a['title'][:50]}")

            try:
                await page.goto(a["link"], wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                pdf_url = await page.evaluate("""
                () => {
                    // Try PDF download button
                    for (const sel of ['a[href*="/doi/pdf"]', 'a[href*="pdf"]',
                                       'a[class*="pdf"]', 'a[href$=".pdf"]',
                                       'a[data-test="pdf-link"]', 'a[data-track*="download"]']) {
                        const el = document.querySelector(sel);
                        if (el && el.href) return el.href;
                    }
                    // Build PDF from DOI
                    const doiMatch = window.location.href.match(/\\/doi\\/(10\\.[^?#]+)/);
                    if (doiMatch) return 'https://onlinelibrary.wiley.com/doi/pdf/' + doiMatch[1];
                    return '';
                }
                """)

                if pdf_url:
                    pdf_b64 = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('{pdf_url}');
                            if (!resp.ok) return 'HTTP' + resp.status;
                            const blob = await resp.blob();
                            if (blob.size < 1000) return 'SMALL:' + blob.size;
                            const buf = await blob.arrayBuffer();
                            const bytes = new Uint8Array(buf);
                            let bin = '';
                            for (let j = 0; j < bytes.length; j++) bin += String.fromCharCode(bytes[j]);
                            return 'data:application/pdf;base64,' + btoa(bin);
                        }} catch(e) {{ return 'ERR:' + e.message; }}
                    }}
                    """)
                    if pdf_b64 and pdf_b64.startswith("data:application/pdf;base64,"):
                        raw = base64.b64decode(pdf_b64.split(",")[1])
                        safe = safe_filename(a["title"], 80).replace(" ", "_")
                        fname = f"{i:02d}_{safe}.pdf"
                        fpath = os.path.join(output_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(raw)
                        log("WILEY", f"  [OK] {fname} ({len(raw)//1024} KB)")
                        downloaded += 1
                    else:
                        failed.add(title=a["title"], link=pdf_url, source="Wiley", reason=f"Fetch failed: {str(pdf_b64)[:40]}")
                else:
                    failed.add(title=a["title"], link=a["link"], source="Wiley", reason="No PDF link found")
            except Exception as e:
                failed.add(title=a["title"], link=a["link"], source="Wiley", reason=str(e)[:60])
                log("WILEY", f"  Error: {str(e)[:60]}")

        log("WILEY", f"Done! {downloaded}/{len(articles)} downloaded to {output_dir}")
        if failed.count > 0:
            xlsx = failed.save_xlsx(output_dir)
            log("WILEY", f"Failed records: {xlsx} ({failed.count} papers)")

    finally:
        await browser.close()
        await p.stop()


def main(args_text: str):
    """同步入口（统一接口）"""
    asyncio.run(main_async(args_text))


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
