"""Evaluación sobre las 25 preguntas de data/eval/preguntas.json, con las métricas del Caso III.

Parte a (sin LLM):  acierto@1/@3/@5 con y sin reordenador y segundos de recuperación por pregunta.
Parte b (con LLM):  con la recuperación ganadora, generación completa con qwen3:8b y qwen3:4b-instruct.

Uso:
    python eval/evaluar.py --parte a
    python eval/evaluar.py --parte b [--modelos qwen3:8b qwen3:4b-instruct]

Todo lo que escribe es MEDIDO en esta máquina. Detalle por pregunta en eval/salidas/*.csv, resumen en eval/resultados.md.
"""
import argparse
import csv
import ctypes
import dataclasses
import datetime
import json
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding='utf-8')

from app.rag.citas import validar  # noqa: E402
from app.rag.config import ConfigRAG, fijar_semillas  # noqa: E402
from app.rag.pipeline import SistemaRAG  # noqa: E402
from app.rag.prompt import mensajes_para  # noqa: E402
from app.rag.recuperacion import Reordenador, buscar  # noqa: E402
from app.rag.troceado import normaliza  # noqa: E402

SALIDAS = Path(__file__).parent / 'salidas'
KS = [1, 3, 5, 10]


# ---------- definiciones del Caso III ----------
def opciones(ancla: dict) -> list[dict]:
    return ancla['alternativas'] if 'alternativas' in ancla else [ancla]


def oro(q: dict, chunks: list[dict]) -> list[set]:
    """Para cada ancla, el conjunto de fragmentos que la contienen entera (vale cualquiera de sus alternativas)."""
    return [{c['chunk_id'] for op in opciones(a) for c in chunks
             if c['doc_id'] == op['doc'] and normaliza(op['texto']) in c['norm']}
            for a in q.get('anclas', [])]


def rango_oro(conjuntos: list[set], orden_ids: list[str]):
    """Puesto (1 = primero) en que ya están TODAS las anclas; None si alguna no está en ningún fragmento."""
    if not conjuntos or any(len(s) == 0 for s in conjuntos):
        return None
    pos = {cid: i + 1 for i, cid in enumerate(orden_ids)}
    return max(min(pos[c] for c in s) for s in conjuntos)


def dato_ok(q: dict, respuesta: str) -> bool:
    """Todos los datos de dato_clave deben salir en la respuesta (cada uno admite variantes separadas por «|»)."""
    t = normaliza(respuesta)
    return all(any(normaliza(v) in t for v in d.split('|')) for d in q.get('dato_clave', []))


