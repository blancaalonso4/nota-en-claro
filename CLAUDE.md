# Nota en Claro · reglas del proyecto

Web app para estudiantes de 2.º de Bachillerato en Madrid que preparan la PAU. RAG sobre normativa (viene del Caso III), modelo local con Ollama.

## Reglas
1. **Todo en castellano**: código comentado, docs, commits, mensajes de la app.
2. **Windows y `py -3.14`**. Entorno virtual en `.venv` (`py -3.14 -m venv .venv`).
3. **Nunca subir a git claves, credenciales ni `.env`** (tokens de Google incluidos). Comprobar `git status` antes de cada commit.
4. **Distinguir siempre cifras medidas de estimaciones**: toda cifra lleva la etiqueta «medido» o «estimado» y, si es medida, cómo se midió.
5. **Cada decisión técnica se registra en `docs/decisiones.md`**: fecha, decisión, por qué, alternativa descartada.
6. **Los prompts relevantes que da el equipo se guardan en `docs/prompts.md`**.
7. **Reproducibilidad**: semilla 42 en random, numpy y torch; toda llamada a Ollama lleva `seed`, `temperature 0`, `num_predict` y `think` explícitos.
8. **Sin frameworks de agentes**: bucle propio en Python sobre la API de Ollama.

## Arquitectura prevista
- Coordinador (`qwen3:4b-instruct`) que enruta a:
  - agente de normativa (RAG, `qwen3:8b` sin razonamiento),
  - agente de acciones (MCP a Google Drive, Calendar y Gmail),
  - verificador de citas en Python sin modelo (`app/rag/citas.py`).
- Interfaz en Streamlit (`app/web/`).
- Límite de tokens en cada llamada (`num_predict`); razonamiento desactivado salvo donde haga falta.

## Estructura
`app/rag/` RAG · `app/agentes/` · `app/mcp_servers/` · `app/web/` · `data/` textos, manifiesto y preguntas (los PDF no se copian) · `eval/` · `docs/`.
`caso3_referencia/` es solo consulta y no se sube a git.
