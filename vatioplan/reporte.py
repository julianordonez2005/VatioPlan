"""
reporte.py — Corre TODO y deja la evidencia lista para la presentación y el informe:

  reporte/metricas.json   → todas las cifras (las leen la app, la presentación y el informe)
  reporte/figuras/*.png   → gráficas de EDA, validación, backtest y planes
  reporte/*.csv           → tablas completas (calidad, rejilla, errores, walk-forward, LLM)

Uso:  python -m vatioplan.reporte
      python -m vatioplan.reporte --guardar-params   (además guarda los hiperparámetros elegidos)
Luego: python entregables/construir_presentacion.py  y  python entregables/construir_informe.py
"""
from __future__ import annotations

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import calidad, eval_llm, validacion  # noqa: E402
from .casos_prueba import casos_optimizador  # noqa: E402
from .perfiles import ahorro_backtest, etiquetas_horas  # noqa: E402
from .pipeline import RAIZ, ejecutar  # noqa: E402

CARPETA = RAIZ / "reporte"
FIG = CARPETA / "figuras"
TINTA, GRIS, ACENTO, ACENTO2, VERDE = "#262D57", "#9AA0B5", "#5468B8", "#B5532A", "#2F7D5B"
plt.rcParams.update({"figure.dpi": 150, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#C9CFEA", "axes.labelcolor": TINTA, "xtick.color": TINTA,
                     "ytick.color": TINTA, "axes.titleweight": "bold", "axes.titlecolor": TINTA,
                     "axes.grid": True, "grid.color": "#EEF0FA", "legend.frameon": False})


def _guardar(fig, nombre):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / nombre, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _marca(fig, fuente):
    if fuente != "REAL":
        fig.text(0.5, 0.5, "DATOS SIMULADOS", ha="center", va="center", fontsize=34, color="#B5532A",
                 alpha=0.18, rotation=20, weight="bold")


def _registros(t: pd.DataFrame) -> list:
    return json.loads(t.reset_index().to_json(orient="records", force_ascii=False, date_format="iso"))


