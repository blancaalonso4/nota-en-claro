"""Servidor MCP de Calendar con servicios falsos (sin red, sin credenciales)."""
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.mcp_servers import comun, mcp_calendar
from tests.ayudas_mcp import ErrorHttpFalso, herramientas, llamar_herramienta

MAD = ZoneInfo('Europe/Madrid')
AHORA = datetime(2026, 12, 1, 9, 0, tzinfo=MAD)


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(comun.time, 'sleep', lambda s: None)


def servidor(estado=None):
    api = MagicMock()
    guardado = {'calendario_id': 'CAL', **(estado or {})}
    mcp = mcp_calendar.construir(api, estado_fn=lambda: dict(guardado), guardar_fn=lambda **k: guardado.update(k),
                                 ahora_fn=lambda: AHORA)
    return mcp, api, guardado


def busy(a, b):
    return {'start': a, 'end': b}


def test_herramientas_sin_borrado():
    mcp, _, _ = servidor()
    assert set(herramientas(mcp)) == {'listar_eventos', 'huecos_libres', 'crear_eventos_estudio'}


# --- cálculo de huecos -------------------------------------------------------------------------------------------------

def iso(d, h, m=0):
    return datetime(2026, 12, d, h, m, tzinfo=MAD)


def test_huecos_sin_ocupacion_son_la_ventana_de_cada_dia():
    h = mcp_calendar.calcular_huecos([], iso(2, 0), iso(3, 23, 59), AHORA, 'Europe/Madrid')
    assert [(x['inicio'][:16], x['fin'][:16]) for x in h] == [('2026-12-02T08:00', '2026-12-02T22:00'),
                                                              ('2026-12-03T08:00', '2026-12-03T22:00')]


def test_huecos_restan_lo_ocupado_y_descartan_los_cortos():
    ocupado = [(iso(2, 10), iso(2, 12)), (iso(2, 12, 15), iso(2, 21, 45))]   # entre medias solo 15 min; al final 15 min
    h = mcp_calendar.calcular_huecos(ocupado, iso(2, 0), iso(2, 23, 59), AHORA, 'Europe/Madrid')
    assert [(x['inicio'][11:16], x['fin'][11:16]) for x in h] == [('08:00', '10:00')]


def test_huecos_no_incluyen_el_pasado():
    ahora = iso(2, 15)
    h = mcp_calendar.calcular_huecos([], iso(2, 0), iso(2, 23, 59), ahora, 'Europe/Madrid')
    assert h[0]['inicio'][11:16] == '15:00'


def test_huecos_con_ocupacion_en_utc_se_convierte_a_madrid():
    utc = ZoneInfo('UTC')
    ocupado = [(datetime(2026, 12, 2, 9, 0, tzinfo=utc), datetime(2026, 12, 2, 11, 0, tzinfo=utc))]   # 10:00-12:00 en Madrid
    h = mcp_calendar.calcular_huecos(ocupado, iso(2, 0), iso(2, 23, 59), AHORA, 'Europe/Madrid')
    assert (h[0]['fin'][11:16], h[1]['inicio'][11:16]) == ('10:00', '12:00')


def test_huecos_con_tope():
    h = mcp_calendar.calcular_huecos([], iso(2, 0), datetime(2027, 1, 20, tzinfo=MAD), AHORA, 'Europe/Madrid')
    assert len(h) == mcp_calendar.MAX_HUECOS


# --- herramientas ---------------------------------------------------------------------------------------------------------

