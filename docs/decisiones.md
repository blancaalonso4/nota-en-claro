# Decisiones técnicas

Formato: fecha · decisión · por qué · alternativa descartada.

## 2026-11-26 · Generar con Ollama (`qwen3:8b`, `think=False`) en lugar de transformers
- **Por qué:** el producto es local, en un portátil de 16 GB sin GPU; Ollama gestiona la cuantización y la memoria.
- **Descartada:** Qwen2.5-3B con transformers (como en el Caso III), que necesitaba GPU.

## 2026-11-26 · Índice en disco con huella
- `data/indice/` guarda `embeddings.npy`, `fragmentos.json` y `meta.json`; la huella (sha256 de textos, encoder, ventana y solape) decide si se reindexa.
- **Por qué:** no reindexar en cada arranque. Medido: construir 100,7 s; cargar 0,02 s (256 fragmentos, primera ejecución con descarga del encoder incluida).
- **Descartada:** reindexar siempre, o una base vectorial externa (sobra para 256 fragmentos).

## 2026-11-26 · Troceado por ventana fija (250 palabras, solape 35) por defecto
- **Por qué:** fue el troceado del sistema final del Caso III. El troceado por secciones queda portado en `troceado.py` como alternativa.
- **Descartada:** secciones como valor por defecto, porque el Caso III no lo adoptó en el sistema final.

## 2026-11-26 · Reordenador opcional y desactivado por defecto
- **Por qué:** añade latencia en CPU; se activa con `ConfigRAG(usar_reordenador=True)` cuando se mida que compensa.

## 2026-11-26 · Prompt v2 y regla de abstención del Caso III
- Se portan tal cual (`prompt.py`, `citas.py`). La cita que se muestra es siempre un trozo literal del documento.

## 2026-11-26 · `caso3_referencia/` fuera de git; solo se copian textos, manifiesto y preguntas
- **Por qué:** los PDF pesan y son reproducibles con `descargar_corpus.py`. **Descartada:** subir el Caso III entero.

## 2026-11-26 · Dependencias en Python 3.14
- Medido: instalan sin errores en `.venv` torch 2.15.0, transformers 5.24.1, sentence-transformers 5.7.0, ollama 0.6.3, streamlit 1.67.0, numpy 2.5.5, pypdf 7.1.1.

## Mediciones de la prueba mínima (P01, `qwen3:8b`, k=3)
Todas **medidas** en este portátil (CPU, sin GPU):
- Tokens de entrada 1792 (todas las ejecuciones).
- 1.ª ejecución, modelo en frío: 147 tokens de salida, 178,56 s.
- Ejecuciones 2.ª a 4.ª, modelo caliente: 115 tokens de salida, 32,6–33,9 s, respuesta idéntica en las tres.
- **La 1.ª ejecución dio una respuesta distinta a las otras tres** pese a `seed=42` y `temperature=0`. Diagnosticado el 2026-11-26: ver la sección siguiente.
- Calidad de P01: la cita es correcta (doc08, «Días 12, 15 y 16 de junio»), pero la respuesta no da el plazo («tres días hábiles» está en doc13/doc07) y la 1.ª ejecución escribió «del 12 al 16 de junio», que no es lo que dice la cita. Con k=3 no se recuperó el fragmento de doc13/doc07. Pendiente para la evaluación de la próxima sesión.

