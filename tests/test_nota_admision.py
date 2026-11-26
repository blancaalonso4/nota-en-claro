"""Pruebas de la calculadora de nota de admisión. Los ejemplos numéricos salen de doc15 y doc16 del corpus."""
from decimal import Decimal as D

import pytest

from app.agentes.nota_admision import (FUENTES, Materia, calcular, calcular_desde_diccionario, desde_diccionario,
                                       explicar, fmt, r3)
from app.rag.config import RAIZ
from app.rag.troceado import normaliza


def acceso(*notas, modalidad=None):
    """Ejercicios de la fase de acceso; `modalidad` = (nombre, nota, ponderación) de la materia obligatoria de modalidad."""
    ms = [Materia(f'Acceso {i}', D(str(n)), 'acceso', D('0')) for i, n in enumerate(notas, 1)]
    if modalidad:
        n, nota, pond = modalidad
        ms.append(Materia(n, D(str(nota)), 'acceso', D(str(pond))))
    return ms


def adm(nombre, nota, pond, sl=False):
    return Materia(nombre, D(str(nota)), 'admision', None if pond is None else D(str(pond)), sl)


# --- ejemplos resueltos del corpus --------------------------------------------------------------------------------

def alumno_doc16(pond_fis, pond_bio):
    """doc16: CAU 8,324 = 0,6·8,5 + 0,4·8,06; Matemáticas II (acceso) 8,5; Física 7,5; Química 4,25; Biología 8,5."""
    base = acceso(8.00, 8.00, 7.74, modalidad=('Matemáticas II', 8.5, 0.2))   # media (8+8+7,74+8,5)/4 = 8,06
    return D('8.5'), base + [adm('Física', 7.5, 0.2), adm('Química', 4.25, 0.2), adm('Biología', 8.5, pond_bio)]


def test_doc16_ingenieria_aeroespacial():
    cfb, ms = alumno_doc16(0.2, 0.1)
    r = calcular(cfb, ms)
    assert r.pau == D('8.060') and r.cau == D('8.324')
    assert r.admision == D('11.524')
    assert {u['nombre'] for u in r.usadas} == {'Matemáticas II', 'Física'}


def test_doc16_ingenieria_biomedica():
    cfb, ms = alumno_doc16(0.2, 0.2)
    r = calcular(cfb, ms)
    assert r.admision == D('11.724')
    assert {u['nombre'] for u in r.usadas} == {'Matemáticas II', 'Biología'}


def test_doc16_no_elige_la_combinacion_peor():
    """doc16: con Biología (0,1) en lugar de Física la nota sería 10,874; el cálculo debe quedarse con 11,524."""
    cfb, ms = alumno_doc16(0.2, 0.1)
    assert calcular(cfb, ms).admision > D('10.874')


def test_doc15_ejemplo_con_cau_9():
    base = acceso(9, 9, 9, modalidad=('Matemáticas II', 9, 0))
    for fis, esperado in (('7.00', '12.000'), ('7.50', '12.100')):
        r = calcular(D('9'), base + [adm('Física', fis, 0.2), adm('Química', 8.00, 0.2)])
        assert r.cau == D('9.000') and r.admision == D(esperado)


# --- reglas ------------------------------------------------------------------------------------------------------

def test_materia_con_nota_menor_de_5_no_pondera():
    base = acceso(7, 7, 7, 7)
    r = calcular(D('7'), base + [adm('Química', 4.99, 0.2), adm('Física', 5.0, 0.2)])
    assert [u['nombre'] for u in r.usadas] == ['Física']
    assert r.admision == D('7.000') + D('1.000')


def test_pondera_como_maximo_dos_materias():
    base = acceso(8, 8, 8, 8)
    r = calcular(D('8'), base + [adm('A', 9, 0.2), adm('B', 8, 0.2), adm('C', 10, 0.2)])
    assert len(r.usadas) == 2 and {u['nombre'] for u in r.usadas} == {'A', 'C'}
    assert r.admision == D('8') + D('1.8') + D('2.0')


