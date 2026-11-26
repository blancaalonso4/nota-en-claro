"""Mensajes claros para los fallos de Ollama. Distingue lo que el estudiante puede hacer en cada caso:

- la respuesta del modelo se cortó (la llamada a una herramienta no cabió en `num_predict` y Ollama devuelve un 500 con
  «invalid tool call arguments ... unexpected end of JSON input»): reformular o pedir algo más corto;
- no se puede conectar con Ollama (cerrado o sin arrancar): abrirlo;
- modelo no descargado (404): `ollama pull`;
- cualquier otro error: se dice el tipo, sin inventar la causa.
"""
from __future__ import annotations

import httpx
import ollama

CORTADA = 'cortada'
SIN_CONEXION = 'sin_conexion'
SIN_MODELO = 'sin_modelo'
INTERNO = 'interno'
OTRO = 'otro'

_MARCAS_CORTE = ('unexpected end of json', 'invalid tool call arguments')


def clasificar(e: BaseException) -> str:
    if isinstance(e, ollama.ResponseError):
        texto = str(e.error).lower()
        if any(m in texto for m in _MARCAS_CORTE):
            return CORTADA
        if e.status_code == 404:
            return SIN_MODELO
        if e.status_code >= 500:
            return INTERNO
        return OTRO
    if isinstance(e, (ConnectionError, ollama.RequestError, httpx.TransportError)):
        return SIN_CONEXION
    return OTRO


def mensaje(e: BaseException, modelo: str = 'qwen3:4b-instruct') -> str:
    tipo = clasificar(e)
    if tipo == CORTADA:
        return ('La respuesta del modelo se cortó antes de terminar (se agotó el límite de tokens de la llamada). '
                'Ollama sí está funcionando: vuelve a intentarlo o pídelo de forma más breve.')
    if tipo == SIN_CONEXION:
        return 'No puedo conectar con Ollama. Comprueba que está abierto (o ejecuta `ollama serve`) y vuelve a intentarlo.'
    if tipo == SIN_MODELO:
        return f'Ollama responde, pero el modelo {modelo} no está descargado. Ejecuta: ollama pull {modelo}'
    if tipo == INTERNO:
        return f'Ollama ha fallado por dentro (error {e.status_code}). Vuelve a intentarlo; si se repite, reinícialo.'
    return f'El modelo local ha dado un error inesperado ({type(e).__name__}). Mira la traza de la sesión para el detalle.'
