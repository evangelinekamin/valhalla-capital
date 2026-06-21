from __future__ import annotations

import structlog

log = structlog.get_logger()

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        log.info("loading_embedding_model", model="all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        log.info("embedding_model_loaded", dimensions=384)
    return _model


def get_embedding(text: str) -> list[float]:
    model = _get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def get_embeddings(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return [emb.tolist() for emb in embeddings]
