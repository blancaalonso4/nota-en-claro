"""Puente MCP: sesiones en memoria con servidores falsos, y un arranque real por stdio (sin llamar a Google)."""
import json
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.agentes.puente_mcp import PuenteMCP, en_memoria
from app.mcp_servers import comun, mcp_calendar, mcp_drive, mcp_gmail
from tests.ayudas_mcp import ErrorHttpFalso

ORI = 'orientador@ejemplo.com'


@pytest.fixture
def puente(monkeypatch):
    monkeypatch.setenv('ORIENTADOR_EMAIL', ORI)
    monkeypatch.setattr(comun.time, 'sleep', lambda s: None)
    apis = {'drive': MagicMock(), 'calendar': MagicMock(), 'gmail': MagicMock()}
    estado = {'hoja_notas_id': 'H1', 'calendario_id': 'CAL'}
    servidores = {'drive': mcp_drive.construir(apis['drive'], estado_fn=lambda: dict(estado), guardar_fn=lambda **k: estado.update(k)),
                  'calendar': mcp_calendar.construir(apis['calendar'], estado_fn=lambda: dict(estado), guardar_fn=lambda **k: estado.update(k)),
                  'gmail': mcp_gmail.construir(apis['gmail'])}
    p = PuenteMCP(en_memoria(servidores))
    p.apis = apis
    yield p
    p.cerrar()


def test_herramientas_en_formato_ollama_sin_titles_y_sin_enviar(puente):
    hs = puente.herramientas(['leer_notas', 'huecos_libres', 'crear_borrador', 'enviar_borrador', 'borrar_todo'])
    assert [h['function']['name'] for h in hs] == ['leer_notas', 'huecos_libres', 'crear_borrador']
    assert all(h['type'] == 'function' for h in hs)
    assert 'title' not in json.dumps(hs) and '\n' not in hs[0]['function']['description']
    assert set(hs[1]['function']['parameters']['properties']) == {'desde', 'hasta'}


def test_llamada_correcta_devuelve_datos(puente):
    puente.apis['drive'].sheets.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': [['Nota media', 8]]}, {'values': [['Física', 7, 'admision', 0.2]]}]}
    r = puente.llamar('leer_notas')
    assert r.ok and r.datos['nota_media_bachillerato'] == 8 and r.datos['materias'][0]['asignatura'] == 'Física'
    assert r.segundos >= 0


def test_error_del_servidor_separa_mensaje_y_detalle(puente):
    puente.apis['drive'].sheets.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.side_effect = ErrorHttpFalso(503)
    r = puente.llamar('leer_notas')
    assert not r.ok and 'Google no responde ahora mismo' in r.mensaje and 'http=503' in r.detalle and 'detalle' not in r.mensaje


def test_reintento_del_servidor_llega_al_resultado(puente):
    ejecutar = puente.apis['calendar'].cal.freebusy.return_value.query.return_value.execute
    ejecutar.side_effect = [ErrorHttpFalso(503), {'calendars': {'primary': {}, 'CAL': {}}}]
    r = puente.llamar('huecos_libres', {'desde': '2026-12-02', 'hasta': '2026-12-03'})
    assert r.ok and r.reintentos == 1


def test_llamar_rechaza_enviar_y_desconocidas(puente):
    for n in ('enviar_borrador', 'borrar_evento'):
        r = puente.llamar(n, {'borrador_id': 'R1'})
        assert not r.ok and 'automática' in r.mensaje
    assert not puente.apis['gmail'].gmail.users.return_value.drafts.return_value.send.called


def test_enviar_confirmado_pasa_por_verificador_y_servidor(puente):
    dr = puente.apis['gmail'].gmail.users.return_value.drafts.return_value
    dr.get.return_value.execute.return_value = {'message': {'payload': {'headers': [{'name': 'To', 'value': ORI}]}}}
    dr.send.return_value.execute.return_value = {'id': 'M1'}
    assert puente.enviar_correo_confirmado('R1', ORI).ok
    assert dr.send.call_count == 1
    assert not puente.enviar_correo_confirmado('', ORI).ok          # sin id: el verificador lo para
    dr.get.return_value.execute.return_value = {'message': {'payload': {'headers': [{'name': 'To', 'value': 'otro@ejemplo.com'}]}}}
    r = puente.enviar_correo_confirmado('R1', ORI)
    assert not r.ok and 'únicamente al orientador' in r.mensaje and dr.send.call_count == 1


def test_enviar_confirmado_con_texto_editado_envia_ese_texto(puente):
    dr = puente.apis['gmail'].gmail.users.return_value.drafts.return_value
    dr.get.return_value.execute.return_value = {'message': {'payload': {'headers': [{'name': 'To', 'value': ORI}, {'name': 'Subject', 'value': 'Duda'}]}}}
    dr.update.return_value.execute.return_value = {'id': 'R1'}
    dr.send.return_value.execute.return_value = {'id': 'M1'}
    assert puente.enviar_correo_confirmado('R1', ORI, cuerpo='Hola, Marta. Un saludo, Luis.').ok
    assert dr.update.call_count == 1 and dr.send.call_count == 1
    r = puente.enviar_correo_confirmado('R1', ORI, cuerpo='Hola [Tu nombre]')      # lo para el verificador
    assert not r.ok and 'corchetes' in r.mensaje and dr.send.call_count == 1


