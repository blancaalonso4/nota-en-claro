# Prueba real de los servidores MCP contra Google

Fecha: 2026-11-26 19:06 · Windows-11-10.0.26200-SP0 · **medido** (segundos: reloj; reintentos: informados por el servidor).

| Paso | Herramienta | Resultado | Segundos | Reintentos | Detalle |
|---|---|---|---|---|---|
| 1. Crear hoja «Mis notas» | `crear_plantilla_notas` | OK | 2.25 | 0 | creada=True url=https://docs.google.com/spreadsheets/d/<id> |
| 2. Leer la hoja | `leer_notas` | OK | 0.27 | 0 | 0 materias, media=None, avisos=0 |
| 3. Guardar informe | `guardar_informe` | OK | 3.23 | 0 | url=https://docs.google.com/document/d/<id> |
| 4. Huecos libres (4 días) | `huecos_libres` | OK | 11.36 | 0 | 4 huecos |
| 5. Crear un evento de estudio | `crear_eventos_estudio` | OK | 0.59 | 0 | 1 creado(s) |
| 6. Listar eventos de estudio | `listar_eventos` | OK | 0.32 | 0 | 1 evento(s) |
| 7. Leer correos del orientador | `leer_correos_orientador` | OK | 1.3 | 0 | 1 correo(s) leídos |
| 8. Crear borrador | `crear_borrador` | OK | 0.35 | 0 | destinatario=blancalonsooo@gmail.com |
| 9. Enviar el borrador (vía confirmada) | `enviar_borrador` | OK | 0.66 | 0 | enviado=True |
