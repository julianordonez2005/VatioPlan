"""VatioPlan — Consumo eléctrico flexible según el precio de bolsa (Colombia)."""
import os
from pathlib import Path

__version__ = "1.0.0"


def _cargar_env() -> None:
    """Lee el archivo .env de la raíz (GEMINI_API_KEY=..., etc.) sin pisar variables ya definidas."""
    ruta = Path(__file__).resolve().parent.parent / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            valor = valor.strip().strip('"').strip("'")
            if valor:
                os.environ.setdefault(clave.strip(), valor)


_cargar_env()
