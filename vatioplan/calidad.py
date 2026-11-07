"""
calidad.py — Calidad de los datos y análisis exploratorio (EDA).

Cada hallazgo del EDA se conecta con una decisión de diseño del modelo o del optimizador:

  Hallazgo                                         → Decisión
  ------------------------------------------------   ---------------------------------------------
  El precio se publica con ~3 días de retraso       → todas las variables con rezago ≥ 7 días
  Fuerte patrón semanal (autocorrelación a 168 h)   → ancla = promedio de la misma hora 1–4 semanas
  El nivel cambia por régimen hidrológico           → no pronosticar el precio absoluto; corregir el ancla
  Distribución sesgada con picos                    → pérdida absolute_error (MAE), robusta a picos
  Diferencia pico/valle grande dentro del día       → hay valor en mover cargas de hora
  Embalses y precio correlacionados (negativo)      → la hidrología explica el régimen, no la hora
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VARIABLES = {"precio": ("Precio de bolsa nacional (COP/kWh)", "SIMEM EC6945 · horario"),
             "vol_util_pct": ("Volumen útil de embalses (%)", "API XM PorcVoluUtilDiar · diario"),
             "aportes_gwh": ("Aportes hídricos (GWh/día)", "API XM AporEner · diario"),
             "oni": ("Índice ONI (El Niño/La Niña)", "NOAA CPC · mensual")}


def reporte_calidad(df: pd.DataFrame) -> pd.DataFrame:
    """Faltantes, cobertura, duplicados, rango y valores atípicos por variable."""
    idx_completo = pd.date_range(df.index.min(), df.index.max(), freq="h")
    filas = []
    for col, (nombre, fuente) in VARIABLES.items():
        if col not in df:
            filas.append({"Variable": nombre, "Fuente": fuente, "Estado": "No disponible"})
            continue
        s = df[col]
        validos = s.dropna()
        q1, q3 = validos.quantile([0.25, 0.75]) if len(validos) else (np.nan, np.nan)
        atipicos = int(((validos > q3 + 3 * (q3 - q1)) | (validos < q1 - 3 * (q3 - q1))).sum()) if len(validos) else 0
        filas.append({
            "Variable": nombre, "Fuente": fuente,
            "Desde": f"{validos.index.min():%Y-%m-%d}" if len(validos) else "—",
            "Hasta": f"{validos.index.max():%Y-%m-%d %H:%M}" if len(validos) else "—",
            "Faltantes (%)": round(100 * s.isna().mean(), 2),
            "Mín": round(float(validos.min()), 1) if len(validos) else np.nan,
            "Mediana": round(float(validos.median()), 1) if len(validos) else np.nan,
            "Máx": round(float(validos.max()), 1) if len(validos) else np.nan,
            "Atípicos (3×IQR)": atipicos,
            "Ceros o negativos": int((validos <= 0).sum()),
            "Estado": "OK" if len(validos) and s.isna().mean() < 0.05 else "Revisar",
        })
    t = pd.DataFrame(filas)
    t.attrs["horas_esperadas"] = len(idx_completo)
    t.attrs["horas_faltantes_indice"] = int(len(idx_completo.difference(df.index)))
    t.attrs["duplicados"] = int(df.index.duplicated().sum())
    return t


def huecos_precio(df: pd.DataFrame) -> pd.DataFrame:
    """Bloques de horas sin precio (para documentar y no inventar datos)."""
    falta = df["precio"].isna()
    if not falta.any():
        return pd.DataFrame(columns=["Inicio", "Fin", "Horas"])
    grupos = (falta != falta.shift()).cumsum()[falta]
    filas = [{"Inicio": g.index.min(), "Fin": g.index.max(), "Horas": len(g)} for _, g in falta[falta].groupby(grupos)]
    return pd.DataFrame(filas).sort_values("Horas", ascending=False)


def perfil_horario_por_regimen(df: pd.DataFrame) -> pd.DataFrame:
    """Precio promedio por hora del día en meses baratos, normales y de escasez."""
    p = df["precio"].dropna()
    mensual = p.resample("MS").mean()
    q1, q2 = mensual.quantile([1 / 3, 2 / 3])
    regimen_mes = pd.cut(mensual, [-np.inf, q1, q2, np.inf], labels=["Barato", "Normal", "Escasez"])
    reg = regimen_mes.reindex(p.index.to_period("M").to_timestamp()).values
    return pd.DataFrame({"precio": p.values, "hora": p.index.hour, "regimen": reg}) \
        .groupby(["hora", "regimen"], observed=True)["precio"].mean().unstack()


def mapa_hora_dia(df: pd.DataFrame, dias: int = 365) -> pd.DataFrame:
    """Precio relativo (precio / promedio del día) por hora y día de la semana, último año."""
    p = df["precio"].dropna()
    p = p[p.index >= p.index.max() - pd.Timedelta(days=dias)]
    rel = p / p.groupby(p.index.date).transform("mean")
    t = pd.DataFrame({"rel": rel.values, "hora": rel.index.hour, "dia": rel.index.dayofweek})
    m = t.groupby(["dia", "hora"])["rel"].mean().unstack()
    m.index = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return m


def cifras_eda(df: pd.DataFrame) -> dict:
    """Cifras clave del análisis exploratorio (las usan la presentación y el informe)."""
    p = df["precio"].dropna()
    ultimo = p.index.max()
    anio = p[p.index >= ultimo - pd.Timedelta(days=365)]
    diario = anio.groupby(anio.index.date)
    mensual = p.resample("MS").mean()
    perfil = anio.groupby(anio.index.hour).mean()
    c = {"ultimo": f"{ultimo:%Y-%m-%d %H:%M}",
         "ratio_pico_valle": float((diario.max() / diario.min().clip(lower=1)).median()),
         "acf24": float(p.autocorr(24)), "acf168": float(p.autocorr(168)),
         "mensual_min": float(mensual.min()), "mensual_max": float(mensual.max()),
         "mes_min": f"{mensual.idxmin():%Y-%m}", "mes_max": f"{mensual.idxmax():%Y-%m}",
         "asimetria": float(p.skew()), "hora_mas_cara": int(perfil.idxmax()), "hora_mas_barata": int(perfil.idxmin()),
         "corr_embalses": None}
    if "vol_util_pct" in df and df["vol_util_pct"].notna().sum() > 100:
        c["corr_embalses"] = float(p.resample("D").mean().corr(df["vol_util_pct"].resample("D").mean()))
    return c


def hallazgos(df: pd.DataFrame) -> list[dict]:
    """Cifras del EDA y la decisión de diseño que justifica cada una."""
    p = df["precio"].dropna()
    ultimo = p.index.max()
    c = cifras_eda(df)
    ratio, acf24, acf168 = c["ratio_pico_valle"], c["acf24"], c["acf168"]
    mensual = p.resample("MS").mean()
    salida = [
        {"Hallazgo": f"El dato más reciente es del {ultimo:%d-%b-%Y %H:%M}: el precio llega con días de retraso.",
         "Decisión": "Todas las variables usan información de hace 7 días o más (sin fuga de datos)."},
        {"Hallazgo": f"En el último año, la hora más cara del día cuesta {ratio:.1f} veces la más barata (mediana).",
         "Decisión": "Mover consumo de hora tiene valor económico: es el problema que resuelve VatioPlan."},
        {"Hallazgo": f"Autocorrelación del precio: {acf24:.2f} a 24 h y {acf168:.2f} a 168 h (misma hora, semana antes).",
         "Decisión": "El ancla del modelo es el promedio de la misma hora en las últimas semanas."},
        {"Hallazgo": f"El promedio mensual va de {mensual.min():,.0f} a {mensual.max():,.0f} COP/kWh "
                     f"({mensual.max() / max(mensual.min(), 1):.1f}×): el nivel cambia por régimen.",
         "Decisión": "No se pronostica el precio absoluto; el GB corrige un ancla reciente que trae el régimen."},
        {"Hallazgo": f"Asimetría de {p.skew():.1f}: picos ocasionales muy altos.",
         "Decisión": "Pérdida absolute_error (MAE) y métricas robustas; se reporta también el acierto de horas baratas."},
    ]
    if "vol_util_pct" in df and df["vol_util_pct"].notna().sum() > 100:
        diario_p = p.resample("D").mean()
        emb = df["vol_util_pct"].resample("D").mean()
        corr = diario_p.corr(emb)
        salida.append({"Hallazgo": f"Correlación precio diario vs. embalses: {corr:.2f}.",
                       "Decisión": "La hidrología explica el nivel (régimen), no la forma horaria; se deja como "
                                   "contexto y en el candidato con todas las variables."})
    return salida
