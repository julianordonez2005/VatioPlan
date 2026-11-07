"""
eval_llm.py — Evaluación del componente de IA generativa (el informe).

El LLM no decide nada: redacta con cifras ya calculadas. Se verifica que
  1. cumpla el FORMATO pedido (titular con ahorro, viñetas, longitud),
  2. NO INVENTE cifras (toda cifra del texto debe estar en el JSON de entrada),
  3. maneje los CASOS BORDE con la conducta esperada definida por el equipo
     (avisar datos simulados, reglas incumplidas, ahorro cero, sin exposición),
  4. sea CONSISTENTE al repetir la misma entrada,
  5. y cuánto TARDA y cuesta por consulta.
Variantes comparadas (ajuste de prompts):
  * Plantilla sin IA (línea base sin LLM)
  * Prompt simple ("resume estos datos")
  * Prompt v1 (anteproyecto)
  * Prompt v2 + verificación automática con un reintento (versión final de VatioPlan)

Uso:  python -m vatioplan.eval_llm   (necesita GEMINI_API_KEY o GROQ_API_KEY)
"""
from __future__ import annotations

import copy
import json
import os
import time

import numpy as np
import pandas as pd

from . import informe
from .verificacion import _NUM, cifras_no_soportadas, conducta, formato  # noqa: F401  (re-exportadas)

PROMPT_SIMPLE = "Resume estos datos de energía para el responsable de la operación:\n\n{datos}"


def casos(resumen_fabrica: dict, resumen_flota: dict) -> list[dict]:
    """Seis casos de prueba. La conducta esperada se deriva de los datos (verificacion.avisos_obligatorios)."""
    c = [{"caso": "Fábrica · día normal", "datos": copy.deepcopy(resumen_fabrica)},
         {"caso": "Flota · día normal", "datos": copy.deepcopy(resumen_flota)}]
    d = copy.deepcopy(resumen_fabrica)
    d["fuente_datos"] = "SIMULADO"
    c.append({"caso": "Borde · datos simulados", "datos": d})
    d = copy.deepcopy(resumen_flota)
    d["reglas"] = "2 incumplimientos"
    c.append({"caso": "Borde · reglas incumplidas", "datos": d})
    d = copy.deepcopy(resumen_fabrica)
    d.update({"costo_vatioplan_cop": d["costo_referencia_cop"], "ahorro_cop": 0, "ahorro_pct": 0.0})
    c.append({"caso": "Borde · ahorro cero (precio plano)", "datos": d})
    d = copy.deepcopy(resumen_flota)
    d["exposicion_bolsa"] = 0.0
    c.append({"caso": "Borde · sin exposición a bolsa", "datos": d})
    return c


def _similitud(a: str, b: str) -> float:
    na, nb = set(_NUM.findall(a)), set(_NUM.findall(b))
    return len(na & nb) / max(1, len(na | nb))


def _variantes(hay_key: bool) -> dict:
    v = {"Plantilla (sin IA)": ("plantilla", 1)}
    if hay_key:
        v["LLM · prompt simple"] = ("simple", 2)
        v["LLM · prompt v1 (anteproyecto)"] = ("v1", 2)
        v["LLM · prompt v2 + verificación (final)"] = ("v2", 3)
    return v


def _ejecutar(tipo: str, datos: dict) -> tuple[str, str]:
    if tipo == "plantilla":
        return informe.plantilla(datos), "plantilla"
    if tipo == "simple":
        return informe.llamar(PROMPT_SIMPLE.format(datos=json.dumps(datos, ensure_ascii=False, default=str)))
    if tipo == "v1":
        return informe.llamar(informe.prompt_para(datos, version=1))
    return informe.generar_informe(datos, version=2, verificar=True)