def test_con_una_sola_materia_pondera_esa():
    r = calcular(D('8'), acceso(8, 8) + [adm('A', 9, 0.1)])
    assert len(r.usadas) == 1 and r.admision == D('8.900')


def test_ninguna_materia_pondera_la_admision_es_la_cau():
    r = calcular(D('8'), acceso(8, 8))
    assert r.usadas == [] and r.admision == r.cau == D('8.000')
    assert 'ninguna materia pondera' in ' '.join(r.avisos)


def test_solo_una_segunda_lengua():
    ms = acceso(8, 8) + [adm('Inglés adicional', 9, 0.2, sl=True), adm('Francés', 8, 0.2, sl=True),
                         adm('Biología', 7, 0.1)]
    r = calcular(D('8'), ms)
    assert {u['nombre'] for u in r.usadas} == {'Inglés adicional', 'Biología'}
    assert r.admision == D('8') + D('1.8') + D('0.7')


def test_de_la_fase_de_acceso_solo_pondera_la_de_modalidad():
    ms = acceso(8, 8, modalidad=('Matemáticas II', 8, 0.2)) + [Materia('Lengua', D('9'), 'acceso', D('0'))]
    r = calcular(D('8'), ms)
    assert r.calculada and [u['nombre'] for u in r.usadas] == ['Matemáticas II']
    mal = acceso(8, 8, modalidad=('Matemáticas II', 8, 0.2)) + [Materia('Lengua', D('9'), 'acceso', D('0.2'))]
    r2 = calcular(D('8'), mal)
    assert not r2.calculada and 'solo pondera la materia obligatoria de modalidad' in ' '.join(r2.problemas)


def test_nota_maxima_14():
    r = calcular(D('10'), acceso(10, 10) + [adm('A', 10, 0.2), adm('B', 10, 0.2)])
    assert r.cau == D('10.000') and r.admision == D('14.000')   # el máximo teórico coincide con el tope


def test_pau_menor_de_4_no_cuenta():
    r = calcular(D('9'), acceso(3.9, 3.9, 3.9, 3.9) + [adm('A', 9, 0.2)])
    assert r.tiene_acceso is False and r.admision is None
    assert 'no llega a 4' in ' '.join(r.avisos)


def test_cau_menor_de_5_no_da_acceso():
    r = calcular(D('3'), acceso(5, 5, 5, 5) + [adm('A', 9, 0.2)])   # 0,6·3 + 0,4·5 = 3,8
    assert r.cau == D('3.800') and r.tiene_acceso is False and r.admision is None
    assert 'no llega a 5' in ' '.join(r.avisos)


def test_cau_justo_en_5_da_acceso():
    r = calcular(D('5'), acceso(5, 5, 5, 5))
    assert r.cau == D('5.000') and r.tiene_acceso is True


# --- redondeo ----------------------------------------------------------------------------------------------------

def test_redondeo_a_la_milesima_con_equidistancia_hacia_arriba():
    assert r3(D('8.0625')) == D('8.063')
    assert r3(D('0.0005')) == D('0.001')
    assert r3(D('8.0624')) == D('8.062')
    r = calcular(D('7'), acceso(8.00, 8.00, 8.00, 8.01))   # media 8,0025 → 8,003 (con float o redondeo bancario saldría 8,002)
    assert r.pau == D('8.003')


# --- datos que faltan: no se inventa nada ---------------------------------------------------------------------------

def test_falta_la_media_de_bachillerato():
    r = calcular(None, acceso(8, 8))
    assert not r.calculada and 'falta la nota media de Bachillerato' in r.problemas
    assert 'No invento' in explicar(r)


def test_faltan_los_ejercicios_de_acceso():
    r = calcular(D('8'), [adm('A', 9, 0.2)])
    assert not r.calculada and any('fase de acceso' in p for p in r.problemas)


