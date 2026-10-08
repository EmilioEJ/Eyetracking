# GazeScope — eye tracking con webcam

GazeScope convierte una webcam normal en un **seguidor ocular de escritorio**, al estilo de Tobii. Calibras tu mirada una vez y la app se queda en segundo plano: una **burbuja transparente** muestra dónde miras sobre cualquier programa, y al grabar guarda la mirada junto con **capturas de lo que había en pantalla**. Así puedes ver sobre la página web real qué zonas llamaron más la atención.

## Qué incluye

- **Seguimiento robusto a la cabeza**: mide el iris *dentro* de cada ojo (respecto a esquinas y párpados) y añade la pose de la cabeza (`solvePnP`). La versión anterior usaba la posición absoluta del iris y fallaba en cuanto movías la cabeza.
- **Calibración guiada**: una guía de posición con la cámara, 13 puntos animados y 5 de **validación** que miden la precisión real en grados y píxeles. Se descartan parpadeos y valores atípicos.
- **Perfiles**: guarda la calibración por persona y reutilízala. La **corrección de deriva** (`Ctrl+Alt+D`) reajusta el perfil mirando un punto durante un segundo, sin recalibrar.
- **Filtro One Euro**: la burbuja se mantiene estable al fijar la vista y sigue rápido los saltos.
- **Overlay click-through** sobre el monitor elegido. Muestra la burbuja de mirada y, si quieres, un mapa de calor en vivo; no interfiere con el ratón ni con el teclado.
- **Grabación en segundo plano**: guarda capturas cuando cambia la pantalla (scroll, otra página, otra ventana) y el título de la ventana activa en cada escena, por ejemplo «Mi página – Google Chrome».
- **Fijaciones reales** con el algoritmo I-VT: duración, posición, fusión de fijaciones cercanas y descarte de las demasiado cortas.
- **Visor de sesiones** con cuatro modos: **Calor**, **Recorrido** (fijaciones numeradas), **Niebla** (solo se ve lo que se miró) y **Replay** animado.
- **Áreas de interés (AOI)**: dibuja rectángulos sobre la escena y obtén el tiempo hasta la primera fijación, la permanencia, el número de fijaciones, las revisitas y el % de atención.
- **Exportación**: reporte HTML autocontenido para compartir, PNG de cada escena y datos en CSV y JSON.

## Requisitos

- **Python 3.10 u 3.11.** MediaPipe 0.10.11 no es compatible con 3.12 o superior.
- Webcam y, en Linux, una sesión **X11**. El overlay y los atajos globales no funcionan en Wayland.
- En Linux, Qt necesita una librería del sistema:
  ```bash
  sudo apt install libxcb-cursor0
  ```

## Instalación

```bash
python3.11 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python -m gazescope                  # webcam
python -m gazescope --source mouse   # sin cámara: el cursor hace de "mirada" (para probar)
python -m gazescope --monitor 1      # rastrear otro monitor
python -m gazescope --hidden         # arrancar minimizado en la bandeja
```

1. **Inicio**: comprueba que los indicadores de cara, distancia, centrado y luz estén en verde.
2. **Calibración**: escribe un nombre de perfil y pulsa *Iniciar calibración*. Sigue el punto solo con los ojos. Al terminar verás la precisión; guárdala si es *Buena* o *Excelente*.
3. **Grabar**: pulsa *Iniciar grabación* o `Ctrl+Alt+R` desde cualquier app y navega con normalidad. Vuelve a pulsar para detener.
4. **Sesiones**: abre la sesión, recorre las escenas, cambia de modo, dibuja AOIs y exporta el reporte.

¿Aún no tienes datos? En **Sesiones → Crear sesión de ejemplo** se genera una página web simulada con una mirada en patrón F.

Si cierras la ventana, la app sigue en la bandeja del sistema. Para cerrarla del todo, usa *Salir* en el menú de la bandeja.

### Atajos globales

| Atajo | Acción |
|---|---|
| `Ctrl+Alt+R` | Iniciar / detener grabación |
| `Ctrl+Alt+B` | Mostrar / ocultar burbuja |
| `Ctrl+Alt+H` | Mapa de calor en vivo |
| `Ctrl+Alt+D` | Corrección de deriva |

## Datos generados

```
sessions/2026-10-07_18-30-12/
├── meta.json        # monitor, px/grado, perfil y precisión, duración, conteos
├── gaze.csv         # t, x, y, valid, scene_id  (todas las muestras, ~30 Hz)
├── fixations.csv    # start, end, duration, x, y, n, scene_id
├── scenes.json      # id, captura, intervalo de tiempo y título de ventana
├── aois.json        # áreas de interés dibujadas en el visor
├── screens/         # scene_000.jpg, scene_001.jpg, …
├── thumb.jpg
└── report.html      # al exportar
profiles/<nombre>.json   # modelo de calibración + resultado de la validación
data/settings.json       # ajustes
```

Las coordenadas están en píxeles **relativas al monitor rastreado**.

## Precisión: qué esperar

Una webcam no es un eye tracker infrarrojo. Con buena luz frontal, la cabeza estable y a unos 60 cm de la pantalla, el error típico es de **1,5 a 4°** (unos 60 a 160 px en un monitor de 24″ a 1080p). Basta para saber qué bloque de una página atrae la mirada (titular, imagen, botón), pero no qué palabra se lee. Por eso el kernel del mapa de calor se ajusta al error medido en la validación. Si la precisión empeora durante la sesión, usa la corrección de deriva.

## Estructura del código

```
gazescope/
├── core/       # visión y análisis (sin dependencias de UI salvo las fuentes Qt)
│   ├── features.py, head_pose.py   # landmarks → características
│   ├── calibration.py              # modelo ridge polinómico, validación, perfiles
│   ├── filters.py, fixations.py    # One Euro, I-VT
│   ├── heatmap.py                  # calor, scanpath, niebla
│   ├── sources.py                  # webcam (hilo) / ratón + motor de mirada
│   ├── recorder.py, session.py     # grabación, métricas, AOIs
│   └── report.py, demo.py
└── ui/         # PySide6: dashboard, overlay, calibración, tema
legacy/eyetracker.py   # versión original en Pygame, como referencia
```

Tests: `python -m pytest tests`
