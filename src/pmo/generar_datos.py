"""Genera el portafolio ficticio de Norvia Operaciones S.L. (datos simulados).

Escribe en data/raw los CSV que la PMO recibe cada semana y en data/control la
lista de errores de carga sembrados a propósito, para que los tests comprueben
que el motor de calidad los encuentra todos.

Cada proyecto tiene un perfil de comportamiento (ritmo de avance y eficiencia
de costo por semana) elegido para que el tablero tenga una historia que contar:
uno en control, uno atrasado, uno con sobrecosto, uno que se degrada, etc.

Uso:
    python -m pmo.generar_datos            # semilla 42
    python -m pmo.generar_datos --semilla 7
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pmo.config import FECHA_REFERENCIA, RAIZ

PRIMER_CORTE = date(2026, 5, 22)
ULTIMO_CORTE = FECHA_REFERENCIA
SEMILLA = 42

# Perfil: semana relativa al primer corte (negativa antes) -> (ritmo, eficiencia de costo).
# Ritmo 1 = avanza como el plan; eficiencia 1 = cada euro rinde un euro de trabajo.
Perfil = Callable[[int], tuple[float, float]]


def constante(ritmo: float, eficiencia: float) -> Perfil:
    return lambda semana: (ritmo, eficiencia)


def se_recupera(semana: int) -> tuple[float, float]:
    # Replanificación con refuerzo del equipo a partir de la semana 12.
    return (0.88, 0.97) if semana < 12 else (1.2, 1.0)


def se_degrada(semana: int) -> tuple[float, float]:
    # Va bien hasta la semana 13 y desde ahí pierde ritmo y eficiencia de a poco.
    if semana < 13:
        return (1.02, 1.0)
    caida = (semana - 13) / 12
    return (1.0 - 0.95 * caida, 1.0 - 0.5 * caida)


@dataclass(frozen=True)
class Proyecto:
    proyecto_id: str
    nombre: str
    area: str
    cliente: str
    pm: str
    sponsor: str
    metodologia: str
    prioridad: str
    inicio_plan: date
    fin_plan: date
    bac: float
    perfil: Perfil
    semanas_retraso_inicio: int = 0


CARTERA: list[Proyecto] = [
    Proyecto("P01", "Automatización de facturas de proveedores", "Finanzas", "Interno",
             "Lucía Herrero", "Dirección Financiera", "Híbrido", "Alta",
             date(2026, 4, 6), date(2026, 12, 18), 85_000, constante(1.0, 1.0)),
    Proyecto("P02", "Migración de CRM", "Comercial", "Interno",
             "Marcos Ibáñez", "Dirección Comercial", "Predictivo", "Alta",
             date(2026, 5, 4), date(2027, 1, 29), 110_000, constante(0.76, 1.0)),
    Proyecto("P03", "Integración ERP–e-commerce", "Tecnología", "Marisma Hogar",
             "Elena Soto", "Dirección de Operaciones", "Predictivo", "Crítica",
             date(2026, 3, 2), date(2027, 2, 26), 120_000, constante(0.79, 0.86)),
    Proyecto("P04", "Portal de autoservicio de clientes", "Tecnología",
             "Varela & Ortiz Distribución",
             "Javier Prieto", "Dirección Comercial", "Ágil", "Alta",
             date(2026, 5, 18), date(2026, 12, 18), 95_000, constante(1.0, 0.81)),
    Proyecto("P05", "Implantación de sistema de tickets", "Operaciones", "Interno",
             "Lucía Herrero", "Dirección de Operaciones", "Ágil", "Media",
             date(2026, 4, 13), date(2027, 1, 15), 70_000, se_recupera),
    Proyecto("P06", "Cuadro de mando comercial", "Comercial", "Interno",
             "Marcos Ibáñez", "Dirección Comercial", "Ágil", "Media",
             date(2026, 6, 1), date(2026, 12, 11), 60_000, constante(1.15, 1.03)),
    Proyecto("P07", "Onboarding digital de empleados", "RRHH", "Interno",
             "Elena Soto", "Dirección de Personas", "Híbrido", "Media",
             date(2026, 3, 16), date(2027, 1, 29), 80_000, se_degrada),
    Proyecto("P08", "Optimización de rutas de reparto", "Logística", "Varela & Ortiz Distribución",
             "Javier Prieto", "Dirección de Operaciones", "Predictivo", "Alta",
             date(2026, 5, 4), date(2027, 2, 12), 75_000, constante(0.97, 0.98)),
    Proyecto("P09", "Firma electrónica de contratos", "Legal", "Interno",
             "Lucía Herrero", "Dirección Financiera", "Predictivo", "Baja",
             date(2026, 3, 2), date(2026, 9, 25), 45_000, constante(1.01, 1.02)),
    Proyecto("P10", "Data warehouse financiero", "Finanzas", "Interno",
             "Marcos Ibáñez", "Dirección Financiera", "Híbrido", "Crítica",
             date(2026, 2, 2), date(2027, 4, 30), 260_000, constante(0.93, 0.84)),
    Proyecto("P11", "Rediseño del proceso de compras", "Compras", "Interno",
             "Elena Soto", "Dirección de Operaciones", "Híbrido", "Media",
             date(2026, 4, 20), date(2027, 1, 22), 90_000, constante(0.98, 1.0)),
    Proyecto("P12", "Integración de pasarela de pagos", "Tecnología", "Marisma Hogar",
             "Javier Prieto", "Dirección Comercial", "Ágil", "Alta",
             date(2026, 6, 15), date(2027, 3, 26), 100_000, constante(1.0, 0.99),
             semanas_retraso_inicio=5),
]

HITOS = [
    (0.25, "Análisis y diseño aprobados"),
    (0.50, "Construcción o configuración completa"),
    (0.75, "Pruebas de aceptación superadas"),
    (1.00, "Puesta en marcha"),
]

RIESGOS = [
    ("P01", "El proveedor de OCR cambia su tarifa a mitad del proyecto", 2, 3, "Abierto"),
    ("P02", "Dos consultores del integrador asignados a otro cliente", 4, 4, "Abierto"),
    ("P02", "La limpieza de contactos duplicados lleva más de lo estimado", 3, 3, "Abierto"),
    ("P03", "La API del e-commerce del cliente no soporta pedidos parciales", 4, 5, "Abierto"),
    ("P03", "Horas extra de integración para llegar al hito de pruebas", 4, 4, "Abierto"),
    ("P04", "El cliente pide funcionalidades fuera del alcance acordado", 4, 4, "Abierto"),
    ("P05", "Resistencia del equipo de soporte al nuevo flujo", 3, 3, "Mitigado"),
    ("P06", "Datos comerciales incompletos en el CRM antiguo", 2, 2, "Abierto"),
    ("P07", "Rotación del responsable funcional de RRHH", 4, 4, "Abierto"),
    ("P07", "Retrasos en la firma del acuerdo de protección de datos", 3, 4, "Abierto"),
    ("P08", "Los PMs del cliente cargan el avance en planillas propias", 4, 3, "Abierto"),
    ("P09", "Validez legal de la firma en contratos con proveedores extranjeros", 2, 4, "Cerrado"),
    ("P10", "Licencias del motor de base de datos más caras de lo presupuestado", 5, 4, "Abierto"),
    ("P10", "Calidad de los datos de origen de las filiales", 4, 4, "Abierto"),
    ("P11", "Aprobación del nuevo circuito de compras pendiente del comité", 4, 3, "Abierto"),
    ("P12", "El banco adquirente demora la entrega de credenciales de prueba", 5, 4, "Mitigado"),
]


def curva(t: float) -> float:
    """Avance acumulado (0–1) para una fracción de tiempo t: mezcla de recta y curva S."""
    t = min(max(t, 0.0), 1.0)
    return 0.5 * t + 0.5 * (3 * t**2 - 2 * t**3)


def viernes_desde(dia: date) -> date:
    return dia + timedelta(days=(4 - dia.weekday()) % 7)


def semana_relativa(dia: date) -> int:
    return (dia - PRIMER_CORTE).days // 7


def simular(p: Proyecto, rng: np.random.Generator) -> tuple[list[dict], dict, list[dict]]:
    """Simula los cortes semanales de un proyecto desde su inicio hasta la fecha de referencia."""
    duracion = (p.fin_plan - p.inicio_plan).days
    inicio_real = p.inicio_plan + timedelta(weeks=p.semanas_retraso_inicio)
    t_real, costo, ev_anterior = 0.0, 0.0, 0.0
    fin_real: date | None = None
    hitos_reales: dict[float, date] = {}
    cortes = []

    viernes = viernes_desde(p.inicio_plan)
    while viernes <= ULTIMO_CORTE:
        eficiencia = 1.0
        if viernes >= inicio_real:
            ritmo, eficiencia = p.perfil(semana_relativa(viernes))
            dias = min(7, (viernes - inicio_real).days)
            ritmo = max(0.0, ritmo + rng.normal(0, 0.03))
            t_real = min(1.0, t_real + ritmo * dias / duracion)

        avance_real = curva(t_real)
        ev = p.bac * avance_real
        costo += (ev - ev_anterior) / max(0.5, eficiencia + rng.normal(0, 0.02))
        ev_anterior = ev

        for fraccion, _ in HITOS:
            if t_real >= fraccion and fraccion not in hitos_reales:
                hitos_reales[fraccion] = viernes

        if viernes >= PRIMER_CORTE:
            cortes.append({
                "proyecto_id": p.proyecto_id,
                "fecha_corte": viernes,
                "avance_plan_pct": round(100 * curva((viernes - p.inicio_plan).days / duracion), 1),
                "avance_real_pct": round(100 * avance_real, 1),
                "costo_real_acum": round(costo, 2),
                "reportado_por": p.pm,
            })

        if t_real >= 1.0:
            fin_real = viernes
            break
        viernes += timedelta(weeks=1)

    avance_final = curva(t_real)
    proyecto = {
        "proyecto_id": p.proyecto_id,
        "nombre": p.nombre,
        "area": p.area,
        "cliente": p.cliente,
        "pm": p.pm,
        "sponsor": p.sponsor,
        "metodologia": p.metodologia,
        "prioridad": p.prioridad,
        "fase": fase(avance_final),
        "estado": "Cerrado" if fin_real else "En ejecución",
        "fecha_inicio_plan": p.inicio_plan,
        "fecha_fin_plan": p.fin_plan,
        "fecha_inicio_real": inicio_real,
        "fecha_fin_real": fin_real,
        "presupuesto_bac": p.bac,
    }
    hitos = [
        {
            "hito_id": f"{p.proyecto_id}-H{i}",
            "proyecto_id": p.proyecto_id,
            "nombre": nombre,
            "fecha_plan": p.inicio_plan + timedelta(days=round(fraccion * duracion)),
            "fecha_real": hitos_reales.get(fraccion),
        }
        for i, (fraccion, nombre) in enumerate(HITOS, start=1)
    ]
    return cortes, proyecto, hitos


def fase(avance: float) -> str:
    if avance >= 1.0:
        return "Cierre"
    if avance < 0.10:
        return "Planificación"
    return "Ejecución"


class Sembrador:
    """Aplica errores de carga típicos y deja registro de cada uno."""

    def __init__(self, proyectos: pd.DataFrame, cortes: pd.DataFrame):
        self.proyectos = proyectos
        self.cortes = cortes
        self.registro: list[dict] = []

    def fila(self, proyecto_id: str, semana: int) -> int:
        fecha = PRIMER_CORTE + timedelta(weeks=semana)
        filtro = (self.cortes["proyecto_id"] == proyecto_id) & (self.cortes["fecha_corte"] == fecha)
        return self.cortes.index[filtro][0]

    def anotar(self, regla, tabla, proyecto_id, fecha_corte, campo, valor, descripcion):
        self.registro.append({
            "regla": regla,
            "tabla": tabla,
            "proyecto_id": proyecto_id,
            "fecha_corte": fecha_corte,
            "campo": campo,
            "valor_sembrado": valor,
            "descripcion": descripcion,
        })

    def cambiar(self, regla, proyecto_id, semana, campo, valor, descripcion):
        i = self.fila(proyecto_id, semana)
        self.cortes.loc[i, campo] = valor
        self.anotar(regla, "cortes_semanales", proyecto_id, self.cortes.loc[i, "fecha_corte"],
                    campo, valor, descripcion)

    def sembrar(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        c = self.cortes
        ultima = semana_relativa(ULTIMO_CORTE)

        self.cambiar("DQ03", "P02", 6, "avance_real_pct", 115.0,
                     "Avance cargado como 115 % (se tipeó un 1 de más)")

        anterior = c.loc[self.fila("P07", 9), "avance_real_pct"]
        self.cambiar("DQ04", "P07", 10, "avance_real_pct", round(anterior - 3, 1),
                     "El avance baja 3 puntos respecto del corte anterior")

        self.cambiar("DQ06", "P04", 3, "costo_real_acum",
                     -c.loc[self.fila("P04", 3), "costo_real_acum"],
                     "Costo acumulado con signo negativo")

        anterior = c.loc[self.fila("P08", ultima - 2), "costo_real_acum"]
        self.cambiar("DQ05", "P08", ultima - 1, "costo_real_acum", round(anterior * 0.9, 2),
                     "El costo acumulado baja un 10 % respecto del corte anterior")

        self.cambiar("DQ01", "P08", ultima, "avance_real_pct", np.nan,
                     "Corte sin avance real informado")

        # P12 compró licencias antes de arrancar: costo sin avance durante 4 cortes.
        p12 = c["proyecto_id"] == "P12"
        licencias = p12 & (c["fecha_corte"] >= date(2026, 6, 26))
        c.loc[licencias, "costo_real_acum"] = c.loc[licencias, "costo_real_acum"] + 1_800
        self.anotar("DQ12", "cortes_semanales", "P12", date(2026, 7, 10), "costo_real_acum",
                    1_800.0, "Tercer corte seguido con costo y sin avance")
        siguiente = c.loc[p12 & (c["fecha_corte"] == date(2026, 7, 24)), "avance_real_pct"].iloc[0]
        i = c.index[p12 & (c["fecha_corte"] == date(2026, 7, 17))][0]
        c.loc[i, "avance_real_pct"] = round(siguiente / 2, 1)
        self.anotar("DQ11", "cortes_semanales", "P12", date(2026, 7, 17), "avance_real_pct",
                    c.loc[i, "avance_real_pct"], "Avance informado antes del inicio real (20/07)")

        # P01 no envió el último corte.
        self.cortes = c = c.drop(index=self.fila("P01", ultima))
        self.anotar("DQ09", "cortes_semanales", "P01", ULTIMO_CORTE, "fecha_corte", None,
                    "Proyecto activo sin corte en los últimos 7 días")

        # P06 cargó el corte con la fecha de la semana siguiente.
        futuro = c.loc[self.fila("P06", ultima)].copy()
        futuro["fecha_corte"] = ULTIMO_CORTE + timedelta(weeks=1)
        c.loc[len(c) + 1000] = futuro
        self.anotar("DQ10", "cortes_semanales", "P06", futuro["fecha_corte"], "fecha_corte",
                    futuro["fecha_corte"], "Corte con fecha posterior a la fecha de referencia")

        # Corte de un proyecto que no existe en la cartera.
        huerfano = c.loc[self.fila("P11", ultima)].copy()
        huerfano["proyecto_id"] = "P15"
        c.loc[len(c) + 2000] = huerfano
        self.anotar("DQ08", "cortes_semanales", "P15", ULTIMO_CORTE, "proyecto_id", "P15",
                    "Corte de un proyecto que no está en la cartera")

        # Proyecto nuevo cargado dos veces y con datos incompletos.
        base = {
            "proyecto_id": "P13", "nombre": "Centralita telefónica en la nube",
            "area": "Operaciones", "cliente": "Interno", "pm": None,
            "sponsor": "Dirección de Operaciones", "metodologia": "Predictivo",
            "prioridad": "Baja", "fase": "Planificación", "estado": "Propuesto",
            "fecha_inicio_plan": date(2027, 1, 11), "fecha_fin_plan": date(2027, 6, 30),
            "fecha_inicio_real": None, "fecha_fin_real": None, "presupuesto_bac": 55_000.0,
        }
        sin_nombre = base | {"nombre": None}
        fecha_mal = base | {"fecha_fin_plan": date(2026, 6, 30)}
        self.proyectos = pd.concat([self.proyectos, pd.DataFrame([sin_nombre, fecha_mal])],
                                   ignore_index=True)
        self.anotar("DQ01", "proyectos", "P13", None, "nombre", None, "Proyecto sin nombre")
        self.anotar("DQ02", "proyectos", "P13", None, "fecha_fin_plan", date(2026, 6, 30),
                    "Fecha de fin planificada anterior al inicio (año mal tipeado)")
        self.anotar("DQ07", "proyectos", "P13", None, "proyecto_id", "P13",
                    "El proyecto está cargado dos veces")

        cortes = c.sort_values(["proyecto_id", "fecha_corte"], kind="stable").reset_index(drop=True)
        return self.proyectos, cortes, pd.DataFrame(self.registro)


def hitos_con_atraso(hitos: pd.DataFrame) -> pd.DataFrame:
    """P11 tiene un hito vencido sin cumplir aunque el avance general vaya bien."""
    i = hitos.index[hitos["hito_id"] == "P11-H2"][0]
    hitos.loc[i, "nombre"] = "Aprobación del nuevo circuito de compras"
    hitos.loc[i, "fecha_plan"] = date(2026, 10, 23)
    hitos.loc[i, "fecha_real"] = None
    return hitos


def generar(semilla: int = SEMILLA) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(semilla)
    cortes, proyectos, hitos = [], [], []
    for p in CARTERA:
        c, pr, h = simular(p, rng)
        cortes += c
        proyectos.append(pr)
        hitos += h

    riesgos = pd.DataFrame(RIESGOS, columns=["proyecto_id", "descripcion", "probabilidad",
                                             "impacto", "estado"])
    riesgos.insert(0, "riesgo_id", [f"R{i:02d}" for i in range(1, len(riesgos) + 1)])
    riesgos["responsable"] = riesgos["proyecto_id"].map({p.proyecto_id: p.pm for p in CARTERA})

    proyectos_df, cortes_df, errores = Sembrador(pd.DataFrame(proyectos),
                                                 pd.DataFrame(cortes)).sembrar()
    return {
        "proyectos": proyectos_df,
        "cortes_semanales": cortes_df,
        "hitos": hitos_con_atraso(pd.DataFrame(hitos)),
        "riesgos": riesgos,
        "errores_sembrados": errores,
    }


def guardar(tablas: dict[str, pd.DataFrame], raiz: Path = RAIZ) -> None:
    for nombre, df in tablas.items():
        carpeta = raiz / "data" / ("control" if nombre == "errores_sembrados" else "raw")
        carpeta.mkdir(parents=True, exist_ok=True)
        df.to_csv(carpeta / f"{nombre}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    args = parser.parse_args()
    tablas = generar(args.semilla)
    guardar(tablas)
    for nombre, df in tablas.items():
        print(f"{nombre:<18} {len(df):>4} filas")


if __name__ == "__main__":
    main()
