"""Evidence retrieval over an authorised source scope (RAG baseline).

Paragraph-level lexical retrieval is enough for the first version; the spec
allows pgvector/hybrid retrieval later, but recall must be *measured* before
swapping it in. Retrieval here never returns spans outside the allowed set, so a
prompt cannot widen its own evidence scope.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_CJK = re.compile(r"[一-鿿]")
_TOKEN = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


@dataclass(frozen=True, slots=True)
class RetrievedSpan:
    span_id: str
    source_id: str
    quote: str
    score: float
    page: int | None = None
    paragraph: int = 0


def tokenize(text: str) -> list[str]:
    """Mixed Chinese/latin tokeniser.

    Chinese is indexed as single characters plus bigrams: that keeps recall for
    short paragraph spans without a dictionary.
    """
    tokens: list[str] = []
    latin = re.findall(r"[A-Za-z0-9]+", text.lower())
    tokens.extend(latin)
    for run in re.findall(r"[一-鿿]+", text):
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _idf(documents: list[Counter[str]]) -> dict[str, float]:
    total = max(len(documents), 1)
    df: Counter[str] = Counter()
    for document in documents:
        df.update(set(document))
    return {term: math.log((total + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def retrieve(
    query: str,
    spans: list[dict[str, object]],
    *,
    limit: int = 6,
    min_score: float = 0.0,
) -> list[RetrievedSpan]:
    """Rank allowed spans by TF-IDF cosine similarity against the query."""
    if not spans:
        return []
    documents = [Counter(tokenize(str(span["quote"]))) for span in spans]
    idf = _idf(documents)
    query_tokens = Counter(tokenize(query))

    def vector(counter: Counter[str]) -> dict[str, float]:
        return {term: (count / sum(counter.values())) * idf.get(term, 1.0) for term, count in counter.items()}

    query_vector = vector(query_tokens)
    query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0

    scored: list[tuple[float, dict[str, object]]] = []
    for counter, span in zip(documents, spans):
        span_vector = vector(counter)
        norm = math.sqrt(sum(value * value for value in span_vector.values())) or 1.0
        dot = sum(weight * span_vector.get(term, 0.0) for term, weight in query_vector.items())
        score = dot / (query_norm * norm)
        if score > min_score:
            scored.append((score, span))
    scored.sort(key=lambda item: (-item[0], str(item[1]["span_id"])))
    return [
        RetrievedSpan(
            span_id=str(span["span_id"]),
            source_id=str(span.get("source_id", "")),
            quote=str(span["quote"]),
            score=round(score, 6),
            page=span.get("page") if isinstance(span.get("page"), int) else None,
            paragraph=int(span.get("paragraph") or 0),
        )
        for score, span in scored[:limit]
    ]
