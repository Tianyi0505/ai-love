from __future__ import annotations

from dataclasses import dataclass

import httpx
from selectolax.parser import HTMLParser


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        endpoint: str,
        result_limit: int,
    ) -> None:
        self._client = http_client
        self._endpoint = endpoint
        self._result_limit = result_limit

    async def search(self, query: str) -> list[SearchResult]:
        response = await self._client.get(self._endpoint, params={"q": query})
        response.raise_for_status()
        return self._parse_html(response.text)

    def _parse_html(self, html: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        for item in HTMLParser(html).css("li.b_algo"):
            link = item.css_first("h2 a")
            if link is None:
                continue
            url = link.attributes["href"]
            if not url.startswith(("http://", "https://")):
                continue
            snippet_node = item.css_first(".b_caption p")
            results.append(
                SearchResult(
                    title=link.text(strip=True),
                    url=url,
                    snippet=snippet_node.text(strip=True) if snippet_node else "",
                )
            )
            if len(results) >= self._result_limit:
                break
        return results
