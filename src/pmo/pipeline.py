"""Orquesta el pipeline: CSV crudos → ETL → calidad → EVM → semáforo → SQLite y CSV para BI.

Uso:
    python -m pmo.pipeline
    python -m pmo.pipeline --fecha-referencia 2026-11-06
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from pmo import calidad, etl, evm, semaforo
from pmo.config import FECHA_REFERENCIA, RUTA_DB, RUTA_PROCESSED, RUTA_RAW


@dataclass
class Resultado:
    calidad: calidad.ResultadoCalidad
    indicadores: pd.DataFrame


def correr(raw: Path = RUTA_RAW, db: Path = RUTA_DB, salida: Path = RUTA_PROCESSED,
           referencia: date = FECHA_REFERENCIA) -> Resultado:
    tablas, formato = etl.leer_crudos(raw)
    resultado = calidad.evaluar(tablas["proyectos"], tablas["cortes_semanales"], referencia,
                                formato)
    indicadores = semaforo.evaluar(
        evm.calcular(resultado.proyectos_validos, resultado.cortes_validos),
        resultado.por_corte, tablas["hitos"], resultado.proyectos_validos["proyecto_id"],
        referencia)

    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conexion:
        etl.cargar(tablas, conexion, prefijo="stg_")
        etl.cargar({
            "proyectos": resultado.proyectos_validos,
            "cortes_semanales": resultado.cortes_validos,
            "hitos": tablas["hitos"],
            "riesgos": tablas["riesgos"],
            "errores_calidad": resultado.errores,
            "calidad_por_corte": resultado.por_corte,
            "indicadores": indicadores,
            "cuarentena_proyectos": resultado.cuarentena_proyectos.reset_index(names="fila"),
            "cuarentena_cortes": resultado.cuarentena_cortes.reset_index(names="fila"),
        }, conexion)

    salida.mkdir(parents=True, exist_ok=True)
    resultado.errores.to_csv(salida / "errores_calidad.csv", index=False)
    resultado.por_corte.to_csv(salida / "calidad_por_corte.csv", index=False)
    indicadores.to_csv(salida / "indicadores.csv", index=False)
    return Resultado(resultado, indicadores)


def resumen(salida: Resultado) -> str:
    resultado = salida.calidad
    errores = resultado.errores
    ultimo = salida.indicadores.groupby("proyecto_id").tail(1)
    columnas = ["proyecto_id", "fecha_corte", "spi", "cpi", "color", "motivo"]
    por_regla = errores.groupby(["regla", "severidad"]).size().rename("errores").reset_index()
    lineas = [
        f"Cortes válidos: {len(resultado.cortes_validos)} · "
        f"en cuarentena: {len(resultado.cuarentena_cortes)}",
        f"Proyectos en cuarentena: {sorted(set(resultado.cuarentena_proyectos['proyecto_id']))}",
        f"Errores: {len(errores)} "
        f"({(errores['severidad'] == calidad.BLOQUEANTE).sum()} bloqueantes)",
        "",
        por_regla.to_string(index=False),
        "",
        "Semáforo al último corte de cada proyecto:",
        ultimo[columnas].round({"spi": 2, "cpi": 2}).to_string(index=False),
    ]
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fecha-referencia", type=date.fromisoformat, default=FECHA_REFERENCIA)
    args = parser.parse_args()
    pd.set_option("display.width", 120)
    print(resumen(correr(referencia=args.fecha_referencia)))


if __name__ == "__main__":
    main()
