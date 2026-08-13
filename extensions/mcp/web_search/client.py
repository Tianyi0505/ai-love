from __future__ import annotations

import re
from dataclasses import dataclass

import httpx


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    def __init__(
        self,
        endpoint: str,
        user_agent: str,
        request_timeout_sec: float,
        result_limit: int,
    ) -> None:
        self._endpoint = endpoint
        self._user_agent = user_agent
        self._request_timeout_sec = request_timeout_sec
        self._result_limit = result_limit

    async def search(self, query: str) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(
                timeout=self._request_timeout_sec,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    self._endpoint,
                    params={"q": query},
                    headers={"User-Agent": self._user_agent},
                )
                response.raise_for_status()
            return self._parse_html(response.text)
        except Exception:
            return []

    def _parse_html(self, html: str) -> list[SearchResult]:
        results = []
        pattern = r'class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        for match in re.finditer(pattern, html, re.S):
            url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if not url.startswith("http"):
                continue
            results.append(SearchResult(title=title, url=url, snippet=""))
            if len(results) >= self._result_limit:
                break
        return results
