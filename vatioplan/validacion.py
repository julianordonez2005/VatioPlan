"""
validacion.py — Validación rigurosa del componente de Machine Learning.

  1. Partición temporal en tres conjuntos (nunca se mezclan horas del futuro con el pasado):
        ENTRENAMIENTO  → todo hasta 180 días antes del último dato
        VALIDACIÓN     → días 180 a 91 antes del final (para elegir hiperparámetros)
        PRUEBA (test)  → últimos 90 días (se usan UNA sola vez, al final)
  2. Ajuste de hiperparámetros: rejilla evaluada en VALIDACIÓN (MAE y horas baratas).
  3. Sensibilidad del ancla: promedio de 1, 2, 3, 4 y 6 semanas.
  4. Sobreajuste: error en entrenamiento vs. validación vs. prueba, y curva de aprendizaje
     (error según el número de árboles).
  5. Análisis de errores en PRUEBA: por hora, por tipo de día, por régimen de precio
     (barato / normal / escasez) y peores días.
  6. Generalización: validación "walk-forward" en varias ventanas de 30 días hacia atrás,
     comparando siempre contra el ingenuo y el promedio de 4 semanas.

Uso:  python -m vatioplan.validacion            (imprime los resultados)
      python -m vatioplan.validacion --guardar  (además guarda los mejores hiperparámetros
                                                 en config/modelo.json)
"""
from __future__ import annotations

import argparse
import itertools
import json
from datetime import date

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from .modelo import (COLUMNAS_MODELO, PARAMS, RUTA_PARAMS, _dataset, acierto_horas_baratas, mape, nuevo_modelo,
                     promedio_semanas)
from .features import construir_features

DIAS_VALIDACION = 90
DIAS_PRUEBA = 90
REJILLA = {"learning_rate": [0.03, 0.05, 0.1], "max_iter": [100, 400], "min_samples_leaf": [20, 40, 100],
           "max_leaf_nodes": [15, 31]}


def particion(y: pd.Series, dias_val: int = DIAS_VALIDACION, dias_prueba: int = DIAS_PRUEBA):
    fin = y.index.max()
    corte_prueba = fin - pd.Timedelta(days=dias_prueba)
    corte_val = corte_prueba - pd.Timedelta(days=dias_val)
    ent = y.index <= corte_val
    val = (y.index > corte_val) & (y.index <= corte_prueba)
    pru = y.index > corte_prueba
    return ent, val, pru


def _metricas(real: pd.Series, pred: pd.Series) -> dict:
    pred = pd.Series(np.asarray(pred), index=real.index)
    return {"MAE": float(mean_absolute_error(real, pred)), "MAPE (%)": mape(real, pred),
            "Sesgo (COP/kWh)": float((pred - real).mean()),
            "Horas baratas (%)": acierto_horas_baratas(real, pred) * 100}


def _rango(mask, idx) -> str:
    i = idx[mask]
    return f"{i.min():%Y-%m-%d} a {i.max():%Y-%m-%d}"


