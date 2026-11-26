"""Carga de los textos limpios y del manifiesto."""
from __future__ import annotations

import csv
from pathlib import Path


def cargar_textos(dir_textos: Path) -> dict[str, list[str]]:
    """doc_id -> lista de páginas (las páginas se separan por línea en blanco doble, como las guardó el Caso III)."""
    textos = {}
    for f in sorted(Path(dir_textos).glob("doc*.txt")):
        textos[f.stem] = f.read_text(encoding="utf-8").split("\n\n")
    return textos


def cargar_manifiesto(ruta: Path) -> dict[str, dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        return {fila["doc_id"]: fila for fila in csv.DictReader(fh)}
