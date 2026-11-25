"""Ingestion: parse -> chunk -> embed -> store. Embedding and vector store sit behind
small interfaces so a neural model or pgvector/Qdrant can replace the defaults."""
from __future__ import annotations

import zlib
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as m
from . import parsers
from .text import detect_language, looks_like_injection, normalize, sentences, tokens

DIM = 512


class EmbeddingProvider:
    name = "base"

    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class LocalHashEmbedding(EmbeddingProvider):
    """Runs fully on-premises with no model download: hashed bag of bilingual
    concepts + character trigrams (robust to Arabic morphology), L2-normalised."""
    name = "local-hash-v1"

    def embed(self, texts):
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokens(t):
                out[i, zlib.crc32(tok.encode()) % DIM] += 1.0
                if len(tok) > 3:
                    for j in range(len(tok) - 2):
                        out[i, zlib.crc32(("#" + tok[j:j + 3]).encode()) % DIM] += 0.35
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class SentenceTransformerEmbedding(EmbeddingProvider):
    """Optional local neural embeddings (set ai.embedding_model to a local model path/name)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # optional dependency
        self.model = SentenceTransformer(model_name)
        self.name = model_name

    def embed(self, texts):
        return np.asarray(self.model.encode(texts, normalize_embeddings=True), dtype=np.float32)


_provider: EmbeddingProvider | None = None


def get_embedder(model_name: str = "local-hash-v1") -> EmbeddingProvider:
    global _provider
    if _provider is None or _provider.name != model_name:
        if model_name == "local-hash-v1":
            _provider = LocalHashEmbedding()
        else:
            try:
                _provider = SentenceTransformerEmbedding(model_name)
            except Exception:
                _provider = LocalHashEmbedding()
    return _provider


class SqlVectorStore:
    """Vectors live beside the chunks in the main database, keyed by project_id.
    Search is exact cosine over the caller's *already authorised* chunk ids."""

    def upsert(self, db: Session, rows: list[tuple[int, int, np.ndarray]], model: str):
        for chunk_id, project_id, vec in rows:
            db.add(m.Embedding(chunk_id=chunk_id, project_id=project_id, model=model, vector=vec.tobytes()))

    def search(self, db: Session, project_id: int, chunk_ids: list[int], qvec: np.ndarray, k: int):
        if not chunk_ids:
            return []
        rows = db.execute(select(m.Embedding.chunk_id, m.Embedding.vector).where(
            m.Embedding.project_id == project_id, m.Embedding.chunk_id.in_(chunk_ids))).all()
        rows = [r for r in rows if len(r[1]) == qvec.nbytes]
        if not rows:
            return []
        mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1)
        sims = mat @ qvec
        order = np.argsort(-sims)[:k]
        return [(rows[i][0], float(sims[i])) for i in order]


vector_store = SqlVectorStore()


def chunk_segments(segs: list[parsers.Segment], max_chars: int = 900) -> list[dict]:
    chunks = []

    def add(page, section, text, kind):
        text = text.strip()
        if text:
            chunks.append({"page": page, "section": section, "text": text, "kind": kind})

    for s in segs:
        if s.kind == "table":
            lines = s.text.split("\n")
            if len(s.text) <= 1500:
                add(s.page, s.section, s.text, "table")
            else:  # long table: repeat the header in each piece
                head, buf = lines[0], []
                for ln in lines[1:]:
                    buf.append(ln)
                    if sum(map(len, buf)) > 1100:
                        add(s.page, s.section, "\n".join([head] + buf), "table")
                        buf = []
                if buf:
                    add(s.page, s.section, "\n".join([head] + buf), "table")
            continue
        if len(s.text) <= max_chars:
            add(s.page, s.section, s.text, "text")
            continue
        buf, size, prev = [], 0, ""
        for sent in sentences(s.text):
            if size + len(sent) > max_chars and buf:
                add(s.page, s.section, " ".join(buf), "text")
                buf, size = ([prev] if prev else []), len(prev)  # one-sentence overlap
            buf.append(sent)
            size += len(sent)
            prev = sent
        if buf:
            add(s.page, s.section, " ".join(buf), "text")
    # merge tiny neighbours in the same section/page so a lone line keeps its context
    merged = []
    for c in chunks:
        if (merged and c["kind"] == "text" and merged[-1]["kind"] == "text" and merged[-1]["page"] == c["page"]
                and merged[-1]["section"] == c["section"] and len(merged[-1]["text"]) + len(c["text"]) < 500):
            merged[-1]["text"] += "\n" + c["text"]
        else:
            merged.append(c)
    return merged


def index_document(db: Session, doc: m.Document, model_name: str = "local-hash-v1") -> int:
    """(Re)index the current version of a document. Older versions keep their own chunks."""
    ver = next((v for v in doc.versions if v.version == doc.current_version), None)
    if ver is None:
        raise parsers.ParseError("Document has no stored version")
    doc.processing_status = "processing"
    db.flush()
    try:
        segs = parsers.parse(Path(ver.storage_path), ver.filename)
        if not segs:
            raise parsers.ParseError("No readable text was found in this file.")
    except parsers.ParseError as e:
        doc.processing_status, doc.processing_error = "failed", str(e)
        db.flush()
        raise
    old = list(db.scalars(select(m.DocumentChunk.id).where(
        m.DocumentChunk.document_id == doc.id, m.DocumentChunk.version == ver.version)))
    if old:
        db.execute(delete(m.Embedding).where(m.Embedding.chunk_id.in_(old)))
        db.execute(delete(m.DocumentChunk).where(m.DocumentChunk.id.in_(old)))
    chunks = chunk_segments(segs)
    rows = []
    for i, c in enumerate(chunks):
        ctx = f"{doc.name} › {c['section']}" if c["section"] else doc.name
        row = m.DocumentChunk(project_id=doc.project_id, document_id=doc.id, version=ver.version, ordinal=i,
                              page=c["page"], section=c["section"][:300], kind=c["kind"], text=c["text"],
                              context=ctx[:400], flagged=looks_like_injection(c["text"]))
        db.add(row)
        rows.append(row)
    db.flush()
    emb = get_embedder(model_name)
    vecs = emb.embed([f"{r.context}\n{r.text}" for r in rows])
    vector_store.upsert(db, [(r.id, doc.project_id, v) for r, v in zip(rows, vecs)], emb.name)
    doc.pages = max((c["page"] for c in chunks), default=0)
    doc.language = doc.language or detect_language(" ".join(c["text"] for c in chunks[:20]))
    doc.processing_status, doc.processing_error = "indexed", None
    doc.embedding_model, doc.last_indexed = emb.name, datetime.utcnow()
    db.flush()
    return len(rows)


__all__ = ["index_document", "chunk_segments", "get_embedder", "vector_store", "normalize"]