def figuras(r, val, err, wf, fuente):
    df, ev = r["df"], r["evaluacion"]
    # 1. Perfil horario por régimen
    perf = calidad.perfil_horario_por_regimen(df)
    fig, ax = plt.subplots(figsize=(7, 3.4))
    nombres = {"Barato": "Meses baratos", "Normal": "Meses normales", "Escasez": "Meses de escasez"}
    for col, color in zip(perf.columns, [VERDE, GRIS, ACENTO2]):
        ax.plot(perf.index, perf[col], lw=2.2, color=color, label=nombres.get(str(col), str(col)))
    ax.set(xlabel="Hora del día", ylabel="COP/kWh", title="Precio promedio por hora según el régimen")
    ax.set_xticks(range(0, 24, 3)); ax.legend(); _marca(fig, fuente); _guardar(fig, "eda_perfil_regimen.png")
    # 2. Mapa hora x día
    m = calidad.mapa_hora_dia(df)
    fig, ax = plt.subplots(figsize=(7, 2.8))
    im = ax.imshow(m.values, aspect="auto", cmap="Blues")
    ax.set_yticks(range(7)); ax.set_yticklabels(m.index); ax.set_xticks(range(0, 24, 3))
    ax.set(xlabel="Hora", title="Precio relativo al promedio del día (último año)"); ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.03); _marca(fig, fuente); _guardar(fig, "eda_mapa_hora_dia.png")
    # 3. Curva de aprendizaje (sobreajuste)
    c = val["curva"]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(c["Árboles"], c["MAE entrenamiento"], "o-", color=GRIS, label="Entrenamiento")
    ax.plot(c["Árboles"], c["MAE validación"], "o-", color=ACENTO, label="Validación")
    ax.set_xscale("log"); ax.set(xlabel="Número de árboles", ylabel="MAE (COP/kWh)", title="Curva de aprendizaje")
    ax.legend(); _marca(fig, fuente); _guardar(fig, "val_curva_aprendizaje.png")
    # 4. Error por hora
    h = err["por_hora"]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(h.index - 0.2, h["MAE ingenuo"], 0.4, color=GRIS, label="Ingenuo (hace 7 días)")
    ax.bar(h.index + 0.2, h["MAE modelo"], 0.4, color=ACENTO, label="Modelo ML")
    ax.set(xlabel="Hora", ylabel="MAE (COP/kWh)", title="Error por hora del día (conjunto de prueba)")
    ax.set_xticks(range(0, 24, 3)); ax.legend(); _marca(fig, fuente); _guardar(fig, "val_error_por_hora.png")
    # 5. Walk-forward
    if len(wf):
        fig, ax = plt.subplots(figsize=(7, 3.2))
        x = np.arange(len(wf))
        ax.plot(x, wf["MAE ingenuo"], "o-", color=GRIS, label="Ingenuo")
        ax.plot(x, wf["MAE promedio 4 sem."], "o-", color=ACENTO2, label="Promedio 4 semanas")
        ax.plot(x, wf["MAE modelo"], "o-", color=ACENTO, lw=2.5, label="Modelo ML")
        ax.set_xticks(x); ax.set_xticklabels([v[:7] for v in wf["Ventana"]], rotation=0)
        ax.set(ylabel="MAE (COP/kWh)", title="Validación walk-forward: ventanas de 30 días"); ax.legend()
        _marca(fig, fuente); _guardar(fig, "val_walk_forward.png")
    # 6. Pronóstico vs real
    v = pd.DataFrame({"real": ev["real"], "pred": ev["pred"], "base": ev["base"]}).tail(24 * 14)
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(v.index, v["real"], color=TINTA, lw=1.4, label="Real")
    ax.plot(v.index, v["base"], color=GRIS, lw=1, label="Ingenuo")
    ax.plot(v.index, v["pred"], color=ACENTO, lw=1.6, label="Modelo ML")
    ax.set(ylabel="COP/kWh", title="Últimas 2 semanas del conjunto de prueba"); ax.legend(ncol=3)
    _marca(fig, fuente); _guardar(fig, "val_pronostico_vs_real.png")
    # 7. Planes y backtest por perfil
    for tipo, res in r["perfiles"].items():
        perfil, dias = res["perfil"], res["plan"]["dias"]
        if dias:
            d = dias[0]
            fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True)
            x = etiquetas_horas(perfil)
            for ax, (titulo, plan) in zip(axes, [(perfil.nombre_referencia, d["plan_referencia"]),
                                                  ("VatioPlan", d["plan_optimo"])]):
                kw = perfil.potencia_kw(plan)
                abajo = np.zeros(24)
                colores = [ACENTO, ACENTO2, VERDE, "#7A86C9", "#C98B6B", "#6FA88C"]
                i = 0
                for col in kw.columns:
                    color = "#DDE2F5" if col == "Carga base" else colores[i % len(colores)]
                    i += col != "Carga base"
                    ax.bar(range(24), kw[col].values, bottom=abajo, color=color, label=col, width=0.85)
                    abajo += kw[col].values
                ax.axhline(perfil.limite_kw, color=ACENTO2, ls="--", lw=1)
                ax2 = ax.twinx(); ax2.plot(range(24), d["precios"], color=TINTA, lw=2); ax2.grid(False)
                ax2.set_ylabel("COP/kWh")
                ax.set_title(f"{titulo} · ${perfil.costo(plan, d['precios']) / 1e6:,.1f} M")
                ax.set_xticks(range(0, 24, 3)); ax.set_xticklabels(x[::3]); ax.set_ylabel("kW")
            manijas, etiquetas = axes[0].get_legend_handles_labels()
            fig.legend(manijas, etiquetas, loc="lower center", ncol=min(len(etiquetas), 6), fontsize=8,
                       bbox_to_anchor=(0.5, -0.06))
            _marca(fig, fuente); _guardar(fig, f"plan_{tipo}.png")
        bt = res["backtest"]
        if len(bt):
            fig, ax = plt.subplots(figsize=(7, 3))
            ax.plot(bt.index, (bt["costo_actual"] - bt["costo_perfecto"]).cumsum() / 1e6, color=GRIS, ls="--",
                    label="Máximo (precio conocido)")
            ax.plot(bt.index, (bt["costo_actual"] - bt["costo_con_pronostico"]).cumsum() / 1e6, color=VERDE, lw=2.5,
                    label="VatioPlan con pronóstico")
            ax.set(ylabel="Millones de COP", title=f"Ahorro acumulado con precios reales · {perfil.etiqueta.split(' ', 1)[1]}")
            ax.legend(); _marca(fig, fuente); _guardar(fig, f"backtest_{tipo}.png")


