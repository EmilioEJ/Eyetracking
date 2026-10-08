"""Paleta, hoja de estilos e íconos vectoriales de la aplicación."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

BG = "#0b0d12"
SURFACE = "#12161e"
SURFACE_2 = "#181d27"
SURFACE_3 = "#1f2532"
LINE = "#252c3a"
FG = "#e8ecf3"
MUTED = "#8a94a6"
FAINT = "#5b6476"
ACCENT = "#22d3ee"
ACCENT_2 = "#a78bfa"
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#f87171"

FONT_FAMILY = "Inter"


def app_font() -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPointSizeF(10.5)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


STYLESHEET = f"""
* {{ font-family: "{FONT_FAMILY}", "Cantarell", sans-serif; color: {FG}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_3}; color: {FG}; border: 1px solid {LINE}; padding: 6px 8px; border-radius: 6px; }}

/* ------------------------------------------------------------ sidebar */
QFrame#sidebar {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
QLabel#brand {{ font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }}
QLabel#brandSub {{ color: {FAINT}; font-size: 11px; }}
QPushButton#nav {{
    text-align: left; padding: 10px 14px; border: none; border-radius: 10px;
    color: {MUTED}; font-size: 13px; font-weight: 500; background: transparent;
}}
QPushButton#nav:hover {{ background: {SURFACE_2}; color: {FG}; }}
QPushButton#nav:checked {{ background: {SURFACE_3}; color: {FG}; }}

/* ------------------------------------------------------------ texto */
QLabel#h1 {{ font-size: 24px; font-weight: 700; letter-spacing: -0.4px; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#faint {{ color: {FAINT}; font-size: 11px; }}
QLabel#kpiValue {{ font-size: 22px; font-weight: 700; }}
QLabel#kpiLabel {{ color: {MUTED}; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }}

/* ------------------------------------------------------------ tarjetas */
QFrame#card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; }}
QFrame#cardHover {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px; }}
QFrame#cardHover:hover {{ border-color: {ACCENT}; background: {SURFACE_2}; }}
QFrame#chip {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 12px; }}

/* ------------------------------------------------------------ botones */
QPushButton {{
    background: {SURFACE_3}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 8px 14px; font-weight: 500;
}}
QPushButton:hover {{ border-color: #3a4456; background: #242b3a; }}
QPushButton:pressed {{ background: {SURFACE_2}; }}
QPushButton:disabled {{ color: {FAINT}; background: {SURFACE_2}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    color: #06121a; border: none; font-weight: 700;
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5ee4f5, stop:1 #c0aaff); }}
QPushButton#primary:disabled {{ background: {SURFACE_3}; color: {FAINT}; }}
QPushButton#danger {{ background: #3a1c22; border: 1px solid #5c2a33; color: #ffd3d3; }}
QPushButton#danger:hover {{ background: #4a2129; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 6px 8px; }}
QPushButton#ghost:hover {{ color: {FG}; background: {SURFACE_2}; }}
QPushButton#seg {{ border-radius: 8px; padding: 6px 12px; background: transparent; border: none; color: {MUTED}; }}
QPushButton#seg:checked {{ background: {SURFACE_3}; color: {FG}; }}
QFrame#segGroup {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; }}

/* ------------------------------------------------------------ formularios */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px; min-height: 20px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: #3a4456; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {LINE}; selection-background-color: {SURFACE_3}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid #3a4456; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {FG}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

/* ------------------------------------------------------------ listas/tablas */
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border-radius: 10px; padding: 6px; margin: 2px 0; color: {MUTED}; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QListWidget::item:selected {{ background: {SURFACE_3}; color: {FG}; }}
QTableWidget {{ background: transparent; border: none; gridline-color: transparent; }}
QTableWidget::item {{ padding: 4px; border-bottom: 1px solid {LINE}; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
    padding: 6px 4px; font-size: 11px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QHeaderView {{ background: transparent; }}
QTableCornerButton::section {{ background: transparent; border: none; }}
QAbstractItemView {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
QMessageBox, QInputDialog, QDialog {{ background: {SURFACE}; }}
"""

# ------------------------------------------------------------------ íconos
# Trazos propios de 24×24, estilo línea; `C` se sustituye por el color.
_ICONS = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5h4v5"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="C"/>',
    "sessions": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M3.5 9h17"/><path d="M8 13.5h8M8 16.5h5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    "record": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4" fill="C"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="C"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
    "flame": '<path d="M12 21c-4 0-6.5-2.6-6.5-6.2 0-3.4 2.4-5.4 3.6-8 .9 1.6 1.6 2.6 2.9 3.2.2-2.5 1.2-4.6 3.1-6.5.4 3.8 3.4 6 3.4 10.6C18.5 18.2 16 21 12 21Z"/>',
    "route": '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="16" cy="16" r="1.6"/><path d="M7.8 16.6 14.5 15M16.6 14.5 17.6 8.2"/>',
    "fog": '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17Z" fill="C"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5Z" fill="C"/>',
    "pause": '<rect x="7" y="5.5" width="3.5" height="13" rx="1" fill="C"/><rect x="13.5" y="5.5" width="3.5" height="13" rx="1" fill="C"/>',
    "export": '<path d="M12 15V3.5M7.5 8 12 3.5 16.5 8"/><path d="M4.5 14v4.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V14"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    "back": '<path d="M14.5 5.5 8 12l6.5 6.5"/>',
    "box": '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="3 2.4"/>',
    "drift": '<circle cx="12" cy="12" r="2.2" fill="C"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>',
    "camera": '<rect x="3" y="6.5" width="13" height="11" rx="2.5"/><path d="m16 10.5 5-3v9l-5-3"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/>',
    "report": '<path d="M7 3.5h7.5L19 8v12.5H7Z"/><path d="M14.5 3.5V8H19"/><path d="M10 16v-3M13 16v-5M16 16v-2"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
}


def icon_pixmap(name: str, color: str = FG, size: int = 20) -> QPixmap:
    body = _ICONS[name].replace('"C"', f'"{color}"')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, size * 2, size * 2))
    p.end()
    pm.setDevicePixelRatio(2.0)
    return pm


def icon(name: str, color: str = FG, size: int = 20) -> QIcon:
    ic = QIcon(icon_pixmap(name, color, size))
    ic.addPixmap(icon_pixmap(name, color, size), QIcon.Mode.Disabled)
    return ic


def nav_icon(name: str) -> QIcon:
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, MUTED), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(icon_pixmap(name, ACCENT), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def app_icon(recording: bool = False, size: int = 64) -> QIcon:
    """Logo: un ojo estilizado con iris degradado; rojo al grabar."""
    from PySide6.QtGui import QBrush, QPainterPath, QPen, QRadialGradient

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(SURFACE_3))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 16 * s, 16 * s)
    path = QPainterPath()
    path.moveTo(10 * s, 32 * s)
    path.quadTo(32 * s, 10 * s, 54 * s, 32 * s)
    path.quadTo(32 * s, 54 * s, 10 * s, 32 * s)
    p.setPen(QPen(QColor(FG), 3.2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    g = QRadialGradient(32 * s, 32 * s, 10 * s)
    if recording:
        g.setColorAt(0, QColor("#ffb4b4"))
        g.setColorAt(1, QColor(DANGER))
    else:
        g.setColorAt(0, QColor(ACCENT))
        g.setColorAt(1, QColor(ACCENT_2))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(22 * s, 22 * s, 20 * s, 20 * s))
    p.setBrush(QColor(BG))
    p.drawEllipse(QRectF(28.5 * s, 28.5 * s, 7 * s, 7 * s))
    p.end()
    return QIcon(pm)