def test_arranque_real_por_stdio_lista_las_diez_herramientas():
    """Lanza los tres servidores como subprocesos (como en la app). No llama a Google."""
    p = PuenteMCP()
    try:
        p.iniciar()
        assert set(p._esquemas) == {'crear_plantilla_notas', 'leer_notas', 'guardar_informe', 'listar_eventos',
                                    'huecos_libres', 'crear_eventos_estudio', 'leer_correos_orientador',
                                    'crear_borrador', 'enviar_borrador', 'aplicar_plan_estudio'}
        r = p.llamar('leer_notas')       # sin hoja en estado (o sin token): mensaje claro, no excepción
        assert isinstance(r.ok, bool) and (r.ok or r.mensaje)
    finally:
        p.cerrar()


def test_el_modelo_no_ve_destinatario_ni_remitente(puente):
    hs = {h['function']['name']: h['function']['parameters'] for h in puente.herramientas(['crear_borrador', 'leer_correos_orientador'])}
    assert set(hs['crear_borrador']['properties']) == {'asunto', 'cuerpo'} and set(hs['crear_borrador']['required']) == {'asunto', 'cuerpo'}
    assert 'remitente' not in hs['leer_correos_orientador']['properties'] and 'remitente' not in hs['leer_correos_orientador'].get('required', [])


# --- aplicar_plan_estudio: solo por el método propio del puente --------------------------------------------------------------

PROPUESTA = [{'titulo': 'Estudio: Física', 'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T17:30:00+01:00'}]
HUECOS_PLAN = [{'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T20:00:00+01:00'}]
AHORA_PLAN = datetime(2026, 12, 1, 9, 0, tzinfo=ZoneInfo('Europe/Madrid'))


def calendario_con(puente, existentes):
    ev = puente.apis['calendar'].cal.events.return_value
    ev.list.return_value.execute.return_value = {'items': [{'id': i} for i in existentes]}
    ev.insert.return_value.execute.return_value = {'id': 'N1'}
    return ev


def test_aplicar_plan_estudio_no_sale_en_herramientas_ni_pasa_por_llamar(puente):
    assert puente.herramientas(['aplicar_plan_estudio', 'leer_notas']) and \
        [h['function']['name'] for h in puente.herramientas(['aplicar_plan_estudio', 'leer_notas'])] == ['leer_notas']
    ev = calendario_con(puente, ['V1'])
    r = puente.llamar('aplicar_plan_estudio', {'eventos': PROPUESTA, 'confirmado': True})
    assert not r.ok and 'automática' in r.mensaje and not ev.delete.called and not ev.insert.called


def test_aplicar_plan_confirmado_pasa_por_verificador_y_servidor(puente):
    ev = calendario_con(puente, ['V1', 'V2'])
    r = puente.aplicar_plan(PROPUESTA, huecos=HUECOS_PLAN, dias=7, zona='Europe/Madrid', confirmado=True, ahora=AHORA_PLAN)
    assert r.ok and r.datos['aplicado'] is True and r.datos['borrados'] == 2
    assert ev.insert.call_count == 1 and ev.delete.call_count == 2
    assert all(c.kwargs['calendarId'] == 'CAL' for c in ev.delete.call_args_list)


def test_aplicar_plan_sin_confirmar_con_eventos_previos_no_borra(puente):
    ev = calendario_con(puente, ['V1'])
    r = puente.aplicar_plan(PROPUESTA, huecos=HUECOS_PLAN, dias=7, zona='Europe/Madrid', ahora=AHORA_PLAN)
    assert r.ok and r.datos == {'aplicado': False, 'existentes': 1, 'reintentos': 0}
    assert not ev.insert.called and not ev.delete.called


def test_aplicar_plan_con_propuesta_que_no_cabe_o_ya_empezada_no_llega_al_servidor(puente):
    ev = calendario_con(puente, ['V1'])
    ya_empezada = datetime(2026, 12, 2, 16, 30, tzinfo=ZoneInfo('Europe/Madrid'))
    r = puente.aplicar_plan(PROPUESTA, huecos=HUECOS_PLAN, dias=7, zona='Europe/Madrid', confirmado=True, ahora=ya_empezada)
    assert not r.ok and 'empieza en el pasado' in r.mensaje
    fuera = [{'titulo': 'x', 'inicio': '2026-12-02T21:00:00+01:00', 'fin': '2026-12-02T22:00:00+01:00'}]
    r = puente.aplicar_plan(fuera, huecos=HUECOS_PLAN, dias=7, zona='Europe/Madrid', confirmado=True, ahora=AHORA_PLAN)
    assert not r.ok and 'no cabe en ningún hueco' in r.mensaje
    assert not ev.insert.called and not ev.delete.called