def main(guardar_params: bool = False):
    CARPETA.mkdir(exist_ok=True)
    print("1/5 Pipeline completo (datos, modelo, dos usuarios, informes)…")
    r = ejecutar(verbose=False, con_informe=True)
    df, ev, fuente = r["df"], r["evaluacion"], r["fuente"]
    print("2/5 Calidad de datos y EDA…")
    cal = calidad.reporte_calidad(df)
    cal.to_csv(CARPETA / "calidad_datos.csv", index=False)
    print("3/5 Validación: train/validación/test, rejilla, sobreajuste, errores, walk-forward…")
    val = validacion.ajustar(df)
    if guardar_params:
        validacion.guardar_params(val["mejores"])
    err = validacion.analisis_errores(df, ev["real"], ev["pred"], ev["base"])
    wf = validacion.walk_forward(df)
    val["rejilla"].to_csv(CARPETA / "rejilla_hiperparametros.csv", index=False)
    wf.to_csv(CARPETA / "walk_forward.csv", index=False)
    print("4/5 Casos de prueba del optimizador y evaluación del LLM…")
    casos = casos_optimizador()
    casos.to_csv(CARPETA / "casos_optimizador.csv", index=False)
    resumenes = {t: dict(res["resumen"]) for t, res in r["perfiles"].items()}
    llm = eval_llm.evaluar(resumenes.get("fabrica"), resumenes.get("flota"))
    llm["detalle"].to_csv(CARPETA / "eval_llm_detalle.csv", index=False)
    (CARPETA / "eval_llm_ejemplos.json").write_text(json.dumps(llm["ejemplos"], ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    print("5/5 Figuras y métricas…")
    figuras(r, val, err, wf, fuente)

    perfiles = {}
    for tipo, res in r["perfiles"].items():
        bt = res["backtest"]
        real, maximo = ahorro_backtest(bt)
        anual = float((bt["costo_actual"] - bt["costo_con_pronostico"]).sum() / max(len(bt), 1) * 365)
        perfiles[tipo] = {"usuario": res["perfil"].nombre, "etiqueta": res["perfil"].etiqueta,
                          "ahorro_real_backtest_pct": real, "ahorro_maximo_backtest_pct": maximo,
                          "captura_del_potencial_pct": 100 * real / maximo if maximo else None,
                          "ahorro_anual_cop": anual, "dias_backtest": len(bt),
                          "costo_referencia_backtest_cop": float(bt["costo_actual"].sum()),
                          "exposicion_bolsa": res["perfil"].exposicion_bolsa,
                          "comparacion": _registros(res["comparacion"].round(2)),
                          "resumen": res["resumen"], "informe": res["informe"], "proveedor_ia": res["proveedor_ia"]}
    m = ev["metricas"]
    metricas = {
        "fuente": fuente, "ultimo_dato": f"{df.index.max():%Y-%m-%d %H:%M}",
        "horas_totales": int(df["precio"].notna().sum()), "desde": f"{df.index.min():%Y-%m-%d}",
        "calidad": {"tabla": _registros(cal), "duplicados": cal.attrs.get("duplicados"),
                    "horas_faltantes_indice": cal.attrs.get("horas_faltantes_indice"),
                    "faltantes_precio_pct": float(100 * df["precio"].isna().mean())},
        "hallazgos_eda": calidad.hallazgos(df),
        "eda": calidad.cifras_eda(df),
        "modelo_test": m,
        "particion": val["periodos"],
        "hiperparametros": {"elegidos_validacion": val["mejores"], "en_uso": val["actuales"],
                            "top5": _registros(val["rejilla"].head(5).round(2)),
                            "combinaciones": len(val["rejilla"])},
        "sobreajuste": _registros(val["sobreajuste"].round(2)),
        "curva_aprendizaje": _registros(val["curva"].round(2)),
        "sensibilidad_ancla": _registros(val["sensibilidad_ancla"].round(2)),
        "errores": {"por_regimen": _registros(err["por_regimen"]), "por_tipo_dia": _registros(err["por_tipo_dia"]),
                    "peores_dias": _registros(err["peores_dias"]), "sesgo": err["sesgo"]},
        "walk_forward": _registros(wf.round(2)),
        "casos_optimizador": _registros(casos), "casos_optimizador_ok": int((casos["Cumple"] == "✅").sum()),
        "casos_optimizador_total": len(casos),
        "llm": {"hay_key": llm["hay_key"], "resumen": _registros(llm["resumen"])},
        "perfiles": perfiles,
    }
    (CARPETA / "metricas.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    print(f"\nListo: {CARPETA / 'metricas.json'} y {len(list(FIG.glob('*.png')))} figuras en {FIG}")
    print(f"Fuente de datos: {fuente}" + ("  ⚠️ NO usar estas cifras en la presentación" if fuente != "REAL" else ""))
    for tipo, p in perfiles.items():
        print(f"  {p['etiqueta']}: ahorro real {p['ahorro_real_backtest_pct']:.1f}% "
              f"(máximo {p['ahorro_maximo_backtest_pct']:.1f}%) ≈ ${p['ahorro_anual_cop']:,.0f} COP/año")
    return metricas


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardar-params", action="store_true")
    main(ap.parse_args().guardar_params)
