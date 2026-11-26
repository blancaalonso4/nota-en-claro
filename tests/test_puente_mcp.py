"""Puente MCP: sesiones en memoria con servidores falsos, y un arranque real por stdio (sin llamar a Google)."""
import json
from unittest.mock import MagicMock

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


def test_arranque_real_por_stdio_lista_las_nueve_herramientas():
    """Lanza los tres servidores como subprocesos (como en la app). No llama a Google."""
    p = PuenteMCP()
    try:
        p.iniciar()
        assert set(p._esquemas) == {'crear_plantilla_notas', 'leer_notas', 'guardar_informe', 'listar_eventos',
                                    'huecos_libres', 'crear_eventos_estudio', 'leer_correos_orientador',
                                    'crear_borrador', 'enviar_borrador'}
        r = p.llamar('leer_notas')       # sin hoja en estado (o sin token): mensaje claro, no excepción
        assert isinstance(r.ok, bool) and (r.ok or r.mensaje)
    finally:
        p.cerrar()
