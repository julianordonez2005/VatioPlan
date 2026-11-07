"""
eval_llm.py — Evaluación del componente de IA generativa (el informe).

El LLM no decide nada: redacta con cifras ya calculadas. Lo que hay que verificar es que
  1. cumpla el FORMATO pedido (titular con ahorro, viñetas, ≤ 230 palabras),
  2. NO INVENTE cifras (toda cifra del texto debe estar en el JSON de entrada),
  3. maneje los CASOS BORDE con la respuesta esperada que definimos (avisar datos simulados,
     reglas incumplidas, ahorro nulo),
  4. sea CONSISTENTE al repetir la misma entrada,
  5. y cuánto TARDA y cuánto cuesta por consulta.
Se compara contra un PROMPT SIMPLE (sin reglas) y contra la PLANTILLA sin IA.

Uso:  python -m vatioplan.eval_llm               (con GEMINI_API_KEY o GROQ_API_KEY)
Sin key solo se evalúa la plantilla y se deja constancia.
"""
from __future__ import annotations

import copy
import json
import os
import re
import time

import numpy as np
import pandas as pd

from . import informe

PROMPT_SIMPLE = "Resume estos datos de energía para el responsable de la operación:\n\n{datos}"


# ---------------- casos de prueba ----------------
def casos(resumen_fabrica: dict, resumen_flota: dict) -> list[dict]:
    """Seis casos con la conducta esperada definida por el equipo."""
    c = []
    c.append({"caso": "Fábrica · día normal", "datos": copy.deepcopy(resumen_fabrica),
              "debe_mencionar": ["ahorro"], "no_debe": []})
    c.append({"caso": "Flota · día normal", "datos": copy.deepcopy(resumen_flota),
              "debe_mencionar": ["ahorro"], "no_debe": []})
    d = copy.deepcopy(resumen_fabrica)
    d["fuente_datos"] = "SIMULADO"
    c.append({"caso": "Borde · datos simulados", "datos": d, "debe_mencionar": ["simulad"], "no_debe": []})
    d = copy.deepcopy(resumen_flota)
    d["reglas"] = "2 incumplimientos"
    c.append({"caso": "Borde · reglas incumplidas", "datos": d, "debe_mencionar": ["incumpl"], "no_debe": []})
    d = copy.deepcopy(resumen_fabrica)
    d.update({"costo_vatioplan_cop": d["costo_referencia_cop"], "ahorro_cop": 0, "ahorro_pct": 0.0})
    c.append({"caso": "Borde · ahorro cero (precio plano)", "datos": d, "debe_mencionar": ["0"], "no_debe": []})
    d = copy.deepcopy(resumen_flota)
    d["exposicion_bolsa"] = 0.0
    c.append({"caso": "Borde · sin exposición a bolsa", "datos": d, "debe_mencionar": ["exposición"], "no_debe": []})
    return c


# ---------------- métricas ----------------
_NUM = re.compile(r"(?<![\w:])\$?-?\d[\d.,]*%?")


