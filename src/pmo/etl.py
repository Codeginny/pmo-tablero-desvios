"""Paso 1 del pipeline: lee los CSV crudos, normaliza tipos y los carga en SQLite.

No corrige ni descarta nada: eso es trabajo del motor de calidad. Si un valor no
se puede convertir (una fecha "31/02" o un costo "12.000,50 €"), queda vacío y
se anota como problema de formato para que calidad.py lo informe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from pmo.config import RUTA_RAW

FECHAS = {
    "proyectos": ["fecha_inicio_plan", "fecha_fin_plan", "fecha_inicio_real", "fecha_fin_real"],
    "cortes_semanales": ["fecha_corte"],
    "hitos": ["fecha_plan", "fecha_real"],
    "riesgos": [],
}
NUMEROS = {
    "proyectos": ["presupuesto_bac"],
    "cortes_semanales": ["avance_plan_pct", "avance_real_pct", "costo_real_acum"],
    "hitos": [],
    "riesgos": ["probabilidad", "impacto"],
}
TABLAS = list(FECHAS)


def normalizar(df: pd.DataFrame, tabla: str) -> tuple[pd.DataFrame, list[dict]]:
    """Recorta espacios, convierte vacíos en nulos y tipa fechas y números."""
    df = df.apply(lambda col: col.str.strip()).replace("", None)
    problemas = []

    def convertir(columna: str, funcion) -> None:
        original = df[columna]
        convertido = funcion(original)
        fallidos = original.notna() & convertido.isna()
        for fila, valor in original[fallidos].items():
            problemas.append({
                "tabla": tabla,
                "fila": fila,
                "proyecto_id": df.loc[fila, "proyecto_id"],
                "campo": columna,
                "valor": valor,
            })
        df[columna] = convertido

    for columna in FECHAS[tabla]:
        convertir(columna, lambda s: pd.to_datetime(s, format="%Y-%m-%d", errors="coerce"))
    for columna in NUMEROS[tabla]:
        convertir(columna, lambda s: pd.to_numeric(s, errors="coerce"))
    return df, problemas


def leer_crudos(carpeta: Path = RUTA_RAW) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Devuelve las tablas tipadas y los valores que no se pudieron convertir.

    El índice de cada tabla es la posición de la fila en el CSV (0 = primera fila
    de datos), así los errores pueden señalar la fila exacta a corregir.
    """
    tablas, problemas = {}, []
    for tabla in TABLAS:
        crudo = pd.read_csv(carpeta / f"{tabla}.csv", dtype=str, keep_default_na=False)
        tablas[tabla], encontrados = normalizar(crudo, tabla)
        problemas += encontrados
    columnas = ["tabla", "fila", "proyecto_id", "campo", "valor"]
    return tablas, pd.DataFrame(problemas, columns=columnas)


def cargar(tablas: dict[str, pd.DataFrame], conexion: sqlite3.Connection,
           prefijo: str = "") -> None:
    for nombre, df in tablas.items():
        df.to_sql(f"{prefijo}{nombre}", conexion, if_exists="replace", index=False)