## 2026-11-26 · Diagnóstico: la salida de Ollama depende del estado del runner (P01, qwen3:8b)
**Medido.** Se registraron los hashes del prompt exacto, de los fragmentos recuperados y de la salida (`eval/diagnostico_frio.py`, datos en `eval/salidas/diagnostico_frio.jsonl`).
- **Prompt y fragmentos: idénticos byte a byte** en todas las ejecuciones (mismos `sha_prompt` y `sha_fragmentos`, 1792 tokens de entrada). El origen no está en nuestro código: está en Ollama.
- Con el modelo recién cargado (`ollama stop qwen3:8b` antes de cada una), P01 dio **147 tokens, misma salida, 3/3**. En caliente, tras esas ejecuciones, **115 tokens, 3/3**. Son salidas distintas entre sí.
- La salida no depende solo de «frío o caliente»: dependió también de lo que se había ejecutado antes en el modelo cargado. Valores distintos de la misma pregunta P01 con las mismas semillas: 147, 115, 120 (tras alternar con P02, estable 3/3) y 155. P02 dio 97 tokens, siempre la misma salida.
- Con `num_thread=8` fijo: en frío sin calentar 147 (2/2, igual que con hilos por defecto); en caliente 155 (3/3, incluso tras recargar el modelo). Con `num_thread=8` y 3 llamadas cortas de calentamiento tras la carga, P01 dio **155 tokens, misma salida, 4/4** (2 con `diagnostico_frio.py` y 2 con `prueba_minima.py`, cada una tras `ollama stop`). Con hilos por defecto y calentamiento, 147 (2/2).
- **Contraejemplo medido:** tras esas ejecuciones, una ejecución en caliente con `prueba_minima.py` (mismo `num_thread=8`, mismo calentamiento) dio 115 tokens, no 155.
- Tiempos medidos: las dos primeras preguntas largas tras una carga tardan 130–170 s; después, 27–41 s. No vimos relación directa entre esa fase lenta y la salida.

**Causa.** No identificada del todo. Lo demostrado es que, con prompt y semilla idénticos, la salida de Ollama 0.40.18 en esta CPU cambia con el estado del runner (historial de llamadas y caché). Mecanismo sin verificar: portátil con CPU híbrida (i7-1255U, 2 núcleos P + 8 E) y caché de contexto reutilizada entre llamadas.

**Arreglo aplicado (protocolo, no garantía).**
- `num_thread=8` fijo, `keep_alive='30m'` (el modelo no se descarga a mitad de una tanda) y 3 llamadas de calentamiento tras cargar (`GeneradorOllama.calentar()`, `SistemaRAG.calentar()`).
- `eval/evaluar.py` hace `ollama stop <modelo>` antes de calentar, para que cada tanda empiece de una carga limpia.
- Con ese protocolo, la primera pregunta tras la carga se reprodujo 4/4. Las siguientes dependen del estado y de su orden: la reproducibilidad exacta solo se puede afirmar para una tanda completa lanzada desde carga limpia, no entre llamadas sueltas.
- **Alternativas descartadas:** `keep_alive=0` en cada llamada (recargar el modelo cada vez, más lento); dejar los hilos por defecto (salidas 115/120/147 según el historial).
- **No probado:** `qwen3:4b-instruct` bajo este protocolo. Las cifras de `eval/resultados.md` deben leerse con esta salvedad.

## 2026-11-26 · Evaluación (`eval/evaluar.py`): definiciones y resultados
- **Definiciones del Caso III:** oro = fragmento con el ancla literal; acierto@k sobre las 20 respondibles (en las de dos evidencias, deben estar las dos); correcta = no se abstiene, cita un fragmento de oro y la respuesta contiene el `dato_clave`; en las 5 sin respuesta, correcta = se abstiene; fidelidad = correctas entre las respondibles con el oro dentro de los k fragmentos; abstención indebida sobre las 20 respondibles.
- **Recuperación ganadora (medido):** con reordenador top-20 (@1 15/20, @3 19/20, @5 19/20) frente a sin reordenador (12/16/17); coste medido 2,75 s/pregunta frente a 0,03 s. Con esto la parte b usa reordenador y k=3. Se mantiene `usar_reordenador=False` en `ConfigRAG` por defecto hasta decidir si la latencia compensa (la generación tarda decenas de segundos, así que 2,7 s es poco).
- **Resultados de generación (medidos, ver `eval/resultados.md`):** `qwen3:8b` 13/25 correctas, abstiene 2/5 sin respuesta, 0/20 abstención indebida; `qwen3:4b-instruct` 16/25, abstiene 5/5, 3/20 indebida. Respondibles correctas, 11/20 en ambos.
- **Salvedades:** los segundos por pregunta de esta tanda (118,8 s con 8b; 85,7 s con 4b) son mucho mayores que los 27–41 s medidos antes en caliente; no se ha investigado la causa (la tanda se ejecutó con el modelo de reordenador cargado en el mismo proceso y otras tareas en la máquina). La reproducibilidad de 4b bajo el protocolo no está comprobada.
- **Alternativa descartada:** medir la generación sin reordenador (la ganadora de la parte a es la que pidió el enunciado).

