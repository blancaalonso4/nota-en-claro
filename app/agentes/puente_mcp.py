"""Puente MCP: cliente síncrono sobre los tres servidores (stdio). Streamlit y el agente son síncronos; el SDK es asyncio.

Un hilo con su propio bucle de eventos mantiene abiertas las sesiones con los servidores. Expone:
- `herramientas(nombres)`: esquemas en el formato de herramientas de Ollama (cortos, para ahorrar tokens).
- `llamar(nombre, args)`: llamada de una herramienta AUTOMÁTICA (el modelo nunca llega a las de confirmar/prohibidas).
- `enviar_correo_confirmado(borrador_id, orientador)`: la única vía para enviar, desde el botón de la interfaz.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field

from app.mcp_servers.comun import RAIZ, SEPARADOR_DETALLE

from . import permisos
from .verificador import verificar

SERVIDORES = {'drive': 'app.mcp_servers.mcp_drive', 'calendar': 'app.mcp_servers.mcp_calendar',
              'gmail': 'app.mcp_servers.mcp_gmail'}
PLATAFORMA_DE = {'crear_plantilla_notas': 'drive', 'leer_notas': 'drive', 'guardar_informe': 'drive',
                 'listar_eventos': 'calendar', 'huecos_libres': 'calendar', 'crear_eventos_estudio': 'calendar',
                 'leer_correos_orientador': 'gmail', 'crear_borrador': 'gmail', 'enviar_borrador': 'gmail'}
TIEMPO_MAXIMO_S = 90


@dataclass
class ResultadoLlamada:
    ok: bool
    datos: dict | None = None        # JSON devuelto por la herramienta
    mensaje: str = ''                # mensaje claro para el estudiante si falló
    detalle: str = ''                # detalle técnico para la traza
    reintentos: int = 0              # reintentos que hizo el servidor ante un fallo transitorio
    segundos: float = 0.0
    extra: dict = field(default_factory=dict)


def _stdio(plataforma: str):
    """Fábrica de sesión real: lanza el servidor como subproceso con el mismo intérprete."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    @asynccontextmanager
    async def abrir():
        params = StdioServerParameters(command=sys.executable, args=['-m', SERVIDORES[plataforma]], cwd=str(RAIZ))
        async with stdio_client(params) as (leer, escribir):
            async with ClientSession(leer, escribir) as sesion:
                await sesion.initialize()
                yield sesion
    return abrir


def en_memoria(servidores: dict):
    """Fábricas de sesión en memoria (tests): {plataforma: FastMCP}."""
    from mcp.shared.memory import create_connected_server_and_client_session

    def hacer(mcp):
        @asynccontextmanager
        async def abrir():
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                yield s
        return abrir
    return {p: hacer(m) for p, m in servidores.items()}


