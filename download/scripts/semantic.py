"""Semantic Scholar — 浏览器搜索 + PDF 下载

通过 Playwright CDP 操作 Semantic Scholar 网站，支持关键词搜索、
年份筛选、批量批量下载 PDF。

用法:
  python main.py semantic "keyword | startYear endYear | count | outputDir"
  python main.py ss "keyword | startYear endYear | count | outputDir"

管道格式:
  第1段: 关键词
  第2段: 起止年份 (空格分隔, 如 "2024 2026")
  第3段: 数量 (默认 5)
  第4段: 输出目录 (默认 ./Semantic_Results)
"""

import asyncio
import os
import re
import json
import sys
import base64
import urllib.parse

from utils import sp, log, safe_filename, ensure_output_dir, connect_playwright_async, FailedRecord


DEFAULT_COUNT = 5
DEFAULT_OUTPUT = "./Semantic_Results"


def parse_args(args_text: str) -> dict:
    """解析 Semantic Scholar 参数

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
        log("SEMANTIC", "Keyword required.")
        return

    log("SEMANTIC", f"Query: {keyword} | Count: {count} | Output: {output_dir}")

    connect_fn = connect_playwright_async()
    log("SEMANTIC", "Connecting to Chrome...")
    try:
        p, browser, page = await connect_fn()
    except Exception as e:
        log("SEMANTIC", f"ERROR: Cannot connect to Chrome: {e}")
        log("SEMANTIC", "Ensure Chrome is running with --remote-debugging-port=9222")
        return
    log("SEMANTIC", "Connected.")

    try:
        # Search
        search_url = f"https://www.semanticscholar.org/search?q={urllib.parse.quote(keyword)}&sort=relevance"
        if params["start_year"]:
            search_url += f"&year%5B0%5D={params['start_year']}&year%5B1%5D={params['end_year'] or params['start_year']}"

        log("SEMANTIC", f"Searching: {search_url}")
        await page.goto(search_url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(5000)

        # Check for Open Access filter
        try:
            # Try to click "Open Access" filter
            oa_btn = page.locator('[data-test-id="filter-open-access"], button:has-text("Open Access")')
            if await oa_btn.count() > 0:
                await oa_btn.first.click()
                log("SEMANTIC", "Open Access filter clicked")
                await page.wait_for_timeout(3000)
        except Exception as e:
            log("SEMANTIC", f"OA filter click failed (non-fatal): {e}")

        # Extract papers
        papers = await page.evaluate("""
        () => {
            const results = [];
            const items = document.querySelectorAll('[data-test-id="search-result"], [data-test-id="result-item"], .cl-paper-row');
            items.forEach(item => {
                const titleEl = item.querySelector('a[data-test-id="title-link"], h2 a, a[href*="/paper/"]');
                if (!titleEl) return;
                const title = (titleEl.textContent || '').trim();
                const link = titleEl.href || '';
                const yearEl = item.querySelector('[data-test-id="year"], .paper-year');
                const year = yearEl ? (yearEl.textContent || '').trim() : '';
                const authorsEl = item.querySelector('[data-test-id="authors"], .author-list');
                const authors = authorsEl ? (authorsEl.textContent || '').trim() : '';
                results.push({ title: title.substring(0, 150), link, year, authors: authors.substring(0, 120) });
            });
            return results;
        }
        """)

        if not papers:
            log("SEMANTIC", "No papers found. The page structure may have changed.")
            try:
                debug_html = await page.content()
                debug_path = os.path.join(output_dir, "semantic_debug.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(debug_html[:200000])
                log("SEMANTIC", f"Saved debug HTML: {debug_path}")
            except Exception:
                pass
            return

        papers = papers[:count]
        log("SEMANTIC", f"Found {len(papers)} papers:")

        # Save metadata
        meta_path = os.path.join(output_dir, "papers_list.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        log("SEMANTIC", f"List saved: {meta_path}")

        for i, p in enumerate(papers, 1):
            sp(f"  {i:2d}. [{p.get('year','?')}] {p['title'][:70]}")

        # Download PDFs
        log("SEMANTIC", f"Downloading {len(papers)} papers...")
        failed = FailedRecord()
        downloaded = 0

        for i, p in enumerate(papers, 1):
            log("SEMANTIC", f"  [{i}/{len(papers)}] {p['title'][:50]}")
            try:
                await page.goto(p["link"], wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                pdf_url = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        const h = a.href || '';
                        if ((h.includes('/pdf') || h.endsWith('.pdf')) && !h.includes('arxiv')) return h;
                    }
                    for (const a of links) {
                        const t = (a.textContent || '').toLowerCase();
                        if (t.includes('pdf') || t.includes('download')) return a.href;
                    }
                    // arxiv link
                    for (const a of links) {
                        const h = a.href || '';
                        if (h.includes('arxiv.org')) return h.replace('abs', 'pdf');
                    }
                    return '';
                }
                """)

                if pdf_url:
                    # Download via fetch + base64
                    pdf_b64 = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('{pdf_url}');
                            if (!resp.ok) return 'HTTP' + resp.status;
                            const blob = await resp.blob();
                            if (blob.size < 1000) return 'TOO_SMALL:' + blob.size;
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
                        safe = safe_filename(p["title"], 80).replace(" ", "_")
                        fname = f"{i:02d}_{safe}.pdf"
                        fpath = os.path.join(output_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(raw)
                        log("SEMANTIC", f"  [OK] {fname} ({len(raw)//1024} KB)")
                        downloaded += 1
                    else:
                        failed.add(title=p["title"], link=pdf_url, source="SemanticScholar", reason=f"Fetch failed: {str(pdf_b64)[:40]}")
                else:
                    failed.add(title=p["title"], link=p["link"], source="SemanticScholar", reason="No PDF link found")
            except Exception as e:
                failed.add(title=p["title"], link=p["link"], source="SemanticScholar", reason=str(e)[:60])
                log("SEMANTIC", f"  Error: {str(e)[:60]}")

        log("SEMANTIC", f"Done! {downloaded}/{len(papers)} downloaded to {output_dir}")
        if failed.count > 0:
            xlsx = failed.save_xlsx(output_dir)
            log("SEMANTIC", f"Failed records: {xlsx} ({failed.count} papers)")

    finally:
        await browser.close()
        await p.stop()


def main(args_text: str):
    """同步入口"""
    asyncio.run(main_async(args_text))


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
