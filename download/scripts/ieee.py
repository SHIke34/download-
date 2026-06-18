"""IEEE Xplore — 搜索 + 被引排序 + PDF 下载（含 Sci-Hub 回退）

通过 Chrome CDP + Playwright 连接已打开的 Chrome，
自动化操作 IEEE Xplore。支持关键词搜索、年份筛选、被引量排序、
PDF 下载（IEEE stamp 端点 + Sci-Hub 回退）。

用法:
  python main.py ieee "keyword | startYear endYear | sortBy | count | outputDir"
"""

import asyncio
import json
import os
import re
import sys
import urllib.parse

from utils import sp, log, safe_filename, save_json, ensure_output_dir, connect_playwright_async


DEFAULT_COUNT = 10
DEFAULT_OUTPUT = "./IEEE_Results"


def parse_args(args_text: str) -> dict:
    """解析 IEEE 专有参数

    格式: keyword | startYear endYear | sortBy | count | outputDir
    sortBy: citations (默认) / date
    """
    params = {
        "query": "",
        "start_year": 2020,
        "end_year": 2026,
        "sort_by": "citations",
        "count": DEFAULT_COUNT,
        "output_dir": DEFAULT_OUTPUT,
    }
    if not args_text or not args_text.strip():
        return params

    parts = [p.strip() for p in args_text.split("|")]

    if len(parts) >= 1 and parts[0]:
        params["query"] = parts[0]
    if len(parts) >= 2 and parts[1]:
        years = parts[1].split()
        if len(years) >= 1 and years[0].isdigit():
            params["start_year"] = int(years[0])
        if len(years) >= 2 and years[1].isdigit():
            params["end_year"] = int(years[1])
    if len(parts) >= 3 and parts[2]:
        sort_map = {"被引": "citations", "日期": "date", "发表": "date",
                    "cited": "citations", "citations": "citations",
                    "newest": "date", "date": "date"}
        params["sort_by"] = sort_map.get(parts[2].lower(), "citations")
    if len(parts) >= 4 and parts[3] and parts[3].isdigit():
        params["count"] = int(parts[3])
    if len(parts) >= 5 and parts[4]:
        params["output_dir"] = parts[4]

    return params


def build_search_url(query, start_year, end_year, sort_by):
    """构建 IEEE Xplore 搜索 URL"""
    return (
        "https://ieeexplore.ieee.org/search/searchresult.jsp"
        f"?queryText={urllib.parse.quote(query)}"
        "&highlight=true&returnFacets=ALL&returnType=SEARCH&matchPubs=true"
        f"&ranges={start_year}_{end_year}_PYear"
        f"&sortType={sort_by}"
    )