class PuenteMCP:
    def __init__(self, fabricas: dict | None = None):
        self.fabricas = fabricas or {p: _stdio(p) for p in SERVIDORES}
        self._sesiones: dict = {}
        self._esquemas: dict[str, dict] = {}
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._hilo: threading.Thread | None = None
        self._listo = threading.Event()
        self._parar: asyncio.Event | None = None
        self._error_inicio: Exception | None = None
        self._cerrojo = threading.Lock()

    # --- ciclo de vida -------------------------------------------------------------------------------------------------
    def iniciar(self) -> None:
        with self._cerrojo:
            if self._hilo is not None:
                return
            self._hilo = threading.Thread(target=self._correr, name='puente-mcp', daemon=True)
            self._hilo.start()
        self._listo.wait(timeout=60)
        if self._error_inicio:
            raise RuntimeError(f'No he podido arrancar los servidores MCP: {self._error_inicio}')

    def _correr(self) -> None:
        self._bucle = asyncio.new_event_loop()
        asyncio.set_event_loop(self._bucle)
        self._bucle.run_until_complete(self._vida())

    async def _vida(self) -> None:
        self._parar = asyncio.Event()
        try:
            async with AsyncExitStack() as pila:
                for p, fabrica in self.fabricas.items():
                    s = await pila.enter_async_context(fabrica())
                    self._sesiones[p] = s
                    for t in (await s.list_tools()).tools:
                        self._esquemas[t.name] = {'description': t.description or '', 'schema': t.inputSchema, 'plataforma': p}
                self._listo.set()
                await self._parar.wait()
        except Exception as e:  # noqa: BLE001
            self._error_inicio = e
            self._listo.set()

    def cerrar(self) -> None:
        if self._bucle and self._parar:
            self._bucle.call_soon_threadsafe(self._parar.set)
        if self._hilo:
            self._hilo.join(timeout=10)
        self._hilo = None

    # --- herramientas para el modelo -------------------------------------------------------------------------------------
    def herramientas(self, nombres) -> list[dict]:
        """Esquemas en formato Ollama. Solo se devuelven las AUTOMÁTICAS que se pidan (nunca enviar_borrador)."""
        self.iniciar()
        out = []
        for n in nombres:
            if permisos.permiso_de(n) != permisos.AUTOMATICO or n not in self._esquemas:
                continue
            e = self._esquemas[n]
            esquema = _ocultar(_sin_titulos(_resolver_refs(e['schema'])))
            desc = e['description'].strip().split('\n')[0]
            out.append({'type': 'function', 'function': {'name': n, 'description': desc, 'parameters': esquema}})
        return out

    # --- llamadas ----------------------------------------------------------------------------------------------------------
    def llamar(self, nombre: str, args: dict | None = None) -> ResultadoLlamada:
        if permisos.permiso_de(nombre) != permisos.AUTOMATICO:
            return ResultadoLlamada(False, mensaje=f'«{nombre}» no se puede ejecutar de forma automática.')
        return self._llamar(nombre, args or {})

    def enviar_correo_confirmado(self, borrador_id: str, orientador: str, cuerpo: str | None = None) -> ResultadoLlamada:
        """Envío tras pulsar «Enviar» en la interfaz. Vuelve a verificar y el servidor comprueba el destinatario.
        `cuerpo` es el texto editado por el estudiante: si llega, es lo que se envía (el servidor actualiza el borrador)."""
        # `orientador` es el correo del destinatario del borrador (el que puso el estudiante); el servidor comprueba que el
        # borrador de Gmail va exactamente a esa dirección
        args = {'borrador_id': borrador_id, 'destinatario': orientador} | ({'cuerpo': cuerpo} if cuerpo is not None else {})
        v = verificar('enviar_borrador', args, orientador=orientador, confirmado_por_usuario=True)
        if not v.ok:
            return ResultadoLlamada(False, mensaje=str(v))
        return self._llamar('enviar_borrador', args | {'confirmado': True})

    def _llamar(self, nombre: str, args: dict) -> ResultadoLlamada:
        self.iniciar()
        if nombre not in self._esquemas:
            return ResultadoLlamada(False, mensaje=f'«{nombre}» no existe en ningún servidor.')
        t0 = time.perf_counter()
        try:
            fut = asyncio.run_coroutine_threadsafe(self._ir(nombre, args), self._bucle)
            r = fut.result(timeout=TIEMPO_MAXIMO_S)
        except Exception as e:  # noqa: BLE001  (servidor caído, tiempo agotado...)
            return ResultadoLlamada(False, mensaje='No he podido hablar con el servicio de Google. Inténtalo de nuevo.',
                                    detalle=f'{type(e).__name__}: {e}', segundos=time.perf_counter() - t0)
        r.segundos = round(time.perf_counter() - t0, 2)
        return r

    async def _ir(self, nombre: str, args: dict) -> ResultadoLlamada:
        sesion = self._sesiones[self._esquemas[nombre]['plataforma']]
        res = await asyncio.wait_for(sesion.call_tool(nombre, args), timeout=TIEMPO_MAXIMO_S - 5)
        texto = res.content[0].text if res.content else ''
        if res.isError:
            texto = texto.removeprefix(f'Error executing tool {nombre}: ')
            mensaje, _, detalle = texto.partition(SEPARADOR_DETALLE)
            return ResultadoLlamada(False, mensaje=mensaje.strip(), detalle=detalle.strip())
        datos = getattr(res, 'structuredContent', None)
        if datos is None:
            try:
                datos = json.loads(texto)
            except ValueError:
                datos = {'texto': texto}
        datos = datos.get('result', datos) if isinstance(datos, dict) and set(datos) == {'result'} else datos
        return ResultadoLlamada(True, datos=datos, reintentos=int(datos.get('reintentos', 0)) if isinstance(datos, dict) else 0)


# Campos que añade el programa con los datos del estudiante: el modelo ni los ve ni puede proponerlos.
OCULTOS_AL_MODELO = ('destinatario', 'remitente')


def _ocultar(esquema: dict) -> dict:
    props = {k: v for k, v in (esquema.get('properties') or {}).items() if k not in OCULTOS_AL_MODELO}
    out = {**esquema, 'properties': props}
    if 'required' in esquema:
        out['required'] = [k for k in esquema['required'] if k not in OCULTOS_AL_MODELO]
    return out


def _sin_titulos(esquema):
    """Quita los «title» del JSON Schema (ahorran tokens y no aportan nada al modelo)."""
    if isinstance(esquema, dict):
        return {k: _sin_titulos(v) for k, v in esquema.items() if k != 'title'}
    if isinstance(esquema, list):
        return [_sin_titulos(x) for x in esquema]
    return esquema


def _resolver_refs(esquema: dict) -> dict:
    """Sustituye cada {"$ref": "#/$defs/X"} por su definición y quita $defs."""
    defs = esquema.get('$defs', {})

    def r(x):
        if isinstance(x, dict):
            if '$ref' in x and x['$ref'].startswith('#/$defs/'):
                return r(defs[x['$ref'].split('/')[-1]])
            return {k: r(v) for k, v in x.items() if k != '$defs'}
        if isinstance(x, list):
            return [r(v) for v in x]
        return x
    return r(esquema)
