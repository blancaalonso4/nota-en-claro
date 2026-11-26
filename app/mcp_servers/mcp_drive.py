"""Servidor MCP de Drive/Sheets (FastMCP, stdio). Permiso mínimo: drive.file (solo los archivos que crea la app).

Herramientas: crear_plantilla_notas, leer_notas, guardar_informe. No existe ninguna para borrar ni compartir.
Arranque (lo hace el puente MCP): python -m app.mcp_servers.mcp_drive
"""
from __future__ import annotations

from fractions import Fraction

from mcp.server.fastmcp import FastMCP

from . import comun
from .comun import ErrorGoogle, convertir_errores, leer_estado, limpiar_texto, llamar

TITULO_HOJA = 'Mis notas'
CARPETA_INFORMES = 'Nota en Claro · Informes'
FILAS_NOTAS = 40
LOCALE_HOJA = 'es_ES'     # decimales con coma
URL_TABLAS = 'consulta la tabla de ponderaciones publicada por tu universidad'


class ApiDrive:
    """Servicios reales, creados al usarlos. Los tests pasan un falso con los mismos atributos."""

    def __init__(self):
        self._drive = self._sheets = None

    @property
    def drive(self):
        self._drive = self._drive or comun.servicio('drive', 'drive', 'v3')
        return self._drive

    @property
    def sheets(self):
        self._sheets = self._sheets or comun.servicio('drive', 'sheets', 'v4')
        return self._sheets


# --- lógica pura (probada sin Google) ---------------------------------------------------------------------------------

def _num(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).strip().replace(',', '.'))
    except ValueError:
        return None


def parsear_hoja(datos: list[list], notas: list[list]) -> dict:
    """Celdas de la hoja → JSON tipado. El modelo nunca ve celdas libres: solo campos con tipo y longitud acotados."""
    avisos: list[str] = []
    cfb = None
    grado = ''
    for fila in datos:
        if len(fila) >= 2 and 'media' in str(fila[0]).lower():
            cfb = _num(fila[1])
            if fila[1] not in ('', None) and (cfb is None or not 0 <= cfb <= 10):
                avisos.append('la nota media de Bachillerato debe ser un número entre 0 y 10')
                cfb = None
        elif len(fila) >= 2 and 'grado' in str(fila[0]).lower():
            grado = limpiar_texto(fila[1], 60)
    materias = []
    for i, fila in enumerate(notas, 2):
        fila = list(fila) + [''] * (5 - len(fila))
        nombre = limpiar_texto(fila[0], 40)
        if not nombre:
            continue
        nota, pond = _num(fila[1]), _num(fila[3])
        if fila[1] not in ('', None) and (nota is None or not 0 <= nota <= 10):
            avisos.append(f'fila {i} ({nombre}): la nota debe ser un número entre 0 y 10')
            nota = None
        if fila[3] not in ('', None) and (pond is None or not 0 <= pond <= 0.2):
            avisos.append(f'fila {i} ({nombre}): la ponderación debe ser 0, 0,1 o 0,2')
            pond = None
        fase = limpiar_texto(fila[2], 12).lower().replace('ó', 'o')
        if fase not in ('acceso', 'admision', ''):
            avisos.append(f'fila {i} ({nombre}): la fase debe ser «acceso» o «admisión»')
            fase = ''
        sl = limpiar_texto(fila[4], 3).lower() in ('si', 'sí', 's', 'x')
        materias.append({'asignatura': nombre, 'nota': nota, 'fase': fase, 'ponderacion': pond, 'segunda_lengua': sl})
    return {'nota_media_bachillerato': cfb, 'grado': grado, 'materias': materias, 'avisos': avisos}


TOTAL_SESIONES = 6      # tope de sesiones de un plan (llamada corta en CPU)


def sesiones_sugeridas(materias: list[dict], total: int = TOTAL_SESIONES) -> list[dict]:
    """Reparte `total` sesiones de estudio entre las asignaturas con nota: cuanto más baja la nota, más sesiones.

    Fórmula: peso = (10 - nota)²; cuota = total · peso / Σ pesos; cada asignatura recibe la parte entera de su cuota y las
    sesiones que sobran van a las de mayor parte decimal (método del mayor resto; empate → la de peor nota, luego el orden
    de la hoja). Elevar al cuadrado hace que una nota muy baja pese bastante más que varias notas medianas.
    Devuelve [{'asignatura', 'sesiones'}] solo con las que reciben alguna, de más a menos sesiones. Sin notas → [].
    """
    con_nota = [(i, m) for i, m in enumerate(materias) if isinstance(m.get('nota'), (int, float))]
    pesos = [Fraction(str(10 - m['nota'])) ** 2 for _, m in con_nota]   # Fraction: sin ruido de coma flotante en los empates
    suma = sum(pesos)
    if not con_nota or suma <= 0:
        return []
    cuotas = [total * p / suma for p in pesos]
    sesiones = [int(c) for c in cuotas]       # int() sobre Fraction trunca (cuotas ≥ 0)
    orden = sorted(range(len(con_nota)), key=lambda k: (-(cuotas[k] - sesiones[k]), con_nota[k][1]['nota'], k))
    for k in orden[:total - sum(sesiones)]:
        sesiones[k] += 1
    res = [{'asignatura': m['asignatura'], 'sesiones': s} for (_, m), s in zip(con_nota, sesiones) if s > 0]
    return sorted(res, key=lambda r: -r['sesiones'])


