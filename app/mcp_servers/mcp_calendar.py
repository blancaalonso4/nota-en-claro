"""Servidor MCP de Calendar (FastMCP, stdio).

Permisos mínimos: calendar.app.created (un calendario secundario «Nota en Claro · Estudio» creado por la app: aquí
se lee y se escribe) y calendar.events.freebusy (del calendario principal solo se ve ocupado/libre, sin títulos).
Herramientas: listar_eventos, huecos_libres, crear_eventos_estudio. Nunca se añaden invitados ni se borra nada.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from app.agentes.verificador import MAX_EVENTOS, a_datetime, a_fecha

from . import comun
from .comun import ErrorGoogle, convertir_errores, limpiar_texto, llamar

NOMBRE_CALENDARIO = 'Nota en Claro · Estudio'
INICIO_DIA, FIN_DIA = 8, 22          # ventana de estudio de cada día (hora local)
MIN_HUECO_MIN, MAX_HUECOS = 30, 30   # no se devuelven huecos de menos de 30 min ni más de 30 (ahorra tokens al modelo)


class Evento(BaseModel):
    """Una sesión de estudio. Los campos que no estén aquí (invitados, etc.) se descartan al recibir la llamada."""
    titulo: str
    inicio: str      # ISO 8601, por ejemplo 2026-12-02T16:00:00
    fin: str
    descripcion: str | None = None


class ApiCalendar:
    def __init__(self):
        self._cal = None

    @property
    def cal(self):
        self._cal = self._cal or comun.servicio('calendar', 'calendar', 'v3')
        return self._cal


# --- lógica pura (probada sin Google) ---------------------------------------------------------------------------------

def calcular_huecos(ocupado: list[tuple[datetime, datetime]], desde: datetime, hasta: datetime, ahora: datetime,
                    zona: str, inicio_dia: int = INICIO_DIA, fin_dia: int = FIN_DIA,
                    minimo: int = MIN_HUECO_MIN, maximo: int = MAX_HUECOS) -> list[dict]:
    """Intervalos libres dentro de la ventana de estudio de cada día, sin pasado, sin huecos cortos."""
    tz = ZoneInfo(zona)
    ocupado = sorted((a.astimezone(tz), b.astimezone(tz)) for a, b in ocupado)
    desde, hasta = max(desde.astimezone(tz), ahora.astimezone(tz)), hasta.astimezone(tz)
    huecos: list[dict] = []
    dia = desde.date()
    while dia <= hasta.date() and len(huecos) < maximo:
        ini = max(datetime.combine(dia, time(inicio_dia), tzinfo=tz), desde)
        fin = min(datetime.combine(dia, time(fin_dia), tzinfo=tz), hasta)
        cursor = ini
        for a, b in ocupado:
            if b <= cursor or a >= fin:
                continue
            if a > cursor and (a - cursor) >= timedelta(minutes=minimo):
                huecos.append((cursor, a))
            cursor = max(cursor, b)
        if fin > cursor and (fin - cursor) >= timedelta(minutes=minimo):
            huecos.append((cursor, fin))
        dia += timedelta(days=1)
    return [{'inicio': a.isoformat(), 'fin': b.isoformat()} for a, b in huecos[:maximo]]


def _cuerpo_evento(ev: dict, zona: str) -> dict:
    """Cuerpo del evento construido campo a campo: no existe forma de que entren invitados ni otros campos."""
    ini, fin = a_datetime(ev['inicio'], zona), a_datetime(ev['fin'], zona)
    if fin <= ini:
        raise ErrorGoogle('El fin de un evento debe ser posterior a su inicio.')
    cuerpo = {'summary': limpiar_texto(ev.get('titulo'), 80) or 'Estudio',
              'start': {'dateTime': ini.isoformat(), 'timeZone': zona},
              'end': {'dateTime': fin.isoformat(), 'timeZone': zona}}
    if ev.get('descripcion'):
        cuerpo['description'] = limpiar_texto(ev['descripcion'], 300)
    return cuerpo


# --- servidor ---------------------------------------------------------------------------------------------------------

def construir(api=None, estado_fn=comun.leer_estado, guardar_fn=comun.guardar_estado, ahora_fn=None) -> FastMCP:
    api = api or ApiCalendar()
    mcp = FastMCP('nota-en-claro-calendar')

    def ahora() -> datetime:
        return ahora_fn() if ahora_fn else datetime.now(ZoneInfo(comun.zona_horaria()))

    def asegurar_calendario() -> tuple[str, int]:
        """Id del calendario de la app; lo crea si no existe. Devuelve (id, reintentos)."""
        cal_id = estado_fn().get('calendario_id')
        total = 0
        if cal_id:
            try:
                api.cal.calendars().get(calendarId=cal_id).execute()
                return cal_id, 0
            except Exception:  # noqa: BLE001  (borrado o inaccesible: se crea de nuevo)
                pass
        c, n = llamar(lambda: api.cal.calendars().insert(
            body={'summary': NOMBRE_CALENDARIO, 'timeZone': comun.zona_horaria()}).execute())
        guardar_fn(calendario_id=c['id'])
        return c['id'], total + n

    @mcp.tool()
    @convertir_errores
    def listar_eventos(desde: str, hasta: str) -> dict:
        """Lista los eventos de estudio del calendario «Nota en Claro · Estudio» entre dos fechas (AAAA-MM-DD o ISO)."""
        zona = comun.zona_horaria()
        d, h = a_fecha(desde, zona), a_fecha(hasta, zona)
        cal_id, n0 = asegurar_calendario()
        r, n = llamar(lambda: api.cal.events().list(calendarId=cal_id, timeMin=d.isoformat(), timeMax=h.isoformat(),
                                                    singleEvents=True, orderBy='startTime', maxResults=50).execute())
        eventos = [{'titulo': limpiar_texto(e.get('summary'), 80),
                    'inicio': e.get('start', {}).get('dateTime', e.get('start', {}).get('date', '')),
                    'fin': e.get('end', {}).get('dateTime', e.get('end', {}).get('date', ''))} for e in r.get('items', [])]
        return {'eventos': eventos, 'reintentos': n0 + n}

    @mcp.tool()
    @convertir_errores
    def huecos_libres(desde: str, hasta: str) -> dict:
        """Huecos libres para estudiar entre dos fechas, de 8:00 a 22:00, mirando el calendario principal (solo
        ocupado/libre) y el de estudio. Devuelve intervalos ISO."""
        zona = comun.zona_horaria()
        d, h = a_fecha(desde, zona), a_fecha(hasta, zona)
        cal_id, n0 = asegurar_calendario()
        cuerpo = {'timeMin': d.isoformat(), 'timeMax': h.isoformat(), 'timeZone': zona,
                  'items': [{'id': 'primary'}, {'id': cal_id}]}
        r, n = llamar(lambda: api.cal.freebusy().query(body=cuerpo).execute())
        ocupado = []
        for cal, datos in r.get('calendars', {}).items():
            if datos.get('errors'):
                raise ErrorGoogle('No he podido consultar si estás libre en uno de tus calendarios.',
                                  detalle=f'freebusy {cal}: {datos["errors"]}')
            ocupado += [(a_datetime(b['start'], zona), a_datetime(b['end'], zona)) for b in datos.get('busy', [])]
        return {'huecos': calcular_huecos(ocupado, d, h, ahora(), zona), 'reintentos': n0 + n}

    @mcp.tool()
    @convertir_errores
    def crear_eventos_estudio(eventos: list[Evento]) -> dict:
        """Crea eventos de estudio (titulo, inicio, fin en ISO) en el calendario «Nota en Claro · Estudio». Sin invitados."""
        if not eventos or len(eventos) > MAX_EVENTOS:
            raise ErrorGoogle(f'Hay que crear entre 1 y {MAX_EVENTOS} eventos por llamada.')
        zona = comun.zona_horaria()
        cuerpos = []
        for ev in eventos:
            try:
                cuerpos.append(_cuerpo_evento(ev.model_dump(), zona))
            except (KeyError, ValueError, TypeError) as e:
                raise ErrorGoogle('Un evento tiene fechas no válidas (usa ISO 8601).', detalle=str(e)) from e
        cal_id, total = asegurar_calendario()
        creados = []
        for c in cuerpos:
            r, n = llamar(lambda c=c: api.cal.events().insert(calendarId=cal_id, body=c, sendUpdates='none').execute())
            total += n
            creados.append({'id': r.get('id', ''), 'titulo': c['summary'], 'inicio': c['start']['dateTime'],
                            'fin': c['end']['dateTime'], 'url': r.get('htmlLink', '')})
        return {'creados': creados, 'reintentos': total}

    return mcp


if __name__ == '__main__':
    construir().run(transport='stdio')
