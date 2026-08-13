
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx


@dataclass
class SearchResult:

    title: str
    url: str
    snippet: str


class WebSearchTool:

    name = "web_search"

    info = {
        "description": "网络搜索：查询最新信息、事实、新闻等（当前资料不足时用）",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"],
        },
    }

    async def execute(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return "搜索失败：缺少 query"
        results = await self._search(query)
        if not results:
            return f"搜索「{query}」无结果"
        return "\n".join(
            f"[{i + 1}] {r.title}\n{r.url}\n{r.snippet}" for i, r in enumerate(results[:5])
        )

    async def _search(self, query: str) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    "https://www.bing.com/search",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
            return self._parse_html(resp.text)
        except Exception:
            return []

    def _parse_html(self, html: str) -> list[SearchResult]:
        results = []
        for m in re.finditer(r'class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            url = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not url.startswith("http"):
                continue
            results.append(SearchResult(title=title, url=url, snippet=""))
            if len(results) >= 5:
                break
        return results