AMARILLO = {'red': 1.0, 'green': 0.95, 'blue': 0.6}      # casillas que hay que rellenar
AVISO_ESCRIBE_AQUI = '← escribe aquí'
SEGUNDA_LENGUA = ('Segunda lengua: pon «sí» solo en una asignatura que sea una segunda lengua extranjera (la adicional). '
                  'Si te examinas de dos idiomas extranjeros en la fase de admisión, solo pondera uno: el que te dé mejor nota de admisión '
                  '(doc06, apartado 8). Por eso la app nunca suma dos asignaturas marcadas con «sí»; en las demás pon «no».')


def _peticion_crear_hoja() -> dict:
    """Cuerpo de spreadsheets.create. Configuración regional española (es_ES): los decimales se escriben con coma (8,5)."""
    cabecera = ['Asignatura', 'Nota', 'Fase (acceso / admisión)', 'Ponderación (0 / 0,1 / 0,2)', 'Segunda lengua (sí / no)']

    def celda(x, formato=None):
        c = {'userEnteredValue': {'numberValue': x} if isinstance(x, (int, float)) else {'stringValue': x}}
        if formato:
            c['userEnteredFormat'] = formato
        return c

    fila = lambda *v: {'values': [celda(x) for x in v]}
    # En «Datos» la casilla B se resalta en amarillo y la C dice dónde escribir
    casilla = {'backgroundColor': AMARILLO}
    aviso = {'textFormat': {'italic': True, 'foregroundColor': {'red': 0.6, 'green': 0.3, 'blue': 0.0}}}
    fila_dato = lambda texto: {'values': [celda(texto), {'userEnteredFormat': casilla}, celda(AVISO_ESCRIBE_AQUI, aviso)]}
    return {'properties': {'title': TITULO_HOJA, 'locale': LOCALE_HOJA, 'timeZone': comun.zona_horaria()}, 'sheets': [
        {'properties': {'title': 'Datos', 'sheetId': 0, 'gridProperties': {'columnCount': 3}},
         'data': [{'startRow': 0, 'startColumn': 0, 'rowData': [
             fila_dato('Nota media de Bachillerato (0-10)'), fila_dato('Grado que quieres pedir')],
             'columnMetadata': [{'pixelSize': 280}, {'pixelSize': 160}, {'pixelSize': 140}]}]},
        {'properties': {'title': 'Notas', 'sheetId': 1, 'gridProperties': {'frozenRowCount': 1}},
         'data': [{'startRow': 0, 'startColumn': 0, 'rowData': [fila(*cabecera)]}]},
        {'properties': {'title': 'Instrucciones', 'sheetId': 2}, 'data': [{'startRow': 0, 'startColumn': 0, 'rowData': [
            fila('1. En «Datos» escribe tu nota media de Bachillerato (sin contar Religión) en la casilla amarilla. Los decimales, con coma (8,5).'),
            fila('2. En «Notas» escribe una fila por asignatura: nota (0-10), fase (acceso o admisión), ponderación para tu grado (0, 0,1 o 0,2) y si es segunda lengua.'),
            fila('3. De la fase de acceso solo pondera la materia obligatoria de modalidad; deja 0 en las demás.'),
            fila('4. La ponderación la dicta tu universidad y tu grado: ' + URL_TABLAS),
            fila('5. ' + SEGUNDA_LENGUA),
            fila('Ejemplo: Matemáticas II | 8,5 | acceso | 0,2 | no'),
            fila('Ejemplo: Física | 7,5 | admisión | 0,2 | no')]}]}]}


def _en_locale(n) -> str:
    """Número tal como lo escribiría el estudiante en la hoja es_ES (coma decimal): las condiciones de validación se interpretan
    «como si se escribieran en una celda», y con es_ES la API rechaza «0.2» (medido contra Google el 2026-11-26)."""
    return str(n).replace('.', ',')


