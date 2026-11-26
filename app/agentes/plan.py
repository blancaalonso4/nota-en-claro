"""Plan de estudio: el modelo elige hueco, asignatura y duración; Python calcula las fechas. Python puro, sin modelo.

El modelo de 4B escribía mal las fechas (sesiones que empezaban en el pasado) y el agente se rendía. Ahora no escribe
ninguna: recibe los huecos libres numerados y propone sesiones como (id del hueco, asignatura, minutos). Aquí se colocan
una detrás de otra dentro de cada hueco, se comprueba que caben y se devuelven los eventos con sus fechas exactas.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta

DURACIONES = (60, 90, 120)
MAX_SESIONES = 6
PREFIJO_TITULO = 'Estudio: '

ESQUEMA_PLANIFICAR = {
    'type': 'function',
    'function': {
        'name': 'planificar_sesiones',
        'description': ('Reparte sesiones de estudio en los huecos libres numerados. No escribas fechas ni horas: '
                        'solo el número del hueco, la asignatura y los minutos; el programa calcula las horas.'),
        'parameters': {
            'type': 'object',
            'properties': {'sesiones': {'type': 'array', 'items': {
                'type': 'object',
                'properties': {'hueco': {'type': 'integer', 'description': 'número del hueco libre (el «id» de la lista)'},
                               'asignatura': {'type': 'string', 'description': 'nombre de la asignatura'},
                               'minutos': {'type': 'integer', 'enum': list(DURACIONES)}},
                'required': ['hueco', 'asignatura', 'minutos']}}},
            'required': ['sesiones']}}}


def _norm(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', str(t).casefold()) if unicodedata.category(c) != 'Mn').strip()


def _entero(v):
    """Acepta 3 o «3» (los modelos pequeños a veces citan los números); rechaza bool, decimales y texto."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def asignatura_canonica(texto, asignaturas: list[str] | None) -> str | None:
    """Nombre de la asignatura tal como está en la hoja. Sin lista de asignaturas se acepta el texto limpio.
    Con lista: coincidencia exacta o, si no, una única asignatura que contenga el texto o esté contenida en él."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    if not asignaturas:
        return texto.strip()[:60]
    n = _norm(texto)
    for a in asignaturas:
        if _norm(a) == n:
            return a
    parecidas = [a for a in asignaturas if n in _norm(a) or _norm(a) in n]
    return parecidas[0] if len(parecidas) == 1 else None


def _etiqueta(h: dict) -> str:
    return f"{h['id']} ({h.get('dia', '')} {h.get('inicio_hora', '')}-{h.get('fin_hora', '')})"


def construir_eventos(sesiones, huecos: list[dict], asignaturas: list[str] | None = None,
                      ahora: datetime | None = None) -> tuple[list[dict], list[str]]:
    """(eventos, errores). Si hay algún error no se devuelve ningún evento: el modelo corrige la lista entera.

    Cada evento es {'titulo', 'inicio', 'fin'} en ISO 8601 con zona. Las sesiones de un mismo hueco se colocan
    seguidas, en el orden en que llegan, empezando al principio del hueco."""
    errores: list[str] = []
    if not isinstance(sesiones, list) or not sesiones:
        return [], ['«sesiones» debe ser una lista con al menos una sesión (hueco, asignatura, minutos)']
    if len(sesiones) > MAX_SESIONES:
        return [], [f'máximo {MAX_SESIONES} sesiones']
    por_id = {h['id']: h for h in huecos if isinstance(h.get('id'), int)}
    cursor: dict[int, datetime] = {}
    eventos: list[dict] = []
    for i, s in enumerate(sesiones, 1):
        n = f'sesión {i}'
        if not isinstance(s, dict):
            errores.append(f'{n}: debe ser un objeto con hueco, asignatura y minutos')
            continue
        raros = set(s) - {'hueco', 'asignatura', 'minutos'}
        if raros:
            errores.append(f'{n}: campos no permitidos {sorted(raros)}; solo hueco, asignatura y minutos (sin fechas)')
        hid, minutos = _entero(s.get('hueco')), _entero(s.get('minutos'))
        asig = asignatura_canonica(s.get('asignatura'), asignaturas)
        if asig is None:
            posibles = f' Las de tu hoja: {", ".join(asignaturas)}.' if asignaturas else ''
            errores.append(f'{n}: asignatura no válida.{posibles}')
        if minutos not in DURACIONES:
            errores.append(f'{n}: «minutos» debe ser 60, 90 o 120')
        if hid not in por_id:
            errores.append(f'{n}: el hueco {s.get("hueco")!r} no existe; usa un número de la lista (1 a {max(por_id, default=0)})')
        if asig is None or minutos not in DURACIONES or hid not in por_id:
            continue
        h = por_id[hid]
        h0, h1 = datetime.fromisoformat(h['inicio']), datetime.fromisoformat(h['fin'])
        ini = cursor.get(hid, h0)
        fin = ini + timedelta(minutes=minutos)
        if fin > h1:
            quedan = int((h1 - ini).total_seconds() // 60)
            errores.append(f'{n}: no cabe en el hueco {_etiqueta(h)}: quedan {quedan} min y pides {minutos}')
            continue
        if ahora is not None and ini <= ahora:
            errores.append(f'{n}: el hueco {_etiqueta(h)} ya ha empezado')
            continue
        cursor[hid] = fin
        eventos.append({'titulo': (PREFIJO_TITULO + asig)[:80], 'inicio': ini.isoformat(), 'fin': fin.isoformat()})
    if errores:
        libres = ', '.join(f"{_etiqueta(h)} {h['minutos']} min" if 'minutos' in h else _etiqueta(h) for h in huecos)
        errores.append('Huecos: ' + libres)
        return [], errores
    return eventos, []