def test_huecos_libres_mira_primary_y_el_calendario_de_estudio():
    mcp, api, _ = servidor()
    q = api.cal.freebusy.return_value.query
    q.return_value.execute.return_value = {'calendars': {
        'primary': {'busy': [busy('2026-12-02T09:00:00+01:00', '2026-12-02T14:00:00+01:00')]},
        'CAL': {'busy': [busy('2026-12-02T16:00:00+01:00', '2026-12-02T17:00:00+01:00')]}}}
    error, r = llamar_herramienta(mcp, 'huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert not error
    assert {i['id'] for i in q.call_args.kwargs['body']['items']} == {'primary', 'CAL'}
    assert [(x['inicio'][11:16], x['fin'][11:16]) for x in r['huecos'][:3]] == [('08:00', '09:00'), ('14:00', '16:00'), ('17:00', '22:00')]
    assert 'summary' not in str(r)      # del calendario principal no sale ningún título


def test_huecos_libres_error_en_un_calendario_no_se_ignora():
    mcp, api, _ = servidor()
    api.cal.freebusy.return_value.query.return_value.execute.return_value = {'calendars': {'primary': {'errors': [{'reason': 'notFound'}]}}}
    error, texto = llamar_herramienta(mcp, 'huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert error and 'No he podido consultar' in texto


def test_crear_eventos_sin_invitados_ni_avisos():
    mcp, api, _ = servidor()
    ins = api.cal.events.return_value.insert
    ins.return_value.execute.return_value = {'id': 'E1', 'htmlLink': 'https://calendar.google.com/e/E1'}
    evento = {'titulo': 'Estudiar Física', 'inicio': '2026-12-02T16:00:00', 'fin': '2026-12-02T17:30:00',
              'attendees': [{'email': 'x@ejemplo.com'}], 'invitados': ['y@ejemplo.com']}
    error, r = llamar_herramienta(mcp, 'crear_eventos_estudio', {'eventos': [evento]})
    assert not error and r['creados'][0]['id'] == 'E1'
    kw = ins.call_args.kwargs
    assert kw['calendarId'] == 'CAL' and kw['sendUpdates'] == 'none'
    assert set(kw['body']) == {'summary', 'start', 'end'}          # ni attendees ni nada que no sea título y fechas
    assert kw['body']['start'] == {'dateTime': '2026-12-02T16:00:00+01:00', 'timeZone': 'Europe/Madrid'}


def test_crear_eventos_rechaza_fechas_malas_y_demasiados():
    mcp, api, _ = servidor()
    error, texto = llamar_herramienta(mcp, 'crear_eventos_estudio', {'eventos': [{'titulo': 'x', 'inicio': 'mañana', 'fin': 'tarde'}]})
    assert error and 'fechas no válidas' in texto
    error, texto = llamar_herramienta(mcp, 'crear_eventos_estudio', {'eventos': [{'titulo': 'x', 'inicio': '2026-12-02T10:00:00', 'fin': '2026-12-02T09:00:00'}]})
    assert error and 'posterior' in texto
    muchos = [{'titulo': 'x', 'inicio': '2026-12-02T10:00:00', 'fin': '2026-12-02T11:00:00'}] * 11
    assert llamar_herramienta(mcp, 'crear_eventos_estudio', {'eventos': muchos})[0]
    assert not api.cal.events.return_value.insert.called


def test_crea_el_calendario_de_la_app_si_no_existe():
    mcp, api, estado = servidor()
    estado.pop('calendario_id')
    api.cal.calendars.return_value.insert.return_value.execute.return_value = {'id': 'NUEVO'}
    api.cal.events.return_value.list.return_value.execute.return_value = {'items': [
        {'summary': 'Estudiar <b>Física', 'start': {'dateTime': '2026-12-02T16:00:00+01:00'}, 'end': {'dateTime': '2026-12-02T17:00:00+01:00'}}]}
    error, r = llamar_herramienta(mcp, 'listar_eventos', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert not error and estado['calendario_id'] == 'NUEVO'
    assert api.cal.calendars.return_value.insert.call_args.kwargs['body']['summary'] == 'Nota en Claro · Estudio'
    assert r['eventos'][0]['titulo'] == 'Estudiar b Física'


def test_recrea_el_calendario_si_lo_borraron():
    mcp, api, estado = servidor()
    api.cal.calendars.return_value.get.return_value.execute.side_effect = ErrorHttpFalso(404)
    api.cal.calendars.return_value.insert.return_value.execute.return_value = {'id': 'OTRO'}
    api.cal.events.return_value.list.return_value.execute.return_value = {'items': []}
    error, _ = llamar_herramienta(mcp, 'listar_eventos', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert not error and estado['calendario_id'] == 'OTRO'


def test_503_se_reintenta_y_400_no():
    mcp, api, _ = servidor()
    q = api.cal.freebusy.return_value.query.return_value.execute
    q.side_effect = [ErrorHttpFalso(503), {'calendars': {'primary': {}, 'CAL': {}}}]
    error, r = llamar_herramienta(mcp, 'huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert not error and r['reintentos'] == 1
    q.side_effect = ErrorHttpFalso(400)
    q.reset_mock()
    error, texto = llamar_herramienta(mcp, 'huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert error and q.call_count == 1 and 'no ha aceptado' in texto
