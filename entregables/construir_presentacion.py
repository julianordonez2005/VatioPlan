"""
construir_presentacion.py — Arma la presentación final con las cifras de reporte/metricas.json
y las gráficas de reporte/figuras/, sobre la plantilla del anteproyecto (mismo estilo y fuente).

Uso (desde la raíz del proyecto, después de `python -m vatioplan.reporte`):
    python entregables/construir_presentacion.py
Salida: entregables/VatioPlan_Proyecto_Final.pptx
Si las cifras vienen de datos SIMULADOS, cada diapositiva lleva un aviso rojo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "entregables" / "plantilla_vatioplan.pptx"
SALIDA = RAIZ / "entregables" / "VatioPlan_Proyecto_Final.pptx"
M = json.loads((RAIZ / "reporte" / "metricas.json").read_text(encoding="utf-8"))
FIG = RAIZ / "reporte" / "figuras"

AZUL, TINTA, GRIS, FONDO, LINEA, ROJO, BLANCO = (RGBColor(0x54, 0x68, 0xB8), RGBColor(0x26, 0x2D, 0x57),
                                                  RGBColor(0x5B, 0x65, 0x90), RGBColor(0xEE, 0xF0, 0xFA),
                                                  RGBColor(0xC9, 0xCF, 0xEA), RGBColor(0xB8, 0x53, 0x2F),
                                                  RGBColor(0xFF, 0xFF, 0xFF))
X0, ANCHO = Inches(1.333), Inches(17.33)
SIMULADO = M["fuente"] != "REAL"
TOTAL = 18


# ---------------- formato de números (español) ----------------
def num(v, dec=0):
    if v is None:
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v, dec=1):
    return f"{num(v, dec)} %"


def millones(v):
    return f"${num(v / 1e6, 0)} M" if abs(v) < 1e9 else f"${num(v / 1e9, 1)} mil M"


# ---------------- primitivas de dibujo ----------------
def texto(s, x, y, w, h, t, tam=21, color=TINTA, negrita=False, alinear=PP_ALIGN.LEFT, ancla=MSO_ANCHOR.TOP):
    caja = s.shapes.add_textbox(x, y, w, h)
    tf = caja.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = ancla
    lineas = t if isinstance(t, list) else [t]
    for i, linea in enumerate(lineas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinear
        partes = linea if isinstance(linea, list) else [(linea, negrita)]
        for contenido, neg in partes:
            r = p.add_run()
            r.text = contenido
            r.font.size = Pt(tam)
            r.font.bold = neg
            r.font.name = "Space Mono Bold" if neg else "Space Mono"
            r.font.color.rgb = color
        p.space_after = Pt(tam * 0.35)
    return caja


def rect(s, x, y, w, h, relleno=FONDO, borde=None):
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    r.fill.solid()
    r.fill.fore_color.rgb = relleno
    if borde is None:
        r.line.fill.background()
    else:
        r.line.color.rgb = borde
        r.line.width = Pt(1.5)
    estilo = r._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
    if estilo is not None:                      # sin sombra ni efectos del tema
        r._element.remove(estilo)
    return r


def linea_h(s, x, y, w, color=LINEA):
    ln = s.shapes.add_connector(1, x, y, x + w, y)
    ln.line.color.rgb = color
    ln.line.width = Pt(1.5)


def tarjeta(s, x, y, w, h, etiqueta, cuerpo, oscura=False, tam=19, color_etiqueta=None):
    rect(s, x, y, w, h, AZUL if oscura else FONDO)
    texto(s, x + Inches(0.3), y + Inches(0.25), w - Inches(0.6), Inches(0.4), etiqueta.upper(), 16,
          BLANCO if oscura else (color_etiqueta or AZUL), True)
    texto(s, x + Inches(0.3), y + Inches(0.75), w - Inches(0.6), h - Inches(0.9), cuerpo, tam,
          BLANCO if oscura else TINTA)


def tabla(s, filas, x, y, w, anchos, tam=15, alto_fila=0.42, resaltar_col=None):
    t = s.shapes.add_table(len(filas), len(filas[0]), x, y, w, Inches(alto_fila * len(filas))).table
    total = sum(anchos)
    for j, a in enumerate(anchos):
        t.columns[j].width = int(w * a / total)
    for i, fila in enumerate(filas):
        t.rows[i].height = Inches(alto_fila)
        for j, valor in enumerate(fila):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.08)
            c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = AZUL if i == 0 else (FONDO if i % 2 == 0 else BLANCO)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = str(valor)
            neg = i == 0 or j == 0
            r.font.size = Pt(tam)
            r.font.bold = neg
            r.font.name = "Space Mono Bold" if neg else "Space Mono"
            r.font.color.rgb = BLANCO if i == 0 else (AZUL if resaltar_col == j else TINTA)
    return t


def imagen(s, nombre, x, y, w=None, h=None):
    ruta = FIG / nombre
    if ruta.exists():
        return s.shapes.add_picture(str(ruta), x, y, w, h)
    texto(s, x, y, w or Inches(6), Inches(0.5), f"[falta la figura {nombre}]", 16, ROJO)


def nueva(prs, titulo, n, pie, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    if kicker:
        texto(s, X0, Inches(0.75), ANCHO, Inches(0.4), kicker, 18, AZUL)
    texto(s, X0, Inches(1.15), ANCHO, Inches(1.0), titulo, 54, AZUL, True)
    texto(s, X0, Inches(10.2), Inches(14), Inches(0.45), pie, 16, GRIS)
    texto(s, Inches(16.08), Inches(10.2), Inches(2.58), Inches(0.45), f"{n:02d} / {TOTAL}", 18, AZUL,
          alinear=PP_ALIGN.RIGHT)
    if SIMULADO:
        rect(s, Inches(12.2), Inches(0.35), Inches(6.45), Inches(0.5), ROJO)
        texto(s, Inches(12.3), Inches(0.42), Inches(6.25), Inches(0.4),
              "DATOS SIMULADOS · regenerar con datos reales", 15, BLANCO, True, PP_ALIGN.CENTER)
    return s


def notas(s, t):
    s.notes_slide.notes_text_frame.text = t


def reemplazar(forma, nuevo):
    p = forma.text_frame.paragraphs[0]
    p.runs[0].text = nuevo
    for r in p.runs[1:]:
        r.text = ""
    for extra in forma.text_frame.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)


# ---------------- presentación ----------------
def construir():
    prs = Presentation(str(PLANTILLA))
    ids = prs.slides._sldIdLst
    conservar = {0: "portada", 11: "gracias", 12: "ref1", 13: "ref2"}
    for i, sld in reversed(list(enumerate(list(ids)))):
        if i not in conservar:
            prs.part.drop_rel(sld.rId)
            ids.remove(sld)
    from pptx.opc.packuri import PackURI
    for rId, rel in list(prs.part.rels.items()):        # la plantilla (Google Slides) enlaza notas desde la raíz
        if rel.reltype.endswith("/notesSlide"):
            prs.part.drop_rel(rId)
    for i, diapo in enumerate(prs.slides, 1):          # nombres de parte sin choques con las nuevas
        diapo.part.partname = PackURI(f"/ppt/slides/slide{i}.xml")
    portada, gracias, ref1, ref2 = list(prs.slides)
    formas = {f.name: f for f in portada.shapes}
    reemplazar(formas["TextBox 2"], "Proyecto final")
    reemplazar(formas["TextBox 7"], "Mover el consumo eléctrico flexible a las horas más baratas de la bolsa de energía")
    notas(portada, "(20 s) Buenas. Somos Tomás y Julián. VatioPlan es una aplicación web que pronostica el precio "
                   "de la energía en Colombia hora a hora y, con ese pronóstico, programa el consumo flexible de dos "
                   "tipos de cliente: una fábrica y una flota de buses eléctricos.")
    formas = {f.name: f for f in gracias.shapes}
    reemplazar(formas["TextBox 2"], "Proyecto final")
    reemplazar(formas["TextBox 8"], "Repositorio: github.com/julianordonez2005/VatioPlan · App local: streamlit run app.py")

    P = M["perfiles"]
    fab, flo = P["fabrica"], P["flota"]
    eda, mt = M["eda"], M["modelo_test"]

    # 2 · Problema
    s = nueva(prs, "el problema", 2, "Fuentes: XM, citado por La República (25 jun 2026); cálculo propio con SIMEM")
    texto(s, X0, Inches(2.6), Inches(10.6), Inches(2.2),
          "Las fábricas y las flotas eléctricas consumen por costumbre de turno, sin mirar el precio de la energía, "
          "que cambia cada hora.", 30)
    texto(s, X0, Inches(5.2), Inches(10.6), Inches(1.3),
          [[("Situación concreta. ", True), ("Molinos que arrancan a la misma hora todos los días y buses que se "
                                              "conectan apenas llegan al patio, justo en el pico de la noche.", False)]], 21)
    texto(s, X0, Inches(6.9), Inches(10.6), Inches(1.5),
          [[("Pregunta guía. ", True), ("¿Un pronóstico a 7 días con datos públicos reduce el costo sin sacrificar "
                                         "producción ni dejar un bus sin carga?", False)]], 21, AZUL)
    cifras = [("516,36", "COP/kWh, promedio de mayo de 2026"), ("+84,3 %", "frente a abril de 2026"),
              (f"{num(eda['ratio_pico_valle'], 1)}×", "la hora más cara vs. la más barata (mediana diaria, último año)")]
    for i, (grande, chico) in enumerate(cifras):
        y = Inches(2.6 + i * 2.15)
        linea_h(s, Inches(12.6), y, Inches(5.9))
        texto(s, Inches(12.6), y + Inches(0.25), Inches(5.9), Inches(1.0), grande, 60, AZUL, True)
        texto(s, Inches(12.6), y + Inches(1.25), Inches(5.9), Inches(0.8), chico, 16, GRIS)
    notas(s, "(40 s) El precio de bolsa en Colombia cambia cada hora y en 2026 se disparó: 516 pesos por kWh en mayo, "
             "84 % más que en abril. Dentro de un mismo día, la hora más cara cuesta varias veces la más barata. Pero "
             "las cargas que se podrían mover siguen arrancando por costumbre. Nuestra pregunta: con datos públicos y "
             "un pronóstico a 7 días, ¿podemos bajar ese costo sin producir menos?")

    # 3 · Cliente, usuario y valor
    s = nueva(prs, "cliente, usuario y valor", 3, "Casos de referencia con información pública: ver fuentes y supuestos "
              "en config/ y en la app")
    for k, (d, titulo_col, cliente, usuario, caso) in enumerate([
        (fab, "fábrica manufacturera", "Industria no regulada con energía expuesta a bolsa.",
         "Jefe de planta o ingeniero de energía.", "Argos Rioclaro: 2 molinos de cemento, crudo, carbón y "
                                                    "trituradora; 21 MW máx."),
        (flo, "flota eléctrica", "Operador de flota eléctrica (concesionario SITP, reparto).",
         "Jefe de patio.", "Patio Fontibón I: 120 buses BYD, 56 puntos dobles de 150 kW.")]):
        x = X0 + k * Inches(8.85)
        w = Inches(8.45)
        texto(s, x, Inches(2.45), w, Inches(0.6), titulo_col, 26, AZUL, True)
        tarjeta(s, x, Inches(3.2), Inches(4.1), Inches(2.1), "Cliente (paga)", cliente, tam=17)
        tarjeta(s, x + Inches(4.35), Inches(3.2), Inches(4.1), Inches(2.1), "Usuario (decide)", usuario, tam=17)
        tarjeta(s, x, Inches(5.5), w, Inches(1.5), "Caso real", caso, tam=17)
        tarjeta(s, x, Inches(7.2), w, Inches(2.6), "Valor medido con precios reales",
                [[(f"−{pct(d['ahorro_real_backtest_pct'])}", True), (" del costo de la energía flexible", False)],
                 [(f"≈ {millones(d['ahorro_anual_cop'])} COP al año", True),
                  (f" con {pct(100 * d['exposicion_bolsa'], 0)} expuesto a bolsa", False)],
                 "Sin producir menos ni dejar un bus sin carga."], oscura=True, tam=18)
    notas(s, f"(40 s) Tenemos dos clientes. La fábrica: el cliente es la empresa que paga energía a precio de bolsa y "
             f"el usuario es el jefe de planta. Como caso usamos la planta Rioclaro de Argos con datos públicos. La "
             f"flota: el operador del patio y su jefe de patio; el caso es Fontibón I, con 120 buses. El valor lo "
             f"medimos con precios reales: {pct(fab['ahorro_real_backtest_pct'])} para la fábrica y "
             f"{pct(flo['ahorro_real_backtest_pct'])} para la flota, del costo de la energía que se puede mover.")

    # 4 · Diferenciación
    s = nueva(prs, "hoy vs. vatioplan", 4, "La tarifa por franjas y la carga inmediata son las prácticas actuales "
              "que reemplaza VatioPlan")
    tabla(s, [["Aspecto", "Cómo se resuelve hoy", "Con VatioPlan"],
              ["Cuándo consumir", "Horario fijo por turno; el bus carga apenas llega", "Plan diario con el precio de cada hora"],
              ["Señal de precio", "Franjas fijas punta / fuera de punta", "Pronóstico horario a 7 días (ML)"],
              ["Restricciones", "De memoria del operador", "Reglas R1–R5 verificadas en cada plan"],
              ["Seguimiento", "Factura mensual, revisada a mano", "Informe cada mañana con ahorro medido"],
              ["Costo de adopción", "Consultoría o software a la medida", "Datos públicos y un archivo JSON por cliente"]],
          X0, Inches(2.6), ANCHO, [3, 6, 6], tam=17, alto_fila=0.8, resaltar_col=2)
    texto(s, X0, Inches(7.9), ANCHO, Inches(1.4),
          "Diferencia clave: el precio de bolsa no respeta las franjas. Una hora “fuera de punta” puede ser cara en "
          "sequía y una de la tarde puede ser barata en invierno. VatioPlan mira el precio de cada hora y cada día.",
          21, AZUL, True)
    notas(s, "(30 s) ¿Cómo se hace hoy? Con horarios fijos y, en el mejor caso, evitando la franja de punta. El "
             "problema es que el precio de bolsa no respeta las franjas. VatioPlan reemplaza la costumbre por un plan "
             "diario con el precio de cada hora, verifica las reglas de operación y entrega el informe sin trabajo manual.")

    # 5 · Datos y calidad
    s = nueva(prs, "datos de entrada y calidad", 5, "Fuentes: SIMEM (CREG, 2022), API de XM, NOAA CPC y librería holidays")
    filas = [["Variable", "Fuente", "Periodo", "Faltantes", "Atípicos", "Estado"]]
    for c in M["calidad"]["tabla"]:
        filas.append([c["Variable"].split(" (")[0], c["Fuente"].split(" ·")[0], f"{c.get('Desde', '—')} a {str(c.get('Hasta', '—'))[:10]}",
                      pct(c.get("Faltantes (%)"), 2) if c.get("Faltantes (%)") is not None else "—",
                      num(c.get("Atípicos (3×IQR)"), 0) if c.get("Atípicos (3×IQR)") is not None else "—",
                      c.get("Estado", "—")])
    tabla(s, filas, X0, Inches(2.5), ANCHO, [4.2, 3.4, 4.6, 2, 1.8, 1.8], tam=15, alto_fila=0.55)
    tarjeta(s, X0, Inches(5.75), Inches(5.55), Inches(2.9), "Preparación documentada",
            ["Versión de liquidación más reciente de cada hora (TX1→TX2→TXR→TXF).",
             "Sin imputar: horas sin precio no entran al modelo."], tam=16)
    tarjeta(s, X0 + Inches(5.9), Inches(5.75), Inches(5.55), Inches(2.9), "Revisión",
            [f"{num(M['horas_totales'])} horas de precio desde {M['desde']}.",
             f"Duplicados: {M['calidad']['duplicados']} · horas sin registro: {num(M['calidad']['horas_faltantes_indice'])}.",
             "Atípicos = picos reales de escasez: se conservan."], tam=16)
    tarjeta(s, X0 + Inches(11.8), Inches(5.75), Inches(5.53), Inches(2.9), "Sesgos y límites",
            ["Solo 2023–2026: pocos episodios de El Niño.",
             "Precio publicado con ~3 días de retraso.",
             "Potencias y baterías de los casos: estimadas."], tam=16, color_etiqueta=ROJO)
    notas(s, "(35 s) Todo es público y se descarga solo. Revisamos faltantes, duplicados y atípicos. Los picos no se "
             "eliminan porque son reales: son justo las horas que queremos evitar. Usamos la última versión de "
             "liquidación de cada hora y no rellenamos huecos. El sesgo principal: solo tenemos desde 2023, así que "
             "hay pocos episodios de El Niño.")

    # 6 · EDA → decisiones
    s = nueva(prs, "del EDA a las decisiones", 6, "Análisis exploratorio con los datos de SIMEM (reporte/figuras)")
    imagen(s, "eda_perfil_regimen.png", X0, Inches(2.45), w=Inches(8.6))
    filas = [["Hallazgo", "Decisión de diseño"],
             [f"Autocorrelación {num(eda['acf168'], 2)} a 168 h", "Ancla = promedio de la misma hora, 4 semanas"],
             [f"Promedio mensual de {num(eda['mensual_min'])} a {num(eda['mensual_max'])} COP/kWh",
              "No pronosticar el nivel absoluto: corregir el ancla"],
             [f"Asimetría {num(eda['asimetria'], 1)}: picos raros y altos", "Pérdida MAE (absolute_error), robusta"],
             [f"Pico/valle {num(eda['ratio_pico_valle'], 1)}× dentro del día", "Hay valor en mover cargas de hora"],
             ["Precio publicado con retraso", "Variables con rezago ≥ 7 días (sin fuga)"]]
    tabla(s, filas, Inches(10.3), Inches(2.45), Inches(8.36), [1, 1], tam=14, alto_fila=0.95)
    texto(s, X0, Inches(7.4), Inches(8.6), Inches(2.4),
          "La forma del día se repite (pico 18–21 h, valle en la madrugada); lo que cambia con la hidrología es el "
          "nivel. Por eso el modelo corrige un ancla reciente.", 19, AZUL, True)
    notas(s, "(35 s) El análisis exploratorio decidió el diseño. La forma del día se repite semana a semana: "
             "autocorrelación alta a 168 horas, por eso el ancla es el promedio de la misma hora en las últimas cuatro "
             "semanas. El nivel cambia muchísimo entre meses según los embalses, por eso no pronosticamos el nivel "
             "absoluto. Y como hay picos raros y altos, usamos error absoluto, que es robusto.")

    # 7 · Arquitectura de IA
    s = nueva(prs, "método de IA y diseño", 7, "ML pronostica · reglas garantizan · LLM redacta (y se verifica)")
    pasos = [("datos públicos", "SIMEM, XM, NOAA · caché y reintentos", False),
             ("machine learning", "Gradient boosting corrige el promedio de 4 semanas", True),
             ("optimización", "Reglas R1–R5 · PuLP: entera (fábrica) y lineal (flota)", False),
             ("IA generativa", "Gemini 3.5 Flash · respaldo gpt-oss-120b · plantilla", True),
             ("app web", "Streamlit: entradas, plan, validación, informe", False)]
    wcaja = Inches(3.15)
    for i, (t1, t2, osc) in enumerate(pasos):
        x = X0 + i * (wcaja + Inches(0.4))
        tarjeta(s, x, Inches(2.6), wcaja, Inches(2.7), t1, t2, oscura=osc, tam=16)
        if i < len(pasos) - 1:
            texto(s, x + wcaja + Inches(0.05), Inches(3.6), Inches(0.35), Inches(0.5), "→", 26, AZUL, True)
    tabla(s, [["Componente", "Por qué este método", "Alternativa descartada"],
              ["Pronóstico", "Datos tabulares (~30.000 h): preciso, rápido, interpretable", "Red neuronal MLP y GB del precio absoluto (comparados en la diapositiva 8)"],
              ["Optimización", "Garantiza las reglas; óptimo exacto en < 1 s", "Heurística “prender en horas baratas” (viola R4/R5)"],
              ["LLM", "Prompt con reglas y solo cifras del JSON; se verifica cada cifra", "Prompt simple (inventa o redondea cifras)"]],
          X0, Inches(5.65), ANCHO, [2.2, 5, 6], tam=15, alto_fila=0.78)
    notas(s, "(40 s) La solución combina tres métodos. Un modelo de machine learning, gradient boosting de "
             "scikit-learn, pronostica el precio corrigiendo el promedio de las últimas cuatro semanas. Un optimizador "
             "con PuLP decide las horas y garantiza las reglas de ingeniería; eso no lo puede hacer un modelo de "
             "lenguaje. Y un LLM, Gemini, redacta el informe usando solo cifras ya calculadas; verificamos "
             "automáticamente que no invente ninguna. Cada pieza tiene una alternativa más simple con la que la comparamos.")

    # 8 · Ajuste y comparación con baseline
    s = nueva(prs, "ajuste y comparación con baseline", 8,
              f"Validación: {M['particion']['validacion']} · prueba: {M['particion']['prueba']}")
    hp = M["hiperparametros"]
    tarjeta(s, X0, Inches(2.5), Inches(5.6), Inches(2.9), "Partición temporal",
            [f"Entrenamiento: {M['particion']['entrenamiento']}", f"Validación: {M['particion']['validacion']}",
             f"Prueba: {M['particion']['prueba']} (se usa una sola vez)"], tam=15)
    tarjeta(s, X0, Inches(5.6), Inches(5.6), Inches(3.3), "Ajuste en validación",
            [f"{hp['combinaciones']} combinaciones de tasa de aprendizaje, árboles, hojas y tamaño mínimo.",
             "Mejor: " + ", ".join(f"{k}={v}" for k, v in hp["elegidos_validacion"].items())], tam=15)
    comp = fab["comparacion"]
    filas = [["Candidato", "MAE", "Horas baratas", "Ahorro fábrica", "Ahorro flota"]]
    flota_por_nombre = {c["Candidato"]: c for c in flo["comparacion"]}
    for c in comp:
        nombre = c["Candidato"].replace(" (modelo principal)", " ★").replace(" (versión anterior)", "").replace(
            " (versión original)", "")
        filas.append([nombre, num(c["MAE (COP/kWh)"]), pct(c["Horas baratas acertadas (%)"], 0),
                      pct(c["Ahorro real en backtest (%)"]),
                      pct(flota_por_nombre.get(c["Candidato"], {}).get("Ahorro real en backtest (%)"))])
    tabla(s, filas, X0 + Inches(5.9), Inches(2.5), Inches(11.43), [6, 1.6, 2.3, 2.4, 2.3], tam=14, alto_fila=0.72)
    texto(s, X0 + Inches(5.9), Inches(7.2), Inches(11.43), Inches(2.4),
          "Criterio de selección: ahorro real en backtest, no el MAE. Un modelo con menor MAE no siempre ordena mejor "
          "las horas del día, que es lo que decide el plan.", 18, AZUL, True)
    notas(s, "(40 s) Partimos el tiempo en entrenamiento, validación y prueba, sin mezclar futuro y pasado. Con "
             f"validación elegimos los hiperparámetros entre {hp['combinaciones']} combinaciones. Luego comparamos "
             "contra cuatro alternativas: el ingenuo, que es el precio de hace 7 días; el promedio de 4 semanas sin "
             "corrección; y dos versiones anteriores del modelo. Ojo: elegimos por ahorro real, no por MAE, porque lo "
             "que importa es ordenar bien las horas de cada día.")

    # 9 · Sobreajuste y generalización
    s = nueva(prs, "sobreajuste y generalización", 9, "Curva de aprendizaje y validación walk-forward (reporte/figuras)")
    so = M["sobreajuste"]
    filas = [["Conjunto", "MAE", "Sesgo", "Horas baratas"]] + [
        [f["Conjunto"], num(f["MAE"]), num(f["Sesgo (COP/kWh)"]), pct(f["Horas baratas (%)"], 0)] for f in so]
    tabla(s, filas, X0, Inches(2.5), Inches(7.6), [3, 1.4, 1.4, 2.2], tam=15, alto_fila=0.6)
    imagen(s, "val_curva_aprendizaje.png", X0, Inches(5.2), w=Inches(7.2))
    imagen(s, "val_walk_forward.png", Inches(9.4), Inches(2.5), w=Inches(9.2))
    wf = M["walk_forward"]
    gana = sum(1 for f in wf if f.get("Gana al ingenuo") == "Sí")
    gana_hb = sum(1 for f in wf if f.get("Horas baratas modelo (%)", 0) > f.get("Horas baratas ingenuo (%)", 0))
    mae = {f["Conjunto"]: f["MAE"] for f in so}
    brecha = 100 * (mae["Validación"] / mae["Entrenamiento"] - 1) if mae.get("Entrenamiento") else 0
    juicio = ("brecha pequeña → sin sobreajuste" if brecha < 25 else "brecha notable → el cambio de régimen pesa más "
              "que la complejidad del modelo")
    texto(s, Inches(9.4), Inches(7.0), Inches(9.2), Inches(2.6),
          [f"Validación vs. entrenamiento: {'+' if brecha >= 0 else ''}{num(brecha, 0)} % de MAE ({juicio}).",
           f"Walk-forward: menor MAE que el ingenuo en {gana} de {len(wf)} ventanas; más horas baratas acertadas en "
           f"{gana_hb} de {len(wf)}. Lo que decide el plan es ordenar las horas, no el valor exacto."], 17, AZUL, True)
    notas(s, f"(40 s) ¿Hay sobreajuste? El error en validación es {num(abs(brecha), 0)} % "
             f"{'mayor' if brecha >= 0 else 'menor'} que en entrenamiento y el de prueba es parecido; la curva de "
             "aprendizaje muestra que más árboles no abren la brecha, así que la diferencia viene del cambio de "
             f"régimen del mercado, no de memorizar. Para la generalización repetimos la prueba en {len(wf)} ventanas de "
             f"30 días: en error absoluto el ingenuo gana en varias ventanas, porque los picos dominan el MAE; pero en "
             f"acierto de horas baratas el modelo es mejor en {gana_hb} de {len(wf)}, y eso es lo que se traduce en "
             "ahorro. Lo decimos abiertamente como límite.")

    # 10 · Análisis de errores y límites
    s = nueva(prs, "análisis de errores y límites", 10, "Conjunto de prueba (90 días que el modelo nunca vio)")
    filas = [["Régimen", "Horas", "Precio medio", "MAE modelo", "MAE ingenuo"]] + [
        [f.get("regimen", f.get("index", "")), num(f["Horas"]), num(f["Precio medio"]), num(f["MAE modelo"]),
         num(f["MAE ingenuo"])] for f in M["errores"]["por_regimen"]]
    tabla(s, filas, X0, Inches(2.5), Inches(8.3), [2, 1.3, 2, 2, 2], tam=15, alto_fila=0.6)
    filas = [["Tipo de día", "MAE modelo", "MAE ingenuo"]] + [
        [f.get("tipo_dia", f.get("index", "")), num(f["MAE modelo"]), num(f["MAE ingenuo"])]
        for f in M["errores"]["por_tipo_dia"]]
    tabla(s, filas, X0, Inches(5.7), Inches(8.3), [3, 2, 2], tam=15, alto_fila=0.6)
    imagen(s, "val_error_por_hora.png", Inches(10.0), Inches(2.5), w=Inches(8.6))
    tarjeta(s, Inches(10.0), Inches(6.9), Inches(8.6), Inches(2.9), "Límites de generalización",
            ["Cambios bruscos de régimen (inicio de El Niño): el error sube.",
             "Solo mercado colombiano y datos desde 2023.",
             "Ahorro solo sobre la energía expuesta a bolsa."], tam=16, color_etiqueta=ROJO)
    notas(s, "(30 s) Analizamos dónde falla. Por régimen: en escasez el precio es alto y el error absoluto también. "
             "Por hora: el error se concentra en el pico de la noche. Por tipo de día: domingos y festivos. Los límites: "
             "no esperamos el mismo desempeño al inicio de un El Niño fuerte, solo sirve para Colombia y el ahorro solo "
             "aplica a la energía que se paga a precio de bolsa.")

    # 11 · Optimizador y LLM
    s = nueva(prs, "validación de reglas y del LLM", 11, "tests/ (pytest) y vatioplan/eval_llm.py: casos con "
              "respuesta esperada definida por el equipo")
    casos = M["casos_optimizador"]
    filas = [["Caso de prueba (optimizador)", "Esperado", "✓"]] + [
        [c["Caso"], c["Resultado esperado"], c["Cumple"]] for c in casos]
    tabla(s, filas, X0, Inches(2.4), Inches(9.6), [4.2, 4.6, 0.6], tam=11, alto_fila=0.58)
    llm = M["llm"]["resumen"]
    filas = [["Variante del informe", "Formato", "Sin cifras inventadas", "Conducta esperada", "s/consulta"]] + [
        [f["Variante"].replace("LLM · ", ""), pct(f["Formato OK (%)"], 0), pct(f["Casos sin cifras inventadas (%)"], 0),
         pct(f["Conducta esperada (%)"], 0), num(f["Segundos por consulta"], 1)] for f in llm]
    tabla(s, filas, Inches(11.2), Inches(2.4), Inches(7.46), [3.4, 1.6, 2, 2, 1.4], tam=12, alto_fila=0.75)
    v = {f["Variante"]: f for f in llm}
    v1 = next((x for k, x in v.items() if "v1" in k), None)
    v2 = next((x for k, x in v.items() if "v2" in k), None)
    lineas = ["6 casos: día normal (fábrica y flota), datos simulados, reglas incumplidas, ahorro cero, sin exposición."]
    if v1 and v2:
        lineas.append(f"Ajuste del prompt v1 → v2 + verificación: formato {pct(v1['Formato OK (%)'], 0)} → "
                      f"{pct(v2['Formato OK (%)'], 0)}; sin cifras inventadas {pct(v1['Casos sin cifras inventadas (%)'], 0)}"
                      f" → {pct(v2['Casos sin cifras inventadas (%)'], 0)}.")
    lineas.append("Si el LLM no pasa la verificación tras un reintento, se publica la plantilla. Costo: $0.")
    texto(s, Inches(11.2), Inches(2.4) + Inches(0.75 * (len(llm) + 1)) + Inches(0.3), Inches(7.46), Inches(3.4),
          lineas, 15, TINTA)
    texto(s, X0, Inches(9.45), Inches(9.6), Inches(0.5),
          f"{M['casos_optimizador_ok']} de {M['casos_optimizador_total']} casos cumplen, incluidos los imposibles.",
          17, AZUL, True)
    notas(s, "(40 s) Validamos cada componente por separado. El optimizador tiene diez casos con resultado esperado "
             "definido antes de correrlos, incluidos casos imposibles: el sistema debe avisar, no inventar un plan. "
             "Para el LLM armamos seis casos de prueba y medimos formato, cifras inventadas, conducta en casos borde, "
             "consistencia al repetir y tiempo por consulta. La primera versión del prompt fallaba en formato y "
             "en cifras inventadas en la mitad de los casos; por eso la ajustamos: estructura fija, prohibición de "
             "calcular cifras nuevas, avisos obligatorios y una verificación automática con un reintento. Si aun así "
             "falla, se publica la plantilla sin IA.")

    # 12 · Resultados de extremo a extremo
    s = nueva(prs, "resultado: ahorro con precios reales", 12,
              "Backtest: cada día se planea con el pronóstico y se paga con el precio real")
    for k, (d, nombre, fig) in enumerate([(fab, "fábrica · Argos Rioclaro", "backtest_fabrica.png"),
                                          (flo, "flota · patio Fontibón I", "backtest_flota.png")]):
        x = X0 + k * Inches(8.85)
        texto(s, x, Inches(2.4), Inches(8.45), Inches(0.5), nombre, 22, AZUL, True)
        texto(s, x, Inches(3.0), Inches(4.2), Inches(1.0), f"−{pct(d['ahorro_real_backtest_pct'])}", 54, AZUL, True)
        texto(s, x + Inches(4.3), Inches(3.05), Inches(4.2), Inches(1.2),
              [f"máximo posible {pct(d['ahorro_maximo_backtest_pct'])}",
               f"captura {pct(d['captura_del_potencial_pct'], 0)} del potencial",
               f"≈ {millones(d['ahorro_anual_cop'])} COP/año"], 16, GRIS)
        imagen(s, fig, x, Inches(4.6), w=Inches(8.45))
    texto(s, X0, Inches(8.65), ANCHO, Inches(1.2),
          f"{fab['dias_backtest']} días de prueba · todas las reglas cumplen · exposición a bolsa supuesta de "
          f"{pct(100 * fab['exposicion_bolsa'], 0)} (ajustable en la app)", 18, TINTA, True)
    notas(s, f"(35 s) Este es el resultado de extremo a extremo con precios reales. La fábrica ahorra "
             f"{pct(fab['ahorro_real_backtest_pct'])} del costo de la energía flexible, frente a un máximo teórico de "
             f"{pct(fab['ahorro_maximo_backtest_pct'])}: capturamos casi todo el potencial. La flota ahorra "
             f"{pct(flo['ahorro_real_backtest_pct'])}. En plata, unos {millones(fab['ahorro_anual_cop'])} y "
             f"{millones(flo['ahorro_anual_cop'])} pesos al año con la mitad de la energía expuesta a bolsa. Ahora lo "
             "vemos funcionando.")

    # 13 · Demo
    s = nueva(prs, "demostración en vivo", 13, "streamlit run app.py · http://localhost:8501")
    pasos = [("1", "Fábrica: plan del día", "Operación actual vs. VatioPlan, horario y por qué"),
             ("2", "Cambiar una entrada", "Bajar la potencia máxima → el plan se reacomoda y R4 se verifica"),
             ("3", "Flota", "Editar un grupo de buses → la carga se mueve a la madrugada"),
             ("4", "Validación", "Train/val/test, baseline, errores, casos de prueba"),
             ("5", "Informe IA", "Gemini redacta; se verifica que no invente cifras")]
    for i, (n, t1, t2) in enumerate(pasos):
        y = Inches(2.5 + i * 1.4)
        linea_h(s, X0, y, ANCHO)
        texto(s, X0, y + Inches(0.2), Inches(1.0), Inches(1.0), n, 48, AZUL, True)
        texto(s, X0 + Inches(1.3), y + Inches(0.25), Inches(6), Inches(0.9), t1, 24, TINTA, True)
        texto(s, X0 + Inches(7.5), y + Inches(0.3), Inches(9.8), Inches(0.9), t2, 20, GRIS)
    notas(s, "(3 min, ver GUIA_DEMO.md) Paso 1: abrir la fábrica y mostrar el plan y el porqué. Paso 2: bajar la "
             "potencia a 19.000 kW y mostrar que las reglas siguen cumpliendo. Paso 3: cambiar a flota y subir la carga "
             "de llegada de un grupo. Paso 4: pestaña de validación. Paso 5: redactar con IA y mostrar la verificación "
             "de cifras.")

    # 14 · Reproducibilidad
    s = nueva(prs, "reproducible y orquestado", 14, "Documentación: README.md y GUIA_DEMO.md en el repositorio")
    tabla(s, [["Paso", "Comando"],
              ["1. Instalar", "pip install -r requirements.txt"],
              ["2. Evidencia completa", "python -m vatioplan.reporte"],
              ["3. Pruebas", "pytest -q"],
              ["4. App web local", "streamlit run app.py"]],
          X0, Inches(2.5), Inches(9.0), [2.2, 4.8], tam=17, alto_fila=0.75)
    tarjeta(s, Inches(10.8), Inches(2.5), Inches(7.86), Inches(3.6), "Orquestación diaria (6:15 a. m.)",
            ["GitHub Actions: descarga, entrena, planea, redacta y guarda resultados.",
             "Prefect: tareas con reintentos; no publica si una regla falla.",
             "n8n: envía el informe al jefe de planta y al jefe de patio."], tam=16)
    tarjeta(s, X0, Inches(6.6), ANCHO, Inches(2.0), "Robustez",
            ["Caché por bloques si SIMEM bloquea · etiqueta SIMULADO si no hay datos · plantilla si el LLM no responde.",
             "Un archivo JSON por cliente: cambiar de planta o de flota no requiere tocar código."], oscura=True, tam=17)
    notas(s, "(20 s) Todo se reproduce con cuatro comandos y corre solo cada mañana con GitHub Actions o Prefect. Si "
             "una fuente falla, usa caché; si el LLM falla, usa la plantilla; y si una regla se incumple, no publica.")

    # Referencias de los casos (nueva) + renumerar las existentes
    s = nueva(prs, "bibliografía · casos", 18, "Diapositiva de apoyo para preguntas")
    refs = ["Alcaldía Mayor de Bogotá. (s. f.). Bogotá estrena primer patio 100 % eléctrico y 120 buses cero emisiones. "
            "https://bogota.gov.co/mi-ciudad/movilidad/bogota-estrena-primer-patio-100-electrico-y-120-buses-cero-emisiones",
            "CemNet. (2014, 21 de mayo). Revamping Rioclaro. International Cement Review. "
            "https://cemnet.com/Articles/story/154516/revamping-rioclaro.html",
            "Enel X. (2022). Enel X entregó 172 buses eléctricos y el quinto patio de recarga a Bogotá [Comunicado de prensa].",
            "Rojas-Innocenti, S., et al. (2024). Electrical consumption flexibility in the cement industry [Preprint]. "
            "arXiv. https://arxiv.org/abs/2403.06573",
            "Summerbell, D. L., Khripko, D., Barlow, C. y Hesselbach, J. (2017). Cost and carbon reductions from industrial "
            "demand-side management: Study of potential savings at a cement plant. Applied Energy, 197, 100–113. "
            "https://doi.org/10.1016/j.apenergy.2017.03.083",
            "Worrell, E., Kermeli, K. y Galitsky, C. (2013). Energy efficiency improvement and cost saving opportunities "
            "for cement making: An ENERGY STAR guide (EPA 430-R-13-009). U.S. Environmental Protection Agency."]
    texto(s, X0, Inches(2.5), ANCHO, Inches(7.4), refs, 15)
    notas(s, "Diapositiva de apoyo para las preguntas. No se lee en voz alta.")
    for diapo, n in [(ref1, 16), (ref2, 17)]:
        for f in diapo.shapes:
            if f.has_text_frame and "/ 14" in f.text_frame.text:
                reemplazar(f, f"{n} / {TOTAL}")

    # Orden final: portada, 2–14 nuevas, gracias, referencias
    ids = prs.slides._sldIdLst
    lista = list(ids)
    portada_id, gracias_id, r1_id, r2_id = lista[0], lista[1], lista[2], lista[3]
    nuevas = lista[4:-1]
    refs_casos = lista[-1]
    for e in lista:
        ids.remove(e)
    for e in [portada_id, *nuevas, gracias_id, r1_id, r2_id, refs_casos]:
        ids.append(e)
    notas(gracias, "(10 s) Gracias. Quedamos atentos a sus preguntas.")
    prs.save(str(SALIDA))
    print(f"Presentación: {SALIDA}" + ("  ⚠️ con DATOS SIMULADOS" if SIMULADO else ""))


if __name__ == "__main__":
    sys.exit(construir())