async def search_ieee(page, query, start_year, end_year, sort_by):
    """搜索 IEEE 并提取论文列表"""
    search_url = build_search_url(query, start_year, end_year, sort_by)
    log("IEEE", f"Searching: {query}")
    log("IEEE", f"URL: {search_url}")

    await page.goto(search_url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(5000)

    papers = await page.evaluate("""
        () => {
            const papers = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/document/"]').forEach(a => {
                const idMatch = a.href.match(/document\\/(\\d+)/);
                if (!idMatch || seen.has(idMatch[1])) return;
                seen.add(idMatch[1]);
                const section = a.closest('div[class], li, article, section') ||
                               a.parentElement?.closest('div, li') || a.parentElement;
                const contextText = section ? section.textContent : '';
                const heading = a.closest('h2, h3, h4');
                const title = heading ? heading.textContent.trim() : a.textContent.trim();
                const yearMatch = contextText.match(/\\b(20[12]\\d)\\b/);
                const year = yearMatch ? yearMatch[1] : '';
                papers.push({ title, link: a.href, year });
            });
            return papers;
        }
    """)

    valid = [p for p in papers if p.get("year", "").isdigit()
             and start_year <= int(p["year"]) <= end_year]
    if len(valid) >= 3:
        papers = valid

    return papers


async def try_direct_pdf(page, doc_id):
    """尝试通过 IEEE stamp 端点直接下载 PDF"""
    stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={doc_id}"
    resp = await page.context.request.get(stamp_url, timeout=30000)
    if resp:
        content = await resp.body()
        if b"%PDF" in content[:500] or len(content) > 80000:
            return content
    return None


async def try_scihub(page, doi):
    """尝试 Sci-Hub 下载 PDF"""
    for domain in ["sci-hub.ru", "sci-hub.st", "sci-hub.sg"]:
        try:
            url = f"https://{domain}/{doi}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(4000)

            pdf_info = await page.evaluate("""
                () => {
                    let pdfUrl = '';
                    try { if (document.contentType === 'application/pdf') pdfUrl = window.location.href; } catch(e) {}
                    const embed = document.querySelector('embed[type="application/pdf"]');
                    if (embed && embed.src) pdfUrl = embed.src;
                    const iframe = document.querySelector('iframe#pdf');
                    if (iframe && iframe.src) pdfUrl = iframe.src;
                    const obj = document.querySelector('object[type="application/pdf"]');
                    if (obj && obj.data) pdfUrl = obj.data;
                    return pdfUrl.substring(0, 500);
                }
            """)

            if pdf_info:
                try:
                    resp = await page.context.request.get(pdf_info, timeout=30000)
                    if resp:
                        content = await resp.body()
                        if b"%PDF" in content[:500]:
                            return content
                except Exception:
                    pass

            links = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('a').forEach(a => {
                        const h = a.href || '';
                        if (h && (h.endsWith('.pdf') || h.includes('/storage/'))) results.push(h);
                    });
                    return results;
                }
            """)

            for link in links:
                try:
                    resp = await page.context.request.get(link, timeout=30000)
                    if resp:
                        content = await resp.body()
                        if b"%PDF" in content[:500]:
                            return content
                except Exception:
                    pass
        except Exception:
            continue

    return None


async def download_papers(page, papers, output_dir, count):
    """批量下载 PDF，返回成功数"""
    downloaded = 0
    for i, paper in enumerate(papers[:count]):
        title = paper.get("title", "")
        link = paper.get("link", "")
        doi = paper.get("doi", "")

        if not link:
            continue

        safe_title = safe_filename(title, 80) or f"paper_{i+1}"
        log("IEEE", f"  [{i+1}/{min(count, len(papers))}] {safe_title[:55]}...")

        doc_match = re.search(r"/document/(\d+)", link)
        doc_id = doc_match.group(1) if doc_match else None
        if not doc_id:
            log("IEEE", "    No document ID")
            continue

        if not doi:
            try:
                await page.goto(link, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                doi = await page.evaluate("""
                    () => {
                        const a = document.querySelector('a[href*="doi"]');
                        if (a) return a.href;
                        const m = document.body.innerText.match(/10\\.\\d{4,}\\/[\\w.\\/-]+/);
                        return m ? m[0] : '';
                    }
                """)
            except Exception:
                pass

        # Method 1: IEEE direct
        content = await try_direct_pdf(page, doc_id)
        if content:
            fp = os.path.join(output_dir, f"{i+1:02d}_{safe_title}.pdf")
            with open(fp, "wb") as f:
                f.write(content)
            log("IEEE", f"    DOWNLOADED from IEEE ({len(content)} bytes)")
            downloaded += 1
            continue

        # Method 2: Sci-Hub
        if doi:
            log("IEEE", f"    Sci-Hub via DOI: {doi[:55]}...")
            content = await try_scihub(page, doi)
            if content:
                fp = os.path.join(output_dir, f"{i+1:02d}_{safe_title}.pdf")
                with open(fp, "wb") as f:
                    f.write(content)
                log("IEEE", f"    DOWNLOADED via Sci-Hub ({len(content)} bytes)")
                downloaded += 1
                continue

        log("IEEE", "    Not available (no open access)")

    return downloaded


async def main_async(args_text: str):
    """异步主入口"""
    params = parse_args(args_text)
    output_dir = ensure_output_dir(params["output_dir"])

    log("IEEE", "=" * 50)
    log("IEEE", f"Query: {params['query']}")
    log("IEEE", f"Year: {params['start_year']}-{params['end_year']}")
    log("IEEE", f"Sort: {params['sort_by']} | Count: {params['count']} | Output: {output_dir}")

    connect_fn = connect_playwright_async()
    log("IEEE", "Connecting to Chrome...")
    try:
        p, browser, page = await connect_fn()
    except Exception as e:
        log("IEEE", f"ERROR: Cannot connect to Chrome: {e}")
        log("IEEE", "Ensure Chrome is running with --remote-debugging-port=9222")
        log("IEEE", 'Example: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
        return

    try:
        papers = await search_ieee(page, params["query"], params["start_year"], params["end_year"], params["sort_by"])
        log("IEEE", f"Found {len(papers)} papers in range {params['start_year']}-{params['end_year']}.")
        for i, p in enumerate(papers[: params["count"]]):
            sp(f"  {i+1:2d}. [{p.get('year','?')}] {p['title'][:70]}")
        sp("")

        if not papers:
            log("IEEE", "No papers found. Try broader keywords.")
            return

        save_json(papers[: params["count"]], os.path.join(output_dir, "papers_list.json"))

        dl_count = await download_papers(page, papers, output_dir, params["count"])

        log("IEEE", f"Done! Papers found: {len(papers)}, PDFs downloaded: {dl_count}/{min(params['count'], len(papers))}")
        if dl_count < min(params["count"], len(papers)):
            log("IEEE", "Undownloaded papers may require IEEE institutional subscription.")
            log("IEEE", "Try with a university network or VPN for full access.")

    finally:
        await browser.close()
        await p.stop()


def main(args_text: str):
    """同步入口"""
    asyncio.run(main_async(args_text))


if __name__ == "__main__":
    args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    main(args)
