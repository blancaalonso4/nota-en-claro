"""Sustituir el plan de estudio en el calendario. Python puro, sin modelo.

El agente de acciones solo PROPONE un plan (el verificador lo aprueba); aquí se escribe en Google, siempre por el
puente (`PuenteMCP.aplicar_plan`), nunca el modelo. Si el calendario «Nota en Claro · Estudio» está vacío se crea sin
preguntar; si ya tiene sesiones, el estudiante debe confirmar antes de que se borren todas (también las editadas a mano).
En la traza queda el número de eventos y el id del calendario, nunca títulos ni fechas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import plan

ETIQUETA_CALENDARIO = 'Nota en Claro · Estudio'
PREGUNTA_SUSTITUIR = ('Ya tienes un plan con {n} sesiones en el calendario «Nota en Claro · Estudio». '
                      'Si lo sustituyes, se borrarán todas, también las que hayas editado. ¿Sustituirlo?')
TEXTO_CANCELADO = 'No he cambiado tu calendario: tu plan anterior sigue igual.'


@dataclass
class ResultadoAplicar:
    ok: bool = False
    texto: str = ''
    pendiente: bool = False          # hay sesiones anteriores y falta la confirmación del estudiante
    existentes: int = 0
    creados: int = 0
    borrados: int = 0
    no_borrados: int = 0
    datos: dict = field(default_factory=dict)


def aplicar(puente, traza, propuesta: list[dict], *, confirmado: bool, zona: str, huecos: list | None = None, dias: int = 7,
            franja=None, agente: str = 'orquestador', ahora=None) -> ResultadoAplicar:
    """Aplica la propuesta. Con `confirmado=False` solo escribe si el calendario está vacío; si no, devuelve `pendiente=True`
    sin tocar nada. Registra siempre un paso `aplicar_plan_estudio` con permiso «confirmar»."""
    with traza.paso('herramienta', agente, herramienta='aplicar_plan_estudio', permiso='confirmar',
                    confirmado_por_usuario=confirmado, calendario=ETIQUETA_CALENDARIO) as paso:
        r = puente.aplicar_plan(propuesta, huecos=huecos, dias=dias, zona=zona, franja=franja, confirmado=confirmado, ahora=ahora)
        paso['reintento'] = r.reintentos > 0
        if not r.ok:
            paso['fallo'], paso['error'] = True, r.detalle or r.mensaje
            return ResultadoAplicar(texto=r.mensaje or 'No he podido cambiar tu calendario.')
        d = r.datos or {}
        existentes = int(d.get('existentes', 0))
        paso['existentes'] = existentes
        if not d.get('aplicado'):
            return ResultadoAplicar(ok=True, pendiente=True, existentes=existentes, datos=d)
        creados, borrados, no_borrados = len(d.get('creados', [])), int(d.get('borrados', 0)), int(d.get('no_borrados', 0))
        paso.update(creados=creados, borrados=borrados, no_borrados=no_borrados, calendario_id=d.get('calendario_id', ''))
    if no_borrados:
        texto = (f'He creado tu plan nuevo, pero no he podido borrar {no_borrados} sesiones del plan anterior: siguen en '
                 '«Nota en Claro · Estudio». Vuelve a pedir el plan o bórralas a mano en Google Calendar.')
    else:
        texto = (f'He creado {creados} sesiones de estudio en tu calendario «Nota en Claro · Estudio»:\n'
                 + plan.lineas_eventos(propuesta))
        if borrados:
            texto += f'\n\nHe borrado las {borrados} sesiones del plan anterior.'
    return ResultadoAplicar(ok=True, texto=texto, existentes=existentes, creados=creados, borrados=borrados,
                            no_borrados=no_borrados, datos=d)


def cancelar(traza, agente: str = 'interfaz') -> str:
    """El estudiante ha dicho que no: se anota el paso y no se llama a nada."""
    traza.registrar('herramienta', agente, herramienta='aplicar_plan_estudio', permiso='confirmar', cancelado=True,
                    confirmado_por_usuario=False, calendario=ETIQUETA_CALENDARIO)
    return TEXTO_CANCELADO
