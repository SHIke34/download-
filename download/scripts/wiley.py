"""
Wiley Online Library — 学术文献检索下载 (Playwright CDP + 浏览器 fetch 管道)
=======================================================================
工作流：连接已登录 VPN 的 Chrome → 搜索 → 筛选 (Journals + 时间 + OA)
→ 逐篇验证OA → pdfdirect 下载 → 失败记录 CSV

返回: (downloaded: int, failed_file: str|None)
"""
import asyncio, json, base64, os, re, sys, csv
from playwright.async_api import async_playwright


def run(search_term: str, max_download: int = 5, download_dir: str = r"D:\md",
        date_filter: str = "Last 12 Months", cdp_port: int = 9222) -> dict:
    """
    入口函数 (同步，供 main.py CLI 调用)

    参数:
        search_term:  搜索关键词
        max_download: 最多处理篇数 (含失败)
        download_dir: PDF 保存目录
        date_filter:  时间筛选 (Last 12 Months / Last 6 Months / Last 3 Months / Last 2 Years)
        cdp_port:     Chrome DevTools Protocol 端口

    返回: {"downloaded": int, "failed": int, "failed_file": str|None}
    """
    sys.stdout.reconfigure(encoding="utf-8")
    return asyncio.run(_main(search_term, max_download, download_dir, date_filter, cdp_port))


