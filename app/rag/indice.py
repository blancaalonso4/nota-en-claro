"""Índice vectorial en disco: embeddings .npy + fragmentos .json + meta.json con huella."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import ConfigRAG
from .corpus import cargar_textos
from .troceado import preparar, trocear_ventana


def _prefijos(encoder: str) -> tuple[str, str]:
    """Los e5 necesitan los prefijos query: / passage:."""
    return ('query: ', 'passage: ') if 'e5' in encoder.lower() else ('', '')


def huella(cfg: ConfigRAG, textos: dict[str, list[str]]) -> str:
    """Huella de textos + parámetros de indexado: si cambia, hay que reindexar."""
    h = hashlib.sha256()
    h.update(json.dumps([cfg.encoder, cfg.ventana_palabras, cfg.solape_palabras]).encode())
    for d in sorted(textos):
        h.update(d.encode())
        h.update('\n\n'.join(textos[d]).encode('utf-8'))
    return h.hexdigest()


@dataclass
class Indice:
    chunks: list[dict]
    embeddings: np.ndarray
    encoder: str
    modelo: object = field(default=None, repr=False)   # SentenceTransformer, carga perezosa
    origen: str = 'construido'                          # 'construido' | 'disco'
    segundos: float = 0.0                               # medido: tiempo de construir o de cargar

    def _encoder(self):
        if self.modelo is None:
            from sentence_transformers import SentenceTransformer
            self.modelo = SentenceTransformer(self.encoder, device='cpu')
        return self.modelo

    def embeber_pregunta(self, pregunta: str) -> np.ndarray:
        pq, _ = _prefijos(self.encoder)
        return self._encoder().encode([pq + pregunta], normalize_embeddings=True, show_progress_bar=False)[0]

    @classmethod
    def construir(cls, cfg: ConfigRAG, textos: dict[str, list[str]]) -> "Indice":
        t0 = time.perf_counter()
        chunks = preparar(trocear_ventana(textos, cfg.ventana_palabras, cfg.solape_palabras))
        idx = cls(chunks, np.zeros((0, 0), dtype=np.float32), cfg.encoder)
        _, pp = _prefijos(cfg.encoder)
        idx.embeddings = idx._encoder().encode([pp + c['texto'] for c in chunks], batch_size=32,
                                               normalize_embeddings=True, show_progress_bar=False)
        idx.segundos = time.perf_counter() - t0
        return idx

    def guardar(self, dir_indice: Path, h: str) -> None:
        d = Path(dir_indice)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / 'embeddings.npy', self.embeddings)
        (d / 'fragmentos.json').write_text(json.dumps(self.chunks, ensure_ascii=False), encoding='utf-8')
        (d / 'meta.json').write_text(
            json.dumps({'huella': h, 'encoder': self.encoder, 'n_fragmentos': len(self.chunks)}), encoding='utf-8')

    @classmethod
    def cargar(cls, dir_indice: Path, encoder: str, h: str):
        d = Path(dir_indice)
        try:
            meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
            if meta.get('huella') != h:
                return None
            t0 = time.perf_counter()
            chunks = json.loads((d / 'fragmentos.json').read_text(encoding='utf-8'))
            emb = np.load(d / 'embeddings.npy')
        except (FileNotFoundError, ValueError, KeyError):
            return None
        return cls(chunks, emb, encoder, origen='disco', segundos=time.perf_counter() - t0)

    @classmethod
    def cargar_o_construir(cls, cfg: ConfigRAG) -> "Indice":
        textos = cargar_textos(cfg.dir_textos)
        h = huella(cfg, textos)
        idx = cls.cargar(cfg.dir_indice, cfg.encoder, h)
        if idx is None:
            idx = cls.construir(cfg, textos)
            idx.guardar(cfg.dir_indice, h)
        return idx
