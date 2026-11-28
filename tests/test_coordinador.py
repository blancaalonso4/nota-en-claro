"""Coordinador y orquestador con un Ollama guionizado y trabajadores falsos (sin modelo, sin Google)."""
import json
from types import SimpleNamespace as NS

from app.agentes import coordinador as co
from app.agentes.plan_calendario import PREGUNTA_SUSTITUIR
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

    def ejecutar(self, intencion, peticion, dias, contacto=None):
        self.llamadas.append((intencion, dias))
        self.contacto = contacto
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
    assert r['texto'].startswith('He calculado tu nota con **las notas introducidas a mano**.')
    assert 'hoja de Google' not in r['texto']
    assert len([p for p in t.pasos if p['tipo'] == 'modelo']) == 1       # solo el coordinador


def test_nota_desde_la_hoja_lee_por_mcp_sin_modelo(tmp_path):
    class Puente:
        def llamar(self, n, a=None):
            assert n == 'leer_notas'
            return ResultadoLlamada(True, datos=NOTAS_MANUALES)
    o, t = orq(tmp_path, 'nota_admision', puente=Puente())
    r = eventos(o)[-1]['resultado']
    assert '11,524' in r['texto'] and r['origen_notas'] == 'hoja'
    assert r['texto'].startswith('He calculado tu nota con **tu hoja de Google «Mis notas»**.')
    assert 'a mano' not in r['texto']
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


# --- datos de contacto del estudiante (sesión 6) ---------------------------------------------------------------------------

HOJA_CON_CONTACTO = {'materias': [], 'nota_media_bachillerato': None, 'avisos': [], 'nombre_estudiante': 'Luis (hoja)',
                     'nombre_orientador': 'Marta (hoja)', 'correo_orientador': 'hoja@instituto.es'}


class PuenteHoja:
    def __init__(self, datos=HOJA_CON_CONTACTO, ok=True):
        self.datos, self.ok, self.llamadas = datos, ok, 0

    def llamar(self, n, a=None):
        self.llamadas += 1
        return ResultadoLlamada(self.ok, datos=self.datos if self.ok else None, mensaje='' if self.ok else 'sin hoja')


def test_correo_usa_los_datos_de_la_hoja(tmp_path):
    ac, p = AccionesFalso(), PuenteHoja()
    o, t = orq(tmp_path, 'correo_orientador', acciones=ac, puente=p)
    eventos(o)
    assert (ac.contacto.nombre_estudiante, ac.contacto.nombre_orientador, ac.contacto.correo_orientador) == ('Luis (hoja)', 'Marta (hoja)', 'hoja@instituto.es')
    assert ('herramienta', 'leer_notas') in [(p_['tipo'], p_['herramienta']) for p_ in t.pasos if p_['tipo'] == 'herramienta']


def test_los_campos_de_la_app_mandan_sobre_la_hoja_campo_a_campo(tmp_path):
    ac = AccionesFalso()
    o, _ = orq(tmp_path, 'correo_orientador', acciones=ac, puente=PuenteHoja())
    eventos(o, contacto_manual={'correo_orientador': 'app@instituto.es', 'nombre_estudiante': '', 'nombre_orientador': ' '})
    c = ac.contacto
    assert (c.nombre_estudiante, c.nombre_orientador, c.correo_orientador) == ('Luis (hoja)', 'Marta (hoja)', 'app@instituto.es')


def test_con_los_tres_campos_de_la_app_no_se_lee_la_hoja(tmp_path):
    ac, p = AccionesFalso(), PuenteHoja()
    o, _ = orq(tmp_path, 'correo_orientador', acciones=ac, puente=p)
    eventos(o, contacto_manual={'nombre_estudiante': 'A', 'nombre_orientador': 'B', 'correo_orientador': 'b@instituto.es'})
    assert p.llamadas == 0 and ac.contacto.correo_orientador == 'b@instituto.es'