def evaluar(resumen_fabrica: dict, resumen_flota: dict, pausa_s: float = 6.0) -> dict:
    hay_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY"))
    filas, ejemplos = [], {}
    for caso in casos(resumen_fabrica, resumen_flota):
        for nombre, (tipo, repeticiones) in _variantes(hay_key).items():
            textos, tiempos, proveedor = [], [], "plantilla"
            for _ in range(repeticiones):
                t0 = time.time()
                try:
                    texto, proveedor = _ejecutar(tipo, caso["datos"])
                except Exception as e:  # se registra el fallo como resultado
                    texto = f"ERROR: {e}"
                tiempos.append(time.time() - t0)
                textos.append(texto)
                if tipo != "plantilla":
                    time.sleep(pausa_s)          # respeta el límite de la capa gratuita
            principal = textos[0]
            f = formato(principal)
            malos = cifras_no_soportadas(principal, caso["datos"])
            faltan = conducta(principal, caso["datos"])
            consist = np.mean([_similitud(principal, t) for t in textos[1:]]) if len(textos) > 1 else 1.0
            filas.append({"Caso": caso["caso"], "Variante": nombre, "Proveedor": proveedor,
                          "Formato OK": f["formato_ok"], "Palabras": f["palabras"],
                          "Cifras inventadas": len(malos), "Ejemplos inventadas": ", ".join(malos[:4]),
                          "Conducta esperada": not faltan, "Avisos faltantes": "; ".join(faltan),
                          "Consistencia (0-1)": round(float(consist), 2),
                          "Segundos por consulta": round(float(np.mean(tiempos)), 2)})
            ejemplos[f"{caso['caso']} | {nombre}"] = principal
    t = pd.DataFrame(filas)
    orden = list(_variantes(hay_key))
    resumen = t.groupby("Variante").agg(**{
        "Casos": ("Caso", "count"),
        "Formato OK (%)": ("Formato OK", lambda s: 100 * s.mean()),
        "Casos sin cifras inventadas (%)": ("Cifras inventadas", lambda s: 100 * (s == 0).mean()),
        "Conducta esperada (%)": ("Conducta esperada", lambda s: 100 * s.mean()),
        "Consistencia media": ("Consistencia (0-1)", "mean"),
        "Segundos por consulta": ("Segundos por consulta", "mean")}).round(2).reindex(orden).reset_index()
    return {"detalle": t, "resumen": resumen, "hay_key": hay_key, "ejemplos": ejemplos}


if __name__ == "__main__":
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    rf = json.loads((raiz / "salidas" / "fabrica" / "resumen.json").read_text(encoding="utf-8"))
    rl = json.loads((raiz / "salidas" / "flota" / "resumen.json").read_text(encoding="utf-8"))
    for d in (rf, rl):                      # solo lo que recibe el LLM en producción
        d.pop("comparacion_modelos", None)
        d.pop("proveedor_ia", None)
    r = evaluar(rf, rl)
    pd.set_option("display.width", 200)
    print(r["resumen"])
    print(r["detalle"][["Caso", "Variante", "Formato OK", "Cifras inventadas", "Ejemplos inventadas",
                        "Avisos faltantes"]])
    if not r["hay_key"]:
        print("\nSin GEMINI_API_KEY / GROQ_API_KEY: solo se evaluó la plantilla.")
    salida = raiz / "reporte"
    salida.mkdir(exist_ok=True)
    r["detalle"].to_csv(salida / "eval_llm_detalle.csv", index=False)
    (salida / "eval_llm_ejemplos.json").write_text(json.dumps(r["ejemplos"], ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    m = salida / "metricas.json"
    if m.exists():                           # actualiza solo la sección del LLM del reporte
        met = json.loads(m.read_text(encoding="utf-8"))
        met["llm"] = {"hay_key": r["hay_key"], "resumen": json.loads(r["resumen"].to_json(orient="records",
                                                                                          force_ascii=False))}
        m.write_text(json.dumps(met, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("Actualizado reporte/metricas.json (sección LLM).")
