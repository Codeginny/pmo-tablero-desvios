from datetime import date

import pandas as pd
import pytest

from pmo.generar_datos import ULTIMO_CORTE, generar, guardar


@pytest.fixture(scope="module")
def tablas():
    return generar()


@pytest.fixture(scope="module")
def indices(tablas):
    """SPI y CPI del último corte válido de cada proyecto (cálculo rápido sólo para el test)."""
    proyectos = tablas["proyectos"].drop_duplicates("proyecto_id").set_index("proyecto_id")
    c = tablas["cortes_semanales"]
    c = c[c["proyecto_id"].isin(proyectos.index) & (c["fecha_corte"] <= ULTIMO_CORTE)]
    c = c.dropna(subset=["avance_real_pct"]).groupby("proyecto_id").tail(1).set_index("proyecto_id")
    ev = c["avance_real_pct"] / 100 * proyectos["presupuesto_bac"]
    pv = c["avance_plan_pct"] / 100 * proyectos["presupuesto_bac"]
    return pd.DataFrame({"spi": ev / pv, "cpi": ev / c["costo_real_acum"]}).dropna()


def errores_de(tablas, regla):
    e = tablas["errores_sembrados"]
    return e[e["regla"] == regla]


def test_misma_semilla_mismos_datos():
    a, b = generar(42), generar(42)
    for nombre in a:
        pd.testing.assert_frame_equal(a[nombre], b[nombre])


def test_otra_semilla_cambia_los_numeros():
    a, b = generar(42), generar(7)
    costo_a = a["cortes_semanales"]["costo_real_acum"]
    assert not costo_a.equals(b["cortes_semanales"]["costo_real_acum"])


def test_cartera_de_12_proyectos_mas_uno_mal_cargado(tablas):
    ids = tablas["proyectos"]["proyecto_id"]
    assert ids.nunique() == 13
    assert ids.value_counts().max() == 2
    assert ids[ids.duplicated()].tolist() == ["P13"]


def test_hay_una_regla_sembrada_por_cada_control(tablas):
    reglas = set(tablas["errores_sembrados"]["regla"])
    assert reglas == {f"DQ{n:02d}" for n in range(1, 13)}


def test_errores_sembrados_son_cerca_del_4_por_ciento(tablas):
    en_cortes = (tablas["errores_sembrados"]["tabla"] == "cortes_semanales").sum()
    assert 0.02 <= en_cortes / len(tablas["cortes_semanales"]) <= 0.06


def test_los_valores_sembrados_estan_en_los_datos(tablas):
    c = tablas["cortes_semanales"]
    for _, e in tablas["errores_sembrados"].query("tabla == 'cortes_semanales'").iterrows():
        if e["regla"] in ("DQ08", "DQ09", "DQ10"):
            continue  # filas agregadas o quitadas; se comprueban aparte
        fila = c[(c["proyecto_id"] == e["proyecto_id"]) & (c["fecha_corte"] == e["fecha_corte"])]
        assert len(fila) == 1, e["regla"]
        valor = fila[e["campo"]].iloc[0]
        if pd.isna(e["valor_sembrado"]):
            assert pd.isna(valor)
        elif e["regla"] != "DQ12":  # DQ12 suma 1.800 € al costo simulado
            assert valor == e["valor_sembrado"], e["regla"]


def test_filas_agregadas_y_quitadas(tablas):
    c = tablas["cortes_semanales"]
    assert (c["proyecto_id"] == "P15").sum() == 1
    assert c["fecha_corte"].max() > ULTIMO_CORTE
    ultimo_p01 = c.loc[c["proyecto_id"] == "P01", "fecha_corte"].max()
    assert (ULTIMO_CORTE - ultimo_p01).days == 7


def test_sin_errores_sembrados_avance_y_costo_no_bajan(tablas):
    c = tablas["cortes_semanales"]
    sembradas = tablas["errores_sembrados"][["proyecto_id", "fecha_corte"]].dropna()
    marca = c.merge(sembradas.assign(sembrado=True), how="left", on=["proyecto_id", "fecha_corte"])
    limpio = c[marca["sembrado"].isna().to_numpy() & (c["fecha_corte"] <= ULTIMO_CORTE)]
    limpio = limpio[limpio["proyecto_id"] != "P15"]
    for _, grupo in limpio.groupby("proyecto_id"):
        assert grupo["avance_real_pct"].is_monotonic_increasing
        assert grupo["costo_real_acum"].is_monotonic_increasing
        assert grupo["avance_real_pct"].between(0, 100).all()
        assert (grupo["costo_real_acum"] >= 0).all()


def test_cortes_son_viernes_entre_mayo_y_noviembre(tablas):
    fechas = tablas["cortes_semanales"]["fecha_corte"]
    assert all(f.weekday() == 4 for f in fechas)
    assert fechas.min() == date(2026, 5, 22)


@pytest.mark.parametrize("proyecto, spi_min, spi_max, cpi_min, cpi_max", [
    ("P02", 0.0, 0.85, 0.95, 9),   # atrasado, costo en línea
    ("P03", 0.0, 0.85, 0.0, 0.95),  # atrasado y con sobrecosto
    ("P04", 0.95, 9, 0.0, 0.85),    # sobrecosto, plazo en línea
    ("P05", 0.95, 9, 0.95, 9),      # se recuperó
    ("P06", 1.05, 9, 0.95, 9),      # adelantado
    ("P07", 0.0, 0.85, 0.0, 9),     # se degradó hasta rojo
    ("P09", 0.95, 9, 0.95, 9),      # cerrado en plazo
    ("P10", 0.85, 0.95, 0.0, 0.85),  # grande y con sobrecosto
    ("P11", 0.95, 9, 0.95, 9),      # en control (el atraso está en un hito)
    ("P12", 0.0, 0.85, 0.85, 9),    # arrancó tarde
])
def test_cada_perfil_cuenta_su_historia(indices, proyecto, spi_min, spi_max, cpi_min, cpi_max):
    spi, cpi = indices.loc[proyecto, "spi"], indices.loc[proyecto, "cpi"]
    assert spi_min <= spi < spi_max
    assert cpi_min <= cpi < cpi_max


def test_p01_en_control(indices):
    assert indices.loc["P01"].between(0.95, 1.05).all()


def test_p09_esta_cerrado(tablas):
    p09 = tablas["proyectos"].set_index("proyecto_id").loc["P09"]
    assert p09["estado"] == "Cerrado"
    assert p09["fecha_fin_real"] <= p09["fecha_fin_plan"]


def test_p11_tiene_un_hito_vencido(tablas):
    h = tablas["hitos"].set_index("hito_id").loc["P11-H2"]
    assert h["fecha_plan"] < ULTIMO_CORTE
    assert pd.isna(h["fecha_real"])


def test_guardar_escribe_raw_y_control(tablas, tmp_path):
    guardar(tablas, tmp_path)
    assert {p.name for p in (tmp_path / "data" / "raw").iterdir()} == {
        "proyectos.csv", "cortes_semanales.csv", "hitos.csv", "riesgos.csv"}
    assert (tmp_path / "data" / "control" / "errores_sembrados.csv").exists()