## 2026-11-26 · Sesión 3 · Reordenador activado por defecto
- **Decisión:** `ConfigRAG.usar_reordenador=True`. Sustituye a la decisión «Reordenador opcional y desactivado por defecto».
- **Cifras (medidas en `eval/evaluar.py --parte a`, 20 respondibles):** acierto@3 19/20 con reordenador frente a 16/20 sin él (acierto@1 15/20 frente a 12/20). Coste medido: +2,75 s por pregunta (2,7451 s frente a 0,0277 s de media).
- **Por qué:** 3 preguntas más con la evidencia dentro de los 3 fragmentos que ve el generador, a cambio de unos segundos frente a una generación de decenas de segundos.
- **Descartada:** dejarlo desactivado.

## 2026-11-26 · Sesión 3 · Generador único: `qwen3:4b-instruct` (se retira `qwen3:8b` del producto)
- **Decisión:** `ConfigRAG.modelo='qwen3:4b-instruct'`. El futuro coordinador usará también `qwen3:4b-instruct`. Sustituye a «Generar con Ollama (`qwen3:8b`…)» y a la parte de la arquitectura de CLAUDE.md que daba `qwen3:8b` al agente de normativa.
- **Cifras (medidas, `eval/resultados.md` parte b, recuperación con reordenador y k=3, 25 preguntas):**

| | `qwen3:8b` | `qwen3:4b-instruct` |
|---|---|---|
| correctas | 13/25 | 16/25 |
| abstención en las 5 sin respuesta | 2/5 | 5/5 |
| s/pregunta (media) | 118,8 | 85,7 |

- **Por qué:** más correctas, abstiene bien en las preguntas sin respuesta y es más rápido; un solo modelo cargado cabe mejor en 16 GB.
- **Salvedad:** `qwen3:4b-instruct` tiene 3/20 abstenciones indebidas (`qwen3:8b`, 0/20) y las respondibles correctas son 11/20 en ambos.
- **Descartada:** mantener `qwen3:8b` como generador de normativa.

## 2026-11-26 · Sesión 3 · Latencia: el orden del prompt no se cambia (la parte fija ya iba primero)
Todo **medido** en este portátil con `qwen3:4b-instruct` (scripts `eval/medir_partes.py` y `eval/medir_cache.py`; tablas en `eval/resultados.md`, sección c).
- **Tokens por parte (media de 25 preguntas, `prompt_eval_count` en modo raw):** instrucciones 202 · ejemplos 219 · fragmentos 1412,4 · pregunta inicial 33,3 · pregunta final 34,3 (más ~13 de plantilla de chat; total medido 1913,8). Parte fija 421 tokens = 22 %.
- **El prefijo fijo ya se reutilizaba.** Las instrucciones y los ejemplos están en el mensaje de sistema, que es lo primero del prompt y es idéntico byte a byte entre preguntas. Con 5 preguntas seguidas en caliente (P01-P05, tras `ollama stop` y calentamiento), según `cached n_tokens` de `server.log` de Ollama: reutilizados 434 tokens en P02-P05 (en P01 solo 1, porque el calentamiento usa otro prompt), evaluados 7771 de 9508; 366,8 s en total (73,4 s por pregunta).
- **Por qué no hay nada que reordenar:** lo que queda por evaluar son los fragmentos (~1412 tokens) y la pregunta, que cambian en cada pregunta y por tanto no se pueden cachear. Evaluar el prompt cuesta ~28 ms/token y supone el 75 % de los segundos de generación (261,8 de 349,7 s).
- **Prueba descartada:** quitar la copia inicial de la pregunta (`pregunta_al_principio=False`). No es solo un cambio de orden (quita 33 tokens de contenido repetido) y no mejora: 378,1 s frente a 366,8 s, reutilizados 1743 frente a 1737, y la salida cambió en 4 de 5 preguntas. No se adopta.
- **Parte c) (reevaluar las 25 preguntas) no se lanza:** el prompt no ha cambiado, así que la tanda de 16/25 de `eval/resultados.md` (parte b, `qwen3:4b-instruct`, reordenador, k=3) sigue siendo la referencia; coincide con la configuración por defecto actual.
- **Para bajar la latencia de verdad** habría que reducir los tokens variables (menos fragmentos o más cortos, cambia el contenido y exige reevaluar) o acelerar la evaluación del prompt (hilos, lote); no se ha probado y queda para otra sesión.

