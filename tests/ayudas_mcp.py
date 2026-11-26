"""Ayudas para probar servidores MCP en memoria con servicios de Google falsos."""
import asyncio
import json
from unittest.mock import MagicMock

from mcp.shared.memory import create_connected_server_and_client_session


class ErrorHttpFalso(Exception):
    """Imita googleapiclient.errors.HttpError: lo que importa es .resp.status."""

    def __init__(self, status):
        super().__init__(f'HttpError {status}')
        self.resp = MagicMock(status=status)


def llamar_herramienta(mcp, nombre, args=None):
    """Llama a una herramienta por el protocolo MCP (en memoria). Devuelve (es_error, contenido): dict si es JSON."""
    async def _ir():
        async with create_connected_server_and_client_session(mcp._mcp_server) as c:
            return await c.call_tool(nombre, args or {})
    r = asyncio.run(_ir())
    texto = r.content[0].text if r.content else ''
    try:
        return r.isError, json.loads(texto)
    except ValueError:
        return r.isError, texto


def herramientas(mcp):
    async def _ir():
        async with create_connected_server_and_client_session(mcp._mcp_server) as c:
            return await c.list_tools()
    return {t.name: t for t in asyncio.run(_ir()).tools}