def ajustar(df: pd.DataFrame) -> dict:
    """Rejilla de hiperparámetros elegida con VALIDACIÓN; la prueba se mira solo al final."""
    X, y, ancla = _dataset(df)
    ent, val, pru = particion(y)
    Xm = X[COLUMNAS_MODELO]
    resid = y - ancla

    filas = []
    for valores in itertools.product(*REJILLA.values()):
        params = dict(zip(REJILLA.keys(), valores))
        m = nuevo_modelo(params=params).fit(Xm[ent], resid[ent])
        pred_val = ancla[val] + m.predict(Xm[val])
        met = _metricas(y[val], pred_val)
        filas.append({**params, "MAE validación": met["MAE"], "Horas baratas validación (%)": met["Horas baratas (%)"]})
    rejilla = pd.DataFrame(filas).sort_values("MAE validación").reset_index(drop=True)
    mejores = {k: (float(v) if k == "learning_rate" else int(v)) for k, v in rejilla.iloc[0][list(REJILLA)].items()}
    actual = {k: PARAMS[k] for k in REJILLA}

    # Sobreajuste: el modelo elegido en entrenamiento / validación / prueba (reentrenado con ent+val)
    m_ent = nuevo_modelo(params=mejores).fit(Xm[ent], resid[ent])
    m_final = nuevo_modelo(params=mejores).fit(Xm[ent | val], resid[ent | val])
    sobreajuste = pd.DataFrame([
        {"Conjunto": "Entrenamiento", "Periodo": _rango(ent, y.index), "Horas": int(ent.sum()),
         **_metricas(y[ent], ancla[ent] + m_ent.predict(Xm[ent]))},
        {"Conjunto": "Validación", "Periodo": _rango(val, y.index), "Horas": int(val.sum()),
         **_metricas(y[val], ancla[val] + m_ent.predict(Xm[val]))},
        {"Conjunto": "Prueba (test)", "Periodo": _rango(pru, y.index), "Horas": int(pru.sum()),
         **_metricas(y[pru], ancla[pru] + m_final.predict(Xm[pru]))},
    ])

    # Curva de aprendizaje: número de árboles
    curva = []
    for n in [10, 25, 50, 100, 200, 400, 800]:
        m = nuevo_modelo(params={**mejores, "max_iter": n}).fit(Xm[ent], resid[ent])
        curva.append({"Árboles": n,
                      "MAE entrenamiento": float(mean_absolute_error(y[ent], ancla[ent] + m.predict(Xm[ent]))),
                      "MAE validación": float(mean_absolute_error(y[val], ancla[val] + m.predict(Xm[val])))})

    # Sensibilidad del ancla (sin corrección, en validación)
    sens = []
    for semanas in [1, 2, 3, 4, 6]:
        a = promedio_semanas(df["precio"], semanas).reindex(y.index)
        ok = val & a.notna().values
        sens.append({"Semanas del promedio": semanas, **_metricas(y[ok], a[ok])})

    return {"rejilla": rejilla, "mejores": mejores, "actuales": actual, "sobreajuste": sobreajuste,
            "curva": pd.DataFrame(curva), "sensibilidad_ancla": pd.DataFrame(sens),
            "periodos": {"entrenamiento": _rango(ent, y.index), "validacion": _rango(val, y.index),
                         "prueba": _rango(pru, y.index)}}


def regimenes(df: pd.DataFrame, indice: pd.DatetimeIndex) -> pd.Series:
    """Régimen de cada hora según el precio promedio de los 28 días previos (sin mirar el futuro).
    Umbrales: terciles históricos de ese promedio → barato / normal / escasez."""
    nivel = df["precio"].rolling(24 * 28, min_periods=24 * 7).mean().shift(1)
    q1, q2 = nivel.quantile([1 / 3, 2 / 3])
    etiqueta = pd.cut(nivel, [-np.inf, q1, q2, np.inf], labels=["Barato", "Normal", "Escasez"])
    return etiqueta.reindex(indice)


def analisis_errores(df: pd.DataFrame, real: pd.Series, pred: pd.Series, base: pd.Series) -> dict:
    """Dónde se equivoca el modelo en el periodo de PRUEBA."""
    d = pd.DataFrame({"real": real, "pred": pred, "base": base}).dropna()
    d["err"] = (d["pred"] - d["real"]).abs()
    d["err_base"] = (d["base"] - d["real"]).abs()
    X = construir_features(df).reindex(d.index)
    d["hora"] = d.index.hour
    d["tipo_dia"] = np.select([X["dia_no_laboral"] == 1, d.index.dayofweek == 5], ["Domingo o festivo", "Sábado"],
                              "Laboral")
    d["regimen"] = regimenes(df, d.index).astype(str)

    def tabla(col):
        g = d.groupby(col)
        t = pd.DataFrame({"Horas": g.size(), "Precio medio": g["real"].mean(), "MAE modelo": g["err"].mean(),
                          "MAE ingenuo": g["err_base"].mean()})
        t["Error relativo (%)"] = 100 * t["MAE modelo"] / t["Precio medio"]
        return t.round(1)

    dias = d.groupby(d.index.date).agg(precio_medio=("real", "mean"), mae=("err", "mean"),
                                       pico_real=("real", "max"))
    peores = dias.sort_values("mae", ascending=False).head(5).round(1)
    peores.index.name = "Día"
    return {"por_hora": tabla("hora"), "por_tipo_dia": tabla("tipo_dia"), "por_regimen": tabla("regimen"),
            "peores_dias": peores, "sesgo": float((d["pred"] - d["real"]).mean())}