def _validaciones() -> dict:
    def regla(col, tipo, valores=None, minimo=None, maximo=None):
        cond = ({'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in valores]} if valores
                else {'type': 'NUMBER_BETWEEN', 'values': [{'userEnteredValue': _en_locale(minimo)}, {'userEnteredValue': _en_locale(maximo)}]})
        return {'setDataValidation': {'range': {'sheetId': 1, 'startRowIndex': 1, 'endRowIndex': FILAS_NOTAS,
                                                 'startColumnIndex': col, 'endColumnIndex': col + 1},
                                      'rule': {'condition': cond, 'strict': True, 'showCustomUi': True}}}
    return {'requests': [regla(1, 'n', minimo=0, maximo=10), regla(2, 'l', ['acceso', 'admisión']),
                         regla(3, 'n', minimo=0, maximo=0.2), regla(4, 'l', ['sí', 'no'])]}


# --- servidor ---------------------------------------------------------------------------------------------------------

def _existe(api, archivo_id: str) -> bool:
    try:
        f = api.drive.files().get(fileId=archivo_id, fields='id,trashed').execute()
        return not f.get('trashed')
    except Exception:  # noqa: BLE001  (404, sin permiso, caído: se trata como que no existe)
        return False


def construir(api=None, estado_fn=comun.leer_estado, guardar_fn=comun.guardar_estado) -> FastMCP:
    api = api or ApiDrive()
    mcp = FastMCP('nota-en-claro-drive')

    @mcp.tool()
    @convertir_errores
    def crear_plantilla_notas() -> dict:
        """Crea en Drive la hoja «Mis notas» del estudiante (o devuelve la que ya existe)."""
        hoja_id = estado_fn().get('hoja_notas_id')
        if hoja_id and _existe(api, hoja_id):
            return {'id': hoja_id, 'url': f'https://docs.google.com/spreadsheets/d/{hoja_id}', 'creada': False, 'reintentos': 0}
        r, n1 = llamar(lambda: api.sheets.spreadsheets().create(body=_peticion_crear_hoja(), fields='spreadsheetId').execute())
        hoja_id = r['spreadsheetId']
        guardar_fn(hoja_notas_id=hoja_id)
        _, n2 = llamar(lambda: api.sheets.spreadsheets().batchUpdate(spreadsheetId=hoja_id, body=_validaciones()).execute())
        return {'id': hoja_id, 'url': f'https://docs.google.com/spreadsheets/d/{hoja_id}', 'creada': True, 'reintentos': n1 + n2}

    @mcp.tool()
    @convertir_errores
    def leer_notas() -> dict:
        """Lee «Mis notas» y devuelve la nota media de Bachillerato y las materias, con tipos y longitudes acotados."""
        hoja_id = estado_fn().get('hoja_notas_id')
        if not hoja_id:
            raise ErrorGoogle('Todavía no has creado tu hoja «Mis notas». Pulsa «Crear mi hoja de notas».')
        r, n = llamar(lambda: api.sheets.spreadsheets().values().batchGet(
            spreadsheetId=hoja_id, ranges=['Datos!A1:B2', f'Notas!A2:E{FILAS_NOTAS}'],
            valueRenderOption='UNFORMATTED_VALUE').execute())
        rangos = r.get('valueRanges', [])
        datos = rangos[0].get('values', []) if len(rangos) > 0 else []
        notas = rangos[1].get('values', []) if len(rangos) > 1 else []
        hoja = parsear_hoja(datos, notas)
        return {**hoja, 'sesiones_sugeridas': sesiones_sugeridas(hoja['materias']), 'reintentos': n}

    @mcp.tool()
    @convertir_errores
    def guardar_informe(titulo: str, contenido: str) -> dict:
        """Guarda un informe como documento de Google en la carpeta «Nota en Claro · Informes» de Drive."""
        from googleapiclient.http import MediaInMemoryUpload
        titulo = limpiar_texto(titulo, 80) or 'Informe'
        total = 0
        carpeta = estado_fn().get('carpeta_informes_id')
        if not carpeta or not _existe(api, carpeta):
            c, n = llamar(lambda: api.drive.files().create(
                body={'name': CARPETA_INFORMES, 'mimeType': 'application/vnd.google-apps.folder'}, fields='id').execute())
            carpeta, total = c['id'], total + n
            guardar_fn(carpeta_informes_id=carpeta)
        medio = MediaInMemoryUpload(contenido.encode('utf-8'), mimetype='text/plain')
        f, n = llamar(lambda: api.drive.files().create(
            body={'name': titulo, 'mimeType': 'application/vnd.google-apps.document', 'parents': [carpeta]},
            media_body=medio, fields='id,webViewLink').execute())
        return {'id': f['id'], 'url': f.get('webViewLink', f"https://docs.google.com/document/d/{f['id']}"),
                'reintentos': total + n}

    return mcp


if __name__ == '__main__':
    construir().run(transport='stdio')
