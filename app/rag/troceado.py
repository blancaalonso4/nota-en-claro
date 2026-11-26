"""Troceado: ventana fija (sistema final del Caso III) y por secciones (alternativa)."""
from __future__ import annotations

import re
import unicodedata

RE_LEGAL = re.compile(r'^(art[íi]culo\s+\d+|cap[íi]tulo\s+[ivxlcdm\d]+|secci[óo]n\s+\d+|t[íi]tulo\s+[ivxlcdm]+\b'
                      r'|anexo\s+[ivxlcdm\d]*|disposici[óo]n\s+(adicional|transitoria|final|derogatoria))', re.I)
RE_NUM = re.compile(r'^\d{1,2}(\.\d{1,2}){0,2}\.?\s+[A-ZÁÉÍÓÚÑ¿]')
RE_MAYUS = re.compile(r'^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 ,.;:()/\-]{5,90}$')


def normaliza(s: str) -> str:
    s = unicodedata.normalize('NFKC', s).lower()
    s = re.sub(r'[^\w%€]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def es_cabecera(linea: str) -> bool:
    l = linea.strip()
    if not l or len(l) > 140:
        return False
    if RE_LEGAL.match(l) or l.startswith('¿') or RE_MAYUS.match(l):
        return True
    return bool(RE_NUM.match(l) and len(l) < 70 and len(l.split()) <= 10 and not l.endswith((',', ';')))


def _ventanas(palabras: list, n: int, solape: int) -> list[list]:
    """palabras: lista de (palabra, pagina). Trozos de n palabras con solape."""
    trozos, i = [], 0
    while i < len(palabras):
        trozos.append(palabras[i:i + n])
        if i + n >= len(palabras):
            break
        i += n - solape
    return trozos


def trocear_ventana(paginas_por_doc: dict[str, list[str]], n: int = 250, solape: int = 35) -> list[dict]:
    chunks = []
    for doc_id, paginas in paginas_por_doc.items():
        palabras = [(w, p) for p, texto in enumerate(paginas, 1) for w in texto.split()]
        for j, t in enumerate(_ventanas(palabras, n, solape)):
            chunks.append({'chunk_id': f'{doc_id}_v{j:03d}', 'doc_id': doc_id, 'pagina': t[0][1],
                           'seccion': '', 'texto': ' '.join(w for w, _ in t)})
    return chunks


def trocear_secciones(paginas_por_doc: dict[str, list[str]], max_palabras: int = 250,
                      min_palabras: int = 40, solape: int = 35) -> list[dict]:
    chunks = []
    for doc_id, paginas in paginas_por_doc.items():
        secciones, actual = [], {'titulo': '', 'pagina': 1, 'palabras': []}
        for p, texto in enumerate(paginas, 1):
            for linea in texto.splitlines():
                if es_cabecera(linea) and actual['palabras']:
                    secciones.append(actual)
                    actual = {'titulo': linea.strip(), 'pagina': p, 'palabras': []}
                elif es_cabecera(linea):
                    actual['titulo'] = (actual['titulo'] + ' ' + linea.strip()).strip()
                actual['palabras'] += [(w, p) for w in linea.split()]
        secciones.append(actual)
        juntas, pendiente = [], None
        for s in secciones:
            if pendiente:
                s = {'titulo': pendiente['titulo'] or s['titulo'], 'pagina': pendiente['pagina'],
                     'palabras': pendiente['palabras'] + s['palabras']}
                pendiente = None
            if len(s['palabras']) < min_palabras:
                pendiente = s
            else:
                juntas.append(s)
        if pendiente:
            if juntas:
                juntas[-1]['palabras'] += pendiente['palabras']
            else:
                juntas.append(pendiente)
        j = 0
        for s in juntas:
            trozos = [s['palabras']] if len(s['palabras']) <= max_palabras else _ventanas(s['palabras'], max_palabras, solape)
            for k_, t in enumerate(trozos):
                cuerpo = ' '.join(w for w, _ in t)
                texto = f"{s['titulo']}. {cuerpo}" if (k_ > 0 and s['titulo']) else cuerpo
                chunks.append({'chunk_id': f'{doc_id}_s{j:03d}', 'doc_id': doc_id, 'pagina': t[0][1],
                               'seccion': s['titulo'][:80], 'texto': texto})
                j += 1
    return chunks


def preparar(chunks: list[dict]) -> list[dict]:
    for c in chunks:
        c['norm'] = normaliza(c['texto'])
    return chunks
