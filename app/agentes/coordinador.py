"""Coordinador y orquestador.

El coordinador hace UNA llamada corta a `qwen3:4b-instruct` con salida JSON restringida por esquema (Ollama `format=`)
y decide a qué trabajador pasa la petición. El orquestador llama a ese trabajador:

  normativa         -> SistemaRAG (RAG, no ve Drive ni Gmail)
  nota_admision     -> calculadora en Python (0 llamadas al modelo)
  plan/informe/correo -> agente de acciones (herramientas MCP)
  fuera_de_ambito   -> mensaje fijo (0 llamadas)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import ollama

from app.rag.config import ConfigRAG

from . import errores_modelo
from .nota_admision import calcular_desde_diccionario
from .traza import Traza

ORIGEN_NOTAS = {'hoja': 'He calculado tu nota con **tu hoja de Google «Mis notas»**.',
                'formulario': 'He calculado tu nota con **las notas introducidas a mano**.'}
INTENCIONES = ['normativa', 'nota_admision', 'plan_estudio', 'informe', 'correo_orientador', 'fuera_de_ambito']
ESQUEMA = {'type': 'object',
           'properties': {'intencion': {'type': 'string', 'enum': INTENCIONES},
                          'dias': {'type': ['integer', 'null']}},
           'required': ['intencion']}
NUM_PREDICT = 40
DIAS_POR_DEFECTO, DIAS_MAXIMOS = 7, 14

# Prompt fijo y corto (idéntico byte a byte en cada llamada: así Ollama reutiliza su caché de prefijo).
SISTEMA = ('Clasifica la petición de un estudiante de 2.º de Bachillerato de Madrid que prepara la PAU. '
           'Responde solo un JSON con "intencion" y "dias".\n'
           '- normativa: cualquier duda sobre la PAU, el acceso o la admisión a la universidad, universidades, grados, '
           'plazas, notas de corte, plazos, requisitos, reglas o documentos oficiales.\n'
           '- nota_admision: calcular SU nota de acceso o de admisión con sus propias notas.\n'
           '- plan_estudio: crear un plan o calendario de estudio.\n'
           '- informe: guardar un informe de sus notas.\n'
           '- correo_orientador: escribir o responder un correo a su orientador.\n'
           '- fuera_de_ambito: solo temas sin relación con la PAU ni con la universidad.\n'
           '"dias": días del plan de estudio si lo indica; si no, 7; null en el resto.')

FUERA_DE_AMBITO = ('Solo puedo ayudarte con la PAU de Madrid: dudas de normativa, calcular tu nota de admisión, '
                   'un plan de estudio, un informe de tus notas o un correo a tu orientador.')
NO_ENTENDIDO = 'No he entendido la petición. ¿Puedes decirlo de otra forma?'


@dataclass
class Decision:
    intencion: str | None
    dias: int = DIAS_POR_DEFECTO
    error: str = ''


class Coordinador:
    def __init__(self, traza: Traza, cfg: ConfigRAG | None = None, cliente=None):
        self.traza, self.cfg = traza, cfg or ConfigRAG()
        self.cliente = cliente or ollama.Client()

    def _opciones(self) -> dict:
        c = self.cfg
        o = {'seed': c.semilla, 'temperature': c.temperature, 'num_predict': NUM_PREDICT, 'num_ctx': c.num_ctx}
        if c.num_thread is not None:
            o['num_thread'] = c.num_thread
        return o

    def clasificar(self, peticion: str) -> Decision:
        """Una llamada al modelo. Si el JSON no es válido no se reintenta ni se inventa una intención."""
        t0 = time.perf_counter()
        try:
            r = self.cliente.chat(model=self.cfg.modelo, format=ESQUEMA, think=self.cfg.think, options=self._opciones(),
                                  keep_alive=self.cfg.keep_alive,
                                  messages=[{'role': 'system', 'content': SISTEMA},
                                            {'role': 'user', 'content': peticion.strip()[:500]}])
        except Exception as e:  # noqa: BLE001
            self.traza.registrar('modelo', 'coordinador', segundos=time.perf_counter() - t0, fallo=True,
                                 error=f'{type(e).__name__}: {e}')
            return Decision(None, error=errores_modelo.mensaje(e, self.cfg.modelo))
        base = dict(tokens_entrada=getattr(r, 'prompt_eval_count', 0) or 0, tokens_salida=getattr(r, 'eval_count', 0) or 0,
                    segundos=time.perf_counter() - t0)
        crudo = (r.message.content or '').strip()
        try:
            d = json.loads(crudo)
            intencion = d['intencion']
            if intencion not in INTENCIONES:
                raise ValueError(f'intención desconocida: {intencion!r}')
            dias = d.get('dias')
            dias = min(max(dias, 1), DIAS_MAXIMOS) if isinstance(dias, int) and not isinstance(dias, bool) else DIAS_POR_DEFECTO
        except (ValueError, KeyError, TypeError) as e:
            self.traza.registrar('modelo', 'coordinador', fallo=True, error=f'salida no válida ({e}): {crudo[:80]}', **base)
            return Decision(None, error=NO_ENTENDIDO)
        self.traza.registrar('modelo', 'coordinador', intencion=intencion, **base)
        return Decision(intencion, dias)


class Orquestador:
    """Une coordinador y trabajadores. Cada trabajador se inyecta (en los tests, falsos)."""

    def __init__(self, coordinador: Coordinador, traza: Traza, rag=None, acciones=None, puente=None):
        self.coordinador, self.traza, self.rag, self.acciones, self.puente = coordinador, traza, rag, acciones, puente

    def atender(self, peticion: str, notas_manuales: dict | None = None):
        """Generador de eventos para la interfaz:
        {'intencion': str}, {'trozo': str} (solo normativa), y al final {'resultado': dict} con 'intencion', 'texto' y los
        datos propios de cada trabajador (fuente, borrador, eventos...)."""
        self.traza.nueva_peticion(peticion)
        d = self.coordinador.clasificar(peticion)
        if d.intencion is None:
            yield {'resultado': {'intencion': None, 'texto': d.error, 'error': True}}
            return
        yield {'intencion': d.intencion}
        if d.intencion == 'fuera_de_ambito':
            yield {'resultado': {'intencion': d.intencion, 'texto': FUERA_DE_AMBITO}}
        elif d.intencion == 'normativa':
            yield from self._normativa(peticion)
        elif d.intencion == 'nota_admision':
            yield {'resultado': self._nota(notas_manuales)}
        else:
            r = self.acciones.ejecutar(d.intencion, peticion, d.dias)
            yield {'resultado': {'intencion': d.intencion, 'texto': r.texto or r.error, 'error': not r.ok,
                                 'borrador': r.borrador, 'eventos': r.eventos, 'informe': r.informe}}

    def _normativa(self, peticion: str):
        from app.rag.pipeline import formatear
        for ev in self.rag.responder_stream(peticion):
            if 'trozo' in ev:
                yield ev
            else:
                r = ev['resultado']
                self.traza.registrar('modelo', 'normativa', tokens_entrada=r['tokens_entrada'], tokens_salida=r['tokens_salida'],
                                     segundos=r['segundos_generar'], abstiene=r['abstiene'])
                yield {'resultado': {'intencion': 'normativa', 'texto': formatear(r), 'datos': r}}

    def _nota(self, notas_manuales: dict | None) -> dict:
        """Calculadora en Python. Notas del formulario manual o, si no hay, de la hoja «Mis notas» (sin modelo)."""
        origen = 'formulario'
        datos = notas_manuales
        if datos is None:
            origen = 'hoja'
            if self.puente is None:
                return {'intencion': 'nota_admision', 'error': True, 'texto': 'No tengo tus notas: rellena el formulario «Introducir mis notas a mano» o crea tu hoja «Mis notas».'}
            with self.traza.paso('herramienta', 'calculadora', herramienta='leer_notas', permiso='automatico') as p:
                r = self.puente.llamar('leer_notas')
                if not r.ok:
                    p['fallo'], p['error'] = True, r.detalle or r.mensaje
                p['reintento'] = r.reintentos > 0
            if not r.ok:
                return {'intencion': 'nota_admision', 'error': True, 'texto': r.mensaje}
            datos = r.datos
        resultado, texto = calcular_desde_diccionario(datos)
        # se dice con qué notas se ha calculado (la hoja de Google o la tabla manual), para que el estudiante lo pueda comprobar
        texto = f'{ORIGEN_NOTAS[origen]}\n\n{texto}'
        return {'intencion': 'nota_admision', 'texto': texto, 'error': bool(resultado.problemas),
                'origen_notas': origen}
