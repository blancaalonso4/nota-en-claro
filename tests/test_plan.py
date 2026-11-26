"""Cálculo de las fechas del plan de estudio en Python (el modelo solo elige hueco, asignatura y minutos)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agentes import plan

MAD = ZoneInfo('Europe/Madrid')
HUECOS = [
    {'id': 1, 'dia': 'martes 1 dic', 'inicio_hora': '16:00', 'fin_hora': '18:00', 'minutos': 120,
     'inicio': '2026-12-01T16:00:00+01:00', 'fin': '2026-12-01T18:00:00+01:00'},
    {'id': 2, 'dia': 'miércoles 2 dic', 'inicio_hora': '10:00', 'fin_hora': '13:00', 'minutos': 180,
     'inicio': '2026-12-02T10:00:00+01:00', 'fin': '2026-12-02T13:00:00+01:00'}]
ASIGS = ['Física', 'Matemáticas II', 'Química']
AHORA = datetime(2026, 12, 1, 9, 0, tzinfo=MAD)


def s(hueco, asignatura, minutos):
    return {'hueco': hueco, 'asignatura': asignatura, 'minutos': minutos}


def test_una_sesion_empieza_al_principio_del_hueco():
    ev, err = plan.construir_eventos([s(2, 'Física', 90)], HUECOS, ASIGS, AHORA)
    assert err == [] and ev == [{'titulo': 'Estudio: Física', 'inicio': '2026-12-02T10:00:00+01:00', 'fin': '2026-12-02T11:30:00+01:00'}]


def test_varias_en_el_mismo_hueco_seguidas_y_en_el_orden_recibido():
    ev, err = plan.construir_eventos([s(2, 'Química', 60), s(1, 'Física', 120), s(2, 'Física', 120)], HUECOS, ASIGS, AHORA)
    assert err == []
    assert [(e['titulo'][-7:], e['inicio'][11:16], e['fin'][11:16]) for e in ev] == [
        ('Química', '10:00', '11:00'), (' Física', '16:00', '18:00'), (' Física', '11:00', '13:00')]


def test_cabe_justo_y_no_cabe_por_un_minuto():
    assert plan.construir_eventos([s(2, 'Física', 90), s(2, 'Química', 90)], HUECOS, ASIGS, AHORA)[1] == []
    ev, err = plan.construir_eventos([s(2, 'Física', 120), s(2, 'Química', 90)], HUECOS, ASIGS, AHORA)
    assert ev == [] and 'quedan 60 min y pides 90' in err[0]


def test_si_hay_un_error_no_se_devuelve_ningun_evento_y_se_listan_los_huecos():
    ev, err = plan.construir_eventos([s(1, 'Física', 60), s(9, 'Física', 60)], HUECOS, ASIGS, AHORA)
    assert ev == [] and 'el hueco 9' in err[0] and err[-1].startswith('Huecos: 1 (martes 1 dic 16:00-18:00)')


def test_duraciones_validas_solo_60_90_120():
    for m in (30, 45, 100, 180, 0, -60, 'mucho', None, True):
        assert plan.construir_eventos([s(1, 'Física', m)], HUECOS, ASIGS, AHORA)[0] == [], m
    for m in (60, 90, 120):
        assert plan.construir_eventos([s(1, 'Física', m)], HUECOS, ASIGS, AHORA)[1] == [], m


def test_numeros_como_texto_se_aceptan_pero_no_los_decimales():
    assert plan.construir_eventos([s('1', 'Física', '60')], HUECOS, ASIGS, AHORA)[1] == []
    assert plan.construir_eventos([s(1.5, 'Física', 60)], HUECOS, ASIGS, AHORA)[0] == []


def test_asignatura_se_normaliza_a_la_de_la_hoja():
    ev, _ = plan.construir_eventos([s(1, 'matematicas', 60), s(2, 'FÍSICA', 60)], HUECOS, ASIGS, AHORA)
    assert [e['titulo'] for e in ev] == ['Estudio: Matemáticas II', 'Estudio: Física']
    ev, err = plan.construir_eventos([s(1, 'Dibujo', 60)], HUECOS, ASIGS, AHORA)
    assert ev == [] and 'Matemáticas II' in err[0]


def test_sin_lista_de_asignaturas_se_acepta_el_texto():
    assert plan.construir_eventos([s(1, 'Latín', 60)], HUECOS, [], AHORA)[0][0]['titulo'] == 'Estudio: Latín'


def test_campos_de_fecha_prohibidos():
    ev, err = plan.construir_eventos([{**s(1, 'Física', 60), 'inicio': '2020-01-01T10:00:00'}], HUECOS, ASIGS, AHORA)
    assert ev == [] and 'sin fechas' in err[0]


def test_lista_vacia_mal_formada_o_demasiado_larga():
    assert plan.construir_eventos([], HUECOS, ASIGS, AHORA)[0] == []
    assert plan.construir_eventos('lunes', HUECOS, ASIGS, AHORA)[0] == []
    assert plan.construir_eventos(['x'], HUECOS, ASIGS, AHORA)[0] == []
    assert 'máximo 6' in plan.construir_eventos([s(2, 'Física', 60)] * 7, HUECOS, ASIGS, AHORA)[1][0]


def test_un_hueco_que_ya_ha_empezado_se_rechaza():
    ev, err = plan.construir_eventos([s(1, 'Física', 60)], HUECOS, ASIGS, datetime(2026, 12, 1, 16, 30, tzinfo=MAD))
    assert ev == [] and 'ya ha empezado' in err[0]
