"""
app.py — Aplicación web local de VatioPlan (Streamlit).

Dos tipos de usuario con el mismo pronóstico del precio de bolsa:
  🏭 Fábrica manufacturera  (caso de referencia: Cementos Argos, planta Rioclaro)
  🚌 Flota eléctrica         (caso de referencia: patio Fontibón I – Refugio, SITP Bogotá)

Entradas del usuario: tipo de usuario, equipos o vehículos (tablas editables), exposición a
bolsa, potencia máxima, día a planear, o un archivo de configuración propio.
Salidas: plan horario recomendado, ahorro esperado, reglas verificadas, ahorro real medido
con precios reales e informe redactado con IA.

Ejecutar:   streamlit run app.py
"""
import copy
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from vatioplan import calidad
from vatioplan.casos_prueba import casos_optimizador
from vatioplan.flotas import grupos_desde_tabla, precios_ventana
from vatioplan.informe import generar_informe, plantilla
from vatioplan.perfiles import (ETIQUETAS, PerfilFlota, ahorro_backtest, backtest, cargar_perfil,
                                etiquetas_horas, planear_periodo, resumen_para_ia, ventanas)
from vatioplan.pipeline import RAIZ, ejecutar
from vatioplan.planta import Carga
from vatioplan.validacion import analisis_errores

