"""Paso 3 del pipeline: indicadores de valor ganado (EVM, PMBOK) por corte.

Las fórmulas son funciones chicas que reciben números (o columnas de pandas) y
devuelven números, para poder testearlas con un ejemplo chico:
BAC 120.000 €, avance plan 50 %, avance real 40 %, costo real 56.000 €.

Cuando un divisor es cero (al arrancar un proyecto el PV o el AC valen 0), el
índice queda vacío en lugar de infinito: todavía no hay con qué medir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _dividir(a, b):
    """División que devuelve NaN si el divisor es 0 (o negativo, que no tiene sentido acá)."""
    if isinstance(b, pd.Series):
        return a / b.where(b > 0)
    return a / b if b > 0 else a * np.nan


def valor_planificado(bac, avance_plan_pct):
    return bac * avance_plan_pct / 100


def valor_ganado(bac, avance_real_pct):
    return bac * avance_real_pct / 100


def sv(ev, pv):
    """Desvío de plazo en euros: negativo = se hizo menos trabajo del planificado."""
    return ev - pv


def cv(ev, ac):
    """Desvío de costo en euros: negativo = se gastó más de lo que vale lo hecho."""
    return ev - ac


def spi(ev, pv):
    return _dividir(ev, pv)


def cpi(ev, ac):
    return _dividir(ev, ac)


def eac(bac, cpi_):
    """Costo estimado al cierre si se sigue gastando con la misma eficiencia."""
    return _dividir(bac, cpi_)


def etc(eac_, ac):
    return eac_ - ac


def vac(bac, eac_):
    """Desvío al cierre: negativo = el proyecto va a costar más que el presupuesto."""
    return bac - eac_


def tcpi(bac, ev, ac):
    """Eficiencia que haría falta de acá al final para cumplir el presupuesto."""
    return _dividir(bac - ev, bac - ac)


def fecha_fin_prevista(inicio_plan, fecha_fin_plan, spi_):
    """Fin estimado estirando la duración planificada al ritmo actual (duración ÷ SPI)."""
    inicio_plan, fecha_fin_plan = pd.to_datetime(inicio_plan), pd.to_datetime(fecha_fin_plan)
    dias = (fecha_fin_plan - inicio_plan) / pd.Timedelta(days=1)
    estirados = _dividir(dias, spi_)
    if isinstance(estirados, pd.Series):
        return inicio_plan + pd.to_timedelta(estirados.round(), unit="D")
    return pd.NaT if pd.isna(estirados) else inicio_plan + pd.Timedelta(days=round(estirados))


def calcular(proyectos: pd.DataFrame, cortes: pd.DataFrame) -> pd.DataFrame:
    """Agrega los indicadores EVM a cada corte válido."""
    datos = proyectos[["proyecto_id", "presupuesto_bac", "fecha_inicio_plan", "fecha_fin_plan",
                       "fecha_fin_real"]]
    c = cortes.merge(datos, on="proyecto_id", how="inner").sort_values(
        ["proyecto_id", "fecha_corte"], ignore_index=True)
    bac = c["presupuesto_bac"]

    c["pv"] = valor_planificado(bac, c["avance_plan_pct"])
    c["ev"] = valor_ganado(bac, c["avance_real_pct"])
    c["ac"] = c["costo_real_acum"]
    c["sv"] = sv(c["ev"], c["pv"])
    c["cv"] = cv(c["ev"], c["ac"])
    c["spi"] = spi(c["ev"], c["pv"])
    c["cpi"] = cpi(c["ev"], c["ac"])
    c["eac"] = eac(bac, c["cpi"])
    c["etc"] = etc(c["eac"], c["ac"])
    c["vac"] = vac(bac, c["eac"])
    c["tcpi"] = tcpi(bac, c["ev"], c["ac"])

    terminado = c["avance_real_pct"] >= 100
    prevista = fecha_fin_prevista(c["fecha_inicio_plan"], c["fecha_fin_plan"], c["spi"])
    # Un proyecto terminado ya tiene fecha de fin: la del corte en que llegó al 100 %.
    fin_real = c["fecha_fin_real"].fillna(c["fecha_corte"])
    c["fecha_fin_prevista"] = prevista.where(~terminado, fin_real)
    duracion = (c["fecha_fin_plan"] - c["fecha_inicio_plan"]).dt.days
    retraso = (c["fecha_fin_prevista"] - c["fecha_fin_plan"]).dt.days
    c["retraso_fin_dias"] = retraso
    c["retraso_fin_pct"] = 100 * retraso / duracion

    return c.drop(columns=["fecha_inicio_plan", "fecha_fin_plan", "fecha_fin_real"])
