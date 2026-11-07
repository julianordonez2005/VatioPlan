# VatioPlan · Guía para ejecutar desde cero y practicar la demostración

Entrega: presentación e informe en Bloque Neón hasta el **17 de noviembre de 2026, 7:00 a. m.**
Presentación: **10 minutos en total, con demostración en vivo** (≈ 7 min de diapositivas + 3 min de demo).

---

## Parte A · Ejecutar el prototipo desde cero (una sola vez, ~30 min)

### A1. Instalar lo necesario
1. **Python 3.11 o 3.12** desde https://www.python.org/downloads/ (en Windows, marquen *Add Python to PATH*).
2. **Git** (opcional, para clonar): https://git-scm.com/downloads
3. Un editor (VS Code) y un navegador (Chrome o Edge).

### A2. Obtener el proyecto y crear SU repositorio nuevo
1. Descomprimir `VatioPlan.zip` y abrir una terminal dentro de la carpeta `VatioPlan`.
2. En https://github.com/new crear un repositorio **vacío** (sin README, sin .gitignore, sin licencia).
3. Configurar el nombre y subir:
```bash
python configurar_repo.py SU_USUARIO/NOMBRE_DEL_REPO
git init
git add .
git commit -m "VatioPlan: versión inicial"
git branch -M main
git remote add origin https://github.com/SU_USUARIO/NOMBRE_DEL_REPO.git
git push -u origin main
```

### A3. Crear el entorno e instalar dependencias
```bash
python -m venv .venv
# Windows:             .venv\Scripts\activate
# Mac / Linux:         source .venv/bin/activate
pip install -r requirements-entregables.txt
```
Comprobación: `python -c "import pulp, sklearn, streamlit; print('ok')"` debe imprimir `ok`.

### A4. Key gratuita del LLM (5 min)
1. Entrar a https://aistudio.google.com/apikey con una cuenta de Google → *Create API key*.
2. Copiar `.env.example` como `.env` y pegar la key: `GEMINI_API_KEY=AIza...`
3. Para la app también sirve `.streamlit/secrets.toml` (copiar de `secrets.toml.example`).
   Sin key todo funciona igual, pero el informe sale con la plantilla y la evaluación del LLM queda incompleta.

### A5. Descargar los datos reales (desde una red en Colombia; 5–15 min la primera vez)
```bash
python -m vatioplan.pipeline
```
- Al final debe decir `Fuente de datos: REAL` (en `salidas/estado.json`).
- Si SIMEM bloquea a mitad de camino (error 403), esperen unos minutos y vuelvan a correrlo: los bloques ya
  descargados quedan en `data/simem_bloques/` y solo pide lo que falta.
- Si sale `SIMULADO`, **no sigan**: revisen la conexión o la red (algunas redes universitarias o VPN bloquean).

### A6. Ajustar hiperparámetros y generar toda la evidencia (≈ 5 min)
```bash
python -m vatioplan.validacion --guardar     # elige hiperparámetros con el conjunto de VALIDACIÓN
python -m vatioplan.reporte                  # pipeline + calidad + validación + casos + LLM + figuras
python entregables/construir_presentacion.py # → entregables/VatioPlan_Proyecto_Final.pptx (cifras reales)
python entregables/construir_informe.py      # → entregables/Informe_VatioPlan.docx (2 páginas)
pytest -q                                    # pruebas de cada componente
```
Revisen que la presentación **ya no tenga el aviso rojo “DATOS SIMULADOS”**. Abran el .pptx, lean las cifras y ajusten
a mano lo que quieran decir distinto (las notas del orador ya traen el guion con tiempos).
El informe: ábranlo en Word, verifiquen que sean 2 páginas y expórtenlo a PDF para Bloque Neón.

### A7. Abrir la aplicación web local
```bash
streamlit run app.py
```
Se abre en http://localhost:8501. La primera carga tarda ~1 minuto (entrena el modelo y calcula los backtests);
después todo responde en segundos mientras la app siga abierta.

### A8. (Opcional) Orquestación
Siga la sección *Pasos que faltan para dejar la orquestación andando* del README (GitHub Actions, Prefect, n8n).
Para la presentación basta con mostrar el workflow y decir que corre a las 6:15 a. m.

---

## Parte B · Guion de la demostración en vivo (3 minutos)

**Antes de empezar:** la app abierta y ya cargada en la pestaña *Plan del día*, usuario **Fábrica**, zoom del navegador
al 80–90 %, la presentación en otra ventana. No pulsen “Actualizar datos” durante la demo.

