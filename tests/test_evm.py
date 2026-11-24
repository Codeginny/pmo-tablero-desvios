import math

import pandas as pd
import pytest

from pmo import evm

# Ejemplo del README y de la metodología: P03 en la semana 14.
BAC, AVANCE_PLAN, AVANCE_REAL, AC = 120_000, 50, 40, 56_000


def test_ejemplo_del_readme():
    pv = evm.valor_planificado(BAC, AVANCE_PLAN)
    ev = evm.valor_ganado(BAC, AVANCE_REAL)
    cpi = evm.cpi(ev, AC)
    eac = evm.eac(BAC, cpi)

    assert (pv, ev) == (60_000, 48_000)
    assert evm.sv(ev, pv) == -12_000
    assert evm.cv(ev, AC) == -8_000
    assert evm.spi(ev, pv) == pytest.approx(0.80)
    assert cpi == pytest.approx(0.857, abs=1e-3)
    assert eac == pytest.approx(140_000)
    assert evm.etc(eac, AC) == pytest.approx(84_000)
    assert evm.vac(BAC, eac) == pytest.approx(-20_000)
    assert evm.tcpi(BAC, ev, AC) == pytest.approx(1.125)


def test_division_por_cero_da_vacio_y_no_infinito():
    assert math.isnan(evm.spi(0, 0))
    assert math.isnan(evm.cpi(5_000, 0))
    serie = evm.spi(pd.Series([10.0, 0.0]), pd.Series([0.0, 0.0]))
    assert serie.isna().all()


def test_tcpi_sin_presupuesto_restante_queda_vacio():
    assert math.isnan(evm.tcpi(100_000, 60_000, 100_000))


def test_fecha_fin_prevista_estira_la_duracion_por_el_spi():
    inicio, fin = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-11")  # 100 días
    assert evm.fecha_fin_prevista(inicio, fin, 0.8) == pd.Timestamp("2026-05-06")  # 125 días
    assert evm.fecha_fin_prevista(inicio, fin, 1.0) == fin
    assert pd.isna(evm.fecha_fin_prevista(inicio, fin, float("nan")))


@pytest.fixture
def proyectos():
    return pd.DataFrame({
        "proyecto_id": ["A", "B"],
        "presupuesto_bac": [120_000.0, 40_000.0],
        "fecha_inicio_plan": pd.to_datetime(["2026-01-05", "2026-01-05"]),
        "fecha_fin_plan": pd.to_datetime(["2026-12-31", "2026-03-27"]),
        "fecha_fin_real": pd.to_datetime([None, "2026-03-20"]),
    })


@pytest.fixture
def cortes():
    return pd.DataFrame({
        "proyecto_id": ["A", "A", "B"],
        "fecha_corte": pd.to_datetime(["2026-01-09", "2026-06-05", "2026-03-20"]),
        "avance_plan_pct": [0.0, 50.0, 98.0],
        "avance_real_pct": [0.0, 40.0, 100.0],
        "costo_real_acum": [0.0, 56_000.0, 39_000.0],
    })


def test_calcular_agrega_los_indicadores(proyectos, cortes):
    c = evm.calcular(proyectos, cortes).set_index(["proyecto_id", "fecha_corte"])
    fila = c.loc[("A", pd.Timestamp("2026-06-05"))]
    assert fila["spi"] == pytest.approx(0.80)
    assert fila["eac"] == pytest.approx(140_000)
    assert fila["retraso_fin_dias"] > 0
    duracion = (pd.Timestamp("2026-12-31") - pd.Timestamp("2026-01-05")).days
    assert fila["retraso_fin_pct"] == pytest.approx(100 * fila["retraso_fin_dias"] / duracion)


def test_primer_corte_sin_plan_ni_gasto_no_tiene_indices(proyectos, cortes):
    fila = evm.calcular(proyectos, cortes).iloc[0]
    assert pd.isna(fila["spi"]) and pd.isna(fila["cpi"]) and pd.isna(fila["eac"])


def test_proyecto_terminado_usa_su_fecha_de_fin_real(proyectos, cortes):
    b = evm.calcular(proyectos, cortes).query("proyecto_id == 'B'").iloc[0]
    assert b["fecha_fin_prevista"] == pd.Timestamp("2026-03-20")
    assert b["retraso_fin_dias"] == -7


def test_cortes_de_proyectos_desconocidos_se_ignoran(proyectos, cortes):
    cortes.loc[len(cortes)] = ["Z", pd.Timestamp("2026-06-05"), 10.0, 10.0, 1_000.0]
    assert "Z" not in set(evm.calcular(proyectos, cortes)["proyecto_id"])
