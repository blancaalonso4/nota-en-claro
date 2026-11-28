"""Verificador de los argumentos de cada herramienta. Python puro, sin modelo.

El agente propone una llamada; aquí se comprueba antes de ejecutarla (fechas válidas, destinatario permitido,
huecos libres, límites de tamaño). Los mensajes de error van en castellano y cortos, porque se devuelven al modelo
para que corrija la llamada. La validación de citas del RAG sigue en `app/rag/citas.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONA_POR_DEFECTO = 'Europe/Madrid'
MAX_EVENTOS = 10
MIN_MINUTOS, MAX_MINUTOS = 30, 180
MAX_DIAS_RANGO = 31
MAX_TITULO, MAX_ASUNTO, MAX_CUERPO, MAX_INFORME = 80, 120, 3000, 6000

# Argumentos permitidos por herramienta (todo lo demás se rechaza: invitados, destinatarios, etc.).
CLAVES_PERMITIDAS: dict[str, set[str]] = {
    'crear_plantilla_notas': set(),
    'leer_notas': set(),
    'guardar_informe': {'titulo', 'contenido'},
    'listar_eventos': {'desde', 'hasta'},
    'huecos_libres': {'desde', 'hasta'},
    'crear_eventos_estudio': {'eventos'},
    'aplicar_plan_estudio': {'eventos'},      # `confirmado` lo añade el puente tras verificar; el modelo nunca la llama
    'leer_correos_orientador': {'max'},      # el remitente lo pone Python (INTERNAS), nunca el modelo
    'crear_borrador': {'asunto', 'cuerpo'},
    'enviar_borrador': {'borrador_id', 'cuerpo', 'destinatario'},
}
# Argumentos que solo añade el programa tras leer los datos del estudiante (con `interno=True`); si los trae el modelo, se rechazan.
INTERNAS: dict[str, set[str]] = {'crear_borrador': {'destinatario'}, 'leer_correos_orientador': {'remitente'}}
CLAVES_EVENTO = {'titulo', 'inicio', 'fin', 'descripcion'}

_RE_MARCADOR = re.compile(r'\[[^\]\n]*\]')


def marcadores(texto) -> list[str]:
    """Marcadores entre corchetes sin rellenar, como «[Nombre del orientador]» o «[Tu nombre]». Lista vacía si no hay."""
    return _RE_MARCADOR.findall(str(texto or ''))


@dataclass
class Resultado:
    ok: bool = True
    errores: list[str] = field(default_factory=list)

    def error(self, mensaje: str) -> None:
        self.ok = False
        self.errores.append(mensaje)

    def __str__(self) -> str:
        return 'ok' if self.ok else '; '.join(self.errores)


def a_datetime(valor, zona: str = ZONA_POR_DEFECTO) -> datetime:
    """ISO 8601 → datetime con zona. Sin zona se asume la del estudiante. Lanza ValueError si no es una fecha válida."""
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError('fecha vacía o no es texto')
    d = datetime.fromisoformat(valor.strip().replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=ZoneInfo(zona))


def a_fecha(valor, zona: str = ZONA_POR_DEFECTO) -> datetime:
    """Acepta 'AAAA-MM-DD' (inicio de ese día) o una fecha-hora completa."""
    if isinstance(valor, str) and len(valor.strip()) == 10:
        return datetime.combine(date.fromisoformat(valor.strip()), time.min, tzinfo=ZoneInfo(zona))
    return a_datetime(valor, zona)


_RE_CORREO = re.compile(r'^[^@\s<>,;\[\]()"]+@[^@\s<>,;\[\]()"]+\.[^@\s<>,;\[\]()"]+$')


def correo_valido(c) -> bool:
    """Una sola dirección, sin espacios, saltos de línea, comas ni corchetes (así no se cuelan cabeceras ni destinatarios extra)."""
    return isinstance(c, str) and len(c) <= 120 and bool(_RE_CORREO.match(c.strip()))


def destinatario_permitido(destinatario: str | None, orientador: str | None) -> bool:
    """El único destinatario posible es el correo del orientador que escribió el estudiante (sin mayúsculas ni espacios)."""
    if not destinatario or not orientador:
        return False
    return destinatario.strip().lower() == orientador.strip().lower()


def _rango(args: dict, r: Resultado, zona: str, ahora: datetime) -> None:
    try:
        d, h = a_fecha(args.get('desde'), zona), a_fecha(args.get('hasta'), zona)
    except (ValueError, TypeError) as e:
        r.error(f'fechas no válidas (usa AAAA-MM-DD o ISO 8601): {e}')
        return
    if h <= d:
        r.error('«hasta» debe ser posterior a «desde»')
    elif (h - d) > timedelta(days=MAX_DIAS_RANGO):
        r.error(f'el rango no puede superar {MAX_DIAS_RANGO} días')
    if h <= ahora:
        r.error('el rango está en el pasado')


def _eventos(args: dict, r: Resultado, zona: str, ahora: datetime, huecos, dias: int) -> None:
    eventos = args.get('eventos')
    if not isinstance(eventos, list) or not eventos:
        r.error('«eventos» debe ser una lista con al menos un evento')
        return
    if len(eventos) > MAX_EVENTOS:
        r.error(f'máximo {MAX_EVENTOS} eventos por llamada')
        return
    if huecos is None:
        r.error('antes de crear eventos hay que consultar huecos_libres')
        return
    try:
        libres = [(a_datetime(x['inicio'], zona), a_datetime(x['fin'], zona)) for x in huecos]
    except (ValueError, TypeError, KeyError):
        r.error('los huecos libres guardados no son válidos')
        return
    limite = datetime.combine(ahora.date() + timedelta(days=dias), time.max, tzinfo=ahora.tzinfo)
    validos: list[tuple[datetime, datetime]] = []
    for i, ev in enumerate(eventos, 1):
        n = f'evento {i}'
        if not isinstance(ev, dict):
            r.error(f'{n}: debe ser un objeto con titulo, inicio y fin')
            continue
        raros = set(ev) - CLAVES_EVENTO
        if raros:
            r.error(f'{n}: campos no permitidos {sorted(raros)} (no se admiten invitados)')
        titulo = ev.get('titulo')
        if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > MAX_TITULO:
            r.error(f'{n}: el título es obligatorio y de máximo {MAX_TITULO} caracteres')
        try:
            ini, fin = a_datetime(ev.get('inicio'), zona), a_datetime(ev.get('fin'), zona)
        except (ValueError, TypeError) as e:
            r.error(f'{n}: fecha no válida ({e})')
            continue
        if fin <= ini:
            r.error(f'{n}: el fin debe ser posterior al inicio')
            continue
        minutos = (fin - ini).total_seconds() / 60
        if not MIN_MINUTOS <= minutos <= MAX_MINUTOS:
            r.error(f'{n}: dura {minutos:.0f} min y debe durar entre {MIN_MINUTOS} y {MAX_MINUTOS}; no uses el hueco entero: pon el fin = inicio + 60 a 120 min')
        if ini <= ahora:
            r.error(f'{n}: empieza en el pasado')
        if fin > limite:
            r.error(f'{n}: queda fuera de los {dias} días pedidos')
        if not any(h0 <= ini and fin <= h1 for h0, h1 in libres):
            r.error(f'{n}: no cabe en ningún hueco libre; los huecos son: ' + '; '.join(f'{h0:%Y-%m-%d %H:%M}-{h1:%H:%M}' for h0, h1 in libres[:8]))
        validos.append((ini, fin))
    validos.sort()
    for (a0, a1), (b0, b1) in zip(validos, validos[1:]):
        if b0 < a1:
            r.error('hay eventos que se solapan entre sí')
            break


def verificar(herramienta: str, args, *, ahora: datetime | None = None, zona: str = ZONA_POR_DEFECTO,
              huecos: list[dict] | None = None, dias: int = 7, orientador: str | None = None,
              confirmado_por_usuario: bool = False, interno: bool = False) -> Resultado:
    """Comprueba los argumentos de una llamada a herramienta. `huecos` son los intervalos libres que devolvió
    huecos_libres en esta ejecución; `dias` el horizonte pedido; `orientador` el correo del orientador que escribió el estudiante.
    `interno=True` es la segunda comprobación, con los argumentos que el programa añade (destinatario o remitente): deben ser
    exactamente ese correo."""
    r = Resultado()
    if herramienta not in CLAVES_PERMITIDAS:
        r.error(f'«{herramienta}» no es una herramienta conocida')
        return r
    if args is None:
        args = {}
    if not isinstance(args, dict):
        r.error('los argumentos deben ser un objeto')
        return r
    raros = set(args) - CLAVES_PERMITIDAS[herramienta] - (INTERNAS.get(herramienta, set()) if interno else set())
    if raros:
        r.error(f'argumentos no permitidos: {sorted(raros)}')
        return r
    ahora = ahora or datetime.now(ZoneInfo(zona))

    if herramienta in ('listar_eventos', 'huecos_libres'):
        _rango(args, r, zona, ahora)
    elif herramienta in ('crear_eventos_estudio', 'aplicar_plan_estudio'):
        _eventos(args, r, zona, ahora, huecos, dias)
    elif herramienta == 'guardar_informe':
        t, c = args.get('titulo'), args.get('contenido')
        if not isinstance(t, str) or not t.strip() or len(t) > MAX_TITULO:
            r.error(f'el título es obligatorio y de máximo {MAX_TITULO} caracteres')
        if not isinstance(c, str) or not c.strip() or len(c) > MAX_INFORME:
            r.error(f'el contenido es obligatorio y de máximo {MAX_INFORME} caracteres')
    elif herramienta == 'crear_borrador':
        a, c = args.get('asunto'), args.get('cuerpo')
        if not isinstance(a, str) or not a.strip() or len(a) > MAX_ASUNTO:
            r.error(f'el asunto es obligatorio y de máximo {MAX_ASUNTO} caracteres')
        if not isinstance(c, str) or not c.strip() or len(c) > MAX_CUERPO:
            r.error(f'el cuerpo es obligatorio y de máximo {MAX_CUERPO} caracteres')
        huecos_sin_rellenar = marcadores(a) + marcadores(c)
        if huecos_sin_rellenar:
            r.error(f'el borrador contiene marcadores entre corchetes sin rellenar ({", ".join(huecos_sin_rellenar[:3])}): '
                    'escribe el texto final, con los nombres reales y sin corchetes')
        if not correo_valido(orientador):
            r.error('falta el correo del orientador: lo escribe el estudiante (hoja «Mis notas» o campos de la app)')
        if interno:
            _mismo_correo(args.get('destinatario'), orientador, r, 'el borrador')
    elif herramienta == 'leer_correos_orientador':
        m = args.get('max', 3)
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= 3:
            r.error('«max» debe ser un entero entre 1 y 3')
        if interno:
            _mismo_correo(args.get('remitente'), orientador, r, 'la búsqueda de correos')
    elif herramienta == 'enviar_borrador':
        if not confirmado_por_usuario:
            r.error('enviar un correo exige la confirmación explícita del estudiante')
        if not isinstance(args.get('borrador_id'), str) or not args['borrador_id'].strip():
            r.error('falta «borrador_id»')
        if 'cuerpo' in args:       # texto editado por el estudiante en la interfaz
            c = args['cuerpo']
            if not isinstance(c, str) or not c.strip() or len(c) > MAX_CUERPO:
                r.error(f'el texto del correo es obligatorio y de máximo {MAX_CUERPO} caracteres')
            elif marcadores(c):
                r.error(f'el texto contiene marcadores entre corchetes sin rellenar ({", ".join(marcadores(c)[:3])}): '
                        'sustitúyelos por el texto real antes de enviar')
        _mismo_correo(args.get('destinatario'), orientador, r, 'el envío')
    return r


def _mismo_correo(valor, orientador, r: Resultado, que: str) -> None:
    """`valor` debe ser una dirección válida y exactamente el correo del orientador que puso el estudiante."""
    if not correo_valido(orientador):
        r.error('falta el correo del orientador: lo escribe el estudiante (hoja «Mis notas» o campos de la app)')
    elif not correo_valido(valor):
        r.error(f'{que} no lleva una dirección válida')
    elif not destinatario_permitido(valor, orientador):
        r.error(f'{que} no va exactamente al correo del orientador que puso el estudiante')
