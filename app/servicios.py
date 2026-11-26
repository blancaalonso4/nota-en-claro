"""Construcción de los servicios que usa la interfaz (RAG, puente MCP, orquestador) y estado de la parte de Google.

Está separado de `interfaz.py` para poder sustituirlo por falsos en las pruebas de la interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agentes.acciones import AgenteAcciones
from app.agentes.coordinador import Coordinador, Orquestador
from app.agentes.puente_mcp import PuenteMCP
from app.agentes.traza import Traza
from app.mcp_servers import comun
from app.rag.config import ConfigRAG


@dataclass
class Recursos:
    """Lo pesado, compartido entre sesiones del navegador: el RAG (índice y modelos cargados) y el puente MCP."""
    rag: object
    puente: object
    cfg: ConfigRAG


def crear_recursos() -> Recursos:
    from app.rag.pipeline import SistemaRAG
    cfg = ConfigRAG()
    rag = SistemaRAG(cfg)
    rag.calentar()
    return Recursos(rag, PuenteMCP(), cfg)       # el puente arranca los servidores MCP al primer uso


def orientador() -> str | None:
    try:
        return comun.orientador()
    except comun.ErrorGoogle:
        return None


def crear_orquestador(recursos: Recursos, traza: Traza) -> Orquestador:
    coord = Coordinador(traza, recursos.cfg)
    acciones = AgenteAcciones(recursos.puente, traza, recursos.cfg, orientador=orientador(), zona=comun.zona_horaria())
    return Orquestador(coord, traza, rag=recursos.rag, acciones=acciones, puente=recursos.puente)


def estado_google() -> dict:
    """¿Está lista la parte de Google? Solo mira archivos y .env; no llama a Google."""
    tokens = {p: comun.ruta_token(p).exists() for p in comun.SCOPES}
    ori = orientador()
    return {'credenciales': comun.CREDENCIALES.exists(), 'tokens': tokens, 'orientador': ori,
            'lista': comun.CREDENCIALES.exists() and all(tokens.values()) and ori is not None,
            'hoja_notas_id': comun.leer_estado().get('hoja_notas_id')}
