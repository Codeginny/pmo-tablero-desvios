from datetime import date

import pandas as pd
import pytest

from pmo import semaforo
from pmo.generar_datos import generar, guardar
from pmo.pipeline import correr
from pmo.semaforo import AMBAR, GRIS, ROJO, VERDE

UMBRALES = semaforo.cargar_umbrales()


@pytest.mark.parametrize("valor, color", [
    (1.10, VERDE), (0.95, VERDE), (0.9499, AMBAR), (0.85, AMBAR), (0.8499, ROJO), (0.0, ROJO),
])
def test_umbral_exacto_cuenta_como_el_color_mejor(valor, color):
    assert semaforo.color_minimo(valor, UMBRALES["spi"]) == color


@pytest.mark.parametrize("valor, color", [(-10, VERDE), (5, VERDE), (5.1, AMBAR), (15, AMBAR),
                                          (15.1, ROJO)])
def test_retraso_de_fin(valor, color):
    assert semaforo.color_maximo(valor, UMBRALES["retraso_fin_pct_duracion"]) == color


def test_sin_dato_no_aporta_color():
    assert semaforo.color_minimo(float("nan"), UMBRALES["cpi"]) is None


def fila(spi=1.0, cpi=1.0, retraso_pct=0.0, retraso_dias=0, hito=0):
    return pd.Series({"spi": spi, "cpi": cpi, "retraso_fin_pct": retraso_pct,
                      "retraso_fin_dias": retraso_dias, "dias_hito_vencido": hito})


def test_gana_el_peor_color_y_el_motivo_empieza_por_el():
    color, motivo = semaforo.colorear(fila(spi=0.90, cpi=0.80), UMBRALES)
    assert color == ROJO
    assert motivo == "CPI 0,80 < 0,85; SPI 0,90 < 0,95"


def test_verde_dice_que_esta_dentro_de_tolerancia():
    assert semaforo.colorear(fila(), UMBRALES) == (VERDE, "Dentro de tolerancia")


def test_hito_vencido():
    assert semaforo.colorear(fila(hito=10), UMBRALES) == (AMBAR, "Hito vencido hace 10 días")


def test_sin_ningun_indicador_queda_gris():
    vacia = fila(spi=float("nan"), cpi=float("nan"), retraso_pct=float("nan"))
    vacia["dias_hito_vencido"] = float("nan")
    assert semaforo.colorear(vacia, UMBRALES)[0] == GRIS


def test_dias_hito_vencido():
    cortes = pd.DataFrame({"proyecto_id": ["A", "A", "A"],
                           "fecha_corte": pd.to_datetime(["2026-03-06", "2026-03-20",
                                                          "2026-04-03"])})
    hitos = pd.DataFrame({"proyecto_id": ["A", "A"],
                          "fecha_plan": pd.to_datetime(["2026-03-10", "2026-03-30"]),
                          "fecha_real": pd.to_datetime(["2026-03-27", None])})
    # 06/03: nada vencido · 20/03: el primero lleva 10 días · 03/04: cumplido, el segundo lleva 4.
    assert semaforo.dias_hito_vencido(cortes, hitos).tolist() == [0, 10, 4]


# --- Contra el dataset del caso ----------------------------------------------

@pytest.fixture(scope="module")
def indicadores(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("caso")
    guardar(generar(), raiz)
    salida = correr(raw=raiz / "data" / "raw", db=raiz / "pmo.sqlite", salida=raiz / "processed")
    return salida.indicadores


def colores(indicadores, proyecto):
    return indicadores[indicadores["proyecto_id"] == proyecto].set_index("fecha_corte")["color"]


@pytest.mark.parametrize("proyecto, color", [
    ("P01", VERDE), ("P02", ROJO), ("P03", ROJO), ("P04", ROJO), ("P05", VERDE),
    ("P06", VERDE), ("P07", ROJO), ("P08", GRIS), ("P09", VERDE), ("P10", ROJO),
    ("P11", AMBAR), ("P12", ROJO),
])
def test_color_al_ultimo_corte(indicadores, proyecto, color):
    assert colores(indicadores, proyecto).iloc[-1] == color


def test_p08_gris_en_los_dos_ultimos_cortes(indicadores):
    assert colores(indicadores, "P08").tail(3).tolist() == [VERDE, GRIS, GRIS]


def test_p07_pasa_de_verde_a_ambar_y_a_rojo(indicadores):
    p07 = colores(indicadores, "P07")
    p07 = p07[p07.index >= pd.Timestamp("2026-08-07")]  # después del error de carga de julio
    cambios = p07[p07 != p07.shift()].tolist()
    assert cambios == [VERDE, AMBAR, ROJO]


def test_p05_termina_verde_tras_recuperarse(indicadores):
    p05 = colores(indicadores, "P05")
    assert p05.loc[pd.Timestamp("2026-07-03")] == ROJO
    assert p05[p05.index >= pd.Timestamp("2026-09-11")].eq(VERDE).all()


def test_p11_ambar_por_el_hito(indicadores):
    ultimo = indicadores[indicadores["proyecto_id"] == "P11"].iloc[-1]
    assert ultimo["motivo"] == "Hito vencido hace 21 días"


def test_no_incluye_cortes_futuros_ni_proyectos_fuera_de_cartera(indicadores):
    assert indicadores["fecha_corte"].max() <= pd.Timestamp(date(2026, 11, 13))
    assert not {"P13", "P15"} & set(indicadores["proyecto_id"])
