"""
configurar_repo.py — Pone el nombre de SU repositorio de GitHub en los archivos que lo usan
(n8n_workflow.json, notebook, presentación y guía).

Uso:   python configurar_repo.py usuario/nombre-del-repo
Ej.:   python configurar_repo.py julianordonez/VatioPlan
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARCHIVOS = ["n8n_workflow.json", "notebooks/VatioPlan_completo.ipynb", "entregables/construir_presentacion.py",
            "GUIA_DEMO.md", "README.md"]
if len(sys.argv) != 2 or "/" not in sys.argv[1]:
    sys.exit("Uso: python configurar_repo.py usuario/nombre-del-repo")
nuevo = sys.argv[1].strip().removesuffix(".git").strip("/")
for nombre in ARCHIVOS:
    ruta = RAIZ / nombre
    if not ruta.exists():
        continue
    texto = ruta.read_text(encoding="utf-8")
    cambiado = texto.replace("TU_USUARIO/VatioPlan", nuevo)
    if cambiado != texto:
        ruta.write_text(cambiado, encoding="utf-8")
        print(f"✔ {nombre}")
print(f"Repositorio configurado: https://github.com/{nuevo}")
