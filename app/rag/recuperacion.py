"""Búsqueda por coseno y reordenador opcional (cross-encoder)."""
from __future__ import annotations

import numpy as np

from .indice import Indice


def buscar(indice: Indice, pregunta: str) -> tuple[list[int], np.ndarray]:
    """Devuelve (orden de fragmentos por similitud descendente, similitudes)."""
    q = indice.embeber_pregunta(pregunta)
    sims = indice.embeddings @ q
    return list(np.argsort(-sims, kind='stable')), sims


class Reordenador:
    """Cross-encoder opcional; el modelo se carga la primera vez que se usa."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self._modelo = None

    def reordenar(self, pregunta: str, ids: list[int], chunks: list[dict]) -> list[int]:
        if self._modelo is None:
            from sentence_transformers import CrossEncoder
            self._modelo = CrossEncoder(self.nombre, device='cpu', max_length=512)
        p = self._modelo.predict([(pregunta, chunks[i]['texto']) for i in ids], show_progress_bar=False)
        return [ids[j] for j in np.argsort(-np.asarray(p), kind='stable')]
