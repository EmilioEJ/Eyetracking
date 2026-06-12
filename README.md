# Eyetracking Project

Un avanzado sistema de seguimiento ocular (Eye-Tracking) y predicción utilizando visión artificial. Este proyecto utiliza tu cámara web para calibrar tu mirada, rastrear a dónde estás mirando en la pantalla y generar un mapa de calor en tiempo real junto con los datos de fijación.

## Requisitos Previos

- **Python 3.10 o 3.11:** Es *muy importante* usar alguna de estas versiones. Versiones más recientes (como Python 3.12+) actualmente tienen problemas de compatibilidad con la librería `mediapipe` utilizada en este proyecto.
- Una cámara web conectada y funcional.

## Instalación y Configuración

Sigue estos pasos para clonar el repositorio, configurar un entorno virtual seguro y ejecutar el programa en tu máquina local.

### 1. Clonar el repositorio
Abre tu terminal y clona el repositorio en tu máquina:
```bash
git clone <URL_DEL_REPOSITORIO>
cd "Eyetracking proyecto"
```
*(Sustituye `<URL_DEL_REPOSITORIO>` por el enlace de tu repositorio de Git).*

### 2. Crear un Entorno Virtual
Se recomienda encarecidamente utilizar un entorno virtual para instalar las dependencias y evitar conflictos con otras librerías de tu sistema.
Asegúrate de tener instalada la herramienta venv para tu versión de Python (ej. `sudo apt install python3.11-venv` en sistemas basados en Debian/Ubuntu).

Crea el entorno virtual usando Python 3.11 (o 3.10):
```bash
python3.11 -m venv venv
```

### 3. Activar el Entorno Virtual
Antes de instalar las dependencias o correr el programa, debes activar el entorno:
- **En Linux/macOS:**
  ```bash
  source venv/bin/activate
  ```
- **En Windows (Símbolo del sistema / PowerShell):**
  ```cmd
  venv\Scripts\activate
  ```
*(Sabrás que está activado porque aparecerá `(venv)` al inicio de la línea en tu terminal).*

### 4. Instalar las Dependencias
Con el entorno activado, instala todas las librerías necesarias ejecutando:
```bash
pip install -r requirements.txt
```

---

## Ejecución del Programa

Para iniciar el programa, asegúrate de que tu entorno virtual sigue activado y ejecuta:
```bash
python3 eyetracker.py
```

### Proceso de Calibración
1. Al iniciar, verás una **pantalla de bienvenida**. Presiona la **barra espaciadora** para comenzar.
2. Mantén la cabeza quieta y la mirada fija en el **punto verde** que aparecerá en pantalla.
3. Alrededor del punto verás un anillo blanco que indica el progreso (tarda unos 3 segundos por punto).
4. El punto verde se moverá a través de 9 posiciones distintas. Síguelo únicamente con la mirada.

### Uso y Mapa de Calor (Heatmap)
Una vez finalizada la calibración, entrarás en el modo de seguimiento y se mostrará un mapa de calor que registrará en tiempo real las zonas de la pantalla que más miras.

**Controles interactivos:**
- **[R]**: Recalibrar (volverá a mostrar los puntos verdes).
- **[C]**: Limpiar el mapa de calor acumulado actualmente.
- **[S]**: **Guardar y Salir.**
- **[ESC]**: Salir sin guardar los datos recientes.

---

## Archivos Generados (Datos de Salida)

Al presionar la tecla **[S]** para salir de la aplicación, el programa generará dos carpetas automáticamente (si no existen) y guardará la sesión actual usando la fecha y hora:

- **Carpeta `Gaze_Images/`**: Guarda una imagen en formato PNG del mapa de calor final (Ejemplo: `heatmap_2026-05-17_16-15-30.png`).
- **Carpeta `fixation_data/`**: Guarda un archivo CSV con las coordenadas (X, Y) y el tiempo acumulado de fijación de la mirada (Ejemplo: `fixation_data_2026-05-17_16-15-30.csv`).