async def _main(search_term: str, max_download: int, download_dir: str,
                date_filter: str, cdp_port: int) -> dict:
    p = await async_playwright().start()
    chrome = await p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
    page = chrome.contexts[0].pages[0]

    failed_file = os.path.join(download_dir, "failed_articles.csv")

    # 1. 导航到 Wiley 首页
    await page.goto("https://onlinelibrary-wiley-com-443.webvpn.upc.edu.cn/",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    # 2. 搜索
    search = page.locator("#searchField1")
    await search.wait_for(timeout=10000)
    await search.fill(search_term)
    await page.wait_for_timeout(500)
    await page.locator(".quick-search__button").click()
    await page.wait_for_timeout(5000)
    print(f"[Wiley] 搜索完成: {search_term}")

    # 3. 筛选: Journals + 时间 + Open Access
    print(f"[Wiley] 筛选: Journals + {date_filter} + Open Access")
    await page.evaluate('document.getElementById("Journals")?.click()')
    await page.wait_for_timeout(3000)
    date_map = {
        "Last 12 Months": "Last 12 Months",
        "Last 6 Months":  "Last 6 Months",
        "Last 3 Months":  "Last 3 Months",
        "Last 2 Years":   "Last 2 Years",
    }
    date_id = date_map.get(date_filter, "Last 12 Months")
    await page.evaluate(f'document.getElementById("{date_id}")?.click()')
    await page.wait_for_timeout(3000)
    await page.evaluate('document.getElementById("Open Access Content")?.click()')
    await page.wait_for_timeout(3000)

    # 4. 获取结果列表 (含期刊信息)
    results = json.loads(await page.evaluate("""() => {
        const items = document.querySelectorAll('[class*=search-item], [class*=result-item], li.search__item, .item__body');
        const seen = new Set();
        return JSON.stringify(Array.from(items).map(item => {
            const el = item.querySelector('h3 a, h2 a, .title a');
            if (!el) return null;
            const link = el.href;
            if (seen.has(link)) return null;
            seen.add(link);
            const journalEl = item.querySelector('[class*=journal], [class*=source], .meta__item a, [class*=pub]');
            const journal = journalEl ? journalEl.textContent.trim() : '';
            return {
                title: el.textContent.trim().substring(0, 200),
                link,
                journal: journal.substring(0, 100)
            };
        }).filter(Boolean));
    }"""))
    print(f"[Wiley] 搜索结果: {len(results)} 篇 (标记为 OA)")

    # 5. 逐篇处理
    os.makedirs(download_dir, exist_ok=True)
    downloaded = []
    failed = []

    for i, art in enumerate(results[:max_download], 1):
        print(f"\n[{i}/{len(results)}] {art['title'][:60]}...")
        try:
            await page.goto(art["link"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # 获取文章页元信息 + 验证 OA
            page_info = json.loads(await page.evaluate("""() => {
                const title = document.querySelector('meta[name="citation_title"]');
                const journal = document.querySelector('meta[name="citation_journal_title"]');
                const authors = document.querySelector('meta[name="citation_author"]');
                const date = document.querySelector('meta[name="citation_publication_date"]');
                const doi = document.querySelector('meta[name="citation_doi"]');
                return JSON.stringify({
                    title: title ? title.content : '',
                    journal: journal ? journal.content : '',
                    author: authors ? authors.content : '',
                    date: date ? date.content : '',
                    doi: doi ? doi.content : ''
                });
            }"""))

            has_oa = await page.evaluate(
                "() => document.body.innerText.includes('Open Access')")
            title = page_info["title"] or art["title"]
            journal = page_info["journal"] or art["journal"]
            doi = page_info["doi"] or art["link"].split("/doi/")[-1].split("?")[0]

            if not has_oa:
                print("  → 非OA (搜索结果标记不准确)")
                failed.append({
                    "title": title,
                    "journal": journal,
                    "doi": doi,
                    "link": art["link"],
                    "reason": "搜索结果标记为OA但文章页面无Open Access标识"
                })
                continue

            pdf_url = f"https://onlinelibrary-wiley-com-443.webvpn.upc.edu.cn/doi/pdfdirect/{doi}"
            pdf_b64 = await page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url);
                    const ct = resp.headers.get('content-type') || '';
                    if (ct.includes('text/html')) return 'HTML';
                    if (!resp.ok) return 'ERR:' + resp.status;
                    const blob = await resp.blob();
                    const buf = await blob.arrayBuffer();
                    const b = new Uint8Array(buf);
                    let s = '';
                    for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
                    return btoa(s);
                } catch(e) { return 'ERR:' + e.message; }
            }""", pdf_url)

            if pdf_b64 == "HTML" or pdf_b64.startswith("ERR:"):
                print(f"  → OA但PDF不可获取 ({pdf_b64[:50]})")
                failed.append({
                    "title": title,
                    "journal": journal,
                    "doi": doi,
                    "link": art["link"],
                    "reason": f"OA标识但PDF获取失败: {pdf_b64[:50]}"
                })
                continue

            # 保存 PDF
            name = re.sub(r"[^\w\s-]", "", title)[:60].strip().replace(" ", "_")
            fp = os.path.join(download_dir, f"{i}_{name}.pdf")
            pad = 4 - len(pdf_b64) % 4
            if pad != 4: pdf_b64 += "=" * pad
            with open(fp, "wb") as f:
                f.write(base64.b64decode(pdf_b64))
            sz = os.path.getsize(fp)
            print(f"  → OK ({sz//1024} KB)")
            downloaded.append(fp)

        except Exception as e:
            print(f"  → 异常: {e}")
            failed.append({
                "title": art["title"],
                "journal": art["journal"],
                "doi": "",
                "link": art["link"],
                "reason": f"处理异常: {str(e)[:80]}"
            })

    # 6. 输出结果
    print(f"\n{'='*50}")
    print(f"成功下载: {len(downloaded)} 篇")
    for f in downloaded:
        print(f"  {os.path.basename(f)}")

    if failed:
        print(f"\n无法下载: {len(failed)} 篇")
        with open(failed_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "journal", "doi", "link", "reason"])
            writer.writeheader()
            writer.writerows(failed)
        print(f"失败记录已保存: {failed_file}")
        for item in failed:
            print(f"  - {item['title'][:55]} | {item['journal'][:25]} | {item['reason']}")
    else:
        print("\n全部OA文章均成功下载!")

    print(f"\n目录: {download_dir}")
    await p.stop()
    return {"downloaded": len(downloaded), "failed": len(failed),
            "failed_file": failed_file if failed else None}


if __name__ == "__main__":
    import sys
    term = sys.argv[1] if len(sys.argv) > 1 else "fintech prediction"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    result = run(term, n)
    print(f"\n结果: {result}")
