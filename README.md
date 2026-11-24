# Tablero PMO de desvíos y semáforo de cartera

> **Datos simulados.** La empresa (Norvia Operaciones S.L.), sus clientes, proyectos y personas son ficticios. El caso muestra cómo armar el reporte de una PMO, no una experiencia real en una.

Tablero que cada semana responde qué proyectos de la cartera se están desviando en plazo y costo, cuánto, por qué y qué tan confiable es el dato. Usa valor ganado (EVM, PMBOK), tolerancias con gestión por excepción (PRINCE2) y un control de calidad del dato que pone en gris los proyectos con errores bloqueantes.

## Estado

- [x] Estructura del repo y umbrales del semáforo (`umbrales.yaml`)
- [x] Generador del portafolio ficticio con errores de carga sembrados
- [x] ETL a SQLite
- [x] Motor de calidad del dato (DQ01–DQ12) con cuarentena e índice de calidad
- [x] Cálculo EVM y semáforo con motivo en texto
- [x] Integración continua (GitHub Actions)
- [ ] Tablero (Looker Studio / Power BI)
- [ ] Metodología en Confluence/Notion
- [ ] API y app web

## Datos

`python -m pmo.generar_datos` escribe, con semilla fija (42):

| Archivo | Contenido |
|---|---|
| `data/raw/proyectos.csv` | 12 proyectos con presupuesto (BAC) y fechas plan/real, más un proyecto nuevo mal cargado (P13) |
| `data/raw/cortes_semanales.csv` | 26 cortes semanales (22/05 al 13/11/2026): avance planificado, avance real y costo acumulado |
| `data/raw/hitos.csv` | 4 hitos por proyecto, plan vs. real |
| `data/raw/riesgos.csv` | Riesgos con probabilidad e impacto |
| `data/control/errores_sembrados.csv` | Los 13 errores de carga plantados a propósito, al menos uno por cada regla de calidad |

Cada proyecto tiene un comportamiento elegido para que el tablero tenga algo que contar:

| Proyecto | Comportamiento |
|---|---|
| P01 Automatización de facturas | En control (no envió el último corte) |
| P02 Migración de CRM | Atrasado, costo en línea |
| P03 Integración ERP–e-commerce | Atrasado y con sobrecosto |
| P04 Portal de autoservicio | Sobrecosto, plazo en línea |
| P05 Sistema de tickets | Se recupera tras replanificar |
| P06 Cuadro de mando comercial | Adelantado |
| P07 Onboarding digital | Se degrada de verde a rojo en 6 semanas |
| P08 Rutas de reparto | Últimos 2 cortes con errores bloqueantes (gris) |
| P09 Firma electrónica | Cerrado en plazo |
| P10 Data warehouse financiero | El mayor presupuesto, con sobrecosto |
| P11 Proceso de compras | En control, con un hito vencido |
| P12 Pasarela de pagos | Arrancó 5 semanas tarde |

## Calidad del dato

`python -m pmo.pipeline` lee los CSV, corre los 12 controles y guarda todo en `data/pmo.sqlite` (más `data/processed/errores_calidad.csv` y `calidad_por_corte.csv`).

| Código | Control | Severidad |
|---|---|---|
| DQ01 | Campo obligatorio vacío o con formato inválido | Bloqueante |
| DQ02 | Fecha de fin planificada anterior al inicio | Bloqueante |
| DQ03 | Avance fuera de 0–100 % | Bloqueante |
| DQ04 | El avance real baja respecto del corte anterior | Advertencia |
| DQ05 | El costo acumulado baja respecto del corte anterior | Bloqueante |
| DQ06 | Costo negativo | Bloqueante |
| DQ07 | Proyecto o corte cargado dos veces | Bloqueante |
| DQ08 | Corte de un proyecto que no está en la cartera | Bloqueante |
| DQ09 | Proyecto activo sin corte en los últimos 7 días | Advertencia |
| DQ10 | Fecha de corte posterior a la fecha de referencia | Bloqueante |
| DQ11 | Avance informado antes del inicio real | Advertencia |
| DQ12 | Más de 2 cortes seguidos con costo y sin avance | Advertencia |

- **Nada se borra.** Los registros con errores bloqueantes pasan a tablas de cuarentena y su corte queda bloqueado (gris en el semáforo). Las advertencias se informan, pero el corte sigue en el cálculo.
- **Los controles entre cortes (DQ04, DQ05, DQ12) comparan sólo contra cortes válidos**, para que un error no se cuente dos veces.
- **Índice de calidad por corte:** 100 − 10 por cada bloqueante − 3 por cada advertencia.
- Sobre el dataset del caso encuentra los 13 errores sembrados y ningún otro (hay un test que lo verifica).

## Desvíos y semáforo

Por cada corte válido se calculan los indicadores de valor ganado: PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC, TCPI y la fecha de fin prevista (duración planificada ÷ SPI). Cuando un divisor es 0, el índice queda vacío en lugar de infinito.

El semáforo usa las tolerancias de `umbrales.yaml`. Plazo (SPI), costo (CPI), fecha de fin prevista e hitos vencidos reciben cada uno un color, y el proyecto toma el peor. El motivo queda escrito, por ejemplo `SPI 0,77 < 0,85; CPI 0,86 < 0,95`. Un corte con errores bloqueantes queda en **gris**.

Al 13/11/2026:

| Color | Proyectos |
|---|---|
| Verde | P01, P05, P06, P09 |
| Ámbar | P11 (hito vencido hace 21 días) |
| Rojo | P02, P03, P04, P07, P10, P12 |
| Gris | P08 |

Los resultados quedan en la tabla `indicadores` de `data/pmo.sqlite` y en `data/processed/indicadores.csv`.

## Cómo correrlo

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pmo.generar_datos
.venv/bin/python -m pmo.pipeline
.venv/bin/pytest
```
