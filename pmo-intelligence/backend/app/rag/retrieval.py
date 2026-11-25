"""Hybrid retrieval: permission filter -> BM25 + vector -> RRF fusion -> rerank.

The permission filter runs first and in the database: the candidate set is built
only from documents of *this* project that *this* user may read. No later stage
can widen it."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m, security
from .index import get_embedder, vector_store
from .text import tokens

TEMPORAL = re.compile(r"الحالي|الراهن|آخر|اخر|أحدث|احدث|الأخير|الاخير|حتى الآن|latest|current|currently|most recent|last|now|so far", re.I)


TEMPORAL_TOKENS = set(tokens("الحالي الحالية الراهن آخر اخر أحدث احدث الأخير الاخير الآن latest current currently recent last now", keep_stop=True))


@dataclass
class Hit:
    chunk: m.DocumentChunk
    doc: m.Document
    score: float      # fused + reranked, for ordering
    coverage: float   # share of query terms found in the chunk (0..1), the evidence test
    bm25: float = 0.0
    vector: float = 0.0
    weights: dict | None = None  # query term -> idf weight, reused to score sentences


class AccessDenied(Exception):
    pass


def authorised_documents(db: Session, user: m.User, project_id: int, doc_ids=None,
                         date_from: date | None = None, date_to: date | None = None) -> list[m.Document]:
    docs = security.readable_documents_query(db, user, project_id)
    if docs is None:
        raise AccessDenied("No access to this project's documents")
    out = []
    for d in docs:
        if d.processing_status != "indexed":
            continue
        if doc_ids and d.id not in doc_ids:
            continue
        dd = d.doc_date or (d.upload_date.date() if d.upload_date else None)
        if date_from and dd and dd < date_from:
            continue
        if date_to and dd and dd > date_to:
            continue
        out.append(d)
    return out


def _bm25(query_toks: list[str], docs_toks: list[list[str]], k1=1.5, b=0.75) -> list[float]:
    n = len(docs_toks)
    if not n:
        return []
    avg = sum(map(len, docs_toks)) / n or 1
    df = Counter(t for toks in docs_toks for t in set(toks))
    scores = []
    for toks in docs_toks:
        tf = Counter(toks)
        s = 0.0
        for q in set(query_toks):
            if q in tf:
                idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                s += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(toks) / avg))
        scores.append(s)
    return scores


def retrieve(db: Session, user: m.User, project_id: int, query: str, k: int = 6, doc_ids=None,
             date_from=None, date_to=None, versions="current", context_hint: str = "") -> list[Hit]:
    docs = authorised_documents(db, user, project_id, doc_ids, date_from, date_to)
    if not docs:
        return []
    by_id = {d.id: d for d in docs}
    q = select(m.DocumentChunk).where(m.DocumentChunk.project_id == project_id,
                                      m.DocumentChunk.document_id.in_(list(by_id)))
    chunks = []
    for c in db.scalars(q):
        d = by_id[c.document_id]
        if versions == "current" and c.version != d.current_version:
            continue
        if isinstance(versions, int) and c.version != versions:
            continue
        chunks.append(c)
    if not chunks:
        return []

    q_toks = tokens(query)
    if not q_toks and context_hint:
        q_toks = tokens(context_hint)
    full_q = tokens(f"{context_hint} {query}") if context_hint else q_toks
    c_toks = [tokens(f"{c.context or ''} {c.text}") for c in chunks]
    bm = _bm25(full_q, c_toks)
    kw_rank = {i: r for r, i in enumerate(sorted(range(len(chunks)), key=lambda i: -bm[i])) if bm[i] > 0}

    qvec = get_embedder(docs[0].embedding_model or "local-hash-v1").embed([f"{context_hint} {query}"])[0]
    vec = dict(vector_store.search(db, project_id, [c.id for c in chunks], qvec, 40))
    vec_rank = {cid: r for r, cid in enumerate(vec)}

    uq = set(full_q) if context_hint else set(q_toks)
    if len(uq - TEMPORAL_TOKENS) >= 1:  # "current", "latest" steer ranking; they are not evidence
        uq -= TEMPORAL_TOKENS
    # idf-weighted coverage: a query term that appears nowhere in the project's documents
    # weighs the most, so "who supplies the servers?" is not "answered" by any chunk about suppliers
    n_c = len(chunks)
    df = Counter(t for toks in c_toks for t in set(toks))
    w = {t: math.log(1 + (n_c - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) + 0.3 for t in uq}
    w_total = sum(w.values()) or 1.0
    temporal = bool(TEMPORAL.search(query))
    dated = [d.doc_date for d in docs if d.doc_date]
    newest = max(dated) if dated else None
    hits = []
    for i, c in enumerate(chunks):
        rrf = (1 / (60 + kw_rank[i]) if i in kw_rank else 0) + (1 / (60 + vec_rank[c.id]) if c.id in vec_rank else 0)
        if rrf == 0:
            continue
        coverage = sum(w[t] for t in uq & set(c_toks[i])) / w_total
        d = by_id[c.document_id]
        # rerank: lexical coverage dominates; approved and (for "current" questions) recent documents win ties
        score = rrf * 30 + coverage
        if d.approval_status == "approved":
            score *= 1.08
        elif d.approval_status == "superseded":
            score *= 0.75
        if temporal and newest and d.doc_date:
            age = (newest - d.doc_date).days
            score *= 1.25 if age == 0 else max(0.7, 1.1 - age / 365)
        if c.flagged:
            score *= 0.5
        hits.append(Hit(c, d, score, coverage, bm[i], vec.get(c.id, 0.0), w))
    hits.sort(key=lambda h: -h.score)
    return hits[:k]
