# Guía de puesta en marcha (paso a paso)

## Fase 1 · En local (20 min)

```bash
mkdir -p ~/projects && cd ~/projects
unzip /mnt/c/Users/alvar/Downloads/us-flight-delays-platform.zip
cd us-flight-delays-platform
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # 11 tests en verde
python -m ingestion.pipeline --months 2     # datos REALES: 2 meses (~1,2 M de vuelos)
streamlit run app/streamlit_app.py          # abre http://localhost:8501 en Windows
```

## Fase 2 · Azure Data Lake (15 min)

1. portal.azure.com → busca **Cuentas de almacenamiento** → **Crear**.
   - Suscripción: **Azure for Students** · Grupo de recursos: **Crear nuevo** → `rg-flights`
   - Nombre: `flightslakealvaro` (minúsculas, único) · Región: la que te deje (p. ej. West Europe)
   - Rendimiento: **Estándar** · Redundancia: **LRS**
   - Pestaña **Opciones avanzadas** → marca **Habilitar espacio de nombres jerárquico** (esto la convierte en Data Lake Gen2)
   - **Revisar y crear** → **Crear**.
2. Cuando termine: **Ir al recurso** → menú izquierdo **Seguridad y redes → Claves de acceso** → **Mostrar** → copia la **Cadena de conexión** de key1.
3. En Ubuntu:
   ```bash
   export AZURE_STORAGE_CONNECTION_STRING="pega_aquí_la_cadena"
   python -m ingestion.pipeline --months 2
   ```
   En el portal → **Contenedores** verás `flights-lake` con `bronze/` y `gold/`.

## Fase 3 · GitHub + ejecución automática (10 min)

```bash
git init -b main && git add . && git commit -m "US flight delays data platform"
gh repo create us-flight-delays-platform --public --source=. --remote=origin --push
```
- Repo → **Settings → Secrets and variables → Actions → New repository secret**
  - Name: `AZURE_STORAGE_CONNECTION_STRING` · Secret: la cadena de conexión.
- Repo → **Settings → Pages** → Source: **GitHub Actions**.
- Repo → **Actions → Data pipeline → Run workflow** (months = 12). Tarda ~20-30 min.

## Fase 4 · Dashboard público en Streamlit Cloud (10 min)

1. En Azure → tu cuenta de almacenamiento → **Firma de acceso compartido**:
   servicios **Blob**, tipos **Contenedor + Objeto**, permisos **Lectura + Lista**, caducidad 1 año →
   **Generar SAS y cadena de conexión** → copia la **Cadena de conexión** (solo lectura: segura para la app).
2. share.streamlit.io → entra con GitHub → **Create app** → repo `us-flight-delays-platform`,
   rama `main`, archivo `app/streamlit_app.py` → **Advanced settings → Secrets**:
   ```toml
   AZURE_STORAGE_CONNECTION_STRING = "cadena_SAS_de_solo_lectura"
   ```
   → **Deploy**. Elige una URL tipo `us-flight-delays.streamlit.app`.
3. Pon esa URL y la de GitHub Pages en el README.
