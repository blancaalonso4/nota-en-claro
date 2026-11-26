# Evaluación del coordinador (2026-11-26)

Modelo `qwen3:4b-instruct`, seed 42, temperature 0.0, num_predict 40, think False, salida restringida por esquema JSON. Windows-11-10.0.26200-SP0, CPU sin GPU. 30 peticiones (5 por intención, `data/eval/intenciones.json`).
Cifras **medidas**: aciertos (intención == etiqueta), tokens (Ollama, por llamada), segundos (reloj, por llamada).

**Aciertos: 30/30.** Tokens de entrada: media 189.2 (mín 181, máx 201); tokens de salida: media 20.6; segundos por llamada: media 3.83, mediana 3.50, máx 10.71.

| intención | aciertos |
|---|---|
| normativa | 5/5 |
| nota_admision | 5/5 |
| plan_estudio | 5/5 |
| informe | 5/5 |
| correo_orientador | 5/5 |
| fuera_de_ambito | 5/5 |