def test_si_la_hoja_falla_se_sigue_con_lo_que_haya(tmp_path):
    ac = AccionesFalso()
    o, t = orq(tmp_path, 'correo_orientador', acciones=ac, puente=PuenteHoja(ok=False))
    r = eventos(o, contacto_manual={'correo_orientador': 'app@instituto.es'})[-1]['resultado']
    assert not r['error'] and ac.contacto.correo_orientador == 'app@instituto.es'
    assert any(p_.get('fallo') for p_ in t.pasos if p_['tipo'] == 'herramienta')


def test_las_demas_acciones_no_leen_el_contacto(tmp_path):
    ac, p = AccionesFalso(), PuenteHoja()
    o, _ = orq(tmp_path, 'plan_estudio', acciones=ac, puente=p)
    eventos(o)
    assert p.llamadas == 0


# --- sustitución del plan de estudio -----------------------------------------------------------------------------------------

class AccionesPlan:
    """El agente de acciones que solo propone: devuelve `plan_propuesto` y no ha escrito nada."""

    def ejecutar(self, intencion, peticion, dias, contacto=None):
        propuesta = [{'titulo': 'Estudio: Física', 'inicio': '2026-12-02T16:00:00+01:00', 'fin': '2026-12-02T17:30:00+01:00'}]
        return NS(ok=True, texto='Te propongo 1 sesiones:\n- miércoles 2 dic 16:00–17:30 · Estudio: Física', error='', borrador=None,
                  eventos=[], informe=None, plan_propuesto=propuesta, huecos=[{'id': 1}], dias=7)


class PuentePlan:
    def __init__(self, existentes):
        self.existentes, self.llamadas = existentes, []

    def aplicar_plan(self, eventos, *, huecos, dias, zona, franja=None, confirmado=False, ahora=None):
        self.llamadas.append((len(eventos), confirmado, huecos, dias, zona))
        if self.existentes and not confirmado:
            return ResultadoLlamada(True, datos={'aplicado': False, 'existentes': self.existentes})
        return ResultadoLlamada(True, datos={'aplicado': True, 'creados': [dict(e) for e in eventos], 'existentes': 0,
                                             'borrados': 0, 'no_borrados': 0, 'calendario_id': 'CAL'})


def test_plan_sin_eventos_previos_se_crea_sin_preguntar(tmp_path):
    p = PuentePlan(existentes=0)
    o, t = orq(tmp_path, 'plan_estudio', acciones=AccionesPlan(), puente=p)
    r = eventos(o)[-1]['resultado']
    assert not r['error'] and 'plan_pendiente' not in r and r['texto'].startswith('He creado 1 sesiones')
    assert p.llamadas == [(1, False, [{'id': 1}], 7, 'Europe/Madrid')]


def test_plan_con_eventos_previos_queda_pendiente_con_la_pregunta(tmp_path):
    p = PuentePlan(existentes=6)
    o, t = orq(tmp_path, 'plan_estudio', acciones=AccionesPlan(), puente=p)
    r = eventos(o)[-1]['resultado']
    assert r['texto'].startswith('Te propongo 1 sesiones:') and r['texto'].endswith(PREGUNTA_SUSTITUIR.format(n=6))
    assert r['plan_pendiente']['existentes'] == 6 and len(r['plan_pendiente']['eventos']) == 1
    assert r['plan_pendiente']['huecos'] == [{'id': 1}] and r['plan_pendiente']['dias'] == 7
    assert p.llamadas == [(1, False, [{'id': 1}], 7, 'Europe/Madrid')]            # una sola llamada y sin confirmar: no se borra nada
    paso = [x for x in t.pasos if x['herramienta'] == 'aplicar_plan_estudio'][0]
    assert paso['agente'] == 'orquestador' and paso['permiso'] == 'confirmar' and paso['existentes'] == 6


def test_los_falsos_sin_plan_propuesto_siguen_funcionando(tmp_path):
    o, _ = orq(tmp_path, 'plan_estudio', puente=PuentePlan(existentes=3))       # AccionesFalso no tiene plan_propuesto
    r = eventos(o)[-1]['resultado']
    assert r['texto'] == 'hecho' and 'plan_pendiente' not in r
