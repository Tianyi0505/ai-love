
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class Doc:

    id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    for ch in text:
        if "一" <= ch <= "鿿":
            tokens.append(ch)
    return tokens


class BM25Index:

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._docs: list[Doc] = []
        self._doc_freq: dict[str, int] = {}
        self._avg_len = 0.0

    def add(self, doc: Doc) -> None:
        self._docs.append(doc)
        tokens = set(_tokenize(doc.text))
        for t in tokens:
            self._doc_freq[t] = self._doc_freq.get(t, 0) + 1
        self._avg_len = sum(len(_tokenize(d.text)) for d in self._docs) / max(1, len(self._docs))

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q_tokens = _tokenize(query)
        n = len(self._docs)
        scores: list[tuple[str, float]] = []
        for doc in self._docs:
            doc_tokens = _tokenize(doc.text)
            dl = len(doc_tokens)
            score = 0.0
            for t in q_tokens:
                if t not in self._doc_freq:
                    continue
                tf = doc_tokens.count(t)
                df = self._doc_freq[t]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                tf_norm = tf * (self._k1 + 1) / (tf + self._k1 * (1 - self._b + self._b * dl / max(1, self._avg_len)))
                score += idf * tf_norm
            if score > 0:
                scores.append((doc.id, score))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


class HybridSearch:

    def __init__(self, top_k: int = 5) -> None:
        self._docs: dict[str, Doc] = {}
        self._bm25 = BM25Index()
        self._top_k = top_k

    def add(self, doc: Doc) -> None:
        self._docs[doc.id] = doc
        self._bm25.add(doc)

    def remove(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._bm25 = BM25Index()
        for d in self._docs.values():
            self._bm25.add(d)

    def search(self, query: str, vector_results: list[tuple[str, float]] | None = None, top_k: int | None = None) -> list[tuple[str, float]]:
        top_k = top_k or self._top_k
        bm25_results = self._bm25.search(query, top_k=top_k)
        k = 60
        fused: dict[str, float] = {}
        for rank, (doc_id, _) in enumerate(bm25_results):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        for rank, (doc_id, _) in enumerate(vector_results or []):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        return ranked[:top_k]

    def get(self, doc_id: str) -> Doc | None:
        return self._docs.get(doc_id)
