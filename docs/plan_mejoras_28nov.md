# Plan de mejoras · 28-11-2026 (Nota en Claro)

> **Paso 0 (lo único que se hace al aprobar este plan):** copiar este documento tal cual a `docs/plan_mejoras_28nov.md` y PARAR. No se ejecuta ninguna fase. Cada fase (1A, 1B, 2) la ejecutará después otra sesión, que solo tendrá este documento, `CLAUDE.md` y el código. Las respuestas del equipo a las dudas están al final («Decisiones del equipo (28-11)»): no hay que volver a preguntarlas.

## Contexto

Tras las sesiones 4-6 la app funciona de punta a punta (normativa con RAG, calculadora en Python, plan de estudio, informe y correo al orientador con MCP). Quedan problemas de uso detectados por el equipo:
- cada plan de estudio nuevo se **suma** al anterior en el calendario «Nota en Claro · Estudio» (la app no borra nada);
- el plan puede poner dos sesiones de la misma asignatura el mismo día, y a horas poco razonables (ventana fija 8:00-22:00, que incluye las horas de clase);
- no se ve de qué notas tira la calculadora, y la tabla a mano muestra puntos decimales y «None»;
- `.env.example` trae un correo y unos nombres de ejemplo que acaban usándose de verdad;
- falta una vista de notas, un «¿qué nota necesito?», una cuenta atrás a la PAU y un diseño más cuidado.

Reglas de `CLAUDE.md` que aplican a todo: todo en castellano; Windows y `py -3.14` con `.venv`; nunca subir `.env`, `credentials.json` ni `token_*.json` (comprobar `git status` antes de cada commit); cifras con «medido»/«estimado»; cada decisión en `docs/decisiones.md` (fecha, decisión, por qué, alternativa descartada); prompts relevantes en `docs/prompts.md`; semilla 42 y llamadas a Ollama con `seed`, `temperature 0`, `num_predict` y `think` explícitos; sin frameworks de agentes.

## Datos de partida comprobados (2026-11-28)

