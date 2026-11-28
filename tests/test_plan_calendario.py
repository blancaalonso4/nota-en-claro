"""Sustitución del plan de estudio (`plan_calendario`): puente falso y, para la propuesta caducada, el puente real en memoria."""
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.agentes import plan_calendario as pc
from app.agentes.puente_mcp import PuenteMCP, ResultadoLlamada, en_memoria
from app.agentes.traza import Traza
from app.mcp_servers import comun, mcp_calendar

ZONA = 'Europe/Madrid'
AHORA = datetime(2026, 12, 1, 9, 0, tzinfo=ZoneInfo(ZONA))
PROPUESTA = [{'titulo': 'Estudio: Física', 'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T17:30:00+01:00'},
             {'titulo': 'Estudio: Historia', 'inicio': '2026-12-03T10:00:00+01:00', 'fin': '2026-12-03T11:00:00+01:00'}]
HUECOS = [{'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T20:00:00+01:00'},
          {'inicio': '2026-12-03T10:00:00+01:00', 'fin': '2026-12-03T13:00:00+01:00'}]


class PuenteFalso:
    """Imita al servidor: sin eventos previos crea; con ellos solo borra si `confirmado`."""

    def __init__(self, existentes=0, no_borrados=0, fallo=None):
        self.existentes, self.no_borrados, self.fallo, self.llamadas = existentes, no_borrados, fallo, []

    def aplicar_plan(self, eventos, *, huecos, dias, zona, franja=None, confirmado=False, ahora=None):
        self.llamadas.append({'eventos': eventos, 'confirmado': confirmado, 'huecos': huecos, 'dias': dias})
        if self.fallo:
            return ResultadoLlamada(False, mensaje=self.fallo, detalle='HttpError http=503')
        if self.existentes and not confirmado:
            return ResultadoLlamada(True, datos={'aplicado': False, 'existentes': self.existentes})
        return ResultadoLlamada(True, datos={
            'aplicado': True, 'creados': [dict(e, id='E') for e in eventos], 'existentes': self.existentes,
            'borrados': self.existentes - self.no_borrados, 'no_borrados': self.no_borrados, 'calendario_id': 'CAL123'})


def aplicar(tmp_path, puente, **kw):
    traza = Traza(tmp_path, sesion='p')
    kw.setdefault('confirmado', False)
    return pc.aplicar(puente, traza, PROPUESTA, zona=ZONA, huecos=HUECOS, dias=7, agente='orquestador', **kw), traza


def test_calendario_vacio_se_crea_sin_preguntar(tmp_path):
    r, traza = aplicar(tmp_path, PuenteFalso(existentes=0))
    assert r.ok and not r.pendiente and r.creados == 2
    assert r.texto.startswith('He creado 2 sesiones de estudio en tu calendario «Nota en Claro · Estudio»')
    assert 'miércoles 2 dic 16:00–17:30 · Estudio: Física' in r.texto and 'He borrado' not in r.texto


def test_con_sesiones_previas_queda_pendiente_con_la_pregunta_exacta(tmp_path):
    puente = PuenteFalso(existentes=6)
    r, traza = aplicar(tmp_path, puente)
    assert r.ok and r.pendiente and r.existentes == 6 and r.creados == 0
    assert [c['confirmado'] for c in puente.llamadas] == [False]
    assert pc.PREGUNTA_SUSTITUIR.format(n=6) == ('Ya tienes un plan con 6 sesiones en el calendario «Nota en Claro · Estudio». '
                                                 'Si lo sustituyes, se borrarán todas, también las que hayas editado. ¿Sustituirlo?')


def test_confirmar_deja_traza_sin_titulos_ni_fechas(tmp_path):
    r, traza = aplicar(tmp_path, PuenteFalso(existentes=6), confirmado=True)
    assert r.ok and (r.creados, r.borrados, r.no_borrados) == (2, 6, 0) and 'He borrado las 6 sesiones del plan anterior' in r.texto
    p = [x for x in traza.pasos if x['herramienta'] == 'aplicar_plan_estudio'][-1]
    assert (p['permiso'], p['agente'], p['tipo']) == ('confirmar', 'orquestador', 'herramienta')
    assert (p['existentes'], p['borrados'], p['no_borrados'], p['creados']) == (6, 6, 0, 2)
    assert p['calendario'] == 'Nota en Claro · Estudio' and p['calendario_id'] == 'CAL123' and p['confirmado_por_usuario'] is True
    volcado = str(p) + (tmp_path / 'sesion_p.jsonl').read_text(encoding='utf-8')
    assert 'Física' not in volcado and 'Historia' not in volcado and '2026-12-02' not in volcado


def test_si_no_se_borra_algo_el_mensaje_lo_dice(tmp_path):
    r, traza = aplicar(tmp_path, PuenteFalso(existentes=6, no_borrados=2), confirmado=True)
    assert r.ok and r.no_borrados == 2
    assert 'He creado tu plan nuevo, pero no he podido borrar 2 sesiones del plan anterior' in r.texto
    assert 'siguen en «Nota en Claro · Estudio»' in r.texto and 'bórralas a mano en Google Calendar' in r.texto
    assert traza.pasos[-1]['no_borrados'] == 2


def test_un_fallo_de_google_sale_con_mensaje_y_queda_en_la_traza(tmp_path):
    r, traza = aplicar(tmp_path, PuenteFalso(fallo='No he podido crear el plan nuevo; tu plan anterior sigue igual.'), confirmado=True)
    assert not r.ok and 'tu plan anterior sigue igual' in r.texto
    assert traza.pasos[-1]['fallo'] is True and 'http=503' in traza.pasos[-1]['error']


def test_cancelar_no_llama_al_puente_y_lo_anota(tmp_path):
    puente, traza = PuenteFalso(existentes=6), Traza(tmp_path, sesion='c')
    texto = pc.cancelar(traza)
    assert texto == 'No he cambiado tu calendario: tu plan anterior sigue igual.' and puente.llamadas == []
    p = traza.pasos[-1]
    assert (p['herramienta'], p['permiso'], p['cancelado'], p['agente']) == ('aplicar_plan_estudio', 'confirmar', True, 'interfaz')


def test_propuesta_caducada_la_para_el_verificador_sin_llamar_al_servidor(tmp_path, monkeypatch):
    monkeypatch.setattr(comun.time, 'sleep', lambda s: None)
    api = MagicMock()
    mcp = mcp_calendar.construir(api, estado_fn=lambda: {'calendario_id': 'CAL'}, guardar_fn=lambda **k: None, ahora_fn=lambda: AHORA)
    puente = PuenteMCP(en_memoria({'calendar': mcp}))
    try:
        tarde = datetime(2026, 12, 2, 16, 30, tzinfo=ZoneInfo(ZONA))        # la primera sesión ya ha empezado
        r, traza = aplicar(tmp_path, puente, confirmado=True, ahora=tarde)
        assert not r.ok and 'ya no es válida' in r.texto and 'empieza en el pasado' in r.texto
        assert not api.cal.events.called and not api.cal.freebusy.called and not api.cal.calendars.called
        assert traza.pasos[-1]['fallo'] is True
    finally:
        puente.cerrar()
