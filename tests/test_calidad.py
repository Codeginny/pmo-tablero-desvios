from datetime import date

import pandas as pd
import pytest

from pmo import calidad
from pmo.generar_datos import generar, guardar
from pmo.pipeline import correr

REFERENCIA = date(2026, 3, 27)


@pytest.fixture
def proyectos():
    return pd.DataFrame({
        "proyecto_id": ["A", "B"],
        "nombre": ["Proyecto A", "Proyecto B"],
        "estado": ["En ejecución", "En ejecución"],
        "fecha_inicio_plan": pd.to_datetime(["2026-03-02", "2026-03-02"]),
        "fecha_fin_plan": pd.to_datetime(["2026-06-26", "2026-08-28"]),
        "fecha_inicio_real": pd.to_datetime(["2026-03-02", "2026-03-02"]),
        "presupuesto_bac": [50_000.0, 80_000.0],
    })


@pytest.fixture
def cortes():
    fechas = pd.to_datetime(["2026-03-06", "2026-03-13", "2026-03-20", "2026-03-27"])
    return pd.DataFrame({
        "proyecto_id": ["A"] * 4 + ["B"] * 4,
        "fecha_corte": list(fechas) * 2,
        "avance_plan_pct": [5.0, 10.0, 15.0, 20.0, 3.0, 6.0, 9.0, 12.0],
        "avance_real_pct": [5.0, 9.0, 14.0, 18.0, 3.0, 6.0, 9.0, 12.0],
        "costo_real_acum": [2500.0, 4600.0, 7000.0, 9500.0, 2400.0, 4800.0, 7200.0, 9600.0],
    })


def reglas(resultado):
    return sorted(resultado.errores["regla"])


def test_datos_limpios_no_dan_errores(proyectos, cortes):
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert r.errores.empty
    assert len(r.cortes_validos) == 8
    assert (r.por_corte["indice_calidad"] == 100).all()
    assert not r.por_corte["bloqueado"].any()


def test_dq01_campo_vacio(proyectos, cortes):
    cortes.loc[2, "costo_real_acum"] = None
    assert reglas(calidad.evaluar(proyectos, cortes, REFERENCIA)) == ["DQ01"]


def test_dq01_muestra_el_valor_original_si_tenia_mal_formato(proyectos, cortes):
    cortes.loc[2, "costo_real_acum"] = None
    formato = pd.DataFrame([{"tabla": "cortes_semanales", "fila": 2, "proyecto_id": "A",
                             "campo": "costo_real_acum", "valor": "7.000 €"}])
    errores = calidad.evaluar(proyectos, cortes, REFERENCIA, formato).errores
    assert errores.loc[0, "valor"] == "7.000 €"


def test_dq02_fechas_invertidas(proyectos, cortes):
    proyectos.loc[1, "fecha_fin_plan"] = pd.Timestamp("2025-08-28")
    assert reglas(calidad.evaluar(proyectos, cortes, REFERENCIA)) == ["DQ02"]


def test_dq03_avance_mayor_a_100(proyectos, cortes):
    cortes.loc[1, "avance_real_pct"] = 109.0
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    # El corte siguiente (14 %) no se informa como "avance que baja": se compara con el 5 %.
    assert reglas(r) == ["DQ03"]


def test_dq04_avance_que_baja_es_advertencia(proyectos, cortes):
    cortes.loc[2, "avance_real_pct"] = 8.0
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert reglas(r) == ["DQ04"]
    assert len(r.cortes_validos) == 8  # una advertencia no manda el corte a cuarentena


def test_dq05_costo_que_baja_bloquea_el_corte(proyectos, cortes):
    cortes.loc[6, "costo_real_acum"] = 4000.0
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert reglas(r) == ["DQ05"]
    assert r.cuarentena_cortes.index.tolist() == [6]


def test_dq06_costo_negativo(proyectos, cortes):
    cortes.loc[0, "costo_real_acum"] = -2500.0
    assert reglas(calidad.evaluar(proyectos, cortes, REFERENCIA)) == ["DQ06"]


def test_dq07_proyecto_duplicado_bloquea_todos_sus_cortes(proyectos, cortes):
    proyectos = pd.concat([proyectos, proyectos.iloc[[0]]], ignore_index=True)
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert reglas(r) == ["DQ07", "DQ07"]
    assert set(r.cuarentena_cortes["proyecto_id"]) == {"A"}
    assert r.por_corte.loc[r.por_corte["proyecto_id"] == "A", "bloqueado"].all()


