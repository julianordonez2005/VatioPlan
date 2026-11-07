"""
verificacion.py — Revisa automáticamente un informe redactado por el LLM antes de publicarlo.

  1. Formato: titular con el ahorro, viñetas y longitud máxima.
  2. Cifras: toda cifra del texto debe estar en los datos de entrada (o ser un redondeo de una).
  3. Conducta: avisos obligatorios según los datos (datos simulados, reglas incumplidas,
     ahorro cero, sin exposición a bolsa).
La usan informe.py (reintento y respaldo) y eval_llm.py (métricas).
"""
from __future__ import annotations

import re

MAX_PALABRAS = 230
_NUM = re.compile(r"(?<![\w:])\$?-?\d[\d.,]*%?")


def a_numero(texto: str) -> float | None:
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


def numeros_json(obj) -> set[float]:
    """Todos los números de los datos, con sus redondeos y escalas habituales (%, millones)."""
    vals = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            vals |= numeros_json(v)
            if isinstance(k, str):
                vals |= numeros_json(k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            vals |= numeros_json(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        x = float(obj)
        for v in (x, x * 100, x / 1e6, x / 1e9):
            vals |= {v, round(v, 2), round(v, 1), round(v)}
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            n = a_numero(m)
            if n is not None:
                vals.add(n)
        for h in re.findall(r"(\d{1,2}):00", obj):
            vals.add(float(h))
    return vals


def cifras_no_soportadas(texto: str, datos: dict) -> list[str]:
    """Cifras del texto que no aparecen en los datos (posibles alucinaciones). Se ignoran
    horas (hh:mm), fechas y enteros pequeños (≤ 24: conteos, horas, numeración)."""
    limpio = re.sub(r"\d{4}-\d{2}-\d{2}", " ", texto)
    limpio = re.sub(r"\d{1,2}:\d{2}", " ", limpio)
    permitidos = numeros_json(datos)
    malos = []
    for m in _NUM.findall(limpio):
        n = a_numero(m)
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
            "formato_ok": titular and vinetas >= 3 and palabras <= MAX_PALABRAS + 30}


def avisos_obligatorios(datos: dict) -> list[tuple[str, str]]:
    """(patrón que debe aparecer, descripción) según la situación de los datos."""
    avisos = []
    if str(datos.get("fuente_datos", "REAL")).upper() != "REAL":
        avisos.append((r"simulad", "avisar que los datos son SIMULADOS"))
    if "incumpl" in str(datos.get("reglas", "")).lower():
        avisos.append((r"incumpl", "avisar que hay reglas incumplidas y que el plan no debe ejecutarse"))
    if not datos.get("ahorro_cop"):
        avisos.append((r"(sin ahorro|no hay ahorro|ahorro (esperado )?(de )?\$?0\b|0 ?%)", "decir que el ahorro es 0"))
    if datos.get("exposicion_bolsa", 1) == 0:
        avisos.append((r"exposici", "explicar que sin exposición a bolsa no hay ahorro en la factura"))
    return avisos


def conducta(texto: str, datos: dict) -> list[str]:
    """Avisos obligatorios que faltan en el texto."""
    return [d for patron, d in avisos_obligatorios(datos) if not re.search(patron, texto, re.I)]


def problemas(texto: str, datos: dict) -> list[str]:
    """Lista legible de problemas del informe (vacía = se puede publicar)."""
    f = formato(texto)
    salida = []
    if not f["titular_con_ahorro"]:
        salida.append("la primera línea debe ser el titular con el ahorro (COP y %)")
    if f["vinetas"] < 3:
        salida.append("usa viñetas que empiecen con '- '")
    if f["palabras"] > MAX_PALABRAS + 30:
        salida.append(f"es demasiado largo ({f['palabras']} palabras; máximo {MAX_PALABRAS})")
    malos = cifras_no_soportadas(texto, datos)
    if malos:
        salida.append("estas cifras no están en los DATOS (no calcules ni redondees cifras nuevas): " + ", ".join(malos))
    salida += [f"falta {d}" for d in conducta(texto, datos)]
    return salida
