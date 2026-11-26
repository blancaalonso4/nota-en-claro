"""Datos de contacto del estudiante para el correo al orientador. Python puro, sin Streamlit ni Google.

Son datos de cada estudiante, no configuración: nombre del estudiante, nombre del orientador y correo del orientador.
Salen de tres sitios, por campos y en este orden de prioridad:
  1. los campos de la app (para quien no usa Google),
  2. la pestaña «Datos» de la hoja «Mis notas» de Drive,
  3. el `.env` (`NOMBRE_ESTUDIANTE`, `NOMBRE_ORIENTADOR`, `ORIENTADOR_EMAIL`), que solo es el valor por defecto de la demo.
El destinatario del correo lo escribe siempre el estudiante: el modelo no lo ve ni lo propone.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.agentes.verificador import correo_valido


@dataclass(frozen=True)
class Contacto:
    nombre_estudiante: str = ''
    nombre_orientador: str = ''
    correo_orientador: str = ''

    @staticmethod
    def de_dict(d: dict | None) -> 'Contacto':
        d = d or {}
        limpio = lambda k: str(d.get(k) or '').strip()
        return Contacto(limpio('nombre_estudiante'), limpio('nombre_orientador'), limpio('correo_orientador'))

    def con_respaldo(self, otro: 'Contacto | None') -> 'Contacto':
        """Cada campo vacío se rellena con el de `otro`; los que ya tienen valor no se tocan."""
        otro = otro or Contacto()
        return Contacto(self.nombre_estudiante or otro.nombre_estudiante, self.nombre_orientador or otro.nombre_orientador,
                        self.correo_orientador or otro.correo_orientador)

    @property
    def completo(self) -> bool:
        return bool(self.nombre_estudiante and self.nombre_orientador and correo_valido(self.correo_orientador))

    @property
    def correo_ok(self) -> bool:
        return correo_valido(self.correo_orientador)


def desde_env() -> Contacto:
    """Valor por defecto de la demo (`.env`). Un correo que no sea válido se ignora."""
    c = Contacto(os.environ.get('NOMBRE_ESTUDIANTE', '').strip(), os.environ.get('NOMBRE_ORIENTADOR', '').strip(),
                 os.environ.get('ORIENTADOR_EMAIL', '').strip())
    return c if c.correo_ok else Contacto(c.nombre_estudiante, c.nombre_orientador, '')


MENSAJE_FALTA_CORREO = ('Falta el correo de tu orientador, y sin él no creo el borrador. Escríbelo en la pestaña «Datos» de tu hoja '
                        '«Mis notas» (casilla amarilla «Correo de tu orientador») o en «Tus datos de contacto» de la página '
                        'principal, y vuelve a pedírmelo.')