## 2026-11-26 · Sesión 3 · Streaming de la respuesta en Streamlit
- `GeneradorOllama.generar_stream` y `SistemaRAG.responder_stream` ceden el texto a medida que sale; `app/web/app.py` lo pinta en un hueco y, al terminar, lo sustituye por la respuesta validada con su fuente (la cita solo se puede verificar con el texto completo).
- **Medido (`eval/prueba_streaming.py`, P03, qwen3:4b-instruct):** con streaming y prompt sin caché, el primer trozo llega a los 63,9 s y la respuesta completa a los 70,0 s (37 trozos); sin streaming, 90,5 s en esa tanda. Con el prompt ya en caché, 10,6 s frente a 10,0 s. **La salida es idéntica con y sin streaming** (1.ª y 2.ª ejecución), con las mismas opciones (seed 42, temperature 0, num_predict, think).
- **Alcance real:** el streaming mejora la sensación de espera solo en la fase de generación; la espera al primer trozo está dominada por evaluar el prompt (~64 s de 70 s), que el streaming no reduce. La diferencia 90,5 s frente a 70,0 s entre las dos tandas no se atribuye al streaming (una sola medición por modo; causa no investigada, y los tiempos ya variaban entre tandas, ver las salvedades de la evaluación).
- Comprobado en la app con `streamlit.testing.v1.AppTest`: respuesta con fuente, sin excepciones.

## 2026-11-26 · Sesión 3 · Un solo punto de arranque: `python -m app.app`
- `app/web/app.py` pasa a `app/interfaz.py` (se elimina `app/web/`) y nuevo `app/app.py`: comprueba Ollama y que `qwen3:4b-instruct` está descargado (mensaje con lo que hay que hacer si no), construye o carga el índice y lanza Streamlit con el mismo intérprete.
- **Por qué `python -m app.app` y no `python app/app.py`:** al ejecutar el archivo directamente, Python pone `app/` al principio del `sys.path` y `app.py` taparía al paquete `app` (fallarían los `from app.rag...`).
- README: apartado «¿Por qué no hay entrenamiento (train.py)?» (falta información, no estilo → RAG; la ingesta se hace al arrancar) y arranque simplificado; se corrige un `ollama pull` duplicado del README.
- **Descartada:** mantener `streamlit run app/web/app.py` como arranque (no comprueba nada y exige dos pasos).


## 2026-11-26 · Sesión 4 · `mcp` fijado en 1.30.0 (FastMCP), no 2.x
- **Decisión:** `mcp==1.30.0` en `requirements.txt`. Los servidores usan `mcp.server.fastmcp.FastMCP` (stdio) y el cliente `mcp.client.stdio`.
- **Por qué:** `pip install mcp` instaló la 2.3.0 (medido), donde `mcp.server.fastmcp` ya no existe: el import falla con un aviso de que FastMCP pasó a llamarse `MCPServer` y que otras APIs cambiaron. El enunciado pide FastMCP y la 1.x es la API que conocemos y documentamos.
- **Descartada:** migrar a `MCPServer` de la 2.x (API sin probar en el equipo; no aporta nada que necesitemos). Si se migra, hay que tocar los tres servidores, el puente y los tests en memoria.
- **Nota:** al volver a la 1.x quedaron restos de la 2.x (`mcp-types`, un directorio `~cp`); se desinstalaron. `pip check`: sin conflictos (medido).