def test_materia_aprobada_sin_ponderacion_no_cuenta_y_se_avisa():
    r = calcular(D('8'), acceso(8, 8) + [adm('Física', 9, None), adm('Biología', 8, 0.1)])
    assert [u['nombre'] for u in r.usadas] == ['Biología']
    assert 'Física' in r.sin_ponderacion and 'Sin ponderación escrita' in explicar(r)


def test_valores_fuera_de_rango():
    assert not calcular(D('11'), acceso(8)).calculada
    assert not calcular(D('8'), acceso(8) + [adm('A', 10.5, 0.2)]).calculada
    assert not calcular(D('8'), acceso(8) + [adm('A', 9, 0.3)]).calculada
    assert not calcular(D('8'), acceso(8) + [Materia('A', D('9'), 'bachillerato', D('0.1'))]).calculada


# --- entrada desde la hoja o el formulario ----------------------------------------------------------------------------

def test_desde_diccionario_acepta_comas_y_vacios():
    cfb, ms, errores = desde_diccionario({
        'nota_media_bachillerato': '8,5',
        'materias': [{'asignatura': 'Matemáticas II', 'nota': '8,5', 'fase': 'acceso', 'ponderacion': '0,2'},
                     {'asignatura': 'Física', 'nota': 7.5, 'fase': 'Admisión', 'ponderacion': ''},
                     {'asignatura': '', 'nota': 3},
                     {'asignatura': 'Inglés adicional', 'nota': 9, 'fase': 'admision', 'ponderacion': 0.2,
                      'segunda_lengua': 'sí'}]})
    assert errores == [] and cfb == D('8.5')
    assert [m.nombre for m in ms] == ['Matemáticas II', 'Física', 'Inglés adicional']
    assert ms[1].fase == 'admision' and ms[1].ponderacion is None and ms[2].segunda_lengua is True


def test_celda_ilegible_no_calcula_con_el_resto():
    r, texto = calcular_desde_diccionario({'nota_media_bachillerato': 'ocho',
                                           'materias': [{'asignatura': 'A', 'nota': 8, 'fase': 'acceso'}]})
    assert not r.calculada and 'no es un número' in texto


def test_calculo_completo_desde_diccionario_y_texto_con_desglose():
    d = {'nota_media_bachillerato': '8,5', 'materias': [
        {'asignatura': 'Acceso 1', 'nota': 8, 'fase': 'acceso'}, {'asignatura': 'Acceso 2', 'nota': 8, 'fase': 'acceso'},
        {'asignatura': 'Acceso 3', 'nota': 7.74, 'fase': 'acceso'},
        {'asignatura': 'Matemáticas II', 'nota': 8.5, 'fase': 'acceso', 'ponderacion': 0.2},
        {'asignatura': 'Física', 'nota': 7.5, 'fase': 'admision', 'ponderacion': 0.2}]}
    r, texto = calcular_desde_diccionario(d)
    assert r.admision == D('11.524')
    for esperado in ('11,524', '8,324', '8,060', 'Matemáticas II: 8,5 × 0,2 = 1,700', 'Física: 7,5 × 0,2 = 1,500',
                     'Fuentes:', '[doc06]', '[doc07]'):
        assert esperado in texto, esperado


def test_formato_espanol():
    assert fmt(D('0.2')) == '0,2' and fmt(D('8.50')) == '8,5' and fmt(D('10')) == '10'
    assert fmt(D('8.324'), 3) == '8,324' and fmt(D('1.7'), 3) == '1,700'


# --- las citas son texto literal del corpus --------------------------------------------------------------------------

@pytest.mark.parametrize('clave', sorted(FUENTES))
def test_la_cita_esta_literalmente_en_el_corpus(clave):
    doc, _, cita = FUENTES[clave]
    texto = (RAIZ / 'data' / 'texto' / f'{doc}.txt').read_text(encoding='utf-8')
    assert f' {normaliza(cita)} ' in f' {normaliza(texto)} '
