"""Cálculo de la nota de admisión en Python (no con el modelo). Sin llamadas a Ollama ni a Google.

Reglas, todas del corpus (texto literal en `FUENTES`, comprobado en los tests):
- PAU = media aritmética de los ejercicios de la fase de acceso, a tres decimales (redondeo a la milésima, y en
  equidistancia hacia arriba); debe ser >= 4 para poder usarse (RD 534/2024, art. 14.2).
- CAU = 0,6 · nota media de Bachillerato + 0,4 · PAU, a tres decimales; debe ser >= 5 (RD 534/2024, art. 15; doc06 §3.1).
- Nota de admisión = CAU + a·M1 + b·M2, como máximo dos materias, solo con nota >= 5, máximo 14 puntos; se eligen las
  dos que dan la mejor nota (doc06 §5-6; RD 534/2024, art. 22.3). De la fase de acceso solo pondera la materia
  obligatoria de modalidad (doc06 §7.1; doc13) y de las segundas lenguas solo una (doc06 §8a).
- Los parámetros a y b (0, 0,1 o 0,2) los escribe el estudiante: el corpus solo trae la tabla de la Universidad de
  Alcalá, con las columnas perdidas en el texto (ver docs/decisiones.md). Si falta uno, se dice y no se inventa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import combinations

PESO_BACHILLERATO, PESO_PAU = Decimal('0.6'), Decimal('0.4')
MINIMO_PAU, MINIMO_CAU, MINIMO_MATERIA = Decimal('4'), Decimal('5'), Decimal('5')
MAXIMO_ADMISION, MAXIMA_PONDERACION = Decimal('14'), Decimal('0.2')
FASES = ('acceso', 'admision')

# (doc_id, título corto, cita literal del corpus). Los tests comprueban que cada cita está en data/texto.
FUENTES: dict[str, tuple[str, str, str]] = {
    'pau': ('doc07', 'Real Decreto 534/2024, art. 14.2',
            'Esta calificación deberá ser igual o superior a cuatro puntos'),
    'cau': ('doc07', 'Real Decreto 534/2024, art. 15.1',
            'media ponderada del 60 por ciento de la nota media de Bachillerato'),
    'formula': ('doc06', 'Acuerdo de las universidades públicas de Madrid 2026-2027, §6',
                'Nota de Admisión = CAU + (a × M1) + (b × M2)'),
    'minimo_materia': ('doc06', 'Acuerdo de las universidades públicas de Madrid 2026-2027, §6',
                       'Únicamente serán ponderables aquellas materias cuya calificación sea igual o superior a cinco puntos'),
    'maximo': ('doc06', 'Acuerdo de las universidades públicas de Madrid 2026-2027, §6',
               'La nota de admisión podrá alcanzar un máximo de 14 puntos'),
}


def r3(x: Decimal) -> Decimal:
    """Tres cifras decimales, a la milésima más próxima y, en equidistancia, a la superior."""
    return Decimal(x).quantize(Decimal('0.001'), ROUND_HALF_UP)


def a_decimal(valor) -> Decimal | None:
    """Número con coma o punto → Decimal. Vacío o None → None. Lanza ValueError si no es un número."""
    if isinstance(valor, bool):
        raise ValueError('un booleano no es un número')
    if valor is None:
        return None
    s = str(valor).strip().replace(',', '.')
    if s == '':
        return None
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f'«{valor}» no es un número') from e
    if not d.is_finite():
        raise ValueError(f'«{valor}» no es un número')
    return d


def fmt(d: Decimal, decimales: int | None = None) -> str:
    """Formato español (coma decimal). Sin `decimales`, quita ceros finales (0,2; 8,5; 10)."""
    s = f'{d:.{decimales}f}' if decimales is not None else format(d.normalize(), 'f')
    return s.replace('.', ',')


@dataclass
class Materia:
    nombre: str
    nota: Decimal | None
    fase: str = ''                      # 'acceso' | 'admision' | '' (sin examinar)
    ponderacion: Decimal | None = None  # 0, 0,1 o 0,2 para el grado que quiere; la escribe el estudiante
    segunda_lengua: bool = False


@dataclass
class ResultadoNota:
    problemas: list[str] = field(default_factory=list)   # datos que faltan o son inválidos: no hay resultado
    avisos: list[str] = field(default_factory=list)
    pau: Decimal | None = None
    n_ejercicios: int = 0
    cfb: Decimal | None = None
    cau: Decimal | None = None
    tiene_acceso: bool | None = None
    admision: Decimal | None = None
    sin_tope: Decimal | None = None
    usadas: list[dict] = field(default_factory=list)
    sin_ponderacion: list[str] = field(default_factory=list)

    @property
    def calculada(self) -> bool:
        return self.admision is not None


def desde_diccionario(d: dict) -> tuple[Decimal | None, list[Materia], list[str]]:
    """Convierte lo que devuelve la herramienta `leer_notas` (o el formulario manual) en (media, materias, errores).
    Formato: {'nota_media_bachillerato': 8.5, 'materias': [{'asignatura', 'nota', 'fase', 'ponderacion', 'segunda_lengua'}]}.
    """
    errores: list[str] = []
    try:
        cfb = a_decimal(d.get('nota_media_bachillerato'))
    except ValueError as e:
        cfb = None
        errores.append(f'nota media de Bachillerato: {e}')
    materias: list[Materia] = []
    for i, fila in enumerate(d.get('materias') or [], 1):
        nombre = str(fila.get('asignatura') or '').strip()
        if not nombre:
            continue
        try:
            nota = a_decimal(fila.get('nota'))
            pond = a_decimal(fila.get('ponderacion'))
        except ValueError as e:
            errores.append(f'{nombre}: {e}')
            continue
        fase = str(fila.get('fase') or '').strip().lower().replace('ó', 'o')
        sl = str(fila.get('segunda_lengua') or '').strip().lower() in ('si', 'sí', 's', 'true', '1', 'x')
        materias.append(Materia(nombre, nota, fase, pond, sl))
    return cfb, materias, errores


def calcular(cfb: Decimal | None, materias: list[Materia]) -> ResultadoNota:
    r = ResultadoNota(cfb=cfb)
    # --- comprobación de datos: si falta algo se dice y no se inventa nada
    if cfb is None:
        r.problemas.append('falta la nota media de Bachillerato')
    elif not Decimal('0') <= cfb <= Decimal('10'):
        r.problemas.append('la nota media de Bachillerato debe estar entre 0 y 10')
    for m in materias:
        if m.nota is not None and not Decimal('0') <= m.nota <= Decimal('10'):
            r.problemas.append(f'{m.nombre}: la nota debe estar entre 0 y 10')
        if m.fase not in FASES + ('',):
            r.problemas.append(f'{m.nombre}: la fase debe ser «acceso» o «admisión»')
        if m.ponderacion is not None and not Decimal('0') <= m.ponderacion <= MAXIMA_PONDERACION:
            r.problemas.append(f'{m.nombre}: la ponderación debe estar entre 0 y 0,2')
    ejercicios = [m.nota for m in materias if m.fase == 'acceso' and m.nota is not None]
    if not ejercicios:
        r.problemas.append('faltan las notas de los ejercicios de la fase de acceso (PAU)')
    ponderables_acceso = [m for m in materias if m.fase == 'acceso' and m.ponderacion and m.nota is not None
                          and m.nota >= MINIMO_MATERIA]
    if len(ponderables_acceso) > 1:
        r.problemas.append('de la fase de acceso solo pondera la materia obligatoria de modalidad: pon 0 de '
                           'ponderación en el resto (' + ', '.join(m.nombre for m in ponderables_acceso) + ')')
    if r.problemas:
        return r

    # --- PAU y CAU
    r.n_ejercicios = len(ejercicios)
    r.pau = r3(sum(ejercicios) / len(ejercicios))
    r.cau = r3(PESO_BACHILLERATO * cfb + PESO_PAU * r.pau)
    if r.pau < MINIMO_PAU:
        r.tiene_acceso = False
        r.avisos.append('la PAU no llega a 4: no se puede tener en cuenta para acceder a la universidad')
        return r
    if r.cau < MINIMO_CAU:
        r.tiene_acceso = False
        r.avisos.append('la calificación de acceso no llega a 5: no se cumplen los requisitos de acceso')
        return r
    r.tiene_acceso = True

    # --- ponderaciones: las dos materias que dan la mejor nota
    aprobadas = [m for m in materias if m.nota is not None and m.nota >= MINIMO_MATERIA]
    r.sin_ponderacion = [m.nombre for m in aprobadas if m.ponderacion is None]
    candidatas = [m for m in aprobadas if m.ponderacion and m.fase in FASES and (m.fase == 'admision' or m in ponderables_acceso)]
    combos = [c for n in (2, 1) for c in combinations(candidatas, n) if sum(x.segunda_lengua for x in c) <= 1]
    mejor: tuple[Materia, ...] = ()
    if combos:
        # el máximo número de materias (hasta 2) da siempre más o igual; a igualdad gana el orden de la hoja
        mejor = max(combos, key=lambda c: (sum(x.nota * x.ponderacion for x in c), len(c)))
    r.usadas = [{'nombre': m.nombre, 'nota': m.nota, 'ponderacion': m.ponderacion, 'aporte': m.nota * m.ponderacion}
                for m in mejor]
    r.sin_tope = r3(r.cau + sum((u['aporte'] for u in r.usadas), Decimal('0')))
    r.admision = min(r.sin_tope, MAXIMO_ADMISION)
    if r.sin_tope > MAXIMO_ADMISION:
        r.avisos.append('la nota de admisión no puede pasar de 14')
    if not candidatas:
        r.avisos.append('ninguna materia pondera (nota < 5, ponderación 0 o sin ponderación): la nota de admisión es la CAU')
    return r


def _cita(clave: str) -> str:
    doc, titulo, texto = FUENTES[clave]
    return f'«{texto}» — {titulo} [{doc}]'


def explicar(r: ResultadoNota) -> str:
    """Texto para el estudiante: desglose paso a paso y fuentes literales del corpus. Sin modelo."""
    if r.problemas:
        return ('No puedo calcular tu nota de admisión todavía:\n- ' + '\n- '.join(r.problemas) +
                '\n\nCompleta esos datos en tu hoja «Mis notas» (o en el formulario) y vuelve a pedírmelo. '
                'No invento ninguna nota ni ponderación.')
    p = [f'1. **PAU**: media de tus {r.n_ejercicios} ejercicios de la fase de acceso = {fmt(r.pau, 3)} (mínimo 4).',
         f'2. **Calificación de acceso (CAU)** = 0,6 × {fmt(r.cfb)} + 0,4 × {fmt(r.pau, 3)} = {fmt(r.cau, 3)} (mínimo 5).']
    fuentes = ['pau', 'cau']
    if not r.tiene_acceso:
        cab = '**No se cumplen los requisitos de acceso**: ' + '; '.join(r.avisos) + '.'
        return cab + '\n\n' + '\n'.join(p) + '\n\nFuentes:\n' + '\n'.join(f'- {_cita(k)}' for k in fuentes)
    if r.usadas:
        partes = [f"{u['nombre']}: {fmt(u['nota'])} × {fmt(u['ponderacion'])} = {fmt(u['aporte'], 3)}" for u in r.usadas]
        p.append('3. **Ponderaciones** (las dos materias que mejor suman, con las ponderaciones que escribiste): '
                 + '; '.join(partes) + '.')
        suma = ' + '.join(fmt(u['aporte'], 3) for u in r.usadas)
        p.append(f'4. **Nota de admisión** = CAU + ponderaciones = {fmt(r.cau, 3)} + {suma} = {fmt(r.sin_tope, 3)}.')
    else:
        p.append(f'3. **Ponderaciones**: ninguna materia suma. Nota de admisión = CAU = {fmt(r.cau, 3)}.')
    fuentes += ['formula', 'minimo_materia', 'maximo']
    cab = f'**Tu nota de admisión es {fmt(r.admision, 3)}** (máximo 14).'
    extra = []
    if r.sin_tope is not None and r.sin_tope > MAXIMO_ADMISION:
        extra.append(f'La suma da {fmt(r.sin_tope, 3)}, pero se queda en 14.')
    if r.sin_ponderacion:
        extra.append('Sin ponderación escrita en tu hoja (no cuentan): ' + ', '.join(r.sin_ponderacion) + '.')
    extra.append('Las ponderaciones dependen del grado y de la universidad: comprueba en su tabla oficial que son las que escribiste.')
    return (cab + '\n\n' + '\n'.join(p) + '\n\n' + '\n'.join(extra) +
            '\n\nFuentes:\n' + '\n'.join(f'- {_cita(k)}' for k in fuentes))


def calcular_desde_diccionario(d: dict) -> tuple[ResultadoNota, str]:
    """Atajo para la interfaz y el agente: datos de la hoja o del formulario → (resultado, texto explicado)."""
    cfb, materias, errores = desde_diccionario(d)
    # si alguna celda no se ha podido leer no se calcula con el resto: el resultado sería engañoso
    r = ResultadoNota(problemas=errores) if errores else calcular(cfb, materias)
    return r, explicar(r)
