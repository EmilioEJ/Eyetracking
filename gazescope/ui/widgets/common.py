"""Componentes visuales reutilizables del dashboard."""

from __future__ import annotations

import numpy as np
import cv2
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setObjectName(role)
    lb.setWordWrap(wrap)
    return lb


def bgr_to_qimage(img: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(np.ascontiguousarray(rgb).data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class Card(QFrame):
    def __init__(self, parent=None, hover: bool = False, padding: int = 18, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("cardHover" if hover else "card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(spacing)


class StatCard(Card):
    def __init__(self, title: str, value: str = "—", sub: str = "", parent=None):
        super().__init__(parent, padding=14, spacing=2)
        self.title = label(title, "kpiLabel")
        self.value = label(value, "kpiValue")
        self.sub = label(sub, "faint")
        for w in (self.title, self.value, self.sub):
            self.lay.addWidget(w)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, value: str, sub: str | None = None) -> None:
        self.value.setText(value)
        if sub is not None:
            self.sub.setText(sub)


class StatusDot(QWidget):
    def __init__(self, color: str = theme.FAINT, size: int = 9, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class Chip(QFrame):
    """Píldora con punto de estado y texto."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("chip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(8)
        self.dot = StatusDot()
        self.text = label(text)
        lay.addWidget(self.dot)
        lay.addWidget(self.text)

    def set(self, ok: bool | None, text: str | None = None) -> None:
        self.dot.set_color(theme.FAINT if ok is None else theme.OK if ok else theme.WARN)
        if text is not None:
            self.text.setText(text)


class Segmented(QFrame):
    """Grupo de botones exclusivos (tipo "segmented control")."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str | None]], parent=None):
        super().__init__(parent)
        self.setObjectName("segGroup")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, text, icon_name in options:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_name:
                b.setIcon(theme.icon(icon_name, theme.MUTED, 16))
            b.setMinimumWidth(b.sizeHint().width() + 8)  # que el texto nunca se corte
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        if options:
            self.buttons[options[0][0]].setChecked(True)

    def set_current(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class ImageView(QWidget):
    """Muestra una QImage ajustada (aspect fit) con esquinas redondeadas."""

    def __init__(self, placeholder: str = "", radius: int = 16, parent=None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.placeholder = placeholder
        self.radius = radius
        self.setMinimumSize(200, 150)

    def set_image(self, img: QImage | None) -> None:
        self.image = img
        self.update()

    def image_rect(self) -> QRectF:
        r = QRectF(self.rect())
        if self.image is None or self.image.isNull():
            return r
        iw, ih = self.image.width(), self.image.height()
        s = min(r.width() / iw, r.height() / ih)
        w, h = iw * s, ih * s
        return QRectF(r.x() + (r.width() - w) / 2, r.y() + (r.height() - h) / 2, w, h)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = self.image_rect()
        path = QPainterPath()
        path.addRoundedRect(target, self.radius, self.radius)
        p.setClipPath(path)
        if self.image is None:
            p.fillRect(target, QColor(theme.SURFACE_2))
            p.setPen(QColor(theme.FAINT))
            p.drawText(target, Qt.AlignmentFlag.AlignCenter, self.placeholder)
        else:
            p.drawImage(target, self.image)
        self.paint_extra(p, target)
        p.setClipping(False)
        p.setPen(QPen(QColor(theme.LINE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()

    def paint_extra(self, p: QPainter, target: QRectF) -> None:
        pass


class Gauge(QWidget):
    """Anillo de calidad 0..1 con valor centrado."""

    def __init__(self, size: int = 92, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.text = "—"
        self.setFixedSize(size, size)

    def set(self, value: float, text: str) -> None:
        self.value, self.text = max(0.0, min(1.0, value)), text
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        p.setPen(QPen(QColor(theme.SURFACE_3), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        col = theme.OK if self.value >= 0.99 else theme.ACCENT if self.value >= 0.6 else theme.WARN
        if self.value <= 0.01:
            col = theme.DANGER
        p.setPen(QPen(QColor(col), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, 90 * 16, int(-self.value * 360 * 16))
        f = p.font()
        f.setPixelSize(17)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.FG))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


def pixmap_rounded(pm: QPixmap, radius: int = 12) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(QPointF(0, 0), pm)
    p.end()
    return out
