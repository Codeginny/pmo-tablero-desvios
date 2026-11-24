"""Paso 2 del pipeline: controles de calidad del dato (DQ01–DQ12).

Las reglas corren en dos tandas:

1. Validez, completitud, unicidad e integridad, sobre cada fila por separado.
2. Consistencia entre cortes (el avance o el costo que bajan), comparando cada
   corte sólo con el corte válido anterior. Así un avance de 115 % se informa una
   vez (DQ03) y no vuelve a aparecer como "avance que baja" en el corte siguiente.

Nada se borra: las filas con errores bloqueantes pasan a cuarentena y el corte
queda marcado como bloqueado, que en el semáforo se ve en gris.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

BLOQUEANTE = "Bloqueante"
ADVERTENCIA = "Advertencia"


@dataclass(frozen=True)
class Regla:
    codigo: str
    descripcion: str
    dimension: str
    severidad: str
    sugerencia: str


REGLAS = {r.codigo: r for r in [
    Regla("DQ01", "Campo obligatorio vacío o con formato inválido", "Completitud", BLOQUEANTE,
          "Completar el dato en la planilla de origen"),
    Regla("DQ02", "Fecha de fin planificada anterior al inicio", "Validez", BLOQUEANTE,
          "Revisar las fechas de la línea base (suele ser un año mal tipeado)"),
    Regla("DQ03", "Avance fuera del rango 0–100 %", "Validez", BLOQUEANTE,
          "Informar el avance como porcentaje entre 0 y 100"),
    Regla("DQ04", "El avance real baja respecto del corte anterior", "Consistencia", ADVERTENCIA,
          "Confirmar con el PM si se reestimó el avance o si es un error de carga"),
    Regla("DQ05", "El costo acumulado baja respecto del corte anterior", "Consistencia",
          BLOQUEANTE, "Revisar las imputaciones: un costo acumulado no puede bajar"),
    Regla("DQ06", "Costo negativo", "Validez", BLOQUEANTE,
          "Cargar el costo en positivo; las devoluciones van como ajuste aparte"),
    Regla("DQ07", "Proyecto o corte cargado dos veces", "Unicidad", BLOQUEANTE,
          "Dejar un solo registro y borrar el duplicado"),
    Regla("DQ08", "Corte de un proyecto que no está en la cartera", "Integridad", BLOQUEANTE,
          "Revisar el código del proyecto o darlo de alta en la cartera"),
    Regla("DQ09", "Proyecto activo sin corte en los últimos 7 días", "Oportunidad", ADVERTENCIA,
          "Pedir el corte semanal al PM"),
    Regla("DQ10", "Fecha de corte posterior a la fecha de referencia", "Validez", BLOQUEANTE,
          "Corregir la fecha del corte"),
    Regla("DQ11", "Avance informado antes del inicio real del proyecto", "Consistencia",
          ADVERTENCIA, "Revisar la fecha de inicio real o el avance informado"),
    Regla("DQ12", "Más de 2 cortes seguidos con costo y sin avance", "Razonabilidad",
          ADVERTENCIA, "Confirmar si hay gastos anticipados (licencias, compras) o falta avance"),
]}

OBLIGATORIOS = {
    "proyectos": ["proyecto_id", "nombre", "fecha_inicio_plan", "fecha_fin_plan",
                  "presupuesto_bac"],
    "cortes_semanales": ["proyecto_id", "fecha_corte", "avance_plan_pct", "avance_real_pct",
                         "costo_real_acum"],
}
COLUMNAS = ["regla", "severidad", "dimension", "descripcion", "tabla", "fila", "proyecto_id",
            "fecha_corte", "campo", "valor", "sugerencia"]
CLAVE = ["proyecto_id", "fecha_corte"]


@dataclass
class ResultadoCalidad:
    errores: pd.DataFrame
    por_corte: pd.DataFrame
    proyectos_validos: pd.DataFrame
    cortes_validos: pd.DataFrame
    cuarentena_proyectos: pd.DataFrame
    cuarentena_cortes: pd.DataFrame


def _hallazgos(codigo: str, tabla: str, filas: pd.DataFrame, campo: str,
               valores: pd.Series | None = None) -> pd.DataFrame:
    """Arma las filas de error de una regla a partir de los registros que la incumplen."""
    regla = REGLAS[codigo]
    valores = filas[campo] if valores is None else valores
    return pd.DataFrame({
        "regla": codigo,
        "severidad": regla.severidad,
        "dimension": regla.dimension,
        "descripcion": regla.descripcion,
        "tabla": tabla,
        "fila": pd.Series(filas.index, index=filas.index, dtype="Int64"),
        "proyecto_id": filas["proyecto_id"],
        "fecha_corte": filas["fecha_corte"] if "fecha_corte" in filas else pd.NaT,
        "campo": campo,
        "valor": valores.map(_texto),
        "sugerencia": regla.sugerencia,
    }, columns=COLUMNAS)


def _texto(valor) -> str | None:
    if pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


# --- Reglas por fila --------------------------------------------------------

def dq01_vacios(df: pd.DataFrame, tabla: str, formato: pd.DataFrame) -> list[pd.DataFrame]:
    salida = []
    mal_formato = formato[formato["tabla"] == tabla]
    for campo in OBLIGATORIOS[tabla]:
        vacios = df[df[campo].isna()]
        valores = vacios[campo].astype(object)
        # Si el vacío viene de un valor que no se pudo convertir, se muestra el original.
        originales = mal_formato[mal_formato["campo"] == campo].set_index("fila")["valor"]
        valores.update(originales[originales.index.isin(valores.index)])
        salida.append(_hallazgos("DQ01", tabla, vacios, campo, valores))
    return salida


def dq02_fechas_invertidas(proyectos: pd.DataFrame) -> pd.DataFrame:
    filas = proyectos[proyectos["fecha_fin_plan"] < proyectos["fecha_inicio_plan"]]
    return _hallazgos("DQ02", "proyectos", filas, "fecha_fin_plan")


def dq03_avance_fuera_de_rango(cortes: pd.DataFrame) -> list[pd.DataFrame]:
    fuera = {c: cortes[cortes[c].notna() & ~cortes[c].between(0, 100)]
             for c in ("avance_plan_pct", "avance_real_pct")}
    return [_hallazgos("DQ03", "cortes_semanales", filas, c) for c, filas in fuera.items()]


def dq06_costo_negativo(cortes: pd.DataFrame) -> pd.DataFrame:
    return _hallazgos("DQ06", "cortes_semanales", cortes[cortes["costo_real_acum"] < 0],
                      "costo_real_acum")


def dq07_duplicados(proyectos: pd.DataFrame, cortes: pd.DataFrame) -> list[pd.DataFrame]:
    # Se marcan todas las copias: hasta que alguien decida cuál vale, ninguna es confiable.
    dup_p = proyectos[proyectos["proyecto_id"].notna()
                      & proyectos["proyecto_id"].duplicated(keep=False)]
    dup_c = cortes[cortes[CLAVE].notna().all(axis=1) & cortes.duplicated(CLAVE, keep=False)]
    return [_hallazgos("DQ07", "proyectos", dup_p, "proyecto_id"),
            _hallazgos("DQ07", "cortes_semanales", dup_c, "fecha_corte")]


def dq08_proyecto_inexistente(cortes: pd.DataFrame, proyectos: pd.DataFrame) -> pd.DataFrame:
    filas = cortes[cortes["proyecto_id"].notna()
                   & ~cortes["proyecto_id"].isin(proyectos["proyecto_id"])]
    return _hallazgos("DQ08", "cortes_semanales", filas, "proyecto_id")


def dq10_fecha_futura(cortes: pd.DataFrame, referencia: pd.Timestamp) -> pd.DataFrame:
    return _hallazgos("DQ10", "cortes_semanales", cortes[cortes["fecha_corte"] > referencia],
                      "fecha_corte")


def dq11_avance_antes_de_inicio(cortes: pd.DataFrame, proyectos: pd.DataFrame) -> pd.DataFrame:
    inicio = proyectos.drop_duplicates("proyecto_id").set_index("proyecto_id")["fecha_inicio_real"]
    antes = cortes["fecha_corte"] < cortes["proyecto_id"].map(inicio)
    return _hallazgos("DQ11", "cortes_semanales", cortes[antes & (cortes["avance_real_pct"] > 0)],
                      "avance_real_pct")


# --- Reglas entre cortes (sólo sobre cortes válidos) ------------------------

def _baja_respecto_del_anterior(cortes: pd.DataFrame, campo: str) -> pd.DataFrame:
    con_dato = cortes[cortes[campo].notna()].sort_values(CLAVE)
    anterior = con_dato.groupby("proyecto_id")[campo].shift()
    return con_dato[con_dato[campo] < anterior]


def dq04_avance_baja(validos: pd.DataFrame) -> pd.DataFrame:
    return _hallazgos("DQ04", "cortes_semanales",
                      _baja_respecto_del_anterior(validos, "avance_real_pct"), "avance_real_pct")


def dq05_costo_baja(validos: pd.DataFrame) -> pd.DataFrame:
    return _hallazgos("DQ05", "cortes_semanales",
                      _baja_respecto_del_anterior(validos, "costo_real_acum"), "costo_real_acum")


def dq12_costo_sin_avance(validos: pd.DataFrame) -> pd.DataFrame:
    c = validos.sort_values(CLAVE)
    sin_avance = (c["costo_real_acum"] > 0) & (c["avance_real_pct"] == 0)
    # Largo de cada racha de cortes seguidos con costo y sin avance.
    corte_de_racha = (~sin_avance).groupby(c["proyecto_id"]).cumsum()
    racha = sin_avance.groupby([c["proyecto_id"], corte_de_racha]).cumsum()
    return _hallazgos("DQ12", "cortes_semanales", c[racha > 2], "costo_real_acum")


def dq09_sin_corte_reciente(cortes: pd.DataFrame, proyectos: pd.DataFrame,
                            referencia: pd.Timestamp) -> pd.DataFrame:
    # Cuenta cualquier corte recibido, aunque tenga errores: la regla mide si el PM reportó.
    activos = proyectos[proyectos["estado"] == "En ejecución"].drop_duplicates("proyecto_id")
    ultimo = cortes[cortes["fecha_corte"] <= referencia].groupby("proyecto_id")["fecha_corte"].max()
    ultimo_de_activos = activos["proyecto_id"].map(ultimo)
    atrasados = activos[ultimo_de_activos.isna()
                        | ((referencia - ultimo_de_activos).dt.days >= 7)]
    filas = atrasados.assign(fecha_corte=referencia)
    hallazgos = _hallazgos("DQ09", "cortes_semanales", filas, "fecha_corte",
                           atrasados["proyecto_id"].map(ultimo))
    hallazgos["fila"] = pd.NA  # el error es la falta de una fila
    return hallazgos


# --- Orquestación -----------------------------------------------------------

def evaluar(proyectos: pd.DataFrame, cortes: pd.DataFrame, referencia: date,
            formato: pd.DataFrame | None = None) -> ResultadoCalidad:
    """Corre las 12 reglas y separa lo confiable de lo que va a cuarentena."""
    referencia = pd.Timestamp(referencia)
    if formato is None:
        formato = pd.DataFrame(columns=["tabla", "fila", "proyecto_id", "campo", "valor"])

    por_fila = [
        *dq01_vacios(proyectos, "proyectos", formato),
        *dq01_vacios(cortes, "cortes_semanales", formato),
        dq02_fechas_invertidas(proyectos),
        *dq03_avance_fuera_de_rango(cortes),
        dq06_costo_negativo(cortes),
        *dq07_duplicados(proyectos, cortes),
        dq08_proyecto_inexistente(cortes, proyectos),
        dq10_fecha_futura(cortes, referencia),
        dq11_avance_antes_de_inicio(cortes, proyectos),
        dq09_sin_corte_reciente(cortes, proyectos, referencia),
    ]
    invalidas = _filas_bloqueadas(por_fila, "cortes_semanales")
    validos = cortes.drop(index=invalidas)

    entre_cortes = [
        dq04_avance_baja(validos),
        dq05_costo_baja(validos),
        dq12_costo_sin_avance(validos),
    ]
    errores = _unir(por_fila + entre_cortes)

    proyectos_bloqueados = _filas_bloqueadas([errores], "proyectos")
    ids_bloqueados = proyectos.loc[proyectos_bloqueados, "proyecto_id"].dropna().unique()
    cortes_bloqueados = cortes.index.isin(_filas_bloqueadas([errores], "cortes_semanales"))
    cortes_bloqueados |= cortes["proyecto_id"].isin(ids_bloqueados).to_numpy()

    return ResultadoCalidad(
        errores=errores,
        por_corte=calidad_por_corte(cortes, errores),
        proyectos_validos=proyectos.drop(index=proyectos_bloqueados),
        cortes_validos=cortes[~cortes_bloqueados],
        cuarentena_proyectos=proyectos.loc[proyectos_bloqueados],
        cuarentena_cortes=cortes[cortes_bloqueados],
    )


def _unir(partes: list[pd.DataFrame]) -> pd.DataFrame:
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=COLUMNAS)
    errores = pd.concat(partes, ignore_index=True)
    return errores.sort_values(["regla", "proyecto_id", "fecha_corte", "campo"],
                               ignore_index=True, na_position="first")


def _filas_bloqueadas(partes: list[pd.DataFrame], tabla: str) -> list[int]:
    errores = _unir(partes)
    filtro = (errores["tabla"] == tabla) & (errores["severidad"] == BLOQUEANTE)
    return sorted(set(errores.loc[filtro, "fila"].dropna().astype(int)))


def calidad_por_corte(cortes: pd.DataFrame, errores: pd.DataFrame) -> pd.DataFrame:
    """Índice de calidad de cada corte: 100 − 10 por bloqueante − 3 por advertencia.

    Los errores del proyecto (no de un corte puntual) cuentan en todos sus cortes.
    Incluye también las fechas donde faltó un corte (DQ09), sin fila de datos.
    """
    claves = pd.concat([
        cortes[CLAVE].dropna(),
        errores.loc[errores["tabla"] == "cortes_semanales", CLAVE].dropna(),
    ]).drop_duplicates()

    def contar(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=por + [BLOQUEANTE, ADVERTENCIA])
        conteo = df.groupby(por + ["severidad"]).size().unstack(fill_value=0)
        return conteo.reindex(columns=[BLOQUEANTE, ADVERTENCIA], fill_value=0).reset_index()

    de_corte = contar(errores[errores["tabla"] == "cortes_semanales"], CLAVE)
    de_proyecto = contar(errores[errores["tabla"] == "proyectos"], ["proyecto_id"])
    tabla = (claves.merge(de_corte, how="left", on=CLAVE)
             .merge(de_proyecto, how="left", on="proyecto_id", suffixes=("", "_proyecto"))
             .fillna(0))
    bloqueantes = (tabla[BLOQUEANTE] + tabla[f"{BLOQUEANTE}_proyecto"]).astype(int)
    advertencias = (tabla[ADVERTENCIA] + tabla[f"{ADVERTENCIA}_proyecto"]).astype(int)
    return pd.DataFrame({
        "proyecto_id": tabla["proyecto_id"],
        "fecha_corte": tabla["fecha_corte"],
        "errores_bloqueantes": bloqueantes,
        "advertencias": advertencias,
        "indice_calidad": (100 - 10 * bloqueantes - 3 * advertencias).clip(lower=0),
        "bloqueado": bloqueantes > 0,
    }).sort_values(CLAVE, ignore_index=True)
