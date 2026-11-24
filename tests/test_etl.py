import sqlite3

import pandas as pd
import pytest

from pmo import etl
from pmo.generar_datos import generar, guardar


@pytest.fixture
def carpeta_raw(tmp_path):
    guardar(generar(), tmp_path)
    return tmp_path / "data" / "raw"


def test_tipa_fechas_y_numeros(carpeta_raw):
    tablas, formato = etl.leer_crudos(carpeta_raw)
    cortes = tablas["cortes_semanales"]
    assert pd.api.types.is_datetime64_any_dtype(cortes["fecha_corte"])
    assert pd.api.types.is_float_dtype(cortes["costo_real_acum"])
    assert pd.api.types.is_datetime64_any_dtype(tablas["proyectos"]["fecha_fin_real"])
    assert formato.empty


def test_no_pierde_filas(carpeta_raw):
    tablas, _ = etl.leer_crudos(carpeta_raw)
    for nombre, df in tablas.items():
        assert len(df) == len(pd.read_csv(carpeta_raw / f"{nombre}.csv")), nombre


def test_vacios_y_espacios_quedan_nulos(carpeta_raw):
    ruta = carpeta_raw / "riesgos.csv"
    df = pd.read_csv(ruta, dtype=str)
    df.loc[0, "estado"] = "   "
    df.loc[1, "responsable"] = "  Elena Soto  "
    df.to_csv(ruta, index=False)
    riesgos = etl.leer_crudos(carpeta_raw)[0]["riesgos"]
    assert pd.isna(riesgos.loc[0, "estado"])
    assert riesgos.loc[1, "responsable"] == "Elena Soto"


def test_anota_los_valores_que_no_se_pueden_convertir(carpeta_raw):
    ruta = carpeta_raw / "cortes_semanales.csv"
    df = pd.read_csv(ruta, dtype=str)
    df.loc[4, "costo_real_acum"] = "12.000,50 €"
    df.loc[7, "fecha_corte"] = "31/02/2026"
    df.to_csv(ruta, index=False)

    tablas, formato = etl.leer_crudos(carpeta_raw)
    assert pd.isna(tablas["cortes_semanales"].loc[4, "costo_real_acum"])
    assert set(zip(formato["fila"], formato["campo"], formato["valor"], strict=True)) == {
        (4, "costo_real_acum", "12.000,50 €"),
        (7, "fecha_corte", "31/02/2026"),
    }


def test_carga_en_sqlite(carpeta_raw, tmp_path):
    tablas, _ = etl.leer_crudos(carpeta_raw)
    with sqlite3.connect(tmp_path / "prueba.sqlite") as conexion:
        etl.cargar(tablas, conexion, prefijo="stg_")
        filas = conexion.execute("select count(*) from stg_cortes_semanales").fetchone()[0]
    assert filas == len(tablas["cortes_semanales"])