def test_dq07_corte_duplicado(proyectos, cortes):
    cortes = pd.concat([cortes, cortes.iloc[[5]]], ignore_index=True)
    assert reglas(calidad.evaluar(proyectos, cortes, REFERENCIA)) == ["DQ07", "DQ07"]


def test_dq08_proyecto_inexistente(proyectos, cortes):
    cortes.loc[7, "proyecto_id"] = "Z"
    assert "DQ08" in reglas(calidad.evaluar(proyectos, cortes, REFERENCIA))


def test_dq09_sin_corte_reciente(proyectos, cortes):
    cortes = cortes.drop(index=7)
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert reglas(r) == ["DQ09"]
    assert pd.isna(r.errores.loc[0, "fila"])
    assert r.errores.loc[0, "valor"] == "2026-03-20"


def test_dq09_ignora_proyectos_cerrados(proyectos, cortes):
    proyectos.loc[1, "estado"] = "Cerrado"
    cortes = cortes.drop(index=7)
    assert calidad.evaluar(proyectos, cortes, REFERENCIA).errores.empty


def test_dq10_fecha_futura(proyectos, cortes):
    cortes.loc[3, "fecha_corte"] = pd.Timestamp("2026-04-03")
    assert "DQ10" in reglas(calidad.evaluar(proyectos, cortes, REFERENCIA))


def test_dq11_avance_antes_del_inicio_real(proyectos, cortes):
    proyectos.loc[0, "fecha_inicio_real"] = pd.Timestamp("2026-03-10")
    assert reglas(calidad.evaluar(proyectos, cortes, REFERENCIA)) == ["DQ11"]


def test_dq12_marca_desde_el_tercer_corte_con_costo_y_sin_avance(proyectos, cortes):
    cortes.loc[4:6, "avance_real_pct"] = 0.0
    r = calidad.evaluar(proyectos, cortes, REFERENCIA)
    assert reglas(r) == ["DQ12"]
    assert r.errores.loc[0, "fecha_corte"] == pd.Timestamp("2026-03-20")


def test_indice_de_calidad(proyectos, cortes):
    cortes.loc[1, "avance_real_pct"] = 109.0  # bloqueante
    cortes.loc[6, "avance_real_pct"] = 5.0    # advertencia (baja respecto de 6 %)
    por_corte = calidad.evaluar(proyectos, cortes, REFERENCIA).por_corte.set_index(
        ["proyecto_id", "fecha_corte"])
    assert por_corte.loc[("A", pd.Timestamp("2026-03-13")), "indice_calidad"] == 90
    assert por_corte.loc[("B", pd.Timestamp("2026-03-20")), "indice_calidad"] == 97
    assert por_corte["bloqueado"].sum() == 1


# --- Contra el dataset del caso ----------------------------------------------

@pytest.fixture(scope="module")
def resultado_del_caso(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("caso")
    tablas = generar()
    guardar(tablas, raiz)
    resultado = correr(raw=raiz / "data" / "raw", db=raiz / "pmo.sqlite",
                       salida=raiz / "processed")
    return resultado.calidad, tablas["errores_sembrados"]


def test_encuentra_todos_los_errores_sembrados_y_ninguno_mas(resultado_del_caso):
    resultado, sembrados = resultado_del_caso
    def claves(df):
        fechas = pd.to_datetime(df["fecha_corte"]).dt.strftime("%Y-%m-%d").fillna("-")
        return sorted(zip(df["regla"], df["proyecto_id"], fechas, strict=True))

    # DQ07 marca las dos copias de P13; el registro de sembrados lo anota una vez.
    encontrados = resultado.errores.drop_duplicates(["regla", "proyecto_id", "fecha_corte"])
    assert claves(encontrados) == claves(sembrados)


def test_cuarentena_del_caso(resultado_del_caso):
    resultado, _ = resultado_del_caso
    gris = resultado.por_corte[resultado.por_corte["bloqueado"]]
    p08 = gris[gris["proyecto_id"] == "P08"]["fecha_corte"].dt.date.tolist()
    assert p08 == [date(2026, 11, 6), date(2026, 11, 13)]
    assert set(resultado.cuarentena_proyectos["proyecto_id"]) == {"P13"}
    assert "P13" not in set(resultado.proyectos_validos["proyecto_id"])
    # La advertencia de P07 no lo saca del cálculo.
    p07 = resultado.cortes_validos[resultado.cortes_validos["proyecto_id"] == "P07"]
    assert pd.Timestamp("2026-07-31") in set(p07["fecha_corte"])
