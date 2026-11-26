"""Interfaz Streamlit con AppTest: orquestador y servicios falsos (sin Ollama ni Google)."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import servicios
from app.agentes import coordinador as co
from app.tabla_notas import tabla_a_notas, tabla_vacia
from app.agentes.puente_mcp import ResultadoLlamada
from app.rag.config import ConfigRAG

INTERFAZ = str(Path(__file__).resolve().parents[1] / 'app' / 'interfaz.py')
ORI = 'orientador@ejemplo.com'


class Cliente:
    """Coordinador falso: responde siempre con la intención indicada."""

    def __init__(self, intencion):
        self.intencion = intencion

    def chat(self, **kw):
        return NS(message=NS(content=json.dumps({'intencion': self.intencion, 'dias': 7})), prompt_eval_count=140, eval_count=11)


class RagFalso:
    def responder_stream(self, p):
        yield {'trozo': 'RESPUESTA: tres días'}
        yield {'resultado': {'abstiene': False, 'respuesta': 'Tienes tres días hábiles.', 'cita': 'tres días hábiles',
                             'tokens_entrada': 1800, 'tokens_salida': 50, 'segundos_generar': 30.0,
                             'fuente': {'doc_id': 'doc13', 'titulo': 'Preguntas frecuentes', 'fecha': '2025', 'pagina': 2, 'chunk_id': 'c1'}}}


class AccionesFalso:
    def ejecutar(self, intencion, peticion, dias):
        borrador = {'borrador_id': 'R1', 'destinatario': ORI, 'asunto': 'Reunión', 'cuerpo': 'Hola, ¿nos vemos el jueves?'}
        return NS(ok=True, texto='He creado un borrador para el orientador (sin enviar).', error='',
                  borrador=borrador if intencion == 'correo_orientador' else None, eventos=[], informe=None)


class PuenteFalso:
    def __init__(self):
        self.enviados = []

    def enviar_correo_confirmado(self, borrador_id, orientador):
        self.enviados.append((borrador_id, orientador))
        return ResultadoLlamada(True, datos={'enviado': True}, segundos=0.4)

    def llamar(self, nombre, args=None):
        return ResultadoLlamada(True, datos={'url': 'https://docs.google.com/spreadsheets/d/H1', 'creada': True})


@pytest.fixture
def app(monkeypatch):
    st.cache_resource.clear()
    puente = PuenteFalso()
    recursos = servicios.Recursos(RagFalso(), puente, ConfigRAG())
    monkeypatch.setattr(servicios, 'crear_recursos', lambda: recursos)
    monkeypatch.setattr(servicios, 'estado_google', lambda: {'credenciales': True, 'tokens': {'drive': True, 'calendar': True, 'gmail': True},
                                                              'orientador': ORI, 'lista': True, 'hoja_notas_id': 'H1'})

    def preparar(intencion):
        monkeypatch.setattr(servicios, 'crear_orquestador', lambda rec, traza: co.Orquestador(
            co.Coordinador(traza, rec.cfg, Cliente(intencion)), traza, rag=rec.rag, acciones=AccionesFalso(), puente=rec.puente))
        at = AppTest.from_file(INTERFAZ, default_timeout=30)
        at.run()
        assert not at.exception
        return at
    preparar.puente = puente
    return preparar


def textos(at):
    return [m.markdown[0].value for m in at.chat_message if m.markdown]


def test_normativa_con_fuente_y_traza(app):
    at = app('normativa')
    at.chat_input[0].set_value('¿Cuántos días tengo para reclamar?').run()
    assert not at.exception
    assert any('Tienes tres días hábiles.' in t and 'doc13' in t for t in textos(at))
    assert any('Tipo de petición: normativa' in c.value for c in at.caption)
    # panel de traza: coordinador + normativa, con tokens
    assert any('2 pasos' in c.value for c in at.caption if 'pasos' in c.value)
    filas = at.dataframe[-1].value
    assert list(filas['agente']) == ['coordinador', 'normativa'] and list(filas['tokens_entrada']) == [140, 1800]


def test_fuera_de_ambito(app):
    at = app('fuera_de_ambito')
    at.chat_input[0].set_value('cuéntame un chiste').run()
    assert any(co.FUERA_DE_AMBITO in t for t in textos(at))


def test_correo_muestra_el_borrador_y_enviar_exige_pulsar_el_boton(app):
    at = app('correo_orientador')
    at.chat_input[0].set_value('escribe a mi orientador').run()
    assert not app.puente.enviados                                 # crear el borrador no envía nada
    assert any('Borrador pendiente' in s.value for s in at.subheader)
    assert any(ORI in m.value for m in at.markdown)
    boton = next(b for b in at.button if b.label == 'Enviar al orientador')
    boton.click().run()
    assert app.puente.enviados == [('R1', ORI)]
    assert any('Correo enviado' in t for t in textos(at)) and not any('Borrador pendiente' in s.value for s in at.subheader)
    assert any(p == 'confirmar' for p in at.dataframe[-1].value['permiso'])    # el envío queda en la traza con su permiso


def test_descartar_no_envia(app):
    at = app('correo_orientador')
    at.chat_input[0].set_value('escribe a mi orientador').run()
    next(b for b in at.button if b.label == 'Descartar').click().run()
    assert app.puente.enviados == [] and any('No lo he enviado' in t for t in textos(at))


def sin_google(monkeypatch):
    monkeypatch.setattr(servicios, 'estado_google', lambda: {'credenciales': False, 'tokens': {'drive': False, 'calendar': False, 'gmail': False},
                                                              'orientador': None, 'lista': False, 'hoja_notas_id': None})


def test_formulario_de_notas_esta_en_el_area_principal_y_con_cabeceras(app, monkeypatch):
    sin_google(monkeypatch)
    at = app('nota_admision')
    assert any('La parte de Google no está lista' in w.value for w in at.sidebar.warning)
    # el formulario ya no vive en la barra lateral: no hay editor ni número de media ahí
    assert not at.sidebar.number_input and not [e for e in at.sidebar if e.type == 'dataframe']
    assert [e.label for e in at.main.number_input] == ['Nota media de Bachillerato (0-10, sin Religión)']
    assert any(e.label == 'Introducir mis notas a mano' for e in at.expander)
    # el editor está dentro del formulario del área principal y es la primera tabla de la página (la de la traza va después)
    cabeceras = json.loads(at.dataframe[0].proto.columns)
    assert all(c in cabeceras for c in ('Asignatura', 'Nota', 'Fase', 'Ponderación', 'Segunda lengua'))
    assert at.dataframe[0].proto.editing_mode == 2   # DYNAMIC: se pueden añadir filas


def test_tabla_a_notas_ignora_filas_vacias_y_traduce_las_columnas():
    tabla = tabla_vacia()
    tabla.loc[0, ['Asignatura', 'Nota', 'Fase', 'Ponderación']] = ['Matemáticas II', 8.5, 'acceso', '0,2']
    tabla.loc[1, ['Asignatura', 'Nota', 'Fase']] = ['Inglés', 7.0, 'admisión']
    tabla.loc[1, 'Segunda lengua'] = True
    tabla.loc[2, 'Nota'] = 9.0                       # sin asignatura: se ignora
    d = tabla_a_notas(tabla, 8.5)
    assert d == {'nota_media_bachillerato': 8.5, 'materias': [
        {'asignatura': 'Matemáticas II', 'nota': 8.5, 'fase': 'acceso', 'ponderacion': '0,2', 'segunda_lengua': ''},
        {'asignatura': 'Inglés', 'nota': 7.0, 'fase': 'admisión', 'ponderacion': '', 'segunda_lengua': 'sí'}]}


def test_nota_con_notas_a_mano_sin_google(app, monkeypatch):
    sin_google(monkeypatch)
    at = app('nota_admision')
    at.number_input(key='media_notas').set_value(8.5)
    filas = [('Acceso 1', 8.0, 'acceso', None), ('Acceso 2', 8.0, 'acceso', None), ('Acceso 3', 7.74, 'acceso', None),
             ('Matemáticas II', 8.5, 'acceso', '0,2'), ('Física', 7.5, 'admisión', '0,2')]
    at.session_state['editor_notas'] = {'edited_rows': {i: {'Asignatura': n, 'Nota': nota, 'Fase': fase, 'Ponderación': pond}
                                                         for i, (n, nota, fase, pond) in enumerate(filas)},
                                        'added_rows': [], 'deleted_rows': []}
    next(b for b in at.button if b.label == 'Usar estas notas').click().run()
    assert not at.exception
    assert at.session_state.notas_manuales is not None
    at.chat_input[0].set_value('calcula mi nota de admisión').run()
    assert not at.exception
    assert any('11,524' in t for t in textos(at))


def test_crear_hoja_de_notas(app):
    at = app('normativa')
    next(b for b in at.sidebar.button if b.label == 'Crear mi hoja de notas').click().run()
    assert any('Hoja creada' in s.value and 'docs.google.com/spreadsheets/d/H1' in s.value for s in at.sidebar.success)
    assert any('Ábrela con la cuenta de Google conectada, rellénala y luego pídeme «calcula mi nota de admisión»' in m.value for m in at.sidebar.markdown)