## 2026-11-26 · Sesión 4 · Arquitectura de agentes y barandillas
Todo en `app/agentes/` y `app/mcp_servers/`. Sin frameworks de agentes: bucle propio sobre la API de Ollama.
- **Coordinador con modelo y salida JSON restringida por esquema** (`format=` de Ollama; una llamada, `num_predict=40`). **Medido** (`eval/evaluar_coordinador.py`, 30 peticiones etiquetadas por el equipo, 5 por intención): 30/30 aciertos; 189,2 tokens de entrada de media, 3,50 s de mediana por llamada (máx. 10,71 s la primera). Salvedad: el conjunto lo escribió el equipo con el mismo estilo, es una cota optimista. **Descartada:** reglas por palabras clave (0 s pero frágiles). Coste: la normativa pasa de 1 a 2 llamadas (~3,5 s más, medido).
- **El modelo nunca tiene la herramienta de enviar correo**: `enviar_borrador` solo se ejecuta desde el botón «Enviar» de la interfaz (`PuenteMCP.enviar_correo_confirmado`), y el servidor además exige `confirmado=True` y comprueba que el borrador va únicamente a `ORIENTADOR_EMAIL`. **Descartada:** que el modelo proponga enviar y se pida confirmación (una inyección podría provocar la propuesta).
- **Subconjunto de herramientas por intención** (plan: leer_notas, huecos_libres, crear_eventos_estudio; informe: leer_notas, guardar_informe; correo: leer_correos_orientador, crear_borrador). Menos tokens y menos confusión. **Descartada:** ofrecer las 9 siempre. Contra: si el coordinador se equivoca de intención, falta la herramienta.
- **Resumen final compuesto en Python**, sin vuelta extra del modelo. **Descartada:** que el modelo redacte el cierre (una llamada más, decenas de segundos en CPU).
- **Un token por plataforma** (`token_drive.json`, `token_calendar.json`, `token_gmail.json`) en lugar del `token.json` único pedido: un servidor nunca tiene los permisos de otro. Contra: tres consentimientos. Todos cubiertos por `token*.json` en `.gitignore`.
- **Tests con pytest** (`tests/`), sin Ollama ni Google: servidores probados en memoria con servicios falsos, agente con un Ollama guionizado.
- **`max_vueltas=4`** en lugar de 3: un plan son 2-3 vueltas y la 4.ª deja corregir un error del verificador.

## 2026-11-26 · Sesión 4 · Scopes de OAuth (mínimo privilegio)
Nombres de los de Calendar comprobados en la documentación de Google el 2026-11-26.
- Drive/Sheets: `drive.file` (solo los archivos que crea la app). **Descartados:** `drive`, `spreadsheets`.
- Calendar: `calendar.app.created` (calendario propio «Nota en Claro · Estudio») + `calendar.events.freebusy` (del principal solo ocupado/libre). **Descartado:** `calendar.events`.
- Gmail: `gmail.readonly` + `gmail.compose`. **Descartados:** `gmail.modify` y acceso total (permiten borrar).
- **Sin verificar con Google real todavía:** que `drive.file` baste para la API de Sheets sobre la hoja creada por la app (la documentación solo describe el scope en general) y qué scope exige exactamente cada método de Gmail. Se comprueba con la prueba real tras autorizar.

