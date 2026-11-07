"""
informe.py — IA generativa: convierte los números del pipeline en un informe claro
para el jefe de planta (fábrica) o el jefe de patio (flota eléctrica).

Proveedores gratuitos soportados (se usa el primero que tenga API key):
  * Google Gemini  → variable de entorno GEMINI_API_KEY (https://aistudio.google.com/apikey)
  * Groq (gpt-oss) → variable de entorno GROQ_API_KEY   (https://console.groq.com/keys)
Si no hay ninguna key, se genera un informe con plantilla (el pipeline nunca se detiene).

Buenas prácticas aplicadas:
  * El LLM recibe SOLO los números calculados por el pipeline (JSON) y se le prohíbe inventar cifras.
  * Las decisiones las toman el modelo y las reglas; el LLM solo redacta y prioriza.
"""
from __future__ import annotations

import json
import os

import requests

GEMINI_MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GROQ_MODELO = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

LECTOR = {"Fábrica manufacturera": ("el jefe de planta", "equipo", "horario recomendado de operación"),
          "Flota eléctrica": ("el jefe de patio de la flota", "grupo de vehículos", "horario recomendado de carga")}

# Versión 1 (anteproyecto). Se conserva para comparar en la evaluación (eval_llm.py).
INSTRUCCIONES_V1 = """Eres el asistente de energía de un cliente industrial en Colombia ({tipo}).
Con los DATOS (JSON) escribe un informe breve en español para {lector}:
1. Titular de una línea con el ahorro esperado (en COP y %) frente a "{referencia}".
2. Qué hacer: una línea por {elemento} con el {accion}.
3. Horas a evitar (las más caras) y horas a aprovechar (las más baratas).
4. Confianza: ahorro real medido en backtest frente al máximo posible.
5. Riesgos y supuestos (exposición a bolsa, límite de potencia, reglas verificadas, fuente de datos, supuestos del caso).
Reglas: usa ÚNICAMENTE cifras que aparezcan en los DATOS; no inventes números;
máximo 230 palabras; formato Markdown con viñetas cortas."""

# Versión 2: estructura fija, reglas de cifras explícitas y avisos obligatorios. Se ajustó
# después de evaluar la v1 (formato y cifras inventadas fallaban en la mitad de los casos).
INSTRUCCIONES = """Eres el asistente de energía de un cliente en Colombia ({tipo}). Redacta en español,
para {lector}, un informe con EXACTAMENTE esta estructura en Markdown:

### ⚡ Ahorro esperado: $<ahorro_cop> COP (<ahorro_pct> %) frente a {referencia}
**Qué hacer**
- <una viñeta por {elemento}: nombre y {accion}, copiado de horario_recomendado_primera_ventana>
**Horas**
- Evitar: <horas_mas_caras> · Aprovechar: <horas_mas_baratas>
**Confianza**
- Ahorro real en backtest: <ahorro_real_backtest_pct> % (máximo <ahorro_maximo_backtest_pct> %, <dias_backtest> días)
**Riesgos y supuestos**
- <2 a 4 viñetas cortas: exposición a bolsa, reglas, fuente de datos, supuesto principal>

REGLAS OBLIGATORIAS
1. Cada cifra que escribas debe aparecer tal cual en los DATOS. No calcules porcentajes, sumas,
   diferencias, promedios ni conversiones nuevas. Puedes escribir 0,5 como 50 %.
2. La primera línea es el titular con el ahorro; usa solo viñetas que empiecen con "- ".
3. Máximo {max_palabras} palabras. Sin introducción ni despedida.
{avisos}"""

AVISO_TEXTO = {
    "avisar que los datos son SIMULADOS": "- Si fuente_datos no es REAL: escribe en la primera viñeta de riesgos "
                                         "'DATOS SIMULADOS: no usar para decidir'.",
    "avisar que hay reglas incumplidas y que el plan no debe ejecutarse": "- Las reglas tienen incumplimientos: "
                                         "escribe 'reglas incumplidas: no ejecutar el plan sin revisión'.",
    "decir que el ahorro es 0": "- El ahorro es 0: dilo explícitamente ('sin ahorro: 0 %') y no lo presentes como ganancia.",
    "explicar que sin exposición a bolsa no hay ahorro en la factura": "- La exposición a bolsa es 0: explica que "
                                         "sin exposición a bolsa mover el consumo no cambia la factura.",
}


