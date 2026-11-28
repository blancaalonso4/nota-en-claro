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


def test_herramientas_y_el_borrado_solo_con_confirmacion():
    mcp, _, _ = servidor()
    hs = herramientas(mcp)
    assert set(hs) == {'listar_eventos', 'huecos_libres', 'crear_eventos_estudio', 'aplicar_plan_estudio'}
    # la única que borra exige confirmación y no admite elegir el calendario: solo recibe eventos y «confirmado»
    props = hs['aplicar_plan_estudio'].inputSchema['properties']
    assert set(props) == {'eventos', 'confirmado'} and props['confirmado']['default'] is False


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
    ahora = iso(2, 15, 7)
    h = mcp_calendar.calcular_huecos([], iso(2, 0), iso(2, 23, 59), ahora, 'Europe/Madrid')
    assert h[0]['inicio'][11:16] == '15:15'      # el siguiente cuarto de hora, estrictamente después de ahora


def test_ningun_hueco_empieza_en_ahora_ni_antes():
    for ahora in (iso(2, 15), iso(2, 15, 14), iso(2, 7, 59), iso(2, 21, 50)):
        h = mcp_calendar.calcular_huecos([], iso(2, 0), iso(3, 23, 59), ahora, 'Europe/Madrid')
        assert h and all(datetime.fromisoformat(x['inicio']) > ahora for x in h)


def test_huecos_numerados_con_dia_y_horas_legibles():
    h = mcp_calendar.calcular_huecos([(iso(2, 10), iso(2, 12))], iso(2, 0), iso(3, 23, 59), AHORA, 'Europe/Madrid')
    assert [x['id'] for x in h] == [1, 2, 3]
    assert (h[0]['dia'], h[0]['inicio_hora'], h[0]['fin_hora'], h[0]['minutos']) == ('miércoles 2 dic', '08:00', '10:00', 120)
    assert h[2]['dia'] == 'jueves 3 dic'


def test_huecos_con_ocupacion_en_utc_se_convierte_a_madrid():
    utc = ZoneInfo('UTC')
    ocupado = [(datetime(2026, 12, 2, 9, 0, tzinfo=utc), datetime(2026, 12, 2, 11, 0, tzinfo=utc))]   # 10:00-12:00 en Madrid
    h = mcp_calendar.calcular_huecos(ocupado, iso(2, 0), iso(2, 23, 59), AHORA, 'Europe/Madrid')
    assert (h[0]['fin'][11:16], h[1]['inicio'][11:16]) == ('10:00', '12:00')


def test_huecos_con_tope():
    h = mcp_calendar.calcular_huecos([], iso(2, 0), datetime(2027, 1, 20, tzinfo=MAD), AHORA, 'Europe/Madrid')
    assert len(h) == mcp_calendar.MAX_HUECOS


# --- herramientas ---------------------------------------------------------------------------------------------------------

