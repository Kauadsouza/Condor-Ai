"""
Armazenamento vetorial para busca semântica.
Usa ChromaDB se disponível, senão fallback para busca por palavras-chave.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("condor.memory.vector")

try:
    import chromadb
    _CHROMA = True
except ImportError:
    _CHROMA = False
    log.warning("chromadb não instalado. Busca semântica desativada. Instale: pip install chromadb")


class VectorStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._client = None
        self._collection = None
        self._available = False

        if _CHROMA:
            try:
                self._client = chromadb.PersistentClient(path=path)
                self._collection = self._client.get_or_create_collection(
                    name="condor_memory",
                    metadata={"hnsw:space": "cosine"},
                )
                self._available = True
                log.info("ChromaDB iniciado em %s (%d docs)", path, self._collection.count())
            except Exception as exc:
                log.error("Erro ao iniciar ChromaDB: %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        if not self._available:
            return
        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata or {}],
            )
        except Exception as exc:
            log.error("Erro ao adicionar documento: %s", exc)

    def search(self, query: str, n: int = 5) -> list[dict]:
        if not self._available:
            return []
        try:
            results = self._collection.query(query_texts=[query], n_results=min(n, max(1, self._collection.count())))
            out = []
            for i, doc in enumerate(results["documents"][0]):
                out.append({
                    "id": results["ids"][0][i],
                    "text": doc,
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                })
            return out
        except Exception as exc:
            log.error("Erro na busca vetorial: %s", exc)
            return []

    def count(self) -> int:
        if not self._available or self._collection is None:
            return 0
        return self._collection.count()
