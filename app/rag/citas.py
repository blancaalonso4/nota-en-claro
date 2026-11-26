"""Validación de citas y regla de abstención. Python puro, sin modelo (base del futuro verificador).

Se abstiene si: (1) el modelo dice NO CONSTA; (2) ninguna frase de los fragmentos sostiene la respuesta;
(3) alguna cifra de la respuesta no está escrita en el fragmento citado.
"""
from __future__ import annotations

import re

from .troceado import normaliza

NUMEROS = {'dos': '2', 'tres': '3', 'cuatro': '4', 'cinco': '5', 'seis': '6', 'siete': '7', 'ocho': '8', 'nueve': '9',
           'diez': '10', 'once': '11', 'doce': '12', 'quince': '15', 'veinte': '20', 'treinta': '30', 'cuarenta': '40',
           'cincuenta': '50', 'sesenta': '60', 'noventa': '90', 'cien': '100', 'doscientos': '200'}

VACIAS = set('para pero como este esta estos estas pueden puede sobre entre desde hasta tiene tienes tengo cuando donde '
             'porque también solo sólo según ellos ellas eres está están será serán debe deben hacer cada otra otro otros '
             'otras todo toda todos todas muy aunque nota'.split())


def parsear(t: str) -> tuple[str, str, str]:
    """(respuesta, id de fragmento, cita) de la salida de tres líneas del modelo."""
    r = re.search(r'RESPUESTA:\s*(.*?)(?=\n\s*FRAGMENTO:|\n\s*CITA:|$)', t, re.S)
    f = re.search(r'FRAGMENTO:\s*\[?\s*([A-Za-z0-9_]+)', t)
    c = re.search(r'CITA:\s*(.*)$', t, re.S)
    cita = c.group(1).strip().split('\n')[0].strip().strip('"«»“”\'').strip() if c else ''
    return (r.group(1).strip() if r else t.strip()), (f.group(1) if f else ''), cita


def cita_esta_en(cita: str, texto_norm: str) -> bool:
    """Literal (normalizando) o casi literal (>= 80 % de sus trigramas)."""
    nc = normaliza(cita)
    w = nc.split()
    if len(w) < 4:
        return False
    if f' {nc} ' in f' {texto_norm} ':
        return True
    trigramas = {' '.join(w[i:i + 3]) for i in range(len(w) - 2)}
    return sum(f' {g} ' in f' {texto_norm} ' for g in trigramas) / len(trigramas) >= 0.8


def trozo_literal(cita: str, texto: str) -> str:
    """Trozo del fragmento, con sus palabras exactas, que más se parece a la cita del modelo."""
    cw, tw = normaliza(cita).split(), texto.split()
    tn = [normaliza(w) for w in tw]
    mejor, trozo = -1, ''
    for n in (len(cw) - 1, len(cw), len(cw) + 1, len(cw) + 2):
        for i in range(0, max(len(tw) - n, 0) + 1):
            ventana = ' '.join(tn[i:i + n]).split()
            if not ventana:
                continue
            puntos = len(set(cw) & set(ventana)) + (ventana[0] == cw[0]) + (ventana[-1] == cw[-1]) - 0.01 * abs(n - len(cw))
            if puntos > mejor:
                mejor, trozo = puntos, ' '.join(tw[i:i + n])
    return trozo


def cifras(s: str) -> set[str]:
    """Cifras de un texto, con números o con letras («tres» cuenta como 3)."""
    n = normaliza(s)
    return {normaliza(x) for x in re.findall(r'\d+(?:[.,]\d+)?', s)} | {NUMEROS[w] for w in n.split() if w in NUMEROS}


def cifra_en(x: str, texto_norm: str) -> bool:
    palabras = [w for w, d in NUMEROS.items() if d == x]
    return any(re.search(r'(?<![\w])' + re.escape(v) + r'(?![\w])', texto_norm) for v in [x] + palabras)


def palabras_clave(s: str) -> set[str]:
    return {NUMEROS.get(w, w) for w in normaliza(s).split() if (len(w) > 3 or w.isdigit() or w in NUMEROS) and w not in VACIAS}


def mejor_frase(respuesta: str, recuperados: list[dict], preferido: str = ''):
    """Trozo de hasta 40 palabras de los fragmentos con más palabras clave de la respuesta."""
    claves = palabras_clave(respuesta)
    mejor = (0.0, 0, '', None)
    if len(claves) < 2:
        return mejor
    for c in recuperados:
        for frase in re.split(r'(?<=[.;:!?])\s+', c['texto']):
            w = frase.split()
            for i in range(0, max(len(w) - 40, 0) + 1, 10):
                trozo = ' '.join(w[i:i + 40])
                n = len(claves & {NUMEROS.get(x, x) for x in normaliza(trozo).split()})
                puntos = n / len(claves) + (0.001 if c['chunk_id'] == preferido else 0)
                if puntos > mejor[0]:
                    mejor = (puntos, n, trozo, c)
    return mejor


def validar(pregunta: str, salida_modelo: str, recuperados: list[dict]) -> dict:
    """Aplica la regla de abstención. Devuelve respuesta, cita (siempre literal del documento), fragmento citado y motivo."""
    resp, frag, cita = parsear(salida_modelo)
    out = {'respuesta': resp, 'cita': cita, 'chunk_citado': '', 'cita_automatica': False, 'cita_aproximada': False}
    if 'NO CONSTA' in resp.upper():
        return {**out, 'abstiene': True, 'motivo': 'el modelo dice NO CONSTA'}
    por_id = {c['chunk_id']: c for c in recuperados}
    candidatos = ([por_id[frag]] if frag in por_id else []) + [c for c in recuperados if c['chunk_id'] != frag]
    citado = next((c for c in candidatos if cita_esta_en(cita, c['norm'])), None)
    if citado is not None and f' {normaliza(cita)} ' not in f" {citado['norm']} ":
        out['cita'], out['cita_aproximada'] = trozo_literal(cita, citado['texto']), True
    if citado is None:
        puntos, n, trozo, c = mejor_frase(resp, recuperados, frag)
        if puntos >= 0.5 and n >= 2:
            citado, out['cita'], out['cita_automatica'] = c, trozo, True
    if citado is None:
        return {**out, 'abstiene': True, 'motivo': 'ninguna frase de los fragmentos sostiene la respuesta'}
    out['chunk_citado'] = citado['chunk_id']
    sueltas = {x for x in cifras(resp) - cifras(pregunta) if not cifra_en(x, citado['norm'])}
    if sueltas:
        return {**out, 'abstiene': True, 'motivo': f'cifra no respaldada: {sorted(sueltas)}'}
    return {**out, 'abstiene': False, 'motivo': ''}