- **Tests:** 219 (medido: `.\.venv\Scripts\python.exe -m pytest --collect-only -q` → «219 tests collected»). El total no puede bajar de 219 en ninguna fase.
- **Versiones instaladas** (medido con `import`): `streamlit 1.67.0`, `altair 6.3.0` (viene con Streamlit; no hay que añadir ninguna librería).
- **Streamlit 1.67:** `NumberColumn(format=...)` no permite fijar la coma decimal (el preset `"localized"` depende del idioma del navegador; comprobado en `.venv/Lib/site-packages/streamlit/elements/lib/column_types.py`). `TextColumn` sí admite `validate=` (expresión regular). Ninguna columna tiene `placeholder`.
- **Permisos de Google Calendar (documentación oficial leída el 2026-11-28, no de memoria):**
  - `calendar.app.created`: «Make secondary Google calendars, and see, create, change, and delete events on them» (https://developers.google.com/workspace/calendar/api/auth).
  - `events.delete` acepta `calendar`, `calendar.events`, **`calendar.app.created`** y `calendar.events.owned`; tiene `sendUpdates` (`all` / `externalOnly` / `none`).
  - `events.list` acepta, entre otros, **`calendar.app.created`**; `maxResults` hasta 2500 por página, con `pageToken`/`nextPageToken`.
  - `calendars.delete` también acepta `calendar.app.created`.
  - `freebusy.query` acepta `calendar.readonly`, `calendar`, `calendar.events.freebusy` y `calendar.freebusy` (**no** `calendar.app.created`): la consulta de huecos sigue usando `calendar.events.freebusy`, que ya tenemos.
  - **Conclusión:** borrar eventos del calendario de la app **no necesita ningún permiso nuevo ni reautorizar**; `SCOPES` en `app/mcp_servers/comun.py` no cambia. Queda confirmarlo con Google real en la prueba manual de la fase 1A (si diera 403, se reautoriza y se anota en `docs/decisiones.md`).

## Cómo está hoy el flujo del plan (para entender los cambios)

`interfaz.atender` → `Orquestador.atender` (`app/agentes/coordinador.py`) → `AgenteAcciones.ejecutar('plan_estudio')` (`app/agentes/acciones.py`): el modelo llama a `leer_notas` y `huecos_libres`, luego a `planificar_sesiones`; `plan.construir_eventos` (`app/agentes/plan.py`) calcula las fechas, `verificador.verificar('crear_eventos_estudio', ...)` las comprueba y **el agente llama él mismo** a `crear_eventos_estudio` por el puente. `huecos_libres` (`app/mcp_servers/mcp_calendar.py`) consulta freebusy de `primary` **y** del calendario de la app, ventana fija 8-22 (`INICIO_DIA`, `FIN_DIA`). El envío de correo es el modelo a copiar para todo lo que exige confirmación: permiso `CONFIRMAR` en `app/agentes/permisos.py`, nunca ofrecido al modelo, método propio del puente (`PuenteMCP.enviar_correo_confirmado`) que vuelve a verificar, y el servidor exige `confirmado=True`.

**Orden para pasar todos los tests** (desde la raíz; la misma en todas las fases):
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
Todo en verde y un total ≥ 219 + los nuevos (anotar la cifra exacta como «medido»).

---

# FASE 1A · El plan nuevo sustituye al anterior (puntos 1.0 y 1.1)

Un commit por punto. Al acabar: tests en verde, `git status` limpio de secretos, entrada en `docs/decisiones.md`.

### 1.0 Registro del prompt
- `docs/prompts.md`: añadir el prompt de planificación del 28-11-2026 y las respuestas del equipo (regla 6 de `CLAUDE.md`).

### 1.1 Sustitución del plan

**Diseño:** el agente ya **no crea** eventos: propone y el verificador aprueba. Una única herramienta nueva de servidor, `aplicar_plan_estudio`, con permiso `CONFIRMAR` (como `enviar_borrador`): el modelo nunca la recibe y `puente.llamar` la rechaza; solo se llega a ella por un método del puente llamado desde Python. Se borran **todos** los eventos del calendario de la app, también los pasados y los editados a mano.

| Fichero | Cambio |
|---|---|
| `app/mcp_servers/mcp_calendar.py` | (a) `huecos_libres`: `items` solo con `{'id': 'primary'}` (las sesiones del plan viejo no cuentan como ocupado). (b) Nueva herramienta `aplicar_plan_estudio(eventos: list[Evento], confirmado: bool = False)`: obtiene `cal_id` **solo** de `asegurar_calendario()` (estado guardado, nunca de un argumento; si `cal_id == 'primary'` lanza `ErrorGoogle`); lista los **ids** de todos los eventos del calendario de la app (`events().list(calendarId=cal_id, maxResults=2500, fields='items(id),nextPageToken', pageToken=...)`, tope de 20 páginas); si hay eventos y `confirmado` no es `True`, devuelve `{'aplicado': False, 'existentes': N}` **sin tocar nada**; si no, **crea primero** los nuevos (mismo `_cuerpo_evento` y `sendUpdates='none'` que `crear_eventos_estudio`) y **después** borra los antiguos por id (`events().delete(calendarId=cal_id, eventId=id, sendUpdates='none')`; un 404/410 cuenta como ya borrado). Si falla una creación: borra los nuevos ya creados en esa misma llamada (marcha atrás) y lanza `ErrorGoogle('No he podido crear el plan nuevo; tu plan anterior sigue igual.')` sin borrar nada antiguo. Devuelve `{'aplicado': True, 'creados': [...], 'existentes': N, 'borrados': n_ok, 'no_borrados': n_fallo, 'calendario_id': cal_id, 'reintentos': ...}`. Actualizar el docstring del módulo («solo se borra en `aplicar_plan_estudio`, con confirmación, y solo en el calendario de la app»). `crear_eventos_estudio` y `listar_eventos` se quedan como están. |
| `app/agentes/permisos.py` | `PERMISOS['aplicar_plan_estudio'] = CONFIRMAR`. No se añade a ninguna intención de `HERRAMIENTAS_POR_INTENCION`. |
| `app/agentes/verificador.py` | `CLAVES_PERMITIDAS['aplicar_plan_estudio'] = {'eventos'}` con las mismas comprobaciones que `crear_eventos_estudio` (`_eventos`). |
| `app/agentes/puente_mcp.py` | `PLATAFORMA_DE['aplicar_plan_estudio'] = 'calendar'`. Método nuevo `aplicar_plan(eventos, *, huecos, dias, zona, franja=None, confirmado=False, ahora=None) -> ResultadoLlamada`: verifica con `verificar('aplicar_plan_estudio', ...)` (con la hora actual: si la propuesta ya ha empezado, se rechaza) y llama `_llamar('aplicar_plan_estudio', {'eventos': ..., 'confirmado': confirmado})`. (`franja` se usará en la fase 1B; en 1A se acepta y se pasa al verificador.) |
| `app/agentes/acciones.py` | En `_herramienta`, rama `planificar_sesiones`: tras `construir_eventos` y `verificar('crear_eventos_estudio', ...)` correctos, **no** se llama al puente: `res.plan_propuesto = eventos`, `res.huecos = self._huecos`, `res.dias = self._dias` y se para el bucle (como hoy tras escribir). `ResultadoAcciones` gana `plan_propuesto: list[dict]`, `huecos: list | None`, `dias: int`; `eventos` se mantiene (vacío en el plan). `_cierre` con propuesta: «Te propongo N sesiones: …». Mover el formateo de líneas («- miércoles 2 dic 16:00–17:30 · Estudio: Física») a `plan.lineas_eventos(eventos)` y reutilizarlo. |
| `app/agentes/plan_calendario.py` (nuevo) | Python puro. `aplicar(puente, traza, propuesta, *, confirmado, zona, franja=None, agente)`: llama `puente.aplicar_plan` y registra en la traza `tipo='herramienta'`, `agente` ('orquestador' o 'interfaz'), `herramienta='aplicar_plan_estudio'`, `permiso='confirmar'`, `existentes`, `borrados`, `no_borrados`, `creados` (número), `calendario='Nota en Claro · Estudio'` y `calendario_id` (el id prueba que nunca se borró en `'primary'`), `confirmado_por_usuario`; **nunca** títulos ni fechas. Devuelve el texto para el estudiante. Si `no_borrados > 0`: «He creado tu plan nuevo, pero no he podido borrar K sesiones del plan anterior: siguen en «Nota en Claro · Estudio». Vuelve a pedir el plan o bórralas a mano en Google Calendar.» `cancelar(traza)`: registra el paso con `cancelado=True` y no llama a nada. Constante `PREGUNTA_SUSTITUIR = 'Ya tienes un plan con {n} sesiones en el calendario «Nota en Claro · Estudio». Si lo sustituyes, se borrarán todas, también las que hayas editado. ¿Sustituirlo?'` |
| `app/agentes/coordinador.py` | `Orquestador.atender`: si el resultado del agente trae `plan_propuesto` (leer con `getattr(r, 'plan_propuesto', None)`, porque los falsos de los tests no lo tienen) y hay puente: `plan_calendario.aplicar(..., confirmado=False)`. Calendario vacío → se crea sin preguntar y el texto es «He creado N sesiones…» como hoy. `existentes > 0` → `resultado['plan_pendiente'] = {'eventos', 'huecos', 'dias', 'existentes'}` y texto «Te propongo N sesiones: …» + `PREGUNTA_SUSTITUIR` con M. |
| `app/interfaz.py` | `ss.plan_pendiente` (en `iniciar_sesion`). Nueva `tarjeta_plan(recursos)` (junto a `tarjeta_borrador`): contenedor con borde, `PREGUNTA_SUSTITUIR` exacta, la lista propuesta y dos botones: «Sustituir mi plan» (primario → `plan_calendario.aplicar(..., confirmado=True, agente='interfaz')`) y «Cancelar» (→ `cancelar`, mensaje «No he cambiado tu calendario: tu plan anterior sigue igual.»). Pedir otro plan reemplaza la propuesta pendiente. |
| `eval/escenarios_acciones.py`, `eval/prueba_plan_real.py` | Leer `res.plan_propuesto` en lugar de `res.eventos`; `prueba_plan_real.py` aplica la propuesta con `plan_calendario.aplicar(..., confirmado=True)` e informa de `borrados` y `no_borrados`. |

### Tests de la fase 1A (Google simulado: `MagicMock` y servidores en memoria)

**Tests existentes que se adaptan** (aceptado por el equipo; ninguno se borra):

| Test | Por qué cambia |
|---|---|
| `test_mcp_calendar.py::test_herramientas_sin_borrado` | aparece `aplicar_plan_estudio`; comprueba las 4 herramientas y que la de borrar exige confirmación (renombrar a `test_herramientas_y_el_borrado_solo_con_confirmacion`). |
| `test_mcp_calendar.py::test_huecos_libres_mira_primary_y_el_calendario_de_estudio` | freebusy ya solo mira `primary` (renombrar a `..._mira_solo_el_calendario_principal`). |
| `test_puente_mcp.py::test_arranque_real_por_stdio_lista_las_nueve_herramientas` | pasan a ser diez. |
| `test_acciones.py::test_plan_de_estudio_completo_en_dos_vueltas`, `::test_varias_sesiones_en_el_mismo_hueco_van_una_detras_de_otra`, `::test_sesion_que_no_cabe_se_devuelve_al_modelo_con_el_espacio_que_queda` | el agente ya no llama a `crear_eventos_estudio`: se comprueba `r.plan_propuesto` y que no hay ninguna llamada de escritura. |

**Nuevos:**
- `test_mcp_calendar.py`: sin eventos previos crea sin confirmar; con eventos previos y sin confirmar no inserta ni borra y devuelve `existentes`; confirmado crea y luego borra **solo** con `calendarId='CAL'` (nunca `'primary'`) y `sendUpdates='none'`, incluidos eventos pasados; paginación (dos páginas); fallo al crear → deshace lo nuevo y no borra lo antiguo; 404 al borrar cuenta como borrado; un fallo no-404 al borrar se cuenta en `no_borrados`; un argumento extra `calendarId='primary'` no cambia el calendario.
- `test_plan_calendario.py` (nuevo): calendario vacío → creado sin pregunta; con eventos → pendiente con el texto exacto de `PREGUNTA_SUSTITUIR`; confirmar → traza con `borrados`, `calendario`, `calendario_id` y sin títulos ni fechas; `no_borrados > 0` → el mensaje lo dice; cancelar → no llama al puente; propuesta caducada → la para el verificador sin llamar al servidor.
- `test_puente_mcp.py`: `aplicar_plan_estudio` no sale en `herramientas()` ni pasa por `llamar()`; `aplicar_plan` confirmado pasa por verificador y servidor.
- `test_traza_permisos.py`: `aplicar_plan_estudio` es `CONFIRMAR` y no está en ninguna intención.
- `test_acciones.py`: el agente propone y no escribe.
- `test_coordinador.py`: plan sin eventos previos se crea; con eventos queda pendiente con la pregunta.
- `test_interfaz.py` (AppTest): tarjeta con la pregunta exacta; «Cancelar» no llama a `aplicar_plan` y lo dice; «Sustituir mi plan» llama con `confirmado=True` y lo dice.

### Prueba manual corta con Google real (fase 1A, la hace el equipo)
Antes: crear a mano un evento en el calendario **personal** («Prueba personal», mañana a las 17:00), editar a mano el título de una sesión de «Nota en Claro · Estudio» y apuntar cuántos eventos hay en ese calendario (ya quedaron 6 de la sesión 6).
1. `python -m app.app` → «Hazme un plan de estudio para esta semana» → sale «Ya tienes un plan con N sesiones en el calendario «Nota en Claro · Estudio». Si lo sustituyes, se borrarán todas, también las que hayas editado. ¿Sustituirlo?» con N = lo apuntado. **Cancelar** → en Google Calendar no cambia nada.
2. Pedirlo otra vez → **Sustituir mi plan** → en «Nota en Claro · Estudio» solo están las sesiones nuevas (la editada también desapareció); «Prueba personal» sigue en el calendario personal; no hubo que reautorizar (si sale un 403, anotarlo). Traza: paso `aplicar_plan_estudio` con `borrados = N`, la etiqueta y el id del calendario, sin títulos.
3. Alguna sesión nueva puede caer donde estaba una vieja (freebusy ya no mira el calendario de la app).

### Decisiones de la fase 1A (para `docs/decisiones.md`)
| Decisión | Por qué | Descartada |
|---|---|---|
| Borrar los **eventos** del calendario de la app por id, todos (también pasados y editados) | queda solo el plan nuevo; el id del calendario, sus colores y avisos y el estado guardado no cambian | borrar y recrear el calendario entero (`calendars.delete` + `insert`): cambia el id, pierde la configuración del estudiante y, si falla la creación, se queda sin calendario |
| Una herramienta `aplicar_plan_estudio` con permiso `CONFIRMAR` y `confirmado` comprobado en el servidor | mismo patrón ya probado que `enviar_borrador`; el modelo no la ve; el servidor no borra sin confirmación aunque cambie el número de eventos entre la pregunta y el clic | una herramienta genérica `borrar_eventos` (más superficie) o borrar desde la interfaz llamando a Google directamente (el proceso de Streamlit cargaría el token de Calendar) |
| Crear lo nuevo **y después** borrar lo viejo, con marcha atrás si falla la creación; `no_borrados > 0` se avisa | si Google falla a mitad, el estudiante conserva su plan anterior | borrar y luego crear: si falla la creación, se queda sin plan |
| El agente propone y Python escribe (orquestador si el calendario está vacío, botón si no) | el modelo no decide nada de lo que se borra | que el agente pregunte (otra vuelta del modelo) |
| freebusy solo de `primary` | las sesiones del plan viejo no cuentan como ocupado | consultar ambos y restar los eventos de la app |
| Traza con etiqueta e id del calendario | el id no es contenido del estudiante y demuestra que nunca se borró en `primary` | solo la etiqueta |

---

# FASE 1B · Reglas del plan, selector, tabla y `.env.example` (puntos 1.2 a 1.5)

Un commit por punto. Mismas comprobaciones al acabar.

### 1.2 Una sesión por asignatura al día y franja horaria
- **Franja por defecto:** entre semana **16:00-21:00**, fin de semana **10:00-20:00**, sin pausas (las horas de instituto no están en el calendario, así que con 8-22 el plan caía en horario lectivo). Constante `FRANJA_POR_DEFECTO = {'laborable': (16, 21), 'fin_de_semana': (10, 20)}` en `app/agentes/plan.py`. Dura solo la sesión del navegador (no se guarda en `estado/`).
- `app/mcp_servers/mcp_calendar.py`: `calcular_huecos` gana `inicio_finde=None, fin_finde=None` (si faltan, la misma franja que entre semana: los tests actuales no cambian). `huecos_libres` gana `hora_inicio`, `hora_fin`, `hora_inicio_finde`, `hora_fin_finde` opcionales (enteros); sin ellos, 8-22 como hoy.
- `app/agentes/acciones.py`: `ejecutar(..., franja=None)`. Si hay franja, el programa **añade** esas cuatro horas a la llamada `huecos_libres` del modelo (generalizar `CORREO_INYECTADO` a «argumentos inyectados») y se comprueban con `verificar(..., interno=True)`. `SISTEMA['plan_estudio']`: añadir «Como máximo una sesión de cada asignatura al día.» → registrar el cambio en `docs/prompts.md` y medirlo con `eval/escenarios_acciones.py a b c` (modelo real, Google simulado) antes y después, con cifras «medido».
- `app/agentes/puente_mcp.py`: `OCULTOS_AL_MODELO` añade las cuatro horas (el modelo no las ve ni las puede proponer).
- `app/agentes/verificador.py`: `INTERNAS['huecos_libres'] = {cuatro horas}` (enteros 6-23, inicio < fin). `verificar(..., franja=None)` y `_eventos`: (1) **siempre**: como máximo una sesión por asignatura y día (asignatura = título sin el prefijo `plan.PREFIJO_TITULO`, normalizada como `plan._norm`), mensaje «evento 3: ya hay una sesión de Física el miércoles 2 dic; como máximo una por asignatura al día»; (2) **si hay franja**: cada evento dentro de la de su día, mensaje «evento 2: 21:00-22:30 se sale de tu franja de estudio entre semana (16:00-21:00)». Los mensajes vuelven al modelo para que corrija, como ya pasa con las fechas pasadas. Sin `franja` no se comprueba el horario (compatibilidad con los tests y los `eval/`). `aplicar_plan_estudio` pasa la misma franja.
- `app/agentes/coordinador.py`: `atender(..., franja=None)`; solo para `plan_estudio` y solo si no es `None` se pasa `franja=` al agente (los `AccionesFalso` de los tests no aceptan ese argumento) y a `plan_pendiente`.
- `app/interfaz.py`: barra lateral, sección «Tu horario de estudio»: dos `st.slider` de rango (horas enteras 7-23), «Entre semana» (16, 21) y «Fin de semana» (10, 20), en `ss.franja`. Si el rango es de menos de 1 h, error y se usa la franja por defecto.

### 1.3 Selector visible de la fuente de notas
- `app/interfaz.py`: en la barra lateral, `st.radio('¿Con qué notas calculo?', ['Hoja de Google', 'Simulación a mano'], key='fuente_notas', horizontal=True)`. Por defecto «Hoja de Google» si `estado_google()['lista']`, si no «Simulación a mano». Debajo, una línea: «El plan de estudio y el informe usan siempre tu hoja de Google, porque actúan sobre tus datos reales. La simulación a mano sirve para probar escenarios.» Se pasa al orquestador como `fuente_notas='hoja' | 'formulario'`.
- `app/agentes/coordinador.py` `_nota(notas_manuales, fuente=None)`: `'hoja'` → lee la hoja aunque haya notas a mano guardadas; `'formulario'` sin notas guardadas → «Has elegido «Simulación a mano», pero aún no has guardado notas: rellena la tabla y pulsa «Usar estas notas».»; `None` → comportamiento de hoy. `ORIGEN_NOTAS` mantiene las frases actuales (los tests buscan «tu hoja de Google «Mis notas»» y «las notas introducidas a mano»). El plan y el informe no cambian.

### 1.4 Tabla a mano y media: coma decimal y sin «None»
- `app/tabla_notas.py`: `tabla_vacia()` con `''` en las columnas de texto (nada de `None`); «Nota» pasa a texto. `PATRON_NOTA` acepta coma **o punto** (0-10, hasta tres decimales, o vacío). Función `con_coma(valor) -> str` (normaliza «8.5» → «8,5»). `tabla_a_notas` trata `''` como vacío y convierte la nota con `nota_admision.a_decimal` → `float` (acepta también un `float`, como en los tests); `nota_media_bachillerato` se pasa tal cual (la calculadora ya entiende la coma).
- `app/interfaz.py`:
  - «Nota» como `st.column_config.TextColumn('Nota', validate=PATRON_NOTA, help='Con coma: 8,5', width=...)`.
  - La media pasa de `st.number_input` a `st.text_input('Nota media de Bachillerato (0-10, sin Religión)', key='media_notas')`, validada con `a_decimal` (0-10; si no vale, error y no se guarda).
  - **Mostrar siempre la coma:** al pulsar «Usar estas notas», guardar en `ss.tabla_notas` la tabla con las notas normalizadas con `con_coma`, marcar `ss.normalizar = True` y `st.rerun()`; al principio de `formulario_notas`, **antes** de crear los widgets, si `ss.normalizar`: borrar `ss['editor_notas']`, poner `ss['media_notas']` con coma y usar `ss.tabla_notas` como datos del editor.
  - Comprobar en el navegador (panel de vista previa) qué columnas mostraban «None» antes y que ya no lo hacen; anotarlo en `docs/decisiones.md`.

### 1.5 `.env.example` y nombres obligatorios
- `.env.example`: `ORIENTADOR_EMAIL=`, `NOMBRE_ESTUDIANTE=` y `NOMBRE_ORIENTADOR=` vacíos. Actualizar el límite (4) de la entrada «Cambio de diseño: los datos del orientador…» de `docs/decisiones.md`.
- `app/contacto.py`: `MENSAJE_FALTAN_NOMBRES = 'Faltan tu nombre o el de tu orientador, y sin ellos no creo el borrador (no firmo con un nombre inventado). Escríbelos en «Tus datos de contacto» de la página principal o en la pestaña «Datos» de tu hoja «Mis notas», y vuelve a pedírmelo.'`
- `app/agentes/acciones.py` `ejecutar`: para `correo_orientador`, después de la comprobación del correo (que va primero, como hoy), si falta `nombre_estudiante` o `nombre_orientador` en el contacto ya combinado (app → hoja → `.env`) → `ResultadoAcciones(error=MENSAJE_FALTAN_NOMBRES)` sin llamar al modelo ni a Gmail. Las ramas de `instrucciones_nombres` sin nombre dejan de usarse (eliminarlas).

### Tests de la fase 1B (Google simulado)

**Tests existentes que se adaptan** (aceptado por el equipo):

| Test | Por qué cambia |
|---|---|
| `test_interfaz.py::test_formulario_de_notas_esta_en_el_area_principal_y_con_cabeceras` | la media ya no es `number_input`: se busca como `text_input` en el área principal y en ninguno de la barra lateral. |
| `test_interfaz.py::test_nota_con_notas_a_mano_sin_google` | la media se escribe con `text_input(key='media_notas').set_value('8,5')`; sigue dando 11,524. |
| `test_interfaz.py::test_los_campos_de_contacto_estan_junto_a_la_tabla_de_notas` | compara el conjunto **exacto** de `text_input` del área principal; pasa a comprobar que los tres campos de contacto están en el área principal y ninguno en la barra lateral (también vale para la fase 2). |
| `test_acciones.py::test_sin_nombres_en_env_el_prompt_no_inventa_ninguno` | sin nombres ya no se llama al modelo: comprueba `MENSAJE_FALTAN_NOMBRES`, 0 llamadas al modelo y a Gmail. |
| Ayudante `AgenteAcciones(...)` de `test_acciones.py` (no es un test) | añade `nombre_estudiante='Luis Pérez'`, `nombre_orientador='Marta Gil'` por defecto, para que los tests de correo que no tratan de nombres sigan igual. |

**Nuevos:**
- `test_mcp_calendar.py`: franja de entre semana y de fin de semana en `calcular_huecos` y en `huecos_libres`.
- `test_verificador.py`: una por asignatura y día (misma asignatura otro día sí; dos asignaturas el mismo día sí); franja con mensaje; sin franja no se comprueba; horas internas de `huecos_libres` (el modelo no las puede poner; con `interno=True` se validan).
- `test_acciones.py`: la franja se inyecta en `huecos_libres` y no está en el esquema que ve el modelo; un rechazo por asignatura repetida vuelve al modelo y la segunda propuesta pasa; el prompt dice «una sesión de cada asignatura al día»; sin nombres no hay borrador (con correo válido).
- `test_coordinador.py`: fuente «hoja» ignora las notas a mano; fuente «formulario» sin notas avisa; la franja llega al agente solo en el plan.
- `test_interfaz.py`: franja por defecto (16-21 / 10-20) y cambiada llegan al orquestador; selector visible, con su línea explicativa, y respetado; tabla sin `None`; nota «8.5» → se guarda 8.5 y se muestra «8,5»; media «8.5» → «8,5»; `.env.example` con los tres valores vacíos.
- `test_tabla_notas.py` (nuevo) o dentro de `test_interfaz.py`: `PATRON_NOTA` acepta «8,5», «8.5», «10», «» y rechaza «11», «8,5555», «abc»; `con_coma`.

### Prueba manual corta con Google real (fase 1B)
1. En «Tu horario de estudio», dejar 16-21 / 10-20 → pedir un plan → todas las sesiones dentro de la franja y ninguna asignatura repetida el mismo día.
2. Cambiar «Entre semana» a 18-20 y repetir → las de lunes a viernes entre 18:00 y 20:00.
3. Selector en «Hoja de Google» → «calcula mi nota» dice «tu hoja de Google»; en «Simulación a mano» con la tabla rellenada (escribir «8.5» en una nota y en la media) → tras «Usar estas notas» se ve «8,5» y la respuesta dice «notas introducidas a mano»; las filas vacías no muestran «None».
4. Con «Tus datos de contacto» sin nombres (y la hoja sin ellos) → «escribe a mi orientador» responde con el aviso de que faltan los nombres y no aparece ningún borrador en Gmail.

### Decisiones de la fase 1B
| Decisión | Por qué | Descartada |
|---|---|---|
| Franja inyectada por Python en `huecos_libres` y comprobada otra vez en el verificador | el modelo ya recibe huecos dentro de la franja (menos rechazos) y la barandilla sigue en Python | solo comprobar en el verificador (más vueltas del modelo) |
| Franja 16-21 / 10-20, solo en la sesión del navegador | encaja con el horario de un estudiante de 2.º; decisión del equipo | guardarla en `estado/`; una sola franja para toda la semana |
| Selector solo para calculadora, panel y «¿Qué nota necesito?» | plan e informe actúan sobre los datos reales de Google | que el plan use las notas simuladas |
| Nota y media como texto (coma o punto, se muestra coma) | única forma en Streamlit 1.67 de garantizar la coma | `NumberColumn(format='localized')` (depende del idioma del navegador) |
| Sin nombres no hay borrador | no se firma con un nombre inventado | saludo y firma genéricos (comportamiento anterior) |

---

# FASE 2 · Panel de notas y diseño

Un commit por punto (2.6 → 2.9). Para el gráfico, cargar antes la skill `dataviz`.

### 2.6 Panel de notas con gráfico
- `app/panel_notas.py` (nuevo, sin Streamlit): `filas_grafico(datos) -> (filas, sin_nota)`; cada fila `{'asignatura', 'nota' (float), 'nota_texto' ('8,5' con `nota_admision.fmt`), 'fase', 'estado' ('aprobada' ≥ 5 / 'suspensa')}`; las asignaturas sin nota van aparte.
- `app/interfaz.py`: expander «Mis notas en gráfico». Fuente = la del selector 1.3: «Simulación a mano» → `ss.notas_manuales`; «Hoja de Google» → botón «Cargar mis notas de la hoja» (una llamada `puente.llamar('leer_notas')` desde Python, registrada en la traza; resultado en `ss.notas_hoja`; nunca se llama en cada recarga). Gráfico `st.altair_chart` de barras horizontales, eje 0-10 fijo, color por `estado`, línea en 5, tooltip con `nota_texto` (coma). Sin `st.dataframe` en el panel (los tests usan `at.dataframe[0]` para el editor y `[-1]` para la traza). Debajo, «Sin nota: …» y de qué fuente salen.

### 2.7 «¿Qué nota necesito?»
- `app/agentes/nota_necesaria.py` (nuevo, Python puro, sin modelo): `calcular(cfb, objetivo, a, b) -> ResultadoNecesaria` y `explicar(r) -> str`.
  - Supuesto (decidido): **la misma nota X** en todos los exámenes de la PAU, incluidas las dos materias que ponderan `a` y `b`. La respuesta lo dice en una frase: «Supongo que sacas la misma nota en todos los exámenes de la PAU, también en las dos materias que ponderan.»
  - Reutiliza `nota_admision.calcular` (mismas fórmulas, redondeo y mínimos: PAU ≥ 4, CAU ≥ 5, ponderan solo materias ≥ 5, máximo 14) construyendo esas materias con nota X, y busca por bisección la X mínima en milésimas (0-10) tal que la nota de admisión ≥ objetivo (la función no decrece con X).
  - `objetivo > 14` → «Imposible: la nota de admisión tiene un máximo de 14 puntos» con la cita `FUENTES['maximo']`. Con X = 10 no se llega → «Con esas ponderaciones el máximo que puedes sacar es …» (valor calculado). Si basta con X = 4 → lo dice (mínimo para que cuente la PAU). Si la X sale justo en 5 por el umbral de las ponderadas → lo explica.
  - Citas con `nota_admision._cita` para `pau`, `cau`, `formula`, `minimo_materia` y `maximo`.
- `app/interfaz.py`: expander «¿Qué nota necesito?» con un formulario: `st.text_input('Nota de corte que buscas')` (coma o punto, leída con `a_decimal`), dos `st.selectbox` de ponderación (0 / 0,1 / 0,2; por defecto 0,2 y 0,2), botón «Calcular». La media sale de la fuente elegida en el selector; si falta, lo dice y no calcula.
- Ejemplos para los tests (calculados a mano con las fórmulas del código): media 8, a = b = 0,2, objetivo 12 → **9,000**; objetivo 14,5 → imposible; media 8, a = b = 0, objetivo 10 → imposible, máximo **8,800**; media 9, a = b = 0,2, objetivo 6 → **4,000**; media 9, a = b = 0,2, objetivo 8,5 → **5,000** (por debajo de 5 no ponderan).

### 2.8 Cuenta atrás hasta la PAU
- `app/cuenta_atras.py` (nuevo, sin Streamlit): `estado_cuenta_atras(fecha, hoy) -> None | ('futuro', días) | ('hoy', 0) | ('pasado', días)`. «Hoy» = `datetime.now(ZoneInfo(comun.zona_horaria())).date()`, inyectable en los tests.
- `app/interfaz.py`: barra lateral «Tu PAU»: `st.date_input('Fecha de tu primer examen de la PAU', value=None, format='DD/MM/YYYY')`, solo para la sesión del navegador. Sin fecha no se muestra nada; futura → `st.metric('Días para tu primer examen', N)` arriba de la página; hoy → «¡Hoy es tu primer examen!»; pasada → `st.warning('Esa fecha ya ha pasado (hace N días): revisa la fecha de tu primer examen.')`. La fecha no sale de ningún documento ni del modelo.

### 2.9 Diseño de la interfaz (misma librería)
- `.streamlit/config.toml` (nuevo): solo `[theme]`, sobrio, **un color principal** y buen contraste (comprobar contraste ≥ 4,5:1 del texto sobre los fondos). `app/app.py` ya lanza Streamlit con `cwd=RAIZ`, así que lo recoge. Comprobar que `.gitignore` no lo excluye.
- `app/interfaz.py`: barra lateral ordenada en secciones con `st.subheader`/`st.divider` (Google · Tus notas y fuente · Tu horario de estudio · Tu PAU); cabecera con título, frase y la métrica de la cuenta atrás; área principal: «Mis notas» (tabla + gráfico), «¿Qué nota necesito?», «Tus datos de contacto», chat, tarjetas pendientes (correo y plan) con borde y la traza al final. `layout` sigue `centered` y **sin `st.tabs`** (sacaría `st.chat_input` de su sitio fijo abajo).
- **No cambiar** textos ni claves que usan los tests: «Introducir mis notas a mano», «Usar estas notas», «Olvidar mis notas», «Tus datos de contacto (para el correo a tu orientador)», «Guardar mis datos», «Tu nombre», «Nombre de tu orientador», «Correo de tu orientador», «Nota media de Bachillerato (0-10, sin Religión)» (clave `media_notas`), clave `editor_notas`, «Crear mi hoja de notas», «Borrador pendiente (aún NO enviado)», «Enviar al orientador», «Descartar», «Sustituir mi plan», «Cancelar», `PREGUNTA_SUSTITUIR`, «Traza de la sesión», el aviso «La parte de Google no está lista…» en la barra lateral y el caption «Tipo de petición: …». El editor debe seguir siendo el primer `dataframe` y la traza el último.

### Tests de la fase 2
No se adapta ningún test existente más (el de los campos de contacto ya se adaptó en 1B).

**Nuevos:** `tests/test_panel_notas.py` (filas, coma, aprobada/suspensa, sin nota); `tests/test_nota_necesaria.py` (los cinco ejemplos, la frase del supuesto, citas presentes y literales en `data/texto` como ya hace `test_nota_admision.py`, objetivo con coma y con punto); `tests/test_cuenta_atras.py` (sin fecha, futura, hoy, pasada); en `test_interfaz.py`: el gráfico aparece con notas a mano (buscar el elemento de Altair con `at.get(...)`; si el nombre no coincide, inspeccionar `at.main`), «Cargar mis notas de la hoja» llama una vez a `leer_notas`, «¿Qué nota necesito?» muestra 9,000 y el aviso de imposible, la cuenta atrás con fecha futura y pasada y nada sin fecha, y los textos y claves de la lista de 2.9 siguen ahí.

### Prueba manual corta con Google real (fase 2)
1. Selector en «Hoja de Google» → «Cargar mis notas de la hoja» → el gráfico muestra las asignaturas de la hoja, las de nota < 5 en otro color, tooltip con coma.
2. «¿Qué nota necesito?» con «12,5» y 0,2 / 0,2 → comprobar la cifra a mano y que sale la frase del supuesto; con «15» → imposible.
3. Fecha de dentro de 10 días → «10»; fecha de ayer → aviso; borrar la fecha → no aparece.
4. Tema: el texto se lee bien en todas las zonas (validación del diseño).
5. Recorrido completo para ver que nada se ha roto: una duda de normativa, «calcula mi nota», un plan (con la pregunta de sustituir) y un borrador al orientador enviado a una dirección de prueba propia.

### Decisiones de la fase 2
| Decisión | Por qué | Descartada |
|---|---|---|
| Gráfico con `st.altair_chart` | Altair ya viene con Streamlit (6.3.0, medido); permite eje 0-10 fijo, color y línea en 5 | `st.bar_chart` (sin línea de referencia ni dominio fijo); otra librería |
| «¿Qué nota necesito?» por bisección sobre `nota_admision.calcular`, misma nota en todos los exámenes | una sola implementación de las fórmulas del RD, con sus redondeos y umbrales | despejar la fórmula a mano (duplica reglas y falla en los umbrales 4 y 5) o que lo diga el modelo |
| Formulario propio, no por el chat | el número lo escribe el estudiante y Python lo lee; sin extracción con el modelo | nueva intención del coordinador |
| Cuenta atrás con `date_input`, solo en la sesión | la fecha la pone el estudiante | sacarla del corpus o del modelo; guardarla en `estado/` |
| Tema sobrio en `.streamlit/config.toml`, sin pestañas | cambia el aspecto sin tocar la lógica ni los tests | `st.tabs` (mueve el chat), CSS inyectado (frágil entre versiones) |

---

# Decisiones del equipo (28-11)

Respuestas a las dudas del primer borrador. Valen para todas las fases; no hay que volver a preguntarlas.

1. **Qué se borra:** todos los eventos del calendario de la app, también los pasados. En el calendario queda solo el plan nuevo.
2. **Orden:** crear primero y borrar después, con marcha atrás si falla la creación. Si queda algún evento viejo sin borrar (`no_borrados > 0`), el mensaje al estudiante lo dice claramente.
3. **Calendario de la app vacío:** se crea sin preguntar.
4. **Eventos editados a mano:** se borran igual, pero la pregunta lo avisa con este texto exacto (los tests lo buscan): «Ya tienes un plan con N sesiones en el calendario «Nota en Claro · Estudio». Si lo sustituyes, se borrarán todas, también las que hayas editado. ¿Sustituirlo?».
5. **Franja:** 16-21 entre semana y 10-20 el fin de semana, sin pausas. Dura solo la sesión del navegador (no se guarda en `estado/`).
6. **Selector de fuente:** solo afecta a la calculadora, al panel de notas y a «¿Qué nota necesito?». El plan de estudio y el informe siguen leyendo siempre la hoja, porque actúan sobre los datos reales del estudiante en Google; la simulación sirve para probar escenarios. La interfaz lo dice en una línea junto al selector.
7. **«None» y coma:** no se sabe en qué columnas salía «None»: el ejecutor lo comprueba en el navegador. La media de Bachillerato también va con coma (se aceptan los dos tests adaptados). En las notas se acepta también el punto («8.5»), se convierte y se muestra siempre la coma.
8. **`.env.example`:** se vacían `ORIENTADOR_EMAIL`, `NOMBRE_ESTUDIANTE` y `NOMBRE_ORIENTADOR`. Si faltan los nombres, la app no crea el borrador y pide rellenar «Tus datos de contacto»; nunca firma con un nombre inventado.
9. **«¿Qué nota necesito?»:** se mantiene el supuesto (la misma nota en todos los exámenes de la PAU, incluidas las dos que ponderan) y la respuesta lo dice explícitamente en una frase.
10. **Tests adaptados:** se aceptan tal como se describen en las tablas de cada fase. El total no baja de 219.
11. **Traza:** se guardan el id y la etiqueta del calendario. El id no es contenido del estudiante y demuestra que nunca se borró en `primary`.
12. **Diseño:** no hay identidad visual previa: tema sobrio, un color principal y buen contraste. Se valida en la prueba manual.
13. **Cuenta atrás:** la fecha dura solo la sesión del navegador.

**Consecuencia del punto 8 (añadida al plan):** como ahora faltar los nombres bloquea el borrador, en la fase 1B se adapta además `test_acciones.py::test_sin_nombres_en_env_el_prompt_no_inventa_ninguno` y el ayudante `AgenteAcciones` de ese fichero recibe nombres por defecto (ver la tabla de la fase 1B).

## Verificación global
- Al final de cada fase (1A, 1B, 2): `.\.venv\Scripts\python.exe -m pytest -q` en verde con un total ≥ 219 más los nuevos; la prueba manual con Google real de esa fase; `git status` sin `.env`, `credentials.json`, `token_*.json` ni `estado/`; entradas en `docs/decisiones.md` y, si cambió un prompt, en `docs/prompts.md`, con las cifras marcadas «medido» o «estimado».