def test_huecos_libres_mira_solo_el_calendario_principal():
    mcp, api, _ = servidor()
    q = api.cal.freebusy.return_value.query
    q.return_value.execute.return_value = {'calendars': {
        'primary': {'busy': [busy('2026-12-02T09:00:00+01:00', '2026-12-02T14:00:00+01:00')]}}}
    error, r = llamar_herramienta(mcp, 'huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert not error
    # las sesiones del plan anterior (calendario de la app) no cuentan como ocupado
    assert [i['id'] for i in q.call_args.kwargs['body']['items']] == ['primary']
    assert [(x['inicio'][11:16], x['fin'][11:16]) for x in r['huecos'][:2]] == [('08:00', '09:00'), ('14:00', '22:00')]
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


# --- aplicar_plan_estudio: sustituir el plan (crear lo nuevo y después borrar lo viejo) ----------------------------------------

EV1 = {'titulo': 'Estudio: Física', 'inicio': '2026-12-02T16:00:00', 'fin': '2026-12-02T17:30:00'}
EV2 = {'titulo': 'Estudio: Historia', 'inicio': '2026-12-03T10:00:00', 'fin': '2026-12-03T11:00:00'}


def plan_con(api, existentes, nuevos=('N1', 'N2')):
    """Calendario de la app con eventos previos. Devuelve la lista donde se anota el orden de las operaciones."""
    orden = []
    ev = api.cal.events.return_value
    ev.list.return_value.execute.return_value = {'items': [{'id': i} for i in existentes]}
    ids = iter(nuevos)

    def insertar(**kw):
        m = MagicMock()
        m.execute.side_effect = lambda: (orden.append(('insert', kw['calendarId'])) or {'id': next(ids), 'htmlLink': ''})
        return m

    def borrar(**kw):
        m = MagicMock()
        m.execute.side_effect = lambda: orden.append(('delete', kw['eventId'], kw['calendarId'], kw['sendUpdates']))
        return m
    ev.insert.side_effect, ev.delete.side_effect = insertar, borrar
    return orden


def test_sin_eventos_previos_crea_sin_pedir_confirmacion():
    mcp, api, _ = servidor()
    orden = plan_con(api, [])
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1, EV2]})
    assert not error and r['aplicado'] is True and r['existentes'] == 0 and r['borrados'] == 0 and r['no_borrados'] == 0
    assert [o[0] for o in orden] == ['insert', 'insert'] and len(r['creados']) == 2 and r['calendario_id'] == 'CAL'


def test_con_eventos_previos_y_sin_confirmar_no_toca_nada():
    mcp, api, _ = servidor()
    plan_con(api, ['V1', 'V2', 'V3'])
    for args in ({'eventos': [EV1]}, {'eventos': [EV1], 'confirmado': False}):
        error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', args)
        assert not error and r['aplicado'] is False and r['existentes'] == 3
    ev = api.cal.events.return_value
    assert not ev.insert.called and not ev.delete.called


def test_confirmado_crea_primero_y_borra_despues_solo_en_el_calendario_de_la_app():
    mcp, api, _ = servidor()
    # V1 es un evento pasado y V2 uno editado a mano: el servidor solo ve ids, así que se borran todos
    orden = plan_con(api, ['V1', 'V2'])
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1, EV2], 'confirmado': True})
    assert not error and (r['aplicado'], r['existentes'], r['borrados'], r['no_borrados']) == (True, 2, 2, 0)
    assert [o[0] for o in orden] == ['insert', 'insert', 'delete', 'delete']         # primero lo nuevo, después lo viejo
    assert [o[1] for o in orden if o[0] == 'delete'] == ['V1', 'V2']
    assert all(o[1] == 'CAL' for o in orden if o[0] == 'insert')
    assert all(o[2:] == ('CAL', 'none') for o in orden if o[0] == 'delete')           # nunca 'primary'; sin avisos a nadie
    ev = api.cal.events.return_value
    llamadas = [c.kwargs for c in ev.list.call_args_list + ev.insert.call_args_list + ev.delete.call_args_list]
    assert llamadas and all(k['calendarId'] == 'CAL' for k in llamadas)
    assert 'primary' not in str(api.cal.mock_calls)       # el servicio de Calendar no se ha tocado con 'primary'


def test_lista_los_ids_de_todas_las_paginas():
    mcp, api, _ = servidor()
    orden = plan_con(api, [])
    api.cal.events.return_value.list.return_value.execute.side_effect = [
        {'items': [{'id': 'V1'}, {'id': 'V2'}], 'nextPageToken': 'T2'}, {'items': [{'id': 'V3'}]}]
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1], 'confirmado': True})
    assert not error and r['existentes'] == 3 and r['borrados'] == 3
    lst = api.cal.events.return_value.list.call_args_list
    assert len(lst) == 2 and 'pageToken' not in lst[0].kwargs and lst[1].kwargs['pageToken'] == 'T2'
    assert lst[0].kwargs['maxResults'] == 2500 and lst[0].kwargs['fields'] == 'items(id),nextPageToken'
    assert [o[1] for o in orden if o[0] == 'delete'] == ['V1', 'V2', 'V3']


