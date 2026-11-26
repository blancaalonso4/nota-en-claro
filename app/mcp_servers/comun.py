"""Piezas comunes de los tres servidores MCP: scopes, credenciales, estado, reintento y errores.

Los servidores hablan por stdio: NUNCA se imprime en stdout (rompería el protocolo); los avisos van a stderr.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
CREDENCIALES = RAIZ / 'credentials.json'
DIR_ESTADO = RAIZ / 'estado'
ARCHIVO_ESTADO = DIR_ESTADO / 'google.json'

# Permisos mínimos por plataforma (nombres comprobados en la documentación de Google el 2026-11-26).
SCOPES: dict[str, list[str]] = {
    'drive': ['https://www.googleapis.com/auth/drive.file'],
    'calendar': ['https://www.googleapis.com/auth/calendar.app.created',
                 'https://www.googleapis.com/auth/calendar.events.freebusy'],
    'gmail': ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.compose'],
}
COMANDO_AUTORIZAR = 'python -m app.mcp_servers.autorizar'

load_dotenv(RAIZ / '.env')


class ErrorGoogle(Exception):
    """Error con un mensaje claro para el estudiante. `detalle` va a la traza."""

    def __init__(self, mensaje: str, detalle: str = '', transitorio: bool = False):
        super().__init__(mensaje)
        self.detalle, self.transitorio = detalle, transitorio


def ruta_token(plataforma: str) -> Path:
    return RAIZ / f'token_{plataforma}.json'


def credenciales(plataforma: str):
    """Credenciales de UNA plataforma (cada servidor solo carga su token). Renueva el token si hace falta."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    ruta = ruta_token(plataforma)
    if not ruta.exists():
        raise ErrorGoogle(f'Falta la autorización de Google para {plataforma}. Ejecuta: {COMANDO_AUTORIZAR}')
    cred = Credentials.from_authorized_user_file(str(ruta), SCOPES[plataforma])
    if not cred.valid:
        try:
            cred.refresh(Request())
        except RefreshError as e:
            raise ErrorGoogle('La autorización de Google ha caducado o se ha revocado (en modo prueba dura 7 días). '
                              f'Vuelve a autorizar con: {COMANDO_AUTORIZAR}', detalle=str(e)) from e
        ruta.write_text(cred.to_json(), encoding='utf-8')
    return cred


def servicio(plataforma: str, api: str, version: str):
    from googleapiclient.discovery import build
    return build(api, version, credentials=credenciales(plataforma), cache_discovery=False)


# --- estado no secreto (ids de la hoja, carpeta y calendario) -------------------------------------------------------

def leer_estado() -> dict:
    try:
        return json.loads(ARCHIVO_ESTADO.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def guardar_estado(**cambios) -> None:
    estado = {**leer_estado(), **cambios}
    DIR_ESTADO.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVO_ESTADO.with_suffix('.tmp')
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, ARCHIVO_ESTADO)


# --- configuración de .env -------------------------------------------------------------------------------------------

_RE_CORREO = re.compile(r'^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$')


def orientador() -> str:
    c = os.environ.get('ORIENTADOR_EMAIL', '').strip()
    if not _RE_CORREO.match(c):
        raise ErrorGoogle('Falta un ORIENTADOR_EMAIL válido en el archivo .env (mira .env.example).')
    return c


def zona_horaria() -> str:
    return os.environ.get('ZONA_HORARIA', 'Europe/Madrid').strip() or 'Europe/Madrid'


# --- errores y reintento ---------------------------------------------------------------------------------------------

def _estado_http(e: Exception) -> int | None:
    r = getattr(e, 'resp', None)
    try:
        return int(r.status) if r is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def es_transitorio(e: Exception) -> bool:
    """Red caída, tiempo agotado, 429 o 5xx: tiene sentido reintentar una vez."""
    if isinstance(e, ErrorGoogle):
        return e.transitorio
    s = _estado_http(e)
    if s is not None:
        return s == 429 or s >= 500
    return isinstance(e, (TimeoutError, ConnectionError, OSError)) or type(e).__name__ in ('HttpLib2Error', 'ServerNotFoundError')


def traducir(e: Exception, reintentos: int) -> ErrorGoogle:
    s = _estado_http(e)
    detalle = f'{type(e).__name__} http={s} reintentos={reintentos}: {str(e)[:200]}'
    if es_transitorio(e):
        return ErrorGoogle('Google no responde ahora mismo (ya lo he intentado dos veces). Inténtalo de nuevo en unos minutos.',
                           detalle, True)
    if s in (401, 403):
        return ErrorGoogle('Google ha rechazado la petición: faltan permisos o la API no está activada en el proyecto. '
                           f'Si acabas de cambiar permisos, vuelve a autorizar con: {COMANDO_AUTORIZAR}', detalle)
    if s == 404:
        return ErrorGoogle('No he encontrado ese elemento en Google (¿se ha borrado o movido?).', detalle)
    if s == 400:
        return ErrorGoogle('Google no ha aceptado los datos de la petición.', detalle)
    return ErrorGoogle('Ha fallado la llamada a Google.', detalle)


def llamar(fn: Callable[[], Any], *, reintentos: int = 1, espera: float = 1.0,
           dormir: Callable[[float], None] = time.sleep) -> tuple[Any, int]:
    """Ejecuta `fn`; si el fallo es transitorio lo repite UNA vez. Devuelve (resultado, reintentos_usados).
    Cualquier otro fallo (o el segundo) sale como ErrorGoogle con un mensaje claro."""
    usados = 0
    while True:
        try:
            return fn(), usados
        except ErrorGoogle:
            raise
        except Exception as e:  # noqa: BLE001
            if es_transitorio(e) and usados < reintentos:
                usados += 1
                dormir(espera)
                continue
            raise traducir(e, usados) from e


def limpiar_texto(s, maximo: int) -> str:
    """Texto de una celda, correo o título que llega al modelo: sin saltos, controles ni marcas de etiqueta."""
    s = re.sub(r'[\x00-\x1f<>{}\[\]"`]', ' ', str(s or ''))
    return re.sub(r'\s+', ' ', s).strip()[:maximo]


SEPARADOR_DETALLE = ' | detalle: '


def convertir_errores(fn):
    """Decorador de herramientas MCP: un ErrorGoogle sale como error de herramienta con el mensaje claro y, tras
    ' | detalle: ', el detalle técnico para la traza (el puente los separa)."""
    import functools
    import sys

    @functools.wraps(fn)
    def envuelta(*a, **k):
        try:
            return fn(*a, **k)
        except ErrorGoogle as e:
            print(f'[{fn.__name__}] {e} {e.detalle}', file=sys.stderr)
            raise ValueError(f'{e}{SEPARADOR_DETALLE}{e.detalle}' if e.detalle else str(e)) from None
    return envuelta
