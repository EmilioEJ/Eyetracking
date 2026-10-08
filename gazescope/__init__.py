"""GazeScope: seguimiento ocular con webcam, mapas de calor y análisis de atención."""

import os

# opencv-python trae sus propios plugins de Qt y, al importarse, apunta Qt hacia
# ellos; eso rompe PySide6. Importamos cv2 primero y deshacemos esos cambios.
import cv2  # noqa: F401

for _var in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR"):
    os.environ.pop(_var, None)

__version__ = "2.0.0"
APP_NAME = "GazeScope"