## 2026-11-26 · Sesión 4 · Nota de admisión en Python; ponderaciones las escribe el estudiante
- Fórmulas del corpus: CAU = 0,6·media Bachillerato + 0,4·PAU, ≥ 5 (doc07 art. 15; doc06 §3.1); PAU = media de los ejercicios de la fase de acceso, ≥ 4 (doc07 art. 14); Admisión = CAU + a·M1 + b·M2, máximo dos materias con nota ≥ 5, máximo 14 (doc06 §5-7; doc07 art. 22.3). Redondeo a la milésima, hacia arriba en equidistancia (`Decimal`). **Medido (tests):** reproduce los ejemplos resueltos de doc16 (11,524 y 11,724) y doc15 (12,000 y 12,100).
- **Las ponderaciones a y b no están utilizables en el corpus:** la única tabla es doc20 (Universidad de Alcalá, 2027-28) y en `data/texto/doc20.txt` se han perdido las columnas. **Decisión del equipo:** las escribe el estudiante en «Mis notas» o en el formulario manual. **Descartada:** reextraer doc20 del PDF (solo valdría para una universidad).
- El tope de 14 es inalcanzable por encima (máx. 10 + 2·10·0,2 = 14): el código lo aplica pero no hay test que lo supere.

## 2026-11-26 · Sesión 4 · OAuth en modo prueba: el refresh token caduca a los 7 días
- La app de OAuth está en **modo prueba**: solo la pueden autorizar los usuarios de prueba y el refresh token caduca a los **7 días**.
- **Hay que reautorizar (`python -m app.mcp_servers.autorizar`) antes de la entrega y antes de la defensa.** El servidor lo detecta (`RefreshError`) y dice al estudiante qué ejecutar.
- Para el profesor: se le añade como usuario de prueba y se le envía `credentials.json` por un canal privado (nunca por git). Sin Google funcionan la normativa y la calculadora con notas a mano.
- **Descartada:** publicar la app (verificación de Google, sin sentido para una cuenta demo).

## 2026-11-26 · Sesión 4 · Agente de acciones con el modelo real: lo que falló y lo que se corrigió
Todo **medido** (`eval/escenarios_acciones.py`; tanda inicial en `eval/salidas/escenarios_acciones_antes.md`, las cinco; la tanda posterior de a y b en `escenarios_acciones.md`). Herramientas de Google simuladas.
- **Antes:** en el plan de estudio (a y b) el modelo leyó notas y huecos y **escribió el plan en prosa** (350 tokens, 0 eventos; 74 s y 71 s). Sí funcionaron: calendario lleno (24,5 s, no crea nada), sin hoja (9,1 s, mensaje claro) y correo con instrucciones inyectadas (30,7 s; solo un borrador a `orientador@ejemplo.com`, sin enviar ni borrar).
- **Cambios (varios a la vez, no se midió cada uno por separado):** (1) esquema tipado del evento (`titulo`, `inicio`, `fin`: antes `list[dict]` y el modelo no sabía los campos), (2) el puente resuelve los `$ref` del esquema, (3) el prompt dice que no escriba el plan en texto y se añade un recordatorio tras los huecos, (4) máximo 6 sesiones en el prompt, (5) `num_predict` del agente 350 → 600 (con 350, Ollama devolvía un 500 porque el JSON de la llamada se cortaba), (6) las notas se presentan ordenadas de peor a mejor.
- **Después (a y b):** 3 vueltas; a: 4 eventos (Física 1, Matemáticas 1, Química 1, Historia 1), 78,0 s; b: 5 eventos, todos de Historia, 142,6 s. El reparto cambia con las notas (decide), pero **con Física floja solo da 1 sesión a Física**: la priorización de un modelo de 4B es floja. No resuelto.
- Un error 500 de Ollama al cortarse el JSON se informa hoy como «No he podido hablar con el modelo local»: mensaje poco preciso, pendiente.

## 2026-11-26 · Sesión 4 · Interfaz
- Chat con coordinador → trabajador; streaming solo en normativa; borrador pendiente con «Enviar al orientador» / «Descartar» (descartar deja el borrador en Gmail, no lo borra); formulario «Introducir mis notas a mano» (alternativa a leerlas de Drive); panel «Traza de la sesión» (`logs/sesion_*.jsonl`).
- Las pruebas con `AppTest` destaparon un fallo real: la clave del formulario chocaba con `session_state['notas_manuales']` y la interfaz se rompía al abrirse. Corregido.
- **Sin probar:** ejecución real de la interfaz con Ollama y Google (solo `AppTest` con falsos).
