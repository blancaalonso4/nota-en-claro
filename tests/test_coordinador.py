"""Coordinador y orquestador con un Ollama guionizado y trabajadores falsos (sin modelo, sin Google)."""
import json
from types import SimpleNamespace as NS

from app.agentes import coordinador as co
from app.agentes.puente_mcp import ResultadoLlamada
from app.agentes.traza import Traza
from app.rag.config import ConfigRAG


class Cliente:
    def __init__(self, *contenidos):
        self.contenidos, self.recibido = list(contenidos), []

    def chat(self, **kw):
        self.recibido.append(kw)
        c = self.contenidos.pop(0)
        if isinstance(c, Exception):
            raise c
        return NS(message=NS(content=c), prompt_eval_count=150, eval_count=12)


def coord(tmp_path, *contenidos):
    t = Traza(tmp_path, sesion='c')
    return co.Coordinador(t, ConfigRAG(), Cliente(*contenidos)), t


def test_clasifica_con_salida_json_restringida_y_opciones_reproducibles(tmp_path):
    c, t = coord(tmp_path, json.dumps({'intencion': 'plan_estudio', 'dias': 5}))
    d = c.clasificar('Hazme un plan de estudio para 5 días')
    assert (d.intencion, d.dias, d.error) == ('plan_estudio', 5, '')
    kw = c.cliente.recibido[0]
    assert kw['format'] == co.ESQUEMA and kw['think'] is False
    assert kw['options']['seed'] == 42 and kw['options']['temperature'] == 0 and kw['options']['num_predict'] == 40
    assert kw['messages'][0] == {'role': 'system', 'content': co.SISTEMA}
    p = t.pasos[0]
    assert (p['agente'], p['tipo'], p['tokens_entrada'], p['tokens_salida'], p['intencion']) == ('coordinador', 'modelo', 150, 12, 'plan_estudio')


def test_el_esquema_cubre_las_seis_intenciones():
    assert set(co.ESQUEMA['properties']['intencion']['enum']) == {'normativa', 'nota_admision', 'plan_estudio', 'informe',
                                                                   'correo_orientador', 'fuera_de_ambito'}
    assert all(i in co.SISTEMA for i in co.INTENCIONES)


def test_dias_se_acota_y_tiene_valor_por_defecto(tmp_path):
    for salida, esperado in ((None, 7), (400, 14), (0, 1), ('tres', 7), (True, 7)):
        c, _ = coord(tmp_path, json.dumps({'intencion': 'plan_estudio', 'dias': salida}))
        assert c.clasificar('plan').dias == esperado, salida


def test_salida_no_valida_no_se_reintenta_ni_se_inventa_intencion(tmp_path):
    for malo in ('esto no es json', '{"intencion": "hackear"}', '{"dias": 3}', '[]'):
        c, t = coord(tmp_path, malo)
        d = c.clasificar('algo')
        assert d.intencion is None and d.error == co.NO_ENTENDIDO and len(c.cliente.recibido) == 1
        assert t.pasos[-1]['fallo'] is True


def test_ollama_caido(tmp_path):
    c, t = coord(tmp_path, ConnectionError('no responde'))
    d = c.clasificar('hola')
    assert d.intencion is None and 'Ollama' in d.error and t.pasos[0]['fallo']


# --- orquestador ---------------------------------------------------------------------------------------------------------

class RagFalso:
    def responder_stream(self, p):
        yield {'trozo': 'RESPUESTA: tres '}
        yield {'resultado': {'abstiene': False, 'respuesta': 'Tres días hábiles.', 'cita': 'tres días hábiles', 'tokens_entrada': 1900,
                             'tokens_salida': 60, 'segundos_generar': 40.0,
                             'fuente': {'doc_id': 'doc13', 'titulo': 'FAQ', 'fecha': '2025', 'pagina': 3, 'chunk_id': 'c1'}}}


class AccionesFalso:
    def __init__(self):
        self.llamadas = []

    def ejecutar(self, intencion, peticion, dias):
        self.llamadas.append((intencion, dias))
        return NS(ok=True, texto='hecho', error='', borrador=None, eventos=[], informe=None)


def orq(tmp_path, intencion, dias=7, **kw):
    c, t = coord(tmp_path, json.dumps({'intencion': intencion, 'dias': dias}))
    o = co.Orquestador(c, t, rag=kw.get('rag', RagFalso()), acciones=kw.get('acciones', AccionesFalso()), puente=kw.get('puente'))
    return o, t


def eventos(o, peticion='x', **kw):
    return list(o.atender(peticion, **kw))