| Tiempo | Qué hacer en la app | Qué decir |
|---|---|---|
| 0:00–0:35 | Barra lateral → *Fábrica manufacturera*. Mostrar las 4 métricas y las dos gráficas. | “Esta es la planta Rioclaro. A la izquierda, cómo opera hoy; a la derecha, el plan de VatioPlan para mañana. La línea negra es el precio pronosticado: los molinos se van a las horas baratas y el costo baja X %.” |
| 0:35–0:55 | Bajar a la tabla *Horario recomendado y por qué*. | “Para cada equipo, el horario y el precio promedio que paga: el molino de crudo paga X % menos por kWh.” |
| 0:55–1:25 | Cambiar *Potencia máxima contratada* a **19.000** kW. Mostrar que el plan se reacomoda y la tabla de reglas sigue en ✅. Luego poner **18.000** → aparece la advertencia; volver a **21.000**. | “Si el contrato baja a 19 MW, el optimizador reacomoda los molinos y verifica las reglas. Con 18 MW no hay forma de cumplir la producción: el sistema lo avisa en lugar de inventar un plan.” |
| 1:25–2:00 | Cambiar a *Flota eléctrica*. Abrir *Vehículos del patio*, poner *Carga al llegar* del primer grupo en **10 %**. | “Ahora el patio de Fontibón. Si los buses llegan más descargados, la carga se reparte en la madrugada sin pasar el límite del patio y todos salen al 95 %.” |
| 2:00–2:30 | Pestaña *Validación*: mostrar tabla de sobreajuste, comparación de modelos y casos de prueba. | “Aquí está la validación: entrenamiento, validación y prueba; comparación contra el ingenuo, la red neuronal y las versiones anteriores; y los casos de prueba del optimizador.” |
| 2:30–3:00 | Pestaña *Informe IA* → *Redactar con IA*. Señalar la línea “Verificación de cifras: ✅”. | “Gemini redacta el informe para el jefe de patio, solo con cifras calculadas. La app verifica que no invente ningún número. Esto le llega cada mañana por correo.” |

**Plan B (si algo falla):**
- *Sin internet en el salón:* la app funciona con los datos guardados en `data/` (no pulsen “Actualizar”). El LLM
  necesita internet; sin él se muestra la plantilla y lo dicen: “sin conexión usamos la plantilla, que es el respaldo”.
- *La app se cuelga:* tengan abierto un segundo navegador con la app ya cargada, o un video de 3 minutos grabado
  (Win + Alt + R en Windows; Cmd + Shift + 5 en Mac) y capturas de pantalla.
- *El LLM tarda más de 10 s:* sigan hablando de la validación y vuelvan al informe al final.

---

## Parte C · Cómo practicar

### Reparto de los 10 minutos (las notas de cada diapositiva traen el texto)
| Diapositivas | Tema | Tiempo | Quién |
|---|---|---|---|
| 1–4 | Portada, problema, cliente y valor, hoy vs. VatioPlan | 2:10 | Persona A |
| 5–7 | Datos y calidad, EDA → decisiones, método de IA | 1:50 | Persona B |
| 8–12 | Ajuste y baseline, sobreajuste, errores, reglas y LLM, resultado | 3:05 | Persona A |
| 13 | Demostración en vivo | 3:00 | Persona B maneja la app, A narra (o al revés) |
| 14–15 | Reproducible, gracias | 0:30 | Persona B |
| **Total** | | **≈ 10:35 → recortar a 10:00** | |

### Plan de ensayo (3 días)
1. **Ensayo 1 (sin reloj):** cada uno lee sus notas en voz alta y marca lo que suena forzado. Ajusten el texto.
2. **Ensayo 2 (con cronómetro):** completo, con demo real. Anoten el tiempo por bloque; recorten hasta 9:30
   (el día real siempre se alarga).
3. **Ensayo 3 (simulacro):** en el computador y la red que usarán, con alguien que haga preguntas. Practiquen el plan B
   una vez (apagar el wifi a mitad de la demo).
4. La mañana de la presentación: abrir la app 10 minutos antes y dejarla cargada.

### Preguntas probables y respuesta corta
- **¿Por qué no una red neuronal?** La comparamos (MLP 64-32 con parada temprana). Con ~30.000 filas tabulares y
  pocas variables, el gradient boosting iguala o supera y es más interpretable. Está en la tabla de comparación.
- **¿Cómo evitan la fuga de datos?** Todas las variables tienen rezago ≥ 7 días y la partición es temporal; hay
  una prueba automática que lo verifica (`tests/test_componentes.py`).
- **¿Por qué el MAE del modelo no es el más bajo?** Elegimos por ahorro real, no por MAE: importa ordenar bien las
  horas de cada día. (Si en sus cifras reales el principal sí tiene el menor MAE, digan que gana en ambos.)
- **¿Los datos de Argos y del patio son reales?** La capacidad y la flota son públicas; las potencias por equipo y
  las baterías son estimaciones con fuentes citadas. Todo es editable en la app.
- **¿Y si el LLM inventa una cifra?** La app compara cada número del texto con los datos de entrada y lo marca;
  en la evaluación medimos el porcentaje de casos sin cifras inventadas.
- **¿Quién paga?** La empresa con energía expuesta a bolsa; el ahorro anual estimado está en la diapositiva 3.
- **¿Qué pasa si SIMEM se cae?** Caché por bloques y reintentos; si no hay datos reales, la app lo dice (SIMULADO)
  y el orquestador no publica.

### Lista de chequeo antes de entregar (17 nov, 7:00 a. m.)
- [ ] `salidas/estado.json` dice `"fuente": "REAL"`.
- [ ] Presentación sin aviso rojo; cifras revisadas; 15 diapositivas + 3 de referencias.
- [ ] Informe de 2 páginas exportado a PDF.
- [ ] `pytest -q` sin errores.
- [ ] Repositorio actualizado (incluye `config/modelo.json` y `reporte/`).
- [ ] Ensayo cronometrado ≤ 10 min.
