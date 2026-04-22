# Dashboard Gas — Hornos & Esmaltado

Dashboard web para visualizar el consumo de gas (kWht/m²) por formato y línea,
con soporte para resolución diaria/mensual y métrica Media/Moda.

**URL pública** (una vez configurado GitHub Pages):  
`https://<tu-usuario>.github.io/<nombre-repo>/`

---

## 🚀 Configuración inicial (una sola vez)

### 1. Crear el repositorio en GitHub

1. Ve a [github.com/new](https://github.com/new)
2. Ponle el nombre que quieras (p.ej. `gas-dashboard`)
3. Déjalo **público** (necesario para GitHub Pages gratuito) o **privado** si tienes GitHub Pro
4. Haz clic en **Create repository**

### 2. Subir este proyecto

En tu ordenador, abre una terminal en la carpeta del proyecto y ejecuta:

```bash
git init
git add .
git commit -m "primera versión"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/<nombre-repo>.git
git push -u origin main
```

### 3. Activar GitHub Pages

1. En GitHub, ve a tu repo → **Settings** → **Pages**
2. En *Source*, selecciona **Deploy from a branch**
3. Rama: `main` / Carpeta: `/docs`
4. Haz clic en **Save**

En 1-2 minutos la web estará disponible en  
`https://<tu-usuario>.github.io/<nombre-repo>/`

### 4. Dar permisos a GitHub Actions

1. Ve a **Settings** → **Actions** → **General**
2. En *Workflow permissions* selecciona **Read and write permissions**
3. Haz clic en **Save**

---

## 🔄 Actualizar datos (uso habitual)

Cada vez que tengas un Excel nuevo:

### Opción A — Desde la web de GitHub (sin instalar nada)

1. Ve a tu repo en GitHub
2. Haz clic en la carpeta `data/`
3. Arrastra el nuevo `.xlsx` encima (o usa el botón *Add file → Upload files*)
4. El nombre del fichero **debe ser exactamente**:
   ```
   P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx
   ```
5. Haz clic en **Commit changes**
6. GitHub Actions arrancará automáticamente (~2 min) y actualizará el dashboard

### Opción B — Con Git en local

```bash
cp /ruta/al/nuevo/archivo.xlsx data/P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx
git add data/
git commit -m "actualizar datos $(date '+%Y-%m-%d')"
git push
```

### Ver el progreso de la actualización

Ve a la pestaña **Actions** en GitHub para ver si el proceso terminó correctamente.
Verás un tick verde ✅ cuando el dashboard esté actualizado.

---

## 🖥️ Ejecutar en local (opcional)

Si quieres probar el dashboard en tu ordenador:

```bash
# 1. Instalar dependencias Python
pip install -r requirements.txt

# 2. Procesar el Excel
python scripts/process.py

# 3. Servir la web localmente
cd docs
python -m http.server 8080
# Abre http://localhost:8080 en el navegador
```

---

## 📁 Estructura del proyecto

```
├── data/
│   └── P1_Control_Consumo_Gas_Energia_...xlsx   ← sube aquí el Excel actualizado
├── docs/
│   ├── index.html          ← dashboard web (GitHub Pages lo sirve desde aquí)
│   └── data.json           ← generado automáticamente por process.py
├── scripts/
│   └── process.py          ← procesa el Excel y genera data.json
├── .github/workflows/
│   └── update.yml          ← GitHub Action que automatiza todo
├── requirements.txt
└── README.md
```

---

## ⚙️ Personalización

### Cambiar número de formatos mostrados

En `scripts/process.py`, modifica:

```python
TOP_N_HOR = 10   # formatos por línea en hornos
TOP_N_ESM = 8    # formatos por línea en esmaltado
```

### Cambiar los límites de outliers

```python
LINE_CUTS_HOR = {1: 100, 3: 100}       # kWht/m² máximo hornos
LINE_CUTS_ESM = {1: 160, 2: 333, ...}  # kWht/m² máximo esmaltado
```

### Cambiar el nombre del fichero Excel

En `scripts/process.py`, modifica:

```python
DEFAULT_XLSX = ROOT / "data" / "tu_nombre_de_archivo.xlsx"
```

Y actualiza también el path en `.github/workflows/update.yml`:

```yaml
paths:
  - "data/tu_nombre_de_archivo.xlsx"
```
