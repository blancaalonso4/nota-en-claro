"""Tabla de notas a mano: columnas del editor y paso al diccionario que entiende la calculadora (sin Streamlit, para poder probarla)."""
import pandas as pd

FILAS_NOTAS = 8
FASES = ['acceso', 'admisión']
PONDERACIONES = ['0', '0,1', '0,2']


def tabla_vacia() -> pd.DataFrame:
    """Tabla inicial del editor: FILAS_NOTAS filas en blanco con el tipo de cada columna."""
    return pd.DataFrame({'Asignatura': pd.Series([None] * FILAS_NOTAS, dtype='object'),
                         'Nota': pd.Series([None] * FILAS_NOTAS, dtype='float64'),
                         'Fase': pd.Series([None] * FILAS_NOTAS, dtype='object'),
                         'Ponderación': pd.Series([None] * FILAS_NOTAS, dtype='object'),
                         'Segunda lengua': pd.Series([False] * FILAS_NOTAS, dtype='bool')})


def tabla_a_notas(tabla: pd.DataFrame, media) -> dict:
    """Tabla del editor + media -> el diccionario que entiende la calculadora (se ignoran las filas sin asignatura)."""
    def vacio(v):
        return v is None or bool(pd.isna(v))
    materias = []
    for _, f in tabla.iterrows():
        nombre = '' if vacio(f['Asignatura']) else str(f['Asignatura']).strip()
        if not nombre:
            continue
        materias.append({'asignatura': nombre, 'nota': None if vacio(f['Nota']) else float(f['Nota']),
                         'fase': '' if vacio(f['Fase']) else f['Fase'],
                         'ponderacion': '' if vacio(f['Ponderación']) else f['Ponderación'],
                         'segunda_lengua': 'sí' if (not vacio(f['Segunda lengua']) and bool(f['Segunda lengua'])) else ''})
    return {'nota_media_bachillerato': media, 'materias': materias}
