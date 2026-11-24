"""Rutas y fecha de referencia compartidas por todos los pasos del pipeline."""

from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RUTA_RAW = RAIZ / "data" / "raw"
RUTA_CONTROL = RAIZ / "data" / "control"
RUTA_PROCESSED = RAIZ / "data" / "processed"
RUTA_DB = RAIZ / "data" / "pmo.sqlite"
RUTA_UMBRALES = RAIZ / "umbrales.yaml"

# "Hoy" para el caso simulado: el viernes del último corte. Fijarla hace que el
# repo dé siempre los mismos resultados, sin importar el día en que se corra.
FECHA_REFERENCIA = date(2026, 11, 13)
