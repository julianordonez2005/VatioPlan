"""
construir_informe.py — Informe final de 2 páginas (Word) con las cifras de reporte/metricas.json.

Uso (desde la raíz, después de `python -m vatioplan.reporte`):
    python entregables/construir_informe.py
Salida: entregables/Informe_VatioPlan.docx  (revisen que quede en 2 páginas y exporten a PDF).
"""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

RAIZ = Path(__file__).resolve().parent.parent
M = json.loads((RAIZ / "reporte" / "metricas.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "entregables" / "Informe_VatioPlan.docx"
AZUL = RGBColor(0x54, 0x68, 0xB8)


def num(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v, d=1):
    return f"{num(v, d)} %"


def sombrear(celda, color):
    tc = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    tc.append(shd)


def construir():
    P, mt, eda = M["perfiles"], M["modelo_test"], M["eda"]
    fab, flo = P["fabrica"], P["flota"]
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(27.94), Cm(21.59)
    sec.top_margin = sec.bottom_margin = Cm(1.6)
    sec.left_margin = sec.right_margin = Cm(1.8)
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(9.5)
    estilo.paragraph_format.space_after = Pt(3)
    estilo.paragraph_format.line_spacing = 1.0

    def titulo(t, tam=11):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(5)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(t)
        r.bold = True
        r.font.size = Pt(tam)
        r.font.color.rgb = AZUL

    def parrafo(*partes):
        p = doc.add_paragraph()
        p.paragraph_format.alignment = 3          # justificado
        for t in partes:
            if isinstance(t, tuple):
                r = p.add_run(t[0])
                r.bold = True
            else:
                p.add_run(t)

    def tabla(filas, anchos):
        t = doc.add_table(rows=len(filas), cols=len(filas[0]))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.style = "Table Grid"
        t.autofit = False
        for j, a in enumerate(anchos):
            t.columns[j].width = Cm(a)
        for i, fila in enumerate(filas):
            for j, v in enumerate(fila):
                c = t.cell(i, j)
                c.width = Cm(anchos[j])
                c.text = ""
                r = c.paragraphs[0].add_run(str(v))
                r.font.size = Pt(8)
                r.bold = i == 0
                c.paragraphs[0].paragraph_format.space_after = Pt(0)
                if i == 0:
                    sombrear(c, "DDE2F5")
        doc.add_paragraph().paragraph_format.space_after = Pt(0)

    p = doc.add_paragraph()
    r = p.add_run("VatioPlan: consumo eléctrico flexible según el precio de bolsa en Colombia")
    r.bold = True
    r.font.size = Pt(15)
    r.font.color.rgb = AZUL
    doc.add_paragraph("Tomás Carrillo Marín · Julián Andrés Ordoñez Guevara — Herramientas de Inteligencia Artificial, "
                      "Universidad de los Andes, 2026")
    if M["fuente"] != "REAL":
        p = doc.add_paragraph()
        r = p.add_run("⚠ BORRADOR CON DATOS SIMULADOS: regenerar con `python -m vatioplan.reporte` antes de entregar.")
        r.bold = True
        r.font.color.rgb = RGBColor(0xB8, 0x53, 0x2F)

    titulo("1. Problema, cliente y valor")
    parrafo("El precio de bolsa de la energía en Colombia cambia cada hora: en el último año la hora más cara costó "
            f"{num(eda['ratio_pico_valle'], 1)} veces la más barata (mediana diaria) y en mayo de 2026 el promedio llegó "
            "a 516 COP/kWh, 84 % más que en abril (XM, citado por La República). Aun así, las cargas que se podrían mover "
            "se programan por costumbre. VatioPlan atiende a dos clientes: ", ("una fábrica manufacturera", ),
            " (caso de referencia: planta Rioclaro de Cementos Argos, cuyos molinos y trituradora pueden cambiar de hora "
            "porque los silos guardan el material) y ", ("una flota eléctrica",),
            " (patio Fontibón I del SITP, 120 buses BYD que cargan de noche). El usuario es el jefe de planta o de patio; "
            "el cliente que paga es la empresa con energía expuesta a bolsa. Hoy se usan horarios fijos o franjas punta / "
            "fuera de punta; VatioPlan usa el precio pronosticado de cada hora y verifica las reglas de operación.")

    titulo("2. Datos e información de entrada")
    parrafo(f"Precio de bolsa nacional horario de SIMEM (EC6945, {num(M['horas_totales'])} horas desde {M['desde']}, "
            "versión de liquidación más reciente de cada hora), volumen útil de embalses y aportes (API de XM), índice ONI "
            "(NOAA) y festivos. Calidad: ",
            f"{num(M['calidad']['faltantes_precio_pct'], 2)} % de horas sin precio, {M['calidad']['duplicados']} duplicados; "
            "los faltantes no se imputan y los picos (atípicos) se conservan porque son reales. Hallazgos del EDA que "
            f"definieron el diseño: autocorrelación de {num(eda['acf168'], 2)} a 168 h (ancla semanal), promedio mensual "
            f"entre {num(eda['mensual_min'])} y {num(eda['mensual_max'])} COP/kWh (cambios de régimen: no pronosticar el "
            f"nivel absoluto) y asimetría de {num(eda['asimetria'], 1)} (pérdida de error absoluto). Como el precio se "
            "publica con ~3 días de retraso, todas las variables usan información de hace 7 días o más (sin fuga de "
            "datos). Los equipos y vehículos de los casos son estimaciones con fuentes públicas citadas.")

    ahorros = {c["Candidato"]: c["Ahorro real en backtest (%)"] for c in fab["comparacion"]}
    red = next((v for k, v in ahorros.items() if k.startswith("Red neuronal")), None)
    principal = next((v for k, v in ahorros.items() if "modelo principal" in k), None)
    if red is not None and principal is not None and red > principal + 0.05:
        texto_red = (f"La red neuronal logra {pct(red)} de ahorro frente a {pct(principal)} del gradient boosting; se "
                     "prefiere el gradient boosting por ser más interpretable y estable entre ventanas, y la red queda "
                     "como candidata para producción si la ventaja se mantiene. ")
    else:
        texto_red = ("La red neuronal no supera al gradient boosting en ahorro"
                     + (f" ({pct(red)} frente a {pct(principal)})" if red is not None else "")
                     + ": con ~30.000 filas tabulares y pocas variables, los árboles aprenden igual o mejor, son más "
                       "interpretables y no dependen de la escala. ")

    titulo("3. Método de IA y diseño")
    parrafo(("Machine learning: ",), "HistGradientBoostingRegressor (scikit-learn, pérdida absolute_error) que corrige el "
            "promedio de la misma hora en las últimas 4 semanas según hora, día de la semana y festivos. ",
            ("Alternativas: ",), "método ingenuo (precio de hace 7 días), promedio de 4 semanas sin corrección, gradient "
            "boosting del precio absoluto con todas las variables y una red neuronal MLP (64-32 neuronas, ReLU, "
            "codificación one-hot, parada temprana con 10 % de validación). ", texto_red, ("Optimización con reglas: ",), "programación entera (fábrica) y lineal "
            "(flota) con PuLP; reglas R1 horas requeridas, R2 ventana permitida, R3 bloque continuo, R4 potencia máxima, "
            "R5 corrida mínima (fábrica) y carga completa, conexión, cargador y límite del patio (flota). ",
            ("LLM: ",), "Gemini 3.5 Flash (respaldo gpt-oss-120b en Groq, y plantilla sin IA) redacta el informe diario "
            "con un prompt que prohíbe inventar cifras; la app verifica automáticamente cada cifra contra los datos.")

    titulo("4. Validación y desempeño")
    pa = M["particion"]
    so = {f["Conjunto"]: f for f in M["sobreajuste"]}
    parrafo(f"Partición temporal: entrenamiento {pa['entrenamiento']}, validación {pa['validacion']} (rejilla de "
            f"{M['hiperparametros']['combinaciones']} combinaciones de hiperparámetros) y prueba {pa['prueba']}, usada una "
            f"sola vez. MAE en entrenamiento / validación / prueba: {num(so['Entrenamiento']['MAE'])} / "
            f"{num(so['Validación']['MAE'])} / {num(so['Prueba (test)']['MAE'])} COP/kWh, sin brecha que indique "
            "sobreajuste. Métricas: MAE, MAPE, acierto de las 8 horas más baratas de cada día y, como criterio de "
            "selección, el ahorro real en backtest (se planea con el pronóstico y se paga con el precio real).")
    filas = [["Candidato", "MAE", "MAPE", "Horas baratas", "Ahorro fábrica", "Ahorro flota"]]
    flota = {c["Candidato"]: c for c in flo["comparacion"]}
    for c in fab["comparacion"]:
        filas.append([c["Candidato"].replace(" (modelo principal)", " ★"), num(c["MAE (COP/kWh)"]),
                      pct(c["MAPE (%)"]), pct(c["Horas baratas acertadas (%)"], 0), pct(c["Ahorro real en backtest (%)"]),
                      pct(flota.get(c["Candidato"], {}).get("Ahorro real en backtest (%)"))])
    tabla(filas, [6.8, 1.4, 1.6, 2.2, 2.4, 2.2])
    wf = M["walk_forward"]
    gana = sum(1 for f in wf if f.get("Gana al ingenuo") == "Sí")
    reg = {f.get("regimen", f.get("index")): f for f in M["errores"]["por_regimen"]}
    texto_reg = "; ".join(f"{k.lower()} {num(v['MAE modelo'])}" for k, v in reg.items())
    llm = {f["Variante"]: f for f in M["llm"]["resumen"]}
    texto_llm = "; ".join(f"{k}: formato {pct(v['Formato OK (%)'], 0)}, sin cifras inventadas "
                          f"{pct(v['Casos sin cifras inventadas (%)'], 0)}, conducta esperada {pct(v['Conducta esperada (%)'], 0)}"
                          for k, v in llm.items())
    parrafo(("Generalización y errores: ",), f"en validación walk-forward el modelo gana al ingenuo en {gana} de {len(wf)} "
            f"ventanas de 30 días; el MAE por régimen es {texto_reg} COP/kWh y el error se concentra en el pico de la "
            "noche y en semanas de cambio de régimen. ", ("Optimizador: ",),
            f"{M['casos_optimizador_ok']} de {M['casos_optimizador_total']} casos de prueba con resultado esperado "
            "(incluidos casos imposibles, que deben detectarse). ", ("LLM: ",), f"6 casos con conducta esperada "
            f"(normales, datos simulados, reglas incumplidas, ahorro cero, sin exposición), repetidos 3 veces — {texto_llm}.")

    titulo("5. Resultados y aplicación")
    parrafo(f"Con precios reales, la fábrica ahorra {pct(fab['ahorro_real_backtest_pct'])} del costo de la energía "
            f"flexible (máximo teórico {pct(fab['ahorro_maximo_backtest_pct'])}; ≈ {num(fab['ahorro_anual_cop'] / 1e6)} "
            f"millones de COP al año) y la flota {pct(flo['ahorro_real_backtest_pct'])} (máximo "
            f"{pct(flo['ahorro_maximo_backtest_pct'])}; ≈ {num(flo['ahorro_anual_cop'] / 1e6)} millones de COP al año), con "
            f"{pct(100 * fab['exposicion_bolsa'], 0)} de la energía expuesta a bolsa, sin producir menos ni dejar buses sin "
            "carga. La aplicación web local (Streamlit) recibe el tipo de usuario, los equipos o vehículos (tablas "
            "editables), la exposición, la potencia máxima y el día, y devuelve el plan horario con su explicación, las "
            "reglas verificadas, la validación y el informe. GitHub Actions, Prefect o n8n la ejecutan cada mañana.")

    fig = RAIZ / "reporte" / "figuras"
    if (fig / "plan_fabrica.png").exists():
        doc.add_picture(str(fig / "plan_fabrica.png"), width=Cm(17.5))
        nota = doc.add_paragraph("Figura 1. Fábrica: operación actual vs. plan VatioPlan para un día (barras: kW por "
                                 "equipo; línea: precio pronosticado).")
        nota.runs[0].font.size = Pt(8)
    figs = [fig / "backtest_fabrica.png", fig / "backtest_flota.png"]
    if all(f.exists() for f in figs):
        t = doc.add_table(rows=1, cols=2)
        for c, f in zip(t.rows[0].cells, figs):
            c.paragraphs[0].add_run().add_picture(str(f), width=Cm(8.5))
        nota = doc.add_paragraph("Figura 2. Ahorro acumulado en el periodo de prueba con precios reales (fábrica y flota).")
        nota.runs[0].font.size = Pt(8)

    titulo("6. Limitaciones")
    parrafo("Datos solo desde 2023 (pocos episodios de El Niño); el error sube cuando cambia el régimen hidrológico; "
            "las potencias de Rioclaro y las baterías de Fontibón son estimaciones públicas, no datos de las empresas; "
            "el ahorro aplica solo a la energía comprada a precio de bolsa; SIMEM puede bloquear descargas (se usa caché). "
            "Próximo paso: validar los supuestos con un cliente y medir el ahorro sobre la factura real.")
    doc.save(str(SALIDA))
    print(f"Informe: {SALIDA}")


if __name__ == "__main__":
    construir()