def walk_forward(df: pd.DataFrame, ventanas: int = 6, dias: int = 30) -> pd.DataFrame:
    """Varios cortes hacia atrás: entrena con todo lo anterior y prueba 30 días.
    Muestra si el desempeño se sostiene en distintos momentos del mercado."""
    X, y, ancla = _dataset(df)
    Xm, resid = X[COLUMNAS_MODELO], y - ancla
    fin = y.index.max()
    filas = []
    for k in range(ventanas, 0, -1):
        ini = fin - pd.Timedelta(days=dias * k)
        hasta = ini + pd.Timedelta(days=dias)
        ent = y.index <= ini
        pru = (y.index > ini) & (y.index <= hasta)
        if pru.sum() < 24 * 7 or ent.sum() < 24 * 180:
            continue
        m = nuevo_modelo().fit(Xm[ent], resid[ent])
        real = y[pru]
        pred = ancla[pru] + m.predict(Xm[pru])
        ingenuo = X.loc[pru, "precio_lag_168h"]
        filas.append({"Ventana": f"{real.index.min():%Y-%m-%d} a {real.index.max():%Y-%m-%d}",
                      "Precio medio": float(real.mean()),
                      "MAE modelo": float(mean_absolute_error(real, pred)),
                      "MAE promedio 4 sem.": float(mean_absolute_error(real, ancla[pru])),
                      "MAE ingenuo": float(mean_absolute_error(real, ingenuo)),
                      "Horas baratas modelo (%)": acierto_horas_baratas(real, pred) * 100,
                      "Horas baratas ingenuo (%)": acierto_horas_baratas(real, ingenuo) * 100})
    t = pd.DataFrame(filas)
    if len(t):
        t["Gana al ingenuo"] = np.where(t["MAE modelo"] < t["MAE ingenuo"], "Sí", "No")
    return t


def guardar_params(mejores: dict) -> None:
    contenido = {"hiperparametros": {**PARAMS, **mejores},
                 "elegidos_con": "MAE en el conjunto de validación (vatioplan/validacion.py)",
                 "fecha": f"{date.today()}"}
    RUTA_PARAMS.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    from .datos import cargar_datos
    from .modelo import evaluar
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardar", action="store_true", help="Guardar los mejores hiperparámetros")
    args = ap.parse_args()
    pd.set_option("display.width", 160)
    df = cargar_datos("2023-01-01")
    print("Fuente:", df.attrs.get("fuente"))
    r = ajustar(df)
    print("\nPeriodos:", r["periodos"])
    print("\nMejores 8 combinaciones (validación):\n", r["rejilla"].head(8).round(2))
    print("\nSobreajuste:\n", r["sobreajuste"].round(1))
    print("\nCurva de aprendizaje:\n", r["curva"].round(1))
    print("\nSensibilidad del ancla:\n", r["sensibilidad_ancla"].round(1))
    ev = evaluar(df)
    e = analisis_errores(df, ev["real"], ev["pred"], ev["base"])
    print("\nErrores por régimen:\n", e["por_regimen"])
    print("\nPeores días:\n", e["peores_dias"])
    print("\nWalk-forward:\n", walk_forward(df).round(1))
    if args.guardar:
        guardar_params(r["mejores"])
        print(f"\nGuardado en {RUTA_PARAMS}: {r['mejores']}")
