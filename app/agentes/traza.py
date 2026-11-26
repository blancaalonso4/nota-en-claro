"""Traza de la sesión: una línea JSON por paso en logs/sesion_<fecha>_<id>.jsonl.

Cada paso lleva la herramienta, su permiso, los tokens de entrada y salida de esa llamada al modelo (los reporta
Ollama), los segundos (reloj) y si falló. Nunca se guarda el contenido de correos, notas ni borradores: solo
nombres de argumentos y longitudes (ver `resumen_argumentos`).
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DIR_LOGS = RAIZ / 'logs'


def resumen_argumentos(args: dict | None) -> dict:
    """Nombres de los argumentos y longitud de cada valor; sin el contenido (puede ser un correo o una nota)."""
    if not isinstance(args, dict):
        return {}
    return {k: (len(v) if isinstance(v, (str, list, dict)) else type(v).__name__) for k, v in args.items()}


class Traza:
    def __init__(self, carpeta: Path | None = None, sesion: str | None = None):
        self.carpeta = Path(carpeta) if carpeta else DIR_LOGS
        self.sesion = sesion or f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}"
        self.archivo = self.carpeta / f'sesion_{self.sesion}.jsonl'
        self.pasos: list[dict] = []
        self.peticion = ''
        self._n = 0

    def nueva_peticion(self, texto: str) -> None:
        """Marca el inicio de una petición del estudiante (se guarda recortada a 200 caracteres)."""
        self.peticion = texto.strip()[:200]

    def registrar(self, tipo: str, agente: str, *, herramienta: str | None = None, permiso: str | None = None,
                  tokens_entrada: int = 0, tokens_salida: int = 0, segundos: float = 0.0, fallo: bool = False,
                  error: str = '', reintento: bool = False, **extra) -> dict:
        """Añade un paso. `tipo`: 'modelo', 'herramienta' o 'verificador'."""
        self._n += 1
        paso = {'ts': datetime.now().isoformat(timespec='seconds'), 'sesion': self.sesion, 'peticion': self.peticion,
                'paso': self._n, 'tipo': tipo, 'agente': agente, 'herramienta': herramienta, 'permiso': permiso,
                'tokens_entrada': int(tokens_entrada), 'tokens_salida': int(tokens_salida),
                'segundos': round(float(segundos), 2), 'fallo': bool(fallo), 'error': error[:300],
                'reintento': bool(reintento), **extra}
        self.pasos.append(paso)
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            with self.archivo.open('a', encoding='utf-8') as f:
                f.write(json.dumps(paso, ensure_ascii=False) + '\n')
        except OSError:
            pass   # la traza nunca debe tumbar la app; el paso sigue en memoria para el panel
        return paso

    @contextmanager
    def paso(self, tipo: str, agente: str, *, herramienta: str | None = None, permiso: str | None = None, **extra):
        """Mide los segundos de un bloque. Cede un dict en el que el bloque puede dejar tokens_entrada, tokens_salida,
        reintento u otros campos. Si el bloque lanza una excepción, el paso queda como fallo y se vuelve a lanzar."""
        datos: dict = {}
        t0 = time.perf_counter()
        try:
            yield datos
        except Exception as e:
            self.registrar(tipo, agente, herramienta=herramienta, permiso=permiso, fallo=True,
                           error=f'{type(e).__name__}: {e}',
                           **{**extra, **datos, 'segundos': time.perf_counter() - t0})
            raise
        self.registrar(tipo, agente, herramienta=herramienta, permiso=permiso,
                       **{**extra, 'segundos': time.perf_counter() - t0, **datos})

    def totales(self) -> dict:
        m = [p for p in self.pasos if p['tipo'] == 'modelo']
        return {'pasos': len(self.pasos), 'llamadas_modelo': len(m),
                'tokens_entrada': sum(p['tokens_entrada'] for p in m),
                'tokens_salida': sum(p['tokens_salida'] for p in m),
                'segundos': round(sum(p['segundos'] for p in self.pasos), 2),
                'fallos': sum(p['fallo'] for p in self.pasos)}