def _a_numero(texto: str) -> float | None:
    t = texto.strip("$%").rstrip(".,")
    if not t or not any(ch.isdigit() for ch in t):
        return None
    if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", t):          # separador de miles
        return float(re.sub(r"[.,]", "", t))
    t = t.replace(",", ".") if t.count(",") == 1 and t.count(".") == 0 else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _numeros_json(obj) -> set[float]:
    vals = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            vals |= _numeros_json(v)
            vals |= _numeros_json(k) if isinstance(k, str) else set()
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            vals |= _numeros_json(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        vals |= {float(obj), round(float(obj), 1), round(float(obj)), round(float(obj) * 100, 1),
                 round(float(obj) * 100)}
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            n = _a_numero(m)
            if n is not None:
                vals.add(n)
        for h in re.findall(r"(\d{1,2}):00", obj):
            vals.add(float(h))
    return vals


def cifras_no_soportadas(texto: str, datos: dict) -> list[str]:
    """Cifras del texto que no aparecen en los datos de entrada (posibles alucinaciones).
    Se ignoran horas (hh:mm), fechas y enteros pequeños (≤ 24: conteos, horas, numeración)."""
    limpio = re.sub(r"\d{4}-\d{2}-\d{2}", " ", texto)
    limpio = re.sub(r"\d{1,2}:\d{2}", " ", limpio)
    permitidos = _numeros_json(datos)
    malos = []
    for m in _NUM.findall(limpio):
        n = _a_numero(m)
        if n is None or (float(n).is_integer() and 0 <= n <= 24):
            continue
        if not any(abs(n - v) <= max(0.051, abs(v) * 0.005) for v in permitidos):
            malos.append(m)
    return malos


def formato(texto: str) -> dict:
    palabras = len(re.findall(r"\w+", texto))
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    titular = bool(lineas) and bool(re.search(r"ahorr", lineas[0], re.I)) and bool(re.search(r"\d", lineas[0]))
    vinetas = sum(l.startswith(("-", "*", "•")) for l in lineas)
    return {"palabras": palabras, "titular_con_ahorro": titular, "vinetas": vinetas,
            "formato_ok": titular and vinetas >= 3 and palabras <= 260}


def _similitud(a: str, b: str) -> float:
    na, nb = set(_NUM.findall(a)), set(_NUM.findall(b))
    return len(na & nb) / max(1, len(na | nb))


# ---------------- ejecución ----------------
def _llamar(prompt: str) -> tuple[str, str]:
    for proveedor, var, fn in [("Gemini", "GEMINI_API_KEY", informe._gemini), ("Groq", "GROQ_API_KEY", informe._groq)]:
        key = os.getenv(var)
        if key:
            return fn(prompt, key), proveedor
    raise RuntimeError("sin API key")


def _prompt_completo(datos: dict) -> str:
    lector, elemento, accion = informe.LECTOR.get(datos.get("tipo_usuario"), informe.LECTOR["Fábrica manufacturera"])
    ins = informe.INSTRUCCIONES.format(tipo=datos.get("tipo_usuario"), lector=lector,
                                       referencia=datos.get("plan_de_referencia"), elemento=elemento, accion=accion)
    return f"{ins}\n\nDATOS:\n{json.dumps(datos, ensure_ascii=False, indent=1, default=str)}"


def evaluar(resumen_fabrica: dict, resumen_flota: dict, repeticiones: int = 3, pausa_s: float = 4.0) -> dict:
    hay_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY"))
    variantes = {"Plantilla (sin IA)": None}
    if hay_key:
        variantes["LLM · prompt completo (VatioPlan)"] = _prompt_completo
        variantes["LLM · prompt simple"] = lambda d: PROMPT_SIMPLE.format(
            datos=json.dumps(d, ensure_ascii=False, default=str))
    filas, ejemplos = [], {}
    for caso in casos(resumen_fabrica, resumen_flota):
        for nombre, armar in variantes.items():
            textos, tiempos, proveedor = [], [], "plantilla"
            for _ in range(1 if armar is None else repeticiones):
                t0 = time.time()
                try:
                    if armar is None:
                        texto = informe.plantilla(caso["datos"])
                    else:
                        texto, proveedor = _llamar(armar(caso["datos"]))
                        time.sleep(pausa_s)          # respeta el límite de la capa gratuita
                except Exception as e:  # se registra el fallo como resultado
                    texto = f"ERROR: {e}"
                tiempos.append(time.time() - t0)
                textos.append(texto)
            principal = textos[0]
            f = formato(principal)
            malos = cifras_no_soportadas(principal, caso["datos"])
            menciona = all(m.lower() in principal.lower() for m in caso["debe_mencionar"])
            consist = np.mean([_similitud(principal, t) for t in textos[1:]]) if len(textos) > 1 else 1.0
            filas.append({"Caso": caso["caso"], "Variante": nombre, "Proveedor": proveedor,
                          "Formato OK": f["formato_ok"], "Palabras": f["palabras"],
                          "Cifras inventadas": len(malos), "Ejemplos inventadas": ", ".join(malos[:4]),
                          "Conducta esperada": menciona, "Consistencia (0-1)": round(float(consist), 2),
                          "Segundos por consulta": round(float(np.mean(tiempos)), 2)})
            ejemplos[(caso["caso"], nombre)] = principal
    t = pd.DataFrame(filas)
    resumen = t.groupby("Variante").agg(**{
        "Casos": ("Caso", "count"),
        "Formato OK (%)": ("Formato OK", lambda s: 100 * s.mean()),
        "Casos sin cifras inventadas (%)": ("Cifras inventadas", lambda s: 100 * (s == 0).mean()),
        "Conducta esperada (%)": ("Conducta esperada", lambda s: 100 * s.mean()),
        "Consistencia media": ("Consistencia (0-1)", "mean"),
        "Segundos por consulta": ("Segundos por consulta", "mean")}).round(2).reset_index()
    return {"detalle": t, "resumen": resumen, "hay_key": hay_key,
            "ejemplos": {f"{a} | {b}": v for (a, b), v in ejemplos.items()}}


if __name__ == "__main__":
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "salidas"
    rf = json.loads((raiz / "fabrica" / "resumen.json").read_text(encoding="utf-8"))
    rl = json.loads((raiz / "flota" / "resumen.json").read_text(encoding="utf-8"))
    for d in (rf, rl):                      # solo lo que recibe el LLM en producción
        d.pop("comparacion_modelos", None)
        d.pop("proveedor_ia", None)
    r = evaluar(rf, rl)
    pd.set_option("display.width", 180)
    print(r["resumen"])
    print(r["detalle"])
    if not r["hay_key"]:
        print("\nSin GEMINI_API_KEY / GROQ_API_KEY: solo se evaluó la plantilla.")
