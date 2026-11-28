"""Permisos por herramienta y defensa contra inyección de prompt. Python puro, sin modelo.

Permisos: automático (leer, crear borrador), confirmar (enviar correo y sustituir el plan de estudio; solo desde la interfaz, nunca ofrecida al
modelo) y prohibido (borrar y cualquier herramienta que no esté en la tabla).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

AUTOMATICO, CONFIRMAR, PROHIBIDO = 'automatico', 'confirmar', 'prohibido'

PERMISOS: dict[str, str] = {
    'crear_plantilla_notas': AUTOMATICO, 'leer_notas': AUTOMATICO, 'guardar_informe': AUTOMATICO,
    'listar_eventos': AUTOMATICO, 'huecos_libres': AUTOMATICO, 'crear_eventos_estudio': AUTOMATICO,
    'planificar_sesiones': AUTOMATICO,   # herramienta del agente (no es de un servidor): Python calcula las fechas y crea los eventos
    'leer_correos_orientador': AUTOMATICO, 'crear_borrador': AUTOMATICO,
    'enviar_borrador': CONFIRMAR,
    # sustituye el plan de estudio (borra los eventos del calendario de la app): solo por el puente, tras la confirmación
    'aplicar_plan_estudio': CONFIRMAR,
}

# Herramientas que el modelo recibe en cada intención. enviar_borrador y aplicar_plan_estudio no están en ninguna: las llama Python (botón de la interfaz u orquestador).
HERRAMIENTAS_POR_INTENCION: dict[str, tuple[str, ...]] = {
    'plan_estudio': ('leer_notas', 'huecos_libres', 'planificar_sesiones'),   # crear_eventos_estudio lo llama Python, no el modelo
    'informe': ('leer_notas', 'guardar_informe'),
    'correo_orientador': ('leer_correos_orientador', 'crear_borrador'),
}

# Herramientas cuyo resultado es contenido ajeno (lo escribió otra persona o un tercero): se trata como dato.
LEEN_CONTENIDO_NO_FIABLE = {'leer_notas': 'drive', 'leer_correos_orientador': 'gmail'}

# Herramientas que sacan algo de la cuenta del estudiante. Hoy solo el envío de correo.
SALEN_DE_LA_CUENTA = {'enviar_borrador'}


def permiso_de(herramienta: str) -> str:
    """Permiso de una herramienta; lo que no está en la tabla (borrar, compartir, etc.) es prohibido."""
    return PERMISOS.get(herramienta, PROHIBIDO)


def herramientas_de(intencion: str) -> tuple[str, ...]:
    return HERRAMIENTAS_POR_INTENCION.get(intencion, ())


@dataclass
class Decision:
    permitida: bool
    permiso: str
    motivo: str = ''


class Contexto:
    """Estado de una ejecución del agente: si ya ha leído contenido no fiable (Drive o Gmail)."""

    def __init__(self, intencion: str):
        self.intencion = intencion
        self.contaminado = False

    def marcar_lectura(self, herramienta: str) -> None:
        if herramienta in LEEN_CONTENIDO_NO_FIABLE:
            self.contaminado = True


def decidir(herramienta: str, ctx: Contexto, *, confirmada_por_usuario: bool = False) -> Decision:
    """¿Puede el agente ejecutar esta herramienta ahora?

    - prohibida o desconocida: no.
    - no está entre las herramientas de la intención (el modelo la inventó o es de otra): no.
    - confirmar: solo si el estudiante la confirmó en la interfaz (`confirmada_por_usuario`).
    - tras leer contenido no fiable, cualquier acción que salga de la cuenta exige confirmación del estudiante.
    """
    permiso = permiso_de(herramienta)
    if permiso == PROHIBIDO:
        return Decision(False, permiso, f'«{herramienta}» está prohibida o no existe')
    if herramienta not in herramientas_de(ctx.intencion) and not confirmada_por_usuario:
        return Decision(False, permiso, f'«{herramienta}» no está disponible en esta petición')
    if permiso == CONFIRMAR and not confirmada_por_usuario:
        return Decision(False, permiso, f'«{herramienta}» necesita la confirmación explícita del estudiante')
    if ctx.contaminado and herramienta in SALEN_DE_LA_CUENTA and not confirmada_por_usuario:
        return Decision(False, permiso, 'se ha leído contenido no fiable: la acción necesita confirmación del estudiante')
    return Decision(True, permiso)


# --- Aislamiento de contenido no fiable -------------------------------------------------------------------------

ETIQUETA = 'datos_no_fiables'
_RE_ETIQUETA = re.compile(r'<\s*/?\s*' + ETIQUETA + r'[^>]*>?', re.I)
_RE_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def envolver_no_fiable(fuente: str, texto: str, max_caracteres: int = 800) -> str:
    """Delimita contenido leído de Drive o Gmail para que el modelo lo trate como datos.

    Quita del contenido cualquier etiqueta que imite el delimitador (para que no pueda «cerrarlo» desde dentro),
    elimina caracteres de control y recorta. El prompt de sistema del agente dice que lo de dentro son datos.
    """
    limpio = _RE_ETIQUETA.sub('[etiqueta eliminada]', str(texto))
    limpio = _RE_CONTROL.sub('', limpio).strip()
    if len(limpio) > max_caracteres:
        limpio = limpio[:max_caracteres] + ' […recortado]'
    fuente = re.sub(r'[^a-z_]', '', fuente.lower())
    return f'<{ETIQUETA} fuente="{fuente}">\n{limpio}\n</{ETIQUETA}>'