# ---------- entorno ----------
def ram_gb() -> float:
    class M(ctypes.Structure):
        _fields_ = [('l', ctypes.c_ulong), ('u', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                    ('a', ctypes.c_ulonglong), ('b', ctypes.c_ulonglong), ('c', ctypes.c_ulonglong),
                    ('d', ctypes.c_ulonglong), ('e', ctypes.c_ulonglong), ('f', ctypes.c_ulonglong)]
    m = M()
    m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.total / 1024 ** 3


def entorno(sistema: SistemaRAG) -> dict:
    try:
        ver_ollama = subprocess.run(['ollama', '--version'], capture_output=True, text=True).stdout.strip()
    except OSError:
        ver_ollama = 'desconocida'
    modelos = {}
    for m in sistema.generador.cliente.list().models:
        modelos[m.model] = f"{(m.digest or '')[:12]} ({(m.size or 0) / 1e9:.1f} GB)"
    libs = {p: metadata.version(p) for p in ['torch', 'sentence-transformers', 'transformers', 'numpy', 'ollama']}
    return {'fecha': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            'maquina': f"{platform.node()} · {platform.platform()} · {platform.processor()} · "
                       f"{__import__('os').cpu_count()} hilos · {ram_gb():.1f} GB RAM · sin GPU",
            'python': platform.python_version(), 'ollama': ver_ollama, 'modelos_ollama': modelos, 'librerias': libs}


def cargar_preguntas(cfg: ConfigRAG) -> list[dict]:
    return json.loads(cfg.preguntas.read_text(encoding='utf-8'))['preguntas']


def escribir_csv(ruta: Path, filas: list[dict]) -> None:
    ruta.parent.mkdir(exist_ok=True)
    with open(ruta, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


# ---------- parte a: solo recuperación ----------
def parte_a(cfg: ConfigRAG) -> dict:
    fijar_semillas(cfg.semilla)
    s = SistemaRAG(cfg)
    idx, preguntas = s.indice, cargar_preguntas(cfg)
    reord = Reordenador(cfg.reordenador)
    # calentamiento fuera de la medida (carga de modelos); la carga se mide aparte
    buscar(idx, 'calentamiento')
    t0 = time.perf_counter()
    reord.reordenar('calentamiento', [0, 1], idx.chunks)
    t_carga_reord = time.perf_counter() - t0

    filas = []
    for q in preguntas:
        t0 = time.perf_counter()
        orden, sims = buscar(idx, q['pregunta'])
        t_busq = time.perf_counter() - t0
        t0 = time.perf_counter()
        n = cfg.n_candidatos
        orden_r = reord.reordenar(q['pregunta'], orden[:n], idx.chunks) + orden[n:]
        t_reord = time.perf_counter() - t0
        conj = oro(q, idx.chunks) if q['tipo'] != 'sin_respuesta' else []
        fila = {'id': q['id'], 'tipo': q['tipo'], 'oro_indexado': bool(conj) and all(conj) if conj else '',
                'seg_buscar': round(t_busq, 4), 'seg_reordenar': round(t_reord, 4),
                'seg_total_con_reordenador': round(t_busq + t_reord, 4)}
        for nombre, o in (('sin', orden), ('con', orden_r)):
            r = rango_oro(conj, [idx.chunks[i]['chunk_id'] for i in o])
            fila[f'rango_{nombre}'] = r if r is not None else ''
            for k in KS:
                fila[f'{nombre}@{k}'] = '' if q['tipo'] == 'sin_respuesta' else int(r is not None and r <= k)
        filas.append(fila)
    escribir_csv(SALIDAS / 'recuperacion.csv', filas)

    resp = [f for f in filas if f['tipo'] != 'sin_respuesta']
    res = {'n_respondibles': len(resp), 'carga_reordenador_s': round(t_carga_reord, 2),
           'indice': {'origen': idx.origen, 'fragmentos': len(idx.chunks)}, 'configs': {}}
    for nombre, etiqueta in (('sin', 'sin reordenador'), ('con', 'con reordenador (top-20)')):
        c = {f'@{k}': sum(f[f'{nombre}@{k}'] for f in resp) for k in KS}
        seg = [f['seg_buscar'] + (f['seg_reordenar'] if nombre == 'con' else 0) for f in filas]
        c['seg_medio'], c['seg_max'] = round(float(np.mean(seg)), 4), round(float(np.max(seg)), 4)
        res['configs'][etiqueta] = c
    # configuración ganadora: más aciertos@3 (k de generación), luego @1, luego @5, y a igualdad la más rápida (sin reordenador)
    def clave(item):
        e, c = item
        return (-c['@3'], -c['@1'], -c['@5'], e.startswith('con'))
    res['ganadora'] = sorted(res['configs'].items(), key=clave)[0][0]
    res['entorno'] = entorno(s)
    (SALIDAS / 'resumen_a.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in res.items() if k != 'entorno'}, ensure_ascii=False, indent=1))
    return res


# ---------- parte b: generación completa ----------
def probar_think(sistema: SistemaRAG) -> bool | None:
    """Algunos modelos (instruct) no admiten el parámetro think: se detecta con una llamada mínima."""
    try:
        sistema.generador.cliente.chat(model=sistema.cfg.modelo, messages=[{'role': 'user', 'content': 'hola'}],
                                       think=False, options={'num_predict': 1, 'seed': 42, 'temperature': 0})
        return False
    except Exception as e:  # noqa: BLE001
        if 'think' in str(e).lower():
            return None
        raise


def parte_b(cfg_base: ConfigRAG, modelos: list[str]) -> dict:
    ra = json.loads((SALIDAS / 'resumen_a.json').read_text(encoding='utf-8'))
    usar_reord = ra['ganadora'].startswith('con')
    preguntas = cargar_preguntas(cfg_base)
    res = {'recuperacion_usada': ra['ganadora'], 'k': cfg_base.k, 'modelos': {}}
    for modelo in modelos:
        cfg = dataclasses.replace(cfg_base, modelo=modelo, usar_reordenador=usar_reord)
        fijar_semillas(cfg.semilla)
        s = SistemaRAG(cfg)
        think = probar_think(s)
        if think is None:   # el modelo no admite think: se deja sin enviar y se anota
            s.generador.cfg = dataclasses.replace(cfg, think=None)
        cache = SALIDAS / f"cache_{modelo.replace(':', '_')}.jsonl"
        hechas = {}
        if cache.exists():
            for l in cache.read_text(encoding='utf-8').splitlines():
                d = json.loads(l)
                hechas[d['id']] = d
        # calentamiento: carga del modelo fuera de la medida (y estado de referencia, ver docs/decisiones.md)
        # descarga previa: cada modelo parte siempre de una carga limpia (la salida de Ollama depende del estado del runner)
        subprocess.run(['ollama', 'stop', modelo], capture_output=True)
        time.sleep(3)
        t0 = time.perf_counter()
        s.calentar()
        carga = round(time.perf_counter() - t0, 1)
        filas = []
        for q in preguntas:
            if q['id'] in hechas:
                filas.append(hechas[q['id']])
                continue
            t0 = time.perf_counter()
            rec = s.recuperar(q['pregunta'])
            t_rec = time.perf_counter() - t0
            msgs = mensajes_para(q['pregunta'], rec, s.manifiesto)
            g = s.generador.generar(msgs)
            v = validar(q['pregunta'], g['texto'], rec)
            conj = oro(q, s.indice.chunks) if q['tipo'] != 'sin_respuesta' else []
            oro_union = set().union(*conj) if conj else set()
            ids = [c['chunk_id'] for c in rec]
            oro_en_k = bool(conj) and all(s & set(ids) for s in conj)   # todas las anclas dentro de los k fragmentos
            dato = dato_ok(q, v['respuesta'])
            correcto = v['abstiene'] if q['tipo'] == 'sin_respuesta' else (
                (not v['abstiene']) and v['chunk_citado'] in oro_union and dato)
            fila = {'id': q['id'], 'tipo': q['tipo'], 'oro_en_k': int(oro_en_k),
                    'abstiene': int(v['abstiene']), 'motivo': v['motivo'], 'cita_oro': int(v['chunk_citado'] in oro_union),
                    'dato_ok': int(dato), 'correcto': int(correcto), 'tokens_entrada': g['tokens_entrada'],
                    'tokens_salida': g['tokens_salida'], 'seg_generar': g['segundos'], 'seg_recuperar': round(t_rec, 3),
                    'respuesta': v['respuesta'], 'chunk_citado': v['chunk_citado'], 'fragmentos': ' '.join(ids)}
            filas.append(fila)
            with open(cache, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + '\n')
            print(f"{modelo} {q['id']} correcto={fila['correcto']} abst={fila['abstiene']} "
                  f"{fila['tokens_entrada']}->{fila['tokens_salida']} tok {fila['seg_generar']} s", flush=True)
        escribir_csv(SALIDAS / f"generacion_{modelo.replace(':', '_')}.csv", filas)
        resp = [f for f in filas if f['tipo'] != 'sin_respuesta']
        sinr = [f for f in filas if f['tipo'] == 'sin_respuesta']
        vistos = [f for f in resp if f['oro_en_k']]
        res['modelos'][modelo] = {
            'correctas': sum(f['correcto'] for f in filas), 'n': len(filas),
            'correctas_respondibles': sum(f['correcto'] for f in resp), 'n_respondibles': len(resp),
            'fidelidad': f"{sum(f['correcto'] for f in vistos)}/{len(vistos)}",
            'abstencion_sin_respuesta': f"{sum(f['abstiene'] for f in sinr)}/{len(sinr)}",
            'abstencion_indebida': f"{sum(f['abstiene'] for f in resp)}/{len(resp)}",
            'tokens_entrada_medio': round(float(np.mean([f['tokens_entrada'] for f in filas])), 1),
            'tokens_salida_medio': round(float(np.mean([f['tokens_salida'] for f in filas])), 1),
            'seg_generar_medio': round(float(np.mean([f['seg_generar'] for f in filas])), 1),
            'seg_generar_max': round(float(np.max([f['seg_generar'] for f in filas])), 1),
            'seg_generar_total': round(float(np.sum([f['seg_generar'] for f in filas])), 0),
            'think_enviado': think is not None, 'carga_modelo_s': carga}
        print(modelo, json.dumps(res['modelos'][modelo], ensure_ascii=False), flush=True)
    res['entorno'] = entorno(s)
    (SALIDAS / 'resumen_b.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    return res


# ---------- resultados.md ----------
def escribir_md() -> None:
    a = json.loads((SALIDAS / 'resumen_a.json').read_text(encoding='utf-8'))
    bp = SALIDAS / 'resumen_b.json'
    b = json.loads(bp.read_text(encoding='utf-8')) if bp.exists() else None
    e = (b or a)['entorno']
    L = ['# Resultados de evaluación', '',
         '**Todas las cifras de este documento son MEDIDAS** en esta máquina, sobre las 25 preguntas de `data/eval/preguntas.json` '
         '(20 respondibles + 5 sin respuesta), con las definiciones del Caso III. Semilla 42, `temperature 0`. '
         'Generado por `eval/evaluar.py`; detalle por pregunta en `eval/salidas/*.csv`.', '',
         '## Entorno', '', f"- Fecha: {e['fecha']}", f"- Máquina: {e['maquina']}", f"- Python: {e['python']}",
         f"- Ollama: {e['ollama']}", '- Modelos Ollama (digest, tamaño): ' +
         '; '.join(f"`{k}` {v}" for k, v in e['modelos_ollama'].items()),
         '- Librerías: ' + ', '.join(f"{k} {v}" for k, v in e['librerias'].items()), '',
         '## a) Solo recuperación (sin LLM)', '',
         f"Índice: {a['indice']['fragmentos']} fragmentos (ventana 250, solape 35, e5-small). Acierto@k sobre las "
         f"{a['n_respondibles']} respondibles; en las de dos evidencias cuenta solo si están las dos. "
         f"Segundos por pregunta (medidos; modelos ya cargados, carga del reordenador {a['carga_reordenador_s']} s aparte).", '',
         '| Configuración | acierto@1 | acierto@3 | acierto@5 | acierto@10 | s/pregunta (media) | s/pregunta (máx) |',
         '|---|---|---|---|---|---|---|']
    n = a['n_respondibles']
    for nombre, c in a['configs'].items():
        L.append(f"| {nombre} | {c['@1']}/{n} | {c['@3']}/{n} | {c['@5']}/{n} | {c['@10']}/{n} | {c['seg_medio']} | {c['seg_max']} |")
    L += ['', f"**Ganadora (criterio: más aciertos@3, luego @1, luego @5, y a igualdad la más rápida): {a['ganadora']}.**", '']
    if b:
        L += ['## b) Generación completa', '',
              f"Recuperación usada: {b['recuperacion_usada']}, k = {b['k']}. `think=False` salvo que el modelo no lo admita (columna «think»). "
              "Correcta = no se abstiene, cita un fragmento de oro y da el `dato_clave` en la respuesta; en las sin respuesta, "
              "correcta = se abstiene. Fidelidad = correctas entre las respondibles con el oro dentro de los k fragmentos.", '',
              '| Modelo | correctas (25) | respondibles correctas | fidelidad | abstención sin respuesta | abstención indebida | tokens entrada (media) | tokens salida (media) | s/pregunta (media) | s/pregunta (máx) | think |',
              '|---|---|---|---|---|---|---|---|---|---|---|']
        for m, r in b['modelos'].items():
            L.append(f"| `{m}` | {r['correctas']}/{r['n']} | {r['correctas_respondibles']}/{r['n_respondibles']} | {r['fidelidad']} | "
                     f"{r['abstencion_sin_respuesta']} | {r['abstencion_indebida']} | {r['tokens_entrada_medio']} | "
                     f"{r['tokens_salida_medio']} | {r['seg_generar_medio']} | {r['seg_generar_max']} | "
                     f"{'enviado' if r['think_enviado'] else 'no admitido'} |")
        L.append('')
    L += seccion_latencia()
    (Path(__file__).parent / 'resultados.md').write_text('\n'.join(L), encoding='utf-8')
    print('Escrito eval/resultados.md')


def seccion_latencia() -> list[str]:
    """Sección c) de resultados.md con los datos de eval/medir_partes.py y eval/medir_cache.py (si existen)."""
    pp, ca, cb = (SALIDAS / n for n in ('partes_prompt.json', 'cache_antes.json', 'cache_sin_pregunta_inicial.json'))
    if not (pp.exists() and ca.exists()):
        return []
    d = json.loads(pp.read_text(encoding='utf-8'))
    f, m = d['fijo'], d['medias_25_preguntas']
    total = f['sistema_completo'] + m['pregunta_inicial'] + m['fragmentos'] + m['pregunta_final']
    L = ['## c) Latencia: tokens por parte del prompt y caché de prefijo (sesión 3)', '',
         f"Modelo `{d['modelo']}`, recuperación con reordenador, k = 3. **Medido** con `eval/medir_partes.py`: cada trozo se manda "
         "a Ollama en modo `raw` con `num_predict=1` y se lee `prompt_eval_count` (sin plantilla de chat; puede haber ±1-2 tokens por frontera).", '',
         '| Parte del prompt | Tokens | ¿Cambia entre preguntas? |', '|---|---|---|',
         f"| Instrucciones del sistema | {f['instrucciones']} | no |", f"| Ejemplos (2, dentro del mensaje de sistema) | {f['ejemplos']} | no |",
         f"| Fragmentos (3, con sus cabeceras) | {m['fragmentos']} (media de 25) | sí |",
         f"| Pregunta, copia inicial | {m['pregunta_inicial']} (media de 25) | sí |",
         f"| Pregunta, copia final | {m['pregunta_final']} (media de 25) | sí |",
         f"| **Suma de trozos** | {total:.0f} (la plantilla de chat añade unos 13: el total medido en la evaluación es 1913,8 de media) | |", '',
         f"Parte fija: {f['sistema_completo']} tokens ({f['sistema_completo'] / total:.0%} del prompt); variable: {total - f['sistema_completo']:.0f}.", '',
         '### Caché de prefijo con 5 preguntas seguidas en caliente (`eval/medir_cache.py`)', '',
         "Protocolo: `ollama stop`, 3 llamadas de calentamiento, P01-P05 seguidas. «Reutilizados» sale de la línea `cached n_tokens` de "
         "`server.log` de Ollama; «evaluados» = total del prompt - reutilizados. `prompt_eval_count` de la API incluye los reutilizados.", '']
    for etiqueta, ruta, nombre in (('antes', ca, 'Prompt actual (la parte fija ya va primero: mensaje de sistema)'),
                                   ('sin_pregunta_inicial', cb, 'Variante: se quita la copia inicial de la pregunta (cambia el contenido, no solo el orden; NO adoptada)')):
        if not ruta.exists():
            continue
        r = json.loads(ruta.read_text(encoding='utf-8'))
        L += [f"**{nombre}**", '', '| Pregunta | Tokens prompt | Reutilizados | Evaluados | s evaluar prompt | s generar | s total (recuperar+generar) |',
              '|---|---|---|---|---|---|---|']
        for x in r['filas']:
            L.append(f"| {x['id']} | {x['tokens_prompt']} | {x['tokens_reutilizados']} | {x['tokens_evaluados']} | "
                     f"{x['seg_eval_prompt']} | {x['seg_generacion']} | {x['seg_total']} |")
        ev = sum(x['seg_eval_prompt'] for x in r['filas'])
        L += [f"| **Suma** | {r['suma_tokens_prompt']} | {r['suma_tokens_reutilizados']} | {r['suma_tokens_evaluados']} | "
              f"{ev:.1f} | {r['suma_seg_generacion']} | {r['suma_seg_total']} |", '',
              f"Evaluar el prompt supone el {ev / r['suma_seg_generacion']:.0%} de los segundos de generación.", '']
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--parte', choices=['a', 'b', 'md'], required=True)
    ap.add_argument('--modelos', nargs='+', default=['qwen3:8b', 'qwen3:4b-instruct'])
    a = ap.parse_args()
    cfg = ConfigRAG()
    SALIDAS.mkdir(exist_ok=True)
    if a.parte == 'a':
        parte_a(cfg)
    elif a.parte == 'md':
        pass   # solo regenera resultados.md con los datos ya medidos
    else:
        parte_b(cfg, a.modelos)
    escribir_md()


if __name__ == '__main__':
    main()
