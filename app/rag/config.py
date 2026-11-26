"""Configuración del RAG y semillas. Sin estado global: todo cuelga de ConfigRAG."""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ConfigRAG:
    dir_textos: Path = RAIZ / "data" / "texto"
    manifiesto: Path = RAIZ / "data" / "manifiesto.csv"
    preguntas: Path = RAIZ / "data" / "eval" / "preguntas.json"
    dir_indice: Path = RAIZ / "data" / "indice"
    encoder: str = "intfloat/multilingual-e5-small"
    reordenador: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    usar_reordenador: bool = False
    ventana_palabras: int = 250
    solape_palabras: int = 35
    k: int = 3
    n_candidatos: int = 20
    modelo: str = "qwen3:8b"
    num_predict: int = 300
    num_ctx: int = 4096
    semilla: int = 42
    temperature: float = 0.0
    think: bool = False


def fijar_semillas(semilla: int = 42) -> None:
    """Fija random, numpy y torch (si está instalado)."""
    os.environ.setdefault("PYTHONHASHSEED", str(semilla))
    random.seed(semilla)
    np.random.seed(semilla)
    try:
        import torch
        torch.manual_seed(semilla)
    except ImportError:
        pass