st.set_page_config(page_title="VatioPlan", page_icon="⚡", layout="wide")
try:   # las keys de .streamlit/secrets.toml también quedan disponibles para el informe
    for _k in ("GEMINI_API_KEY", "GROQ_API_KEY", "GEMINI_MODEL", "GROQ_MODEL"):
        if _k in st.secrets and not os.getenv(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # sin archivo de secretos
    pass
NOTA_PRONOSTICO = "Calculado con el precio pronosticado, no con el precio real."
COLORES = ["#5468B8", "#B5532A", "#2F7D5B", "#7A86C9", "#C98B6B", "#6FA88C", "#262D57"]
RUTA_METRICAS = RAIZ / "reporte" / "metricas.json"


# ---------------- funciones en caché ----------------
@st.cache_resource(show_spinner="Cargando datos, entrenando el modelo y planeando los dos usuarios…")
def correr_pipeline(_clave: int):
    return ejecutar(verbose=False, con_informe=False)


@st.cache_data(show_spinner="Calculando el ahorro real con precios reales (backtest)…")
def backtest_guardado(_perfil, _real, _pred, clave: str):
    """`clave` resume los parámetros del perfil: si cambian, se recalcula."""
    return backtest(_real, _pred, _perfil)


@st.cache_data(show_spinner="La IA está redactando el informe…")
def informe_ia(resumen_json: str):
    return generar_informe(json.loads(resumen_json))


@st.cache_data(show_spinner=False)
def casos_guardados():
    return casos_optimizador()


def metricas_reporte():
    if RUTA_METRICAS.exists():
        try:
            return json.loads(RUTA_METRICAS.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def clave_perfil(perfil) -> str:
    """Representación canónica de los parámetros (tipos normalizados para comparar)."""
    if isinstance(perfil, PerfilFlota):
        datos = [[str(g.nombre), int(g.cantidad), float(g.bateria_kwh), float(g.cargador_kw), int(g.hora_llegada),
                  int(g.hora_salida), float(g.carga_llegada_pct), float(g.carga_salida_pct)] for g in perfil.flota.grupos]
    else:
        datos = [[str(c.nombre), float(c.potencia_kw), int(c.horas_dia), bool(c.continua), sorted(c.permitidas),
                  int(c.inicio_actual), int(c.min_horas_seguidas)] for c in perfil.planta.cargas]
    return json.dumps([perfil.tipo, float(perfil.limite_kw), int(perfil.hora_inicio), datos], default=str)


def grafica_plan(titulo, kw: pd.DataFrame, precios, perfil):
    x = etiquetas_horas(perfil)
    fig = go.Figure()
    i = 0
    for col in kw.columns:
        color = "#DDE2F5" if col == "Carga base" else COLORES[i % len(COLORES)]
        i += col != "Carga base"
        fig.add_bar(x=x, y=kw[col].values, name=col, marker_color=color)
    fig.add_scatter(x=x, y=precios, name="Precio pronosticado (COP/kWh)", yaxis="y2",
                    line=dict(color="#262D57", width=2.5))
    fig.add_hline(y=perfil.limite_kw, line_dash="dash", line_color="#B5532A", annotation_text="Límite de potencia")
    fig.update_layout(barmode="stack", title=titulo, height=380, xaxis_title="Hora", yaxis_title="kW",
                      yaxis2=dict(overlaying="y", side="right", title="COP/kWh", showgrid=False),
                      legend=dict(orientation="h", y=-0.28), margin=dict(t=50, b=10))
    return fig


def precio_medio_pagado(perfil, plan, precios) -> list:
    """Precio promedio ponderado por energía que paga cada equipo o grupo (COP/kWh)."""
    kw = perfil.potencia_kw(plan)
    salida = []
    for e in perfil.elementos:
        energia = kw[e].values
        salida.append(float(np.sum(energia * precios) / energia.sum()) if energia.sum() > 0 else float("nan"))
    return salida


def tabla_equipos(perfil) -> pd.DataFrame:
    return pd.DataFrame([{"Equipo": c.nombre, "Potencia (kW)": c.potencia_kw, "Horas por día": c.horas_dia,
                          "Bloque continuo": c.continua, "Corrida mínima (h)": c.min_horas_seguidas,
                          "Desde (hora)": min(c.permitidas), "Hasta (hora)": max(c.permitidas),
                          "Arranque actual": c.inicio_actual} for c in perfil.planta.cargas])


def equipos_desde_tabla(tabla: pd.DataFrame, originales) -> list:
    motivos = {c.nombre: c.motivo_restriccion for c in originales}
    cargas = []
    for _, f in tabla.dropna(subset=["Equipo"]).iterrows():
        if not str(f["Equipo"]).strip():
            continue
        cargas.append(Carga(nombre=str(f["Equipo"]), potencia_kw=float(f["Potencia (kW)"]),
                            horas_dia=int(f["Horas por día"]), continua=bool(f["Bloque continuo"]),
                            horas_permitidas=[int(f["Desde (hora)"]), int(f["Hasta (hora)"])],
                            inicio_actual=int(f["Arranque actual"]),
                            min_horas_seguidas=max(1, int(f["Corrida mínima (h)"])),
                            motivo_restriccion=motivos.get(str(f["Equipo"]), "")))
    return cargas


def errores_equipos(cargas) -> list[str]:
    errores = []
    for c in cargas:
        disponibles = len(c.permitidas)
        if c.horas_dia > disponibles:
            errores.append(f"«{c.nombre}» pide {c.horas_dia} h pero su ventana solo tiene {disponibles} h.")
        if c.potencia_kw <= 0 or c.horas_dia <= 0:
            errores.append(f"«{c.nombre}»: la potencia y las horas deben ser mayores que cero.")
        if not (0 <= min(c.permitidas) <= max(c.permitidas) <= 23):
            errores.append(f"«{c.nombre}»: las horas deben estar entre 0 y 23.")
    return errores


# ---------------- barra lateral (entradas) ----------------
st.sidebar.title("⚡ VatioPlan")
st.sidebar.caption("Mueve el consumo flexible a las horas más baratas de la bolsa de energía.")
tipo = st.sidebar.radio("1 · Tipo de usuario", ["fabrica", "flota"], format_func=lambda t: ETIQUETAS[t])
if st.sidebar.button("🔄 Actualizar datos y pronóstico", help="Descarga lo nuevo de SIMEM y re-entrena el modelo."):
    st.session_state["clave"] = st.session_state.get("clave", 0) + 1
try:
    r = correr_pipeline(st.session_state.get("clave", 0))
except Exception as e:  # la app no se cae: explica qué pasó
    st.error(f"No se pudo correr el pipeline: {e}")
    st.stop()
ev, pron, m = r["evaluacion"], r["pronostico"], r["evaluacion"]["metricas"]

subido = st.sidebar.file_uploader("Configuración propia (.json, opcional)", type="json",
                                  help="Mismo formato que los archivos de la carpeta config/. "
                                       "El campo \"tipo\" debe ser \"fabrica\" o \"flota\".")
perfil = copy.deepcopy(r["perfiles"][tipo]["perfil"])
if subido is not None:
    try:
        contenido = json.loads(subido.getvalue().decode("utf-8"))
        if contenido.get("tipo", tipo) != tipo:
            st.sidebar.warning(f"El archivo es de tipo «{contenido.get('tipo')}»; cambie el tipo de usuario.")
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                json.dump(contenido, tmp)
            perfil = cargar_perfil(tipo, tmp.name)
            Path(tmp.name).unlink(missing_ok=True)
    except Exception as e:  # el archivo no tiene el formato esperado
        st.sidebar.error(f"No se pudo leer la configuración: {e}")

st.sidebar.subheader("2 · Parámetros")
perfil.exposicion_bolsa = st.sidebar.slider("Exposición a precio de bolsa", 0.0, 1.0, float(perfil.exposicion_bolsa),
                                            0.05, help="Fracción de la energía que se paga a precio de bolsa.",
                                            key=f"exp_{tipo}")
etiqueta_limite = "Potencia máxima contratada (kW)" if tipo == "fabrica" else "Potencia máxima del patio (kW)"
perfil.limite_kw = st.sidebar.number_input(etiqueta_limite, 50, 100000, int(perfil.limite_kw), 100, key=f"lim_{tipo}")
if tipo == "flota":
    perfil.flota.hora_inicio = st.sidebar.selectbox(
        "La ventana de 24 h empieza a las", list(range(24)), index=perfil.hora_inicio,
        format_func=lambda h: f"{h:02d}:00", help="Con 12:00, la carga nocturna queda en una sola ventana.")
st.sidebar.caption(f"Datos: **{r['fuente']}** · último precio publicado {r['df'].index.max():%d-%b-%Y %H:%M}")
if r["fuente"] == "SIMULADO":
    st.warning("⚠️ Sin conexión a SIMEM y sin caché: se muestran DATOS SIMULADOS solo para probar la app.")

# ---------------- encabezado ----------------
st.title(f"{ETIQUETAS[tipo].split(' ', 1)[0]} {perfil.nombre}")
st.caption(perfil.descripcion)

if tipo == "flota":
    with st.expander("🚌 Vehículos del patio (editable: cada fila es un grupo de vehículos iguales)"):
        tabla = st.data_editor(perfil.flota.tabla(), num_rows="dynamic", hide_index=True, width="stretch",
                               key=f"tabla_flota_{subido.name if subido else 'base'}",
                               column_config={
                                   "Cantidad": st.column_config.NumberColumn(min_value=0, step=1),
                                   "Llega (hora)": st.column_config.NumberColumn(min_value=0, max_value=23, step=1),
                                   "Sale (hora)": st.column_config.NumberColumn(min_value=0, max_value=23, step=1),
                                   "Carga al llegar (%)": st.column_config.NumberColumn(min_value=0, max_value=100),
                                   "Carga al salir (%)": st.column_config.NumberColumn(min_value=0, max_value=100)})
    perfil.flota.grupos = grupos_desde_tabla(tabla)
    errores = perfil.errores() if perfil.flota.grupos else ["Agregue al menos un grupo de vehículos."]
else:
    with st.expander("🏭 Equipos flexibles de la planta (editable: cambie potencias, horas o ventanas)"):
        tabla = st.data_editor(tabla_equipos(perfil), num_rows="dynamic", hide_index=True, width="stretch",
                               key=f"tabla_fabrica_{subido.name if subido else 'base'}",
                               column_config={
                                   "Potencia (kW)": st.column_config.NumberColumn(min_value=0, step=50),
                                   "Horas por día": st.column_config.NumberColumn(min_value=1, max_value=24, step=1),
                                   "Corrida mínima (h)": st.column_config.NumberColumn(min_value=1, max_value=24),
                                   "Desde (hora)": st.column_config.NumberColumn(min_value=0, max_value=23, step=1),
                                   "Hasta (hora)": st.column_config.NumberColumn(min_value=0, max_value=23, step=1),
                                   "Arranque actual": st.column_config.NumberColumn(min_value=0, max_value=23)})
        st.caption("La carga base (horno, servicios) no se mueve. Bloque continuo = opera en un solo bloque.")
    perfil.planta.cargas = equipos_desde_tabla(tabla, r["perfiles"][tipo]["perfil"].planta.cargas)
    errores = errores_equipos(perfil.planta.cargas) if perfil.planta.cargas else ["Agregue al menos un equipo."]
if errores:
    for e in errores:
        st.error(e)
    st.stop()

fechas = ventanas(pron, perfil, r["fechas"]) or ventanas(pron, perfil)
if not fechas:
    st.error("El pronóstico no cubre una ventana completa de 24 horas con esta hora de inicio.")
    st.stop()
fecha = st.sidebar.selectbox("3 · Día a planear", fechas,
                             format_func=lambda d: f"{d:%a %d-%b-%Y} desde las {perfil.hora_inicio:02d}:00")
precios = precios_ventana(pron, fecha, perfil.hora_inicio)
ref, opt = perfil.plan_referencia(), perfil.optimizar(precios)
if opt is None:
    st.error("No hay un plan que cumpla todas las reglas con estos parámetros: el patio o la potencia no alcanzan "
             "para cargar a todos a tiempo. Aumente el límite de potencia o el tiempo en el patio.")
    st.stop()
validacion = perfil.validar(opt)
if not validacion["cumple"].all():
    st.warning("⚠️ Con estos parámetros no existe un plan que cumpla todas las reglas (por ejemplo, la potencia "
               "máxima no alcanza para las horas de producción). Se muestra el mejor plan aproximado; revise la "
               "tabla de reglas.")
c_ref, c_opt = perfil.costo(ref, precios), perfil.costo(opt, precios)

# Ahorro real (backtest): si los parámetros son los del archivo, se usa el del pipeline
mismos = clave_perfil(perfil) == clave_perfil(r["perfiles"][tipo]["perfil"])
clave = clave_perfil(perfil)
if mismos:      # la exposición solo escala los COP (no cambia el plan ni el %)
    base = r["perfiles"][tipo]["perfil"].exposicion_bolsa or 1.0
    bt = r["perfiles"][tipo]["backtest"] * (perfil.exposicion_bolsa / base)
elif st.session_state.get("bt_clave") == clave:
    bt = st.session_state["bt"] * (perfil.exposicion_bolsa / (st.session_state["bt_exp"] or 1.0))
else:
    bt = None
ahorro_real, ahorro_max = ahorro_backtest(bt) if bt is not None else (float("nan"), float("nan"))

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Costo estimado · {perfil.nombre_referencia.lower()}", f"${c_ref:,.0f}", help=NOTA_PRONOSTICO)
k2.metric("Costo estimado con VatioPlan", f"${c_opt:,.0f}",
          f"-{(1 - c_opt / c_ref) * 100:.1f}%" if c_ref else None, delta_color="inverse", help=NOTA_PRONOSTICO)
k3.metric("Ahorro estimado del día (COP)", f"${c_ref - c_opt:,.0f}", help=NOTA_PRONOSTICO)
if bt is not None:
    k4.metric("Ahorro real en backtest", f"{ahorro_real:.1f}%", f"máximo posible {ahorro_max:.1f}%",
              help=f"{len(bt)} días del periodo de prueba: cada uno se planea con el pronóstico y se paga con el "
                   "precio real.")
else:
    k4.metric("Ahorro real en backtest", "—", "cambió los parámetros", delta_color="off")
    if k4.button("Recalcular con estos parámetros"):
        st.session_state["bt"] = backtest_guardado(perfil, ev["real"], ev["pred"], clave + str(perfil.exposicion_bolsa))
        st.session_state["bt_clave"] = clave
        st.session_state["bt_exp"] = perfil.exposicion_bolsa
        st.rerun()
st.caption("Los costos del día usan el pronóstico. El ahorro real en backtest planea con el pronóstico y paga con "
           "el precio real de 90 días que el modelo nunca vio.")

tab_plan, tab_datos, tab_pron, tab_val, tab_inf, tab_caso = st.tabs(
    ["📋 Plan del día", "📊 Datos y calidad", "📈 Pronóstico", "🧪 Validación", "🤖 Informe IA",
     "🧾 Caso real y supuestos"])

with tab_plan:
    c1, c2 = st.columns(2)
    c1.plotly_chart(grafica_plan(perfil.nombre_referencia, perfil.potencia_kw(ref), precios, perfil), width="stretch")
    c2.plotly_chart(grafica_plan("Plan VatioPlan (optimizado)", perfil.potencia_kw(opt), precios, perfil),
                    width="stretch")
    pm_opt, pm_ref = precio_medio_pagado(perfil, opt, precios), precio_medio_pagado(perfil, ref, precios)
    horario = pd.DataFrame({perfil.unidad_elemento.capitalize(): perfil.elementos,
                            "Horario VatioPlan": list(perfil.horario(opt).values()),
                            f"Horario {perfil.nombre_referencia.lower()}": list(perfil.horario(ref).values()),
                            "Precio medio VatioPlan (COP/kWh)": np.round(pm_opt, 0),
                            "Precio medio hoy (COP/kWh)": np.round(pm_ref, 0)})
    horario["Por qué"] = [f"Paga {100 * (1 - a / b):.0f}% menos por kWh" if b and a < b - 0.5 else "Ya estaba en horas baratas"
                          for a, b in zip(pm_opt, pm_ref)]
    st.subheader("Horario recomendado y por qué")
    st.dataframe(horario, hide_index=True, width="stretch")
    if tipo == "flota":
        faltante = sum(g.energia_red_kwh() for g in perfil.flota.grupos) - ref.values.sum()
        if faltante > 0.5:
            st.warning(f"Con carga inmediata faltarían {faltante:,.0f} kWh porque el patio se queda corto en las "
                       "horas de llegada. VatioPlan sí completa la carga.")
    st.subheader("Reglas de ingeniería verificadas")
    st.dataframe(validacion[["regla", "elemento", "resultado"]], hide_index=True, width="stretch")
    plan_csv = perfil.potencia_kw(opt).assign(hora=etiquetas_horas(perfil)).set_index("hora")
    st.download_button("⬇️ Descargar plan (CSV, kW por hora)", plan_csv.to_csv().encode("utf-8"),
                       file_name=f"plan_vatioplan_{tipo}_{fecha}.csv")

with tab_datos:
    df = r["df"]
    st.markdown("**Fuentes:** precio de bolsa horario (SIMEM, conjunto EC6945, versión de liquidación más reciente), "
                "embalses y aportes (API de XM) e índice ONI (NOAA). Todo público y gratuito.")
    cal = calidad.reporte_calidad(df)
    st.subheader("Calidad de los datos")
    st.dataframe(cal, hide_index=True, width="stretch")
    st.caption(f"Horas esperadas {cal.attrs['horas_esperadas']:,} · horas sin registro "
               f"{cal.attrs['horas_faltantes_indice']:,} · marcas de tiempo duplicadas {cal.attrs['duplicados']}. "
               "Los faltantes no se rellenan: esas horas no se usan para entrenar ni para evaluar.")
    st.subheader("Hallazgos del análisis exploratorio → decisiones de diseño")
    st.dataframe(pd.DataFrame(calidad.hallazgos(df)), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    perf = calidad.perfil_horario_por_regimen(df)
    c1.plotly_chart(px.line(perf, labels={"value": "COP/kWh", "hora": "Hora", "regimen": "Régimen"},
                            title="Precio promedio por hora según el régimen"), width="stretch")
    mapa = calidad.mapa_hora_dia(df)
    c2.plotly_chart(px.imshow(mapa, color_continuous_scale="Blues", aspect="auto",
                              labels={"x": "Hora", "y": "", "color": "Precio relativo"},
                              title="Precio relativo al promedio del día (último año)"), width="stretch")
    huecos = calidad.huecos_precio(df)
    if len(huecos):
        with st.expander(f"Bloques de horas sin precio ({len(huecos)})"):
            st.dataframe(huecos.head(20), hide_index=True)

with tab_pron:
    hist = r["df"]["precio"].tail(24 * 21)
    fig = go.Figure()
    fig.add_scatter(x=hist.index, y=hist.values, name="Real (SIMEM)", line=dict(color="#262D57"))
    fig.add_scatter(x=pron.index, y=pron.values, name="Pronóstico", line=dict(color="#B5532A", dash="dot"))
    fig.update_layout(height=420, yaxis_title="COP/kWh", title="Precio de bolsa: últimas 3 semanas + pronóstico")
    st.plotly_chart(fig, width="stretch")
    st.caption("El precio real se publica con ~3 días de retraso; el pronóstico cubre ese hueco y los días a planear. "
               "Es el mismo pronóstico para los dos tipos de usuario.")

with tab_val:
    rep = metricas_reporte()
    st.markdown("Se valida **cada componente por separado** (modelo ML, optimizador con reglas, LLM) y **el flujo "
                "completo** (ahorro con precios reales).")
    st.subheader("1 · Modelo de ML en el conjunto de prueba (90 días que el modelo no vio)")
    c1, c2, c3 = st.columns(3)
    c1.metric("MAE modelo", f"{m['mae_modelo']:.0f} COP/kWh", f"{-m['mejora_mae_pct']:.0f}% vs. ingenuo",
              delta_color="inverse")
    c2.metric("Horas baratas acertadas", f"{m['acierto_horas_baratas_modelo']:.0%}",
              f"{(m['acierto_horas_baratas_modelo'] - m['acierto_horas_baratas_base']) * 100:+.0f} pts vs. ingenuo")
    c3.metric("MAPE modelo", f"{m['mape_modelo']:.1f}%", f"ingenuo {m['mape_base']:.1f}%", delta_color="off")
    if rep:
        p = rep["particion"]
        st.caption(f"Entrenamiento: {p['entrenamiento']} · Validación: {p['validacion']} · Prueba: {p['prueba']}. "
                   f"Hiperparámetros elegidos en validación entre {rep['hiperparametros']['combinaciones']} "
                   "combinaciones.")
        c1, c2 = st.columns(2)
        c1.markdown("**Sobreajuste: error en cada conjunto**")
        c1.dataframe(pd.DataFrame(rep["sobreajuste"]).round(1), hide_index=True, width="stretch")
        curva = pd.DataFrame(rep["curva_aprendizaje"]).set_index("Árboles")
        c2.plotly_chart(px.line(curva, log_x=True, markers=True, title="Curva de aprendizaje",
                                labels={"value": "MAE (COP/kWh)", "variable": ""}), width="stretch")
        st.markdown("**Generalización: validación walk-forward (ventanas de 30 días)**")
        st.dataframe(pd.DataFrame(rep["walk_forward"]).round(1), hide_index=True, width="stretch")
    else:
        st.info("Para ver la partición entrenamiento/validación/prueba, la rejilla de hiperparámetros, la curva de "
                "aprendizaje y el walk-forward, ejecute una vez:  `python -m vatioplan.reporte`")

    err = analisis_errores(r["df"], ev["real"], ev["pred"], ev["base"])
    st.markdown("**Análisis de errores en prueba**")
    c1, c2 = st.columns(2)
    c1.dataframe(err["por_regimen"], width="stretch")
    c2.dataframe(err["por_tipo_dia"], width="stretch")
    st.caption(f"Sesgo medio: {err['sesgo']:+.1f} COP/kWh (positivo = el modelo sobreestima). Peores días:")
    st.dataframe(err["peores_dias"], width="stretch")
    ult = pd.DataFrame({"Real": ev["real"], "Modelo ML": ev["pred"], "Ingenuo (hace 7 días)": ev["base"]}).tail(24 * 14)
    st.plotly_chart(px.line(ult, labels={"value": "COP/kWh", "index": ""},
                            title="Últimas 2 semanas del periodo de prueba"), width="stretch")

    st.subheader("2 · Comparación contra alternativas (mismo periodo, ahorro real para este usuario)")
    comparacion = r["perfiles"][tipo]["comparacion"]
    if comparacion is not None:
        t = comparacion.round(1)
        t["MAE (COP/kWh)"] = t["MAE (COP/kWh)"].round(0).astype(int)
        st.dataframe(t, hide_index=True, width="stretch")
    st.caption("El criterio de selección es el ahorro real: a la planta le importa ordenar bien las horas de cada día, "
               "no acertar el valor exacto del precio.")

    st.subheader("3 · Optimizador y reglas: casos de prueba con resultado esperado")
    st.dataframe(casos_guardados(), hide_index=True, width="stretch")

    st.subheader("4 · IA generativa: formato, cifras inventadas, casos borde y consistencia")
    if rep and rep.get("llm"):
        st.dataframe(pd.DataFrame(rep["llm"]["resumen"]), hide_index=True, width="stretch")
        if not rep["llm"]["hay_key"]:
            st.caption("El reporte se generó sin API key: solo se evaluó la plantilla. Con GEMINI_API_KEY se comparan "
                       "el prompt completo, un prompt simple y la plantilla.")
    else:
        st.info("Ejecute `python -m vatioplan.reporte` (con GEMINI_API_KEY) para evaluar el LLM con 6 casos de prueba.")

    st.subheader("5 · Flujo completo: ahorro acumulado con precios reales")
    if bt is not None and len(bt):
        acumulado = pd.DataFrame({"VatioPlan con pronóstico": (bt["costo_actual"] - bt["costo_con_pronostico"]).cumsum(),
                                  "Máximo (precio conocido)": (bt["costo_actual"] - bt["costo_perfecto"]).cumsum()})
        st.plotly_chart(px.line(acumulado, labels={"value": "COP", "fecha": "", "variable": ""}), width="stretch")
    st.markdown("**Límites conocidos:** el modelo aprende de 2023 en adelante y del mercado colombiano; en semanas de "
                "cambio brusco de régimen (inicio de El Niño, racionamiento) el error sube; las potencias y baterías de "
                "los casos son estimaciones públicas; el ahorro solo aplica a la energía expuesta a bolsa.")

with tab_inf:
    plan_periodo = planear_periodo(pron, perfil, fechas)
    bt_inf = bt if bt is not None else r["perfiles"][tipo]["backtest"]
    resumen = resumen_para_ia(plan_periodo, pron, ev, bt_inf, perfil, r["fuente"])
    st.caption("El informe usa los parámetros actuales. La IA solo redacta: las cifras vienen del pipeline y se "
               "verifican (ninguna cifra puede faltar en los datos de entrada).")
    if st.button("✍️ Redactar con IA (Gemini / Groq)"):
        st.session_state[f"ia_{tipo}"] = json.dumps(resumen, ensure_ascii=False, default=str)
    if st.session_state.get(f"ia_{tipo}") == json.dumps(resumen, ensure_ascii=False, default=str):
        texto, proveedor = informe_ia(st.session_state[f"ia_{tipo}"])
    else:
        texto, proveedor = plantilla(resumen), "plantilla (pulse el botón para redactar con IA)"
    st.markdown(texto)
    from vatioplan.verificacion import problemas
    fallas = problemas(texto, resumen)
    st.caption(f"Redactado con: {proveedor}. Verificación automática (formato, cifras y avisos): "
               + ("✅ todas las cifras aparecen en los datos y el formato cumple." if not fallas
                  else "⚠️ " + "; ".join(fallas)))
    st.download_button("⬇️ Descargar informe", texto, file_name=f"informe_vatioplan_{tipo}.md")
    with st.expander("Datos que recibe la IA (JSON)"):
        st.json(resumen)

with tab_caso:
    st.markdown(f"**{perfil.nombre}**\n\n{perfil.descripcion}")
    st.dataframe(perfil.tabla_elementos(), hide_index=True, width="stretch")
    if perfil.supuestos:
        st.info(f"**Supuestos:** {perfil.supuestos}")
    if perfil.fuentes:
        st.markdown("**Fuentes**\n" + "\n".join(f"- {f}" for f in perfil.fuentes))
    st.caption("Para otro cliente: copie el archivo de config/, cambie los valores y súbalo en la barra lateral.")
