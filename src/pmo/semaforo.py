"""Paso 4 del pipeline: semáforo por proyecto y corte, con el motivo en texto.

Cada dimensión (plazo, costo, fecha de fin y hitos) recibe un color según las
tolerancias de umbrales.yaml y el proyecto toma el peor. Un corte bloqueado por
errores de calidad no se pinta: queda en gris, porque un verde sobre datos malos
es peor que no decir nada.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from pmo.config import RUTA_UMBRALES

VERDE, AMBAR, ROJO, GRIS = "Verde", "Ámbar", "Rojo", "Gris"
GRAVEDAD = {VERDE: 0, AMBAR: 1, ROJO: 2}
CLAVE = ["proyecto_id", "fecha_corte"]


def cargar_umbrales(ruta: Path = RUTA_UMBRALES) -> dict:
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def color_minimo(valor: float, umbral: dict) -> str | None:
    """Para índices donde más es mejor (SPI, CPI). El umbral exacto cuenta como el color mejor."""
    if pd.isna(valor):
        return None
    if valor >= umbral["verde"]:
        return VERDE
    return AMBAR if valor >= umbral["ambar"] else ROJO


def color_maximo(valor: float, umbral: dict) -> str | None:
    """Para medidas donde menos es mejor (días o % de retraso)."""
    if pd.isna(valor):
        return None
    if valor <= umbral["verde"]:
        return VERDE
    return AMBAR if valor <= umbral["ambar"] else ROJO


def dias_hito_vencido(cortes: pd.DataFrame, hitos: pd.DataFrame) -> pd.Series:
    """Días del hito más vencido sin cumplir a la fecha de cada corte (0 si no hay)."""
    cruce = cortes[CLAVE].merge(hitos[["proyecto_id", "fecha_plan", "fecha_real"]],
                                on="proyecto_id", how="left")
    pendiente = (cruce["fecha_plan"] < cruce["fecha_corte"]) & ~(
        cruce["fecha_real"] <= cruce["fecha_corte"])
    cruce["dias"] = (cruce["fecha_corte"] - cruce["fecha_plan"]).dt.days.where(pendiente, 0)
    dias = cruce.groupby(CLAVE, as_index=False)["dias"].max()
    return (cortes[CLAVE].merge(dias, on=CLAVE, how="left")["dias"]
            .fillna(0).astype(int).set_axis(cortes.index))


def _numero(valor: float, decimales: int = 2) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")


def _bajo_umbral(indice: str, valor: float, umbral: dict, color: str) -> str:
    """Ej.: "SPI 0,82 < 0,85" (el umbral que se cruzó para llegar a ese color)."""
    limite = umbral["verde"] if color == AMBAR else umbral["ambar"]
    return f"{indice} {_numero(valor)} < {_numero(limite)}"


def _texto_gris(errores: int) -> str:
    cuantos = "1 error bloqueante" if errores == 1 else f"{errores} errores bloqueantes"
    return f"{cuantos} en el corte: corregir para ver el semáforo"


def colorear(fila: pd.Series, umbrales: dict) -> tuple[str, str]:
    """Devuelve (color, motivo) de un corte con indicadores."""
    u_spi, u_cpi = umbrales["spi"], umbrales["cpi"]
    u_fin, u_hito = umbrales["retraso_fin_pct_duracion"], umbrales["hito_vencido_dias"]
    dimensiones = [
        (color_minimo(fila["spi"], u_spi), lambda c: _bajo_umbral("SPI", fila["spi"], u_spi, c)),
        (color_minimo(fila["cpi"], u_cpi), lambda c: _bajo_umbral("CPI", fila["cpi"], u_cpi, c)),
        (color_maximo(fila["retraso_fin_pct"], u_fin),
         lambda c: f"Fin previsto {fila['retraso_fin_dias']:+.0f} días "
                   f"({_numero(fila['retraso_fin_pct'], 0)} % de la duración)"),
        (color_maximo(fila["dias_hito_vencido"], u_hito),
         lambda c: f"Hito vencido hace {int(fila['dias_hito_vencido'])} días"),
    ]
    con_color = [(c, texto) for c, texto in dimensiones if c is not None]
    if not con_color:
        return GRIS, "Sin datos suficientes para calcular los indicadores"
    peor = max((c for c, _ in con_color), key=GRAVEDAD.get)
    if peor == VERDE:
        return VERDE, "Dentro de tolerancia"
    # Primero lo que define el color, después el resto de lo que está fuera de verde.
    fuera = sorted(((c, texto) for c, texto in con_color if c != VERDE),
                   key=lambda par: -GRAVEDAD[par[0]])
    return peor, "; ".join(texto(c) for c, texto in fuera)


def evaluar(indicadores: pd.DataFrame, por_corte: pd.DataFrame, hitos: pd.DataFrame,
            proyectos_ids, referencia: date, umbrales: dict | None = None) -> pd.DataFrame:
    """Semáforo de cada corte hasta la fecha de referencia, incluidos los bloqueados (gris)."""
    umbrales = umbrales or cargar_umbrales()
    referencia = pd.Timestamp(referencia)

    bloqueados = por_corte[por_corte["bloqueado"]
                           & por_corte["proyecto_id"].isin(proyectos_ids)
                           & (por_corte["fecha_corte"] <= referencia)][CLAVE]
    tabla = pd.concat([indicadores[indicadores["fecha_corte"] <= referencia], bloqueados],
                      ignore_index=True)
    tabla = tabla.drop_duplicates(CLAVE).merge(
        por_corte[CLAVE + ["errores_bloqueantes", "advertencias", "indice_calidad", "bloqueado"]],
        on=CLAVE, how="left")
    tabla["bloqueado"] = tabla["bloqueado"].fillna(False).astype(bool)
    tabla["indice_calidad"] = tabla["indice_calidad"].fillna(100)
    tabla["dias_hito_vencido"] = dias_hito_vencido(tabla, hitos)

    colores = [
        (GRIS, _texto_gris(int(f["errores_bloqueantes"])))
        if f["bloqueado"] and umbrales["gris_si_errores_bloqueantes"]
        else colorear(f, umbrales)
        for _, f in tabla.iterrows()
    ]
    tabla["color"] = [c for c, _ in colores]
    tabla["motivo"] = [m for _, m in colores]
    return tabla.sort_values(CLAVE, ignore_index=True)
