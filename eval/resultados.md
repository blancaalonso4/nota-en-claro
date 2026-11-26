# Resultados de evaluación

**Todas las cifras de este documento son MEDIDAS** en esta máquina, sobre las 25 preguntas de `data/eval/preguntas.json` (20 respondibles + 5 sin respuesta), con las definiciones del Caso III. Semilla 42, `temperature 0`. Generado por `eval/evaluar.py`; detalle por pregunta en `eval/salidas/*.csv`.

## Entorno

- Fecha: 2026-11-26 12:19
- Máquina: HPBlanca · Windows-11-10.0.26200-SP0 · Intel64 Family 6 Model 154 Stepping 4, GenuineIntel · 12 hilos · 15.7 GB RAM · sin GPU
- Python: 3.14.10
- Ollama: ollama version is 0.40.18
- Modelos Ollama (digest, tamaño): `qwen3:4b-instruct` 0edcdef34593 (2.5 GB); `qwen3:8b` 500a1f067a9f (5.2 GB)
- Librerías: torch 2.15.0, sentence-transformers 5.7.0, transformers 5.24.1, numpy 2.5.5, ollama 0.6.3

## a) Solo recuperación (sin LLM)

Índice: 256 fragmentos (ventana 250, solape 35, e5-small). Acierto@k sobre las 20 respondibles; en las de dos evidencias cuenta solo si están las dos. Segundos por pregunta (medidos; modelos ya cargados, carga del reordenador 64.9 s aparte).

| Configuración | acierto@1 | acierto@3 | acierto@5 | acierto@10 | s/pregunta (media) | s/pregunta (máx) |
|---|---|---|---|---|---|---|
| sin reordenador | 12/20 | 16/20 | 17/20 | 18/20 | 0.0277 | 0.0385 |
| con reordenador (top-20) | 15/20 | 19/20 | 19/20 | 19/20 | 2.7451 | 3.4249 |

**Ganadora (criterio: más aciertos@3, luego @1, luego @5, y a igualdad la más rápida): con reordenador (top-20).**

## b) Generación completa

Recuperación usada: con reordenador (top-20), k = 3. `think=False` salvo que el modelo no lo admita (columna «think»). Correcta = no se abstiene, cita un fragmento de oro y da el `dato_clave` en la respuesta; en las sin respuesta, correcta = se abstiene. Fidelidad = correctas entre las respondibles con el oro dentro de los k fragmentos.

| Modelo | correctas (25) | respondibles correctas | fidelidad | abstención sin respuesta | abstención indebida | tokens entrada (media) | tokens salida (media) | s/pregunta (media) | s/pregunta (máx) | think |
|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3:8b` | 13/25 | 11/20 | 11/19 | 2/5 | 0/20 | 1921.8 | 85.1 | 118.8 | 163.6 | enviado |
| `qwen3:4b-instruct` | 16/25 | 11/20 | 11/19 | 5/5 | 3/20 | 1913.8 | 136.5 | 85.7 | 124.7 | enviado |

## c) Latencia: tokens por parte del prompt y caché de prefijo (sesión 3)

Modelo `qwen3:4b-instruct`, recuperación con reordenador, k = 3. **Medido** con `eval/medir_partes.py`: cada trozo se manda a Ollama en modo `raw` con `num_predict=1` y se lee `prompt_eval_count` (sin plantilla de chat; puede haber ±1-2 tokens por frontera).

| Parte del prompt | Tokens | ¿Cambia entre preguntas? |
|---|---|---|
| Instrucciones del sistema | 202 | no |
| Ejemplos (2, dentro del mensaje de sistema) | 219 | no |
| Fragmentos (3, con sus cabeceras) | 1412.4 (media de 25) | sí |
| Pregunta, copia inicial | 33.3 (media de 25) | sí |
| Pregunta, copia final | 34.3 (media de 25) | sí |
| **Suma de trozos** | 1901 (la plantilla de chat añade unos 13: el total medido en la evaluación es 1913,8 de media) | |

Parte fija: 421 tokens (22% del prompt); variable: 1480.

### Caché de prefijo con 5 preguntas seguidas en caliente (`eval/medir_cache.py`)

Protocolo: `ollama stop`, 3 llamadas de calentamiento, P01-P05 seguidas. «Reutilizados» sale de la línea `cached n_tokens` de `server.log` de Ollama; «evaluados» = total del prompt - reutilizados. `prompt_eval_count` de la API incluye los reutilizados.

**Prompt actual (la parte fija ya va primero: mensaje de sistema)**

| Pregunta | Tokens prompt | Reutilizados | Evaluados | s evaluar prompt | s generar | s total (recuperar+generar) |
|---|---|---|---|---|---|---|
| P01 | 1820 | 1 | 1819 | 57.1 | 76.85 | 79.24 |
| P02 | 1983 | 434 | 1549 | 53.79 | 68.38 | 71.85 |
| P03 | 1888 | 434 | 1454 | 51.67 | 58.44 | 63.48 |
| P04 | 1880 | 434 | 1446 | 48.46 | 72.8 | 75.53 |
| P05 | 1937 | 434 | 1503 | 50.74 | 73.26 | 76.71 |
| **Suma** | 9508 | 1737 | 7771 | 261.8 | 349.7 | 366.8 |

Evaluar el prompt supone el 75% de los segundos de generación.

**Variante: se quita la copia inicial de la pregunta (cambia el contenido, no solo el orden; NO adoptada)**

| Pregunta | Tokens prompt | Reutilizados | Evaluados | s evaluar prompt | s generar | s total (recuperar+generar) |
|---|---|---|---|---|---|---|
| P01 | 1789 | 1 | 1788 | 61.6 | 78.69 | 81.07 |
| P02 | 1944 | 435 | 1509 | 55.12 | 74.83 | 80.2 |
| P03 | 1854 | 435 | 1419 | 55.4 | 62.69 | 67.36 |
| P04 | 1844 | 436 | 1408 | 52.44 | 65.96 | 70.21 |
| P05 | 1910 | 436 | 1474 | 51.59 | 75.65 | 79.22 |
| **Suma** | 9341 | 1743 | 7598 | 276.1 | 357.8 | 378.1 |

Evaluar el prompt supone el 77% de los segundos de generación.