def test_demasiadas_paginas_no_cambia_nada():
    mcp, api, _ = servidor()
    plan_con(api, [])
    api.cal.events.return_value.list.return_value.execute.side_effect = lambda: {'items': [{'id': 'V'}], 'nextPageToken': 'T'}
    error, texto = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1], 'confirmado': True})
    assert error and 'demasiados' in texto
    assert api.cal.events.return_value.list.call_count == mcp_calendar.MAX_PAGINAS_EVENTOS
    assert not api.cal.events.return_value.insert.called and not api.cal.events.return_value.delete.called


def test_si_falla_crear_se_deshace_lo_nuevo_y_no_se_borra_nada_antiguo():
    mcp, api, _ = servidor()
    orden = plan_con(api, ['V1', 'V2'])
    ev = api.cal.events.return_value
    buenos = iter(['N1'])

    def insertar(**kw):
        m = MagicMock()

        def ejecutar():
            try:
                i = next(buenos)
            except StopIteration:
                raise ErrorHttpFalso(400)     # la segunda creación falla
            orden.append(('insert', kw['calendarId']))
            return {'id': i}
        m.execute.side_effect = ejecutar
        return m
    ev.insert.side_effect = insertar
    error, texto = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1, EV2], 'confirmado': True})
    assert error and 'No he podido crear el plan nuevo; tu plan anterior sigue igual.' in texto
    borrados = [o[1] for o in orden if o[0] == 'delete']
    assert borrados == ['N1']          # marcha atrás: solo se quita lo nuevo ya creado; V1 y V2 siguen ahí


def test_un_404_al_borrar_cuenta_como_borrado_y_otro_fallo_como_no_borrado():
    mcp, api, _ = servidor()
    plan_con(api, ['V1', 'V2', 'V3'])
    borrar = api.cal.events.return_value.delete
    estados = {'V1': ErrorHttpFalso(404), 'V2': ErrorHttpFalso(410), 'V3': ErrorHttpFalso(400)}

    def uno(**kw):
        m = MagicMock()
        m.execute.side_effect = estados[kw['eventId']]
        return m
    borrar.side_effect = uno
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1], 'confirmado': True})
    assert not error and r['aplicado'] is True and (r['borrados'], r['no_borrados']) == (2, 1)
    assert len(r['creados']) == 1


def test_un_argumento_calendarid_primary_no_cambia_el_calendario():
    mcp, api, _ = servidor()
    orden = plan_con(api, ['V1'])
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio',
                                  {'eventos': [EV1], 'confirmado': True, 'calendarId': 'primary', 'calendario_id': 'primary'})
    assert not error and r['calendario_id'] == 'CAL'
    assert all('primary' not in o for o in orden) and 'primary' not in str(api.cal.mock_calls)


def test_si_el_calendario_guardado_fuera_primary_se_niega():
    mcp, api, _ = servidor({'calendario_id': 'primary'})
    plan_con(api, ['V1'])
    error, texto = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1], 'confirmado': True})
    assert error and 'calendario principal' in texto and not api.cal.events.return_value.delete.called


def test_crea_el_calendario_de_la_app_si_no_existe_y_aplica_el_plan():
    mcp, api, estado = servidor()
    estado.pop('calendario_id')
    api.cal.calendars.return_value.insert.return_value.execute.return_value = {'id': 'NUEVO'}
    orden = plan_con(api, [])
    error, r = llamar_herramienta(mcp, 'aplicar_plan_estudio', {'eventos': [EV1]})
    assert not error and r['calendario_id'] == 'NUEVO' and orden == [('insert', 'NUEVO')]
