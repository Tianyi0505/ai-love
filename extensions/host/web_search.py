
from __future__ import annotations

import re
from dataclasses import dataclass
from string import Template

import httpx

from shared.infrastructure.runtime_config import required_config


@dataclass
class SearchResult:

    title: str
    url: str
    snippet: str


class WebSearchTool:

    name = "web_search"

    def __init__(self, config: dict) -> None:
        self.info = dict(required_config(config, "definition", "service.extension-host.web_search.definition"))
        self._request_timeout_sec = float(required_config(config, "request_timeout_sec", "service.extension-host.web_search.request_timeout_sec"))
        self._endpoint = str(required_config(config, "endpoint", "service.extension-host.web_search.endpoint"))
        self._user_agent = str(required_config(config, "user_agent", "service.extension-host.web_search.user_agent"))
        self._result_limit = int(required_config(config, "result_limit", "service.extension-host.web_search.result_limit"))
        messages = dict(required_config(config, "messages", "service.extension-host.web_search.messages"))
        self._missing_query = str(required_config(messages, "missing_query", "service.extension-host.web_search.messages.missing_query"))
        self._no_result = Template(str(required_config(messages, "no_result", "service.extension-host.web_search.messages.no_result")))
        self._result = Template(str(required_config(messages, "result", "service.extension-host.web_search.messages.result")))

    async def execute(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return self._missing_query
        results = await self._search(query)
        if not results:
            return self._no_result.substitute(query=query)
        return "\n".join(
            self._result.substitute(index=i + 1, title=r.title, url=r.url, snippet=r.snippet)
            for i, r in enumerate(results[: self._result_limit])
        )

    async def _search(self, query: str) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_sec, follow_redirects=True) as client:
                resp = await client.get(
                    self._endpoint,
                    params={"q": query},
                    headers={"User-Agent": self._user_agent},
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
            if len(results) >= self._result_limit:
                break
        return results
