"""
casos_prueba.py — Casos de prueba del componente de reglas y optimización, con el
resultado esperado definido ANTES de correrlos. Los usa tests/ (pytest) y el reporte.

Cada caso es pequeño y verificable a mano, e incluye casos difíciles (sin solución posible,
potencia al límite, ventanas que cruzan la medianoche).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .flotas import GrupoVehiculos, carga_inmediata, optimizar_carga, verificar_plan
from .perfiles import cargar_perfil
from .planta import Carga, Planta, optimizar_dia, validar_plan

PRECIO_PICO = np.array([300.0] * 24)
PRECIO_PICO[17:22] = 900.0            # pico de la tarde
PRECIO_PICO[0:5] = 150.0              # madrugada barata


def _planta(cargas, pmax=10000):
    return Planta(nombre="prueba", potencia_maxima_kw=pmax,
                  base={"turno_operado": 1000, "noche": 1000, "inicio_turno": 6, "fin_turno": 22}, cargas=cargas)


def _caso(nombre, esperado, obtenido: bool, detalle=""):
    return {"Caso": nombre, "Resultado esperado": esperado, "Cumple": "✅" if obtenido else "❌", "Detalle": detalle}


def casos_optimizador() -> pd.DataFrame:
    filas = []

    # F1: un molino de 5 h sin restricciones debe ir a las 5 horas más baratas (00–05)
    p = _planta([Carga("Molino", 1000, 5, False, [0, 23], 18)])
    plan = optimizar_dia(PRECIO_PICO, p)
    horas = list(plan.index[plan["Molino"] == 1])
    filas.append(_caso("F1 · Fábrica: equipo libre de 5 h", "Opera 00:00–05:00 (la madrugada barata)",
                       horas == [0, 1, 2, 3, 4], f"horas elegidas {horas}"))

    # F2: carga continua de 4 h con ventana 6–17: un solo bloque dentro de la ventana
    p = _planta([Carga("Horno", 500, 4, True, [6, 17], 8)])
    plan = optimizar_dia(PRECIO_PICO, p)
    horas = list(plan.index[plan["Horno"] == 1])
    ok = len(horas) == 4 and horas[-1] - horas[0] == 3 and min(horas) >= 6 and max(horas) <= 17
    filas.append(_caso("F2 · Fábrica: bloque continuo en ventana", "4 h seguidas entre 06:00 y 17:00",
                       ok, f"horas elegidas {horas}"))

    # F3: corrida mínima de 4 h con 6 h requeridas: ningún bloque menor a 4 h
    p = _planta([Carga("Molino", 1000, 6, False, [0, 23], 0, min_horas_seguidas=4)])
    plan = optimizar_dia(PRECIO_PICO, p)
    v = validar_plan(plan, p)
    filas.append(_caso("F3 · Fábrica: corrida mínima (R5)", "Bloques de 4 h o más; R1–R5 cumplen",
                       bool(v["cumple"].all()), f"{int(plan['Molino'].sum())} h programadas"))

    # F4: potencia máxima impide prender dos molinos a la vez → no se superan los kW
    p = _planta([Carga("M1", 3000, 5, False, [0, 23], 0), Carga("M2", 3000, 5, False, [0, 23], 0)], pmax=4500)
    plan = optimizar_dia(PRECIO_PICO, p)
    pico = float((plan.values * np.array([3000, 3000])).sum(axis=1).max() + 1000)
    filas.append(_caso("F4 · Fábrica: potencia máxima (R4)", "Pico total ≤ 4.500 kW (no operan juntos)",
                       pico <= 4500, f"pico {pico:,.0f} kW"))

    # F5 (difícil): no hay horas suficientes en la ventana → el validador debe detectarlo
    p = _planta([Carga("Trituradora", 900, 8, True, [6, 10], 6)])
    plan = optimizar_dia(PRECIO_PICO, p)
    v = validar_plan(plan, p)
    filas.append(_caso("F5 · Fábrica: caso imposible (8 h en ventana de 5 h)",
                       "El validador marca incumplimiento (no se publica)", not bool(v["cumple"].all()),
                       f"{int((~v['cumple']).sum())} reglas incumplidas detectadas"))

    # B1: grupo de buses que llega 20:00 y sale 05:00 → carga en las horas baratas 00–05
    g = [GrupoVehiculos("Buses", 10, 300, 100, 20, 5, 20, 90)]
    precios_v = np.roll(PRECIO_PICO, -12)              # ventana empieza a las 12:00
    plan = optimizar_carga(precios_v, g, 5000, 12)
    activas = [(h + 12) % 24 for h in plan.index[plan["Buses"] > 0.5]]
    filas.append(_caso("B1 · Flota: carga nocturna", "Carga entre 00:00 y 05:00, no en el pico 20–22",
                       all(h < 5 for h in activas), f"horas con carga {sorted(activas)}"))

    # B2: R1–R4 se cumplen y el costo es ≤ al de cargar apenas llegan
    ref = carga_inmediata(g, 5000, 12)
    v = verificar_plan(plan, g, 5000, 12)
    ok = (v.iloc[0, 3:] == "Sí").all() and float((plan.sum(axis=1) * precios_v).sum()) <= float(
        (ref.sum(axis=1) * precios_v).sum()) + 1e-6
    filas.append(_caso("B2 · Flota: reglas y costo", "R1–R4 cumplen y costo ≤ carga inmediata", bool(ok)))

    # B3 (difícil): el patio no alcanza a cargar a todos → el optimizador lo informa (None)
    g = [GrupoVehiculos("Buses", 40, 300, 150, 2, 4, 10, 95)]
    plan = optimizar_carga(precios_v, g, 3000, 12)
    filas.append(_caso("B3 · Flota: caso imposible (2 h y patio pequeño)", "Sin plan posible: se avisa, no se inventa",
                       plan is None))

    # B4: casos reales completos (Argos Rioclaro y Fontibón I) con precio de pico típico
    fab = cargar_perfil("fabrica")
    plan = fab.optimizar(PRECIO_PICO)
    filas.append(_caso("R1 · Caso Argos Rioclaro", "Todas las reglas cumplen y ahorra frente a la operación actual",
                       bool(fab.validar(plan)["cumple"].all())
                       and fab.costo(plan, PRECIO_PICO) < fab.costo(fab.plan_referencia(), PRECIO_PICO)))
    flo = cargar_perfil("flota")
    pv = np.roll(PRECIO_PICO, -flo.hora_inicio)
    plan = flo.optimizar(pv)
    filas.append(_caso("R2 · Caso patio Fontibón I", "Todas las reglas cumplen y ahorra frente a la carga inmediata",
                       plan is not None and bool(flo.validar(plan)["cumple"].all())
                       and flo.costo(plan, pv) < flo.costo(flo.plan_referencia(), pv)))
    return pd.DataFrame(filas)
