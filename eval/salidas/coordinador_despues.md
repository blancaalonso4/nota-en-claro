# Evaluación del coordinador (2026-11-26) · despues

Modelo `qwen3:4b-instruct`, seed 42, temperature 0.0, num_predict 40, think False, salida restringida por esquema JSON. Windows-11-10.0.26200-SP0, CPU sin GPU.
Cifras **medidas**: aciertos (intención == etiqueta), tokens (Ollama, por llamada), segundos (reloj, por llamada).

- **Conjunto principal** (`data/eval/intenciones.json`, 5 por intención): **30/30**.
- **Conjunto de control** (`data/eval/intenciones_control.json`, 10 peticiones nuevas escritas como un estudiante): **9/10**.
- Tokens de entrada: media 230.6 (mín 223, máx 243); tokens de salida: media 20.5; segundos por llamada: media 2.79, mediana 2.73, máx 6.53.

| intención (principal) | aciertos |
|---|---|
| normativa | 5/5 |
| nota_admision | 5/5 |
| plan_estudio | 5/5 |
| informe | 5/5 |
| correo_orientador | 5/5 |
| fuera_de_ambito | 5/5 |

## Conjunto de control, petición a petición

| petición | esperada | obtenida |
|---|---|---|
| ¿Cuántas plazas hay en Medicina en la UCM? | normativa | normativa |
| cual es la nota de corte de enfermeria? | normativa | nota_admision ✗ |
| cuando salen las notas de la pau | normativa | normativa |
| q pasa si suspendo la pau en junio | normativa | normativa |
| cuanto me sale de nota si tengo un 9 de media y un 8 en la pau | nota_admision | nota_admision |
| ayudame con un plan pa estudiar mates y fisica esta semana | plan_estudio | plan_estudio |
| guarda un informe con mis notas pls | informe | informe |
| escribele a mi orientador que quiero quedar el jueves | correo_orientador | correo_orientador |
| dime una receta de tortilla de patatas | fuera_de_ambito | fuera_de_ambito |
| quien es el mejor jugador de baloncesto | fuera_de_ambito | fuera_de_ambito |

Confusiones: normativa→nota_admision ×1
