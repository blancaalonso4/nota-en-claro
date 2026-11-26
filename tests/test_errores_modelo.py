"""Mensajes de error de Ollama: «la respuesta se cortó» frente a «no puedo conectar»."""
import httpx
import ollama
import pytest

from app.agentes import errores_modelo as em
from app.agentes.coordinador import Coordinador
from app.rag.config import ConfigRAG
from app.agentes.traza import Traza
from tests.test_acciones import OllamaGuionizado, PuenteFalso, agente

CORTE = ollama.ResponseError('llama-server returned invalid tool call arguments for "crear_eventos_estudio": '
                             'unexpected end of JSON input', 500)


@pytest.mark.parametrize('error, tipo', [
    (CORTE, em.CORTADA),
    (ollama.ResponseError('model "x" not found', 404), em.SIN_MODELO),
    (ollama.ResponseError('se cayó el runner', 500), em.INTERNO),
    (ollama.ResponseError('petición mala', 400), em.OTRO),
    (ConnectionError('Failed to connect to Ollama'), em.SIN_CONEXION),
    (httpx.ConnectError('refused'), em.SIN_CONEXION),
    (ollama.RequestError('sin modelo'), em.SIN_CONEXION),
    (ValueError('x'), em.OTRO),
])
def test_clasifica(error, tipo):
    assert em.clasificar(error) == tipo


def test_los_dos_mensajes_principales_se_distinguen():
    corte, conexion = em.mensaje(CORTE), em.mensaje(ConnectionError('x'))
    assert 'se cortó' in corte and 'No puedo conectar' not in corte and 'está funcionando' in corte
    assert 'No puedo conectar con Ollama' in conexion and 'se cortó' not in conexion


def test_el_agente_de_acciones_distingue_corte_y_conexion(tmp_path):
    a, traza = agente(tmp_path, OllamaGuionizado(CORTE), PuenteFalso())
    r = a.ejecutar('plan_estudio', 'plan')
    assert not r.ok and 'se cortó' in r.error and 'conectar' not in r.error
    assert 'ResponseError' in traza.pasos[0]['error'] and '500' in traza.pasos[0]['error']      # el detalle técnico sigue en la traza
    a, _ = agente(tmp_path, OllamaGuionizado(ConnectionError('x')), PuenteFalso())
    assert 'No puedo conectar con Ollama' in a.ejecutar('plan_estudio', 'plan').error


def test_el_coordinador_usa_el_mismo_mensaje(tmp_path):
    class Cliente:
        def __init__(self, e):
            self.e = e

        def chat(self, **kw):
            raise self.e
    t = Traza(tmp_path, 's')
    assert 'se cortó' in Coordinador(t, ConfigRAG(), Cliente(CORTE)).clasificar('hola').error
    assert 'No puedo conectar' in Coordinador(t, ConfigRAG(), Cliente(ConnectionError('x'))).clasificar('hola').error