def test_normativa_va_al_rag_y_registra_sus_tokens(tmp_path):
    o, t = orq(tmp_path, 'normativa')
    ev = eventos(o, '¿Cuántos días hay para reclamar?')
    assert ev[0] == {'intencion': 'normativa'} and {'trozo': 'RESPUESTA: tres '} in ev
    r = ev[-1]['resultado']
    assert r['intencion'] == 'normativa' and 'Tres días hábiles.' in r['texto'] and 'doc13' in r['texto']
    assert [p['agente'] for p in t.pasos] == ['coordinador', 'normativa'] and t.pasos[1]['tokens_entrada'] == 1900
    assert t.peticion == '¿Cuántos días hay para reclamar?'


def test_fuera_de_ambito_no_llama_a_nadie(tmp_path):
    ac = AccionesFalso()
    o, t = orq(tmp_path, 'fuera_de_ambito', acciones=ac)
    r = eventos(o, 'cuéntame un chiste')[-1]['resultado']
    assert r['texto'] == co.FUERA_DE_AMBITO and ac.llamadas == [] and len(t.pasos) == 1


def test_acciones_reciben_intencion_y_dias(tmp_path):
    ac = AccionesFalso()
    o, _ = orq(tmp_path, 'plan_estudio', dias=5, acciones=ac)
    r = eventos(o)[-1]['resultado']
    assert ac.llamadas == [('plan_estudio', 5)] and r['texto'] == 'hecho' and not r['error']


def test_coordinador_sin_intencion_valida_corta(tmp_path):
    c, t = coord(tmp_path, 'basura')
    ev = list(co.Orquestador(c, t).atender('???'))
    assert len(ev) == 1 and ev[0]['resultado']['error'] and ev[0]['resultado']['texto'] == co.NO_ENTENDIDO


NOTAS_MANUALES = {'nota_media_bachillerato': '8,5', 'materias': [
    {'asignatura': 'Acceso 1', 'nota': 8, 'fase': 'acceso'}, {'asignatura': 'Acceso 2', 'nota': 8, 'fase': 'acceso'},
    {'asignatura': 'Acceso 3', 'nota': 7.74, 'fase': 'acceso'},
    {'asignatura': 'Matemáticas II', 'nota': 8.5, 'fase': 'acceso', 'ponderacion': 0.2},
    {'asignatura': 'Física', 'nota': 7.5, 'fase': 'admision', 'ponderacion': 0.2}]}


def test_nota_con_formulario_manual_funciona_sin_google_ni_segunda_llamada(tmp_path):
    o, t = orq(tmp_path, 'nota_admision')
    r = eventos(o, 'Calcula mi nota de admisión', notas_manuales=NOTAS_MANUALES)[-1]['resultado']
    assert '11,524' in r['texto'] and not r['error'] and r['origen_notas'] == 'formulario'
    assert len([p for p in t.pasos if p['tipo'] == 'modelo']) == 1       # solo el coordinador


def test_nota_desde_la_hoja_lee_por_mcp_sin_modelo(tmp_path):
    class Puente:
        def llamar(self, n, a=None):
            assert n == 'leer_notas'
            return ResultadoLlamada(True, datos=NOTAS_MANUALES)
    o, t = orq(tmp_path, 'nota_admision', puente=Puente())
    r = eventos(o)[-1]['resultado']
    assert '11,524' in r['texto'] and r['origen_notas'] == 'hoja'
    assert [(p['tipo'], p['herramienta']) for p in t.pasos if p['tipo'] == 'herramienta'] == [('herramienta', 'leer_notas')]


def test_nota_sin_notas_ni_puente_lo_dice(tmp_path):
    o, _ = orq(tmp_path, 'nota_admision')
    r = eventos(o)[-1]['resultado']
    assert r['error'] and 'formulario' in r['texto']


def test_nota_fallo_de_google_mensaje_claro(tmp_path):
    class Puente:
        def llamar(self, n, a=None):
            return ResultadoLlamada(False, mensaje='Todavía no has creado tu hoja «Mis notas».', detalle='x')
    o, t = orq(tmp_path, 'nota_admision', puente=Puente())
    r = eventos(o)[-1]['resultado']
    assert r['error'] and 'Todavía no has creado' in r['texto'] and t.pasos[-1]['fallo']


def test_nota_con_datos_incompletos_no_inventa(tmp_path):
    o, _ = orq(tmp_path, 'nota_admision')
    r = eventos(o, notas_manuales={'nota_media_bachillerato': None, 'materias': []})[-1]['resultado']
    assert r['error'] and 'No invento' in r['texto']
