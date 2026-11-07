"""Pruebas de cada componente por separado y del flujo completo (pytest -q)."""
import os

import numpy as np
import pandas as pd
import pytest

from vatioplan.casos_prueba import casos_optimizador
from vatioplan.datos import generar_datos_simulados
from vatioplan.eval_llm import cifras_no_soportadas, formato
from vatioplan.features import construir_features
from vatioplan.informe import plantilla


@pytest.fixture(scope="module")
def df():
    d = generar_datos_simulados(pd.Timestamp("2024-01-01").date(), pd.Timestamp("2025-06-30").date())
    d.attrs["fuente"] = "SIMULADO"
    return d


def test_optimizador_casos_con_resultado_esperado():
    t = casos_optimizador()
    assert (t["Cumple"] == "✅").all(), t[t["Cumple"] != "✅"].to_string()


def test_sin_fuga_de_datos(df):
    """Ninguna variable del modelo puede depender del precio de las últimas 167 horas."""
    X1 = construir_features(df)
    df2 = df.copy()
    df2.iloc[-167:, df2.columns.get_loc("precio")] = 99999.0     # cambiar el futuro cercano
    X2 = construir_features(df2)
    cols = [c for c in X1.columns if c.startswith(("precio", "media", "forma", "volatilidad"))]
    pd.testing.assert_frame_equal(X1[cols].iloc[-167:], X2[cols].iloc[-167:])


def test_modelo_supera_o_iguala_baseline(df):
    from vatioplan.modelo import evaluar
    ev = evaluar(df, dias_prueba=60)
    assert ev["metricas"]["mae_modelo"] < 1.5 * ev["metricas"]["mae_base"]
    assert len(ev["real"]) == len(ev["pred"]) and ev["pred"].notna().all()


def test_plantilla_no_inventa_cifras():
    datos = {"tipo_usuario": "Flota eléctrica", "usuario": "Patio", "fuente_datos": "REAL",
             "plan_de_referencia": "Carga inmediata", "ventanas_planeadas": 3, "fechas": [],
             "costo_referencia_cop": 1000000, "costo_vatioplan_cop": 800000, "ahorro_cop": 200000,
             "ahorro_pct": 20.0, "horario_recomendado_primera_ventana": {"A": "00:00–04:00"},
             "horas_mas_caras": ["18:00"], "horas_mas_baratas": ["02:00"], "precio_max": 900,
             "precio_min": 150, "precio_promedio": 400, "mae_modelo": 50, "acierto_horas_baratas": 0.7,
             "ahorro_real_backtest_pct": 18.5, "ahorro_maximo_backtest_pct": 21.0, "dias_backtest": 90,
             "exposicion_bolsa": 0.5, "limite_potencia_kw": 8400, "reglas": "todas cumplen", "supuestos": ""}
    texto = plantilla(datos)
    assert cifras_no_soportadas(texto, datos) == []
    assert formato(texto)["titular_con_ahorro"]
    assert cifras_no_soportadas("Ahorro de 123.456 COP", datos) == ["123.456"]   # detecta una inventada


@pytest.mark.skipif(os.getenv("VATIOPLAN_PRUEBA_LENTA") != "1", reason="flujo completo: VATIOPLAN_PRUEBA_LENTA=1")
def test_flujo_completo(tmp_path):
    from vatioplan.pipeline import ejecutar, incumplimientos
    r = ejecutar(carpeta_salida=tmp_path, verbose=False, con_informe=True)
    assert all(n == 0 for n in incumplimientos(r).values())
    for tipo in ["fabrica", "flota"]:
        assert (tmp_path / tipo / "informe.md").exists()