def _gemini(prompt: str, key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODELO}:generateContent"
    r = requests.post(url, headers={"x-goog-api-key": key},
                      json={"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.2}}, timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq(prompt: str, key: str) -> str:
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": GROQ_MODELO, "temperature": 0.2,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def plantilla(d: dict) -> str:
    """Informe sin LLM: mismas cifras, redacción fija."""
    _, elemento, accion = LECTOR.get(d.get("tipo_usuario"), LECTOR["Fábrica manufacturera"])
    lin = [f"### ⚡ Ahorro esperado: ${d['ahorro_cop']:,.0f} COP ({d['ahorro_pct']:.1f}%) en "
           f"{d['ventanas_planeadas']} días frente a {d['plan_de_referencia'].lower()}",
           "", f"**{d['usuario']}** · {accion.capitalize()} (primera ventana):"]
    lin += [f"- **{c}**: {h}" for c, h in d["horario_recomendado_primera_ventana"].items()]
    lin += ["", f"**Evitar:** {', '.join(d['horas_mas_caras'])} (hasta {d['precio_max']:,.0f} COP/kWh). "
                f"**Aprovechar:** {', '.join(d['horas_mas_baratas'])} (desde {d['precio_min']:,.0f} COP/kWh).",
            "", "**Confianza y supuestos:**",
            f"- Ahorro real en backtest: {d['ahorro_real_backtest_pct']:.1f}% "
            f"(máximo posible {d['ahorro_maximo_backtest_pct']:.1f}%, {d['dias_backtest']} días con precio real).",
            f"- El pronóstico identifica {d['acierto_horas_baratas']:.0%} de las horas baratas "
            f"(error medio {d['mae_modelo']:,.0f} COP/kWh).",
            f"- Exposición a precio de bolsa: {d['exposicion_bolsa']:.0%} · límite de potencia "
            f"{d['limite_potencia_kw']:,.0f} kW.",
            f"- Reglas de ingeniería: {d['reglas']}.",
            f"- Fuente de datos: {d['fuente_datos']}."]
    return "\n".join(lin)


def prompt_para(datos: dict, version: int = 2) -> str:
    from .verificacion import MAX_PALABRAS, avisos_obligatorios
    lector, elemento, accion = LECTOR.get(datos.get("tipo_usuario"), LECTOR["Fábrica manufacturera"])
    referencia = datos.get("plan_de_referencia", "la operación actual")
    if version == 1:
        ins = INSTRUCCIONES_V1.format(tipo=datos.get("tipo_usuario", "industria"), lector=lector,
                                      referencia=referencia, elemento=elemento, accion=accion)
    else:
        avisos = "\n".join(AVISO_TEXTO[d] for _, d in avisos_obligatorios(datos))
        ins = INSTRUCCIONES.format(tipo=datos.get("tipo_usuario", "industria"), lector=lector,
                                   referencia=referencia.lower(), elemento=elemento, accion=accion,
                                   max_palabras=MAX_PALABRAS, avisos=("AVISOS OBLIGATORIOS\n" + avisos) if avisos else "")
    return f"{ins}\n\nDATOS:\n{json.dumps(datos, ensure_ascii=False, indent=1, default=str)}"


def _proveedores():
    """Proveedores con API key, en orden. LLM_PROVEEDOR=groq pone primero a Groq (útil si Gemini
    agotó su cuota gratuita del día)."""
    orden = [("Gemini", "GEMINI_API_KEY", _gemini), ("Groq", "GROQ_API_KEY", _groq)]
    if os.getenv("LLM_PROVEEDOR", "").strip().lower() == "groq":
        orden.reverse()
    for proveedor, var, fn in orden:
        key = os.getenv(var)
        if key:
            yield proveedor, key, fn


def llamar(prompt: str, intentos_429: int = 3) -> tuple[str, str]:
    """Llama al primer proveedor disponible; ante límite de uso (429) espera y reintenta."""
    import time
    ultimo_error = None
    for proveedor, key, fn in _proveedores():
        for intento in range(intentos_429):
            try:
                return fn(prompt, key), proveedor
            except requests.HTTPError as e:
                ultimo_error = e
                if e.response is not None and e.response.status_code == 429 and intento < intentos_429 - 1:
                    time.sleep(20 * (intento + 1))
                    continue
                break
            except Exception as e:  # red, formato de respuesta
                ultimo_error = e
                break
        print(f"⚠️  {proveedor} falló ({ultimo_error}); probando la siguiente opción.")
    raise RuntimeError(f"ningún proveedor respondió ({ultimo_error})")


def generar_informe(datos: dict, version: int = 2, verificar: bool = True) -> tuple[str, str]:
    """Devuelve (texto_markdown, proveedor_usado).
    Con verificar=True: si el texto no pasa la verificación (formato, cifras, avisos), se pide
    UNA corrección al LLM indicando los problemas; si sigue fallando, se publica la plantilla."""
    from .verificacion import problemas
    if not any(True for _ in _proveedores()):
        return plantilla(datos), "plantilla (sin API key)"
    prompt = prompt_para(datos, version)
    try:
        texto, proveedor = llamar(prompt)
    except RuntimeError as e:
        print(f"⚠️  {e}")
        return plantilla(datos), "plantilla (el LLM no respondió)"
    if not verificar:
        return texto, proveedor
    fallas = problemas(texto, datos)
    if not fallas:
        return texto, proveedor
    correccion = (f"{prompt}\n\nTu respuesta anterior fue:\n{texto}\n\nTenía estos problemas:\n- "
                  + "\n- ".join(fallas) + "\nEscribe de nuevo el informe completo corrigiéndolos.")
    try:
        texto2, proveedor = llamar(correccion)
    except RuntimeError:
        return plantilla(datos), "plantilla (el LLM no pasó la verificación)"
    if not problemas(texto2, datos):
        return texto2, f"{proveedor} (corregido tras verificación)"
    return plantilla(datos), "plantilla (el LLM no pasó la verificación)"
