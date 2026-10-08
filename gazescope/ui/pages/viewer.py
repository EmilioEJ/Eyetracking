"""Visor de sesión: heatmap, scanpath, fog y replay sobre cada escena, con AOIs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...config import COLORMAPS
from ...core import report
from ...core.heatmap import fog_image, heatmap_image, scanpath_image
from ...core.session import AOI, Session
from .. import theme
from ..widgets.common import Card, ImageView, Segmented, StatCard, bgr_to_qimage, label

AOI_COLORS = ["#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa"]


def _session_title(s: Session) -> str:
    from datetime import datetime

    try:
        return "Sesión del " + datetime.fromisoformat(s.meta.get("started", "")).strftime("%d %b %Y · %H:%M")
    except ValueError:
        return f"Sesión {s.id}"


class SceneCanvas(ImageView):
    """Imagen de la escena + AOIs + capa de replay pintada con QPainter."""

    aoi_drawn = Signal(QRectF)  # en coordenadas de imagen

    def __init__(self, parent=None):
        super().__init__("Selecciona una escena", radius=14, parent=parent)
        self.aois: list[AOI] = []
        self.drawing = False
        self._drag: tuple[QPointF, QPointF] | None = None
        self.replay_trail: list[tuple[float, float]] = []
        self.replay_fix: tuple[float, float, float] | None = None  # x, y, duración
        self.setMouseTracking(True)

    def _to_image(self, pt: QPointF) -> QPointF:
        r = self.image_rect()
        if self.image is None:
            return pt
        s = self.image.width() / r.width()
        return QPointF((pt.x() - r.x()) * s, (pt.y() - r.y()) * s)

    def _to_widget(self, x: float, y: float) -> QPointF:
        r = self.image_rect()
        if self.image is None:
            return QPointF(x, y)
        s = r.width() / self.image.width()
        return QPointF(r.x() + x * s, r.y() + y * s)

    def set_drawing(self, on: bool) -> None:
        self.drawing = on
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e) -> None:
        if self.drawing and e.button() == Qt.MouseButton.LeftButton and self.image is not None:
            p = e.position()
            self._drag = (p, p)

    def mouseMoveEvent(self, e) -> None:
        if self._drag:
            self._drag = (self._drag[0], e.position())
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            a, b = (self._to_image(p) for p in self._drag)
            self._drag = None
            rect = QRectF(a, b).normalized()
            self.update()
            if rect.width() > 12 and rect.height() > 12:
                self.aoi_drawn.emit(rect)

    def paint_extra(self, p: QPainter, target: QRectF) -> None:
        if self.image is None:
            return
        s = target.width() / self.image.width()
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        for i, a in enumerate(self.aois):
            col = QColor(AOI_COLORS[i % len(AOI_COLORS)])
            tl = self._to_widget(a.x, a.y)
            r = QRectF(tl.x(), tl.y(), a.w * s, a.h * s)
            fill = QColor(col)
            fill.setAlphaF(0.12)
            p.setBrush(fill)
            p.setPen(QPen(col, 2))
            p.drawRoundedRect(r, 6, 6)
            tag = QRectF(r.left(), r.top() - 22, max(60, len(a.name) * 8 + 16), 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(tag, 5, 5)
            p.setPen(QColor("#06121a"))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, a.name)
        if self._drag:
            p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self._drag[0], self._drag[1]).normalized())

        # replay
        n = len(self.replay_trail)
        for i, (x, y) in enumerate(self.replay_trail):
            k = (i + 1) / n
            c = QColor(theme.ACCENT)
            c.setAlphaF(0.15 + 0.5 * k)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(self._to_widget(x, y), 2 + 3 * k, 2 + 3 * k)
        if self.replay_fix:
            x, y, d = self.replay_fix
            c = self._to_widget(x, y)
            r = (18 + min(d, 2.0) * 30) * s * 2
            g = QRadialGradient(c, r)
            a0 = QColor(theme.ACCENT_2)
            a0.setAlphaF(0.55)
            a1 = QColor(theme.ACCENT_2)
            a1.setAlphaF(0.0)
            g.setColorAt(0, a0)
            g.setColorAt(1, a1)
            p.setBrush(g)
            p.drawEllipse(c, r, r)
        if n:
            x, y = self.replay_trail[-1]
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self._to_widget(x, y), 14, 14)


class ViewerPage(QWidget):
    back = Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.session: Session | None = None
        self.scene_id: int | None = None
        self.mode = "heatmap"
        self._density_cache: dict[int, np.ndarray] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # --------------------------------------------------- barra superior
        top = QHBoxLayout()
        top.setSpacing(12)
        btn_back = QPushButton(theme.icon("back", theme.MUTED, 18), "Sesiones")
        btn_back.setObjectName("ghost")
        btn_back.clicked.connect(self._go_back)
        top.addWidget(btn_back)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = label("", "h2")
        self.subtitle = label("", "faint")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        top.addLayout(titles, 1)
        self.modes = Segmented([
            ("heatmap", "Calor", "flame"),
            ("scanpath", "Recorrido", "route"),
            ("fog", "Niebla", "fog"),
            ("replay", "Replay", "play"),
        ])
        self.modes.changed.connect(self._set_mode)
        top.addWidget(self.modes)
        self.cmap = QComboBox()
        for c in COLORMAPS:
            self.cmap.addItem(c.capitalize(), c)
        self.cmap.setCurrentIndex(max(0, list(COLORMAPS).index(ctrl.settings.colormap))
                                  if ctrl.settings.colormap in COLORMAPS else 0)
        self.cmap.currentIndexChanged.connect(lambda _i: self._render())
        top.addWidget(self.cmap)
        self.btn_export = QPushButton(theme.icon("export"), "Exportar")
        menu = QMenu(self)
        menu.addAction(theme.icon("report"), "Reporte HTML de la sesión", self._export_html)
        menu.addAction(theme.icon("flame"), "Imagen de la escena (PNG)", self._export_png)
        menu.addAction(theme.icon("folder"), "Abrir carpeta de datos (CSV)", self._open_folder)
        menu.addSeparator()
        menu.addAction(theme.icon("trash", theme.DANGER), "Eliminar sesión", self._delete)
        self.btn_export.setMenu(menu)
        top.addWidget(self.btn_export)
        root.addLayout(top)

        # --------------------------------------------------- cuerpo
        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        center = QVBoxLayout()
        center.setSpacing(10)
        self.canvas = SceneCanvas()
        self.canvas.aoi_drawn.connect(self._add_aoi)
        center.addWidget(self.canvas, 1)
        self.replay_bar = QWidget()
        rb = QHBoxLayout(self.replay_bar)
        rb.setContentsMargins(0, 0, 0, 0)
        self.btn_play = QPushButton(theme.icon("play"), "")
        self.btn_play.setFixedWidth(44)
        self.btn_play.clicked.connect(self._toggle_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self._seek)
        self.time_lbl = label("0.0 s", "muted")
        self.time_lbl.setMinimumWidth(110)
        self.speed = QComboBox()
        for s in (0.5, 1.0, 2.0, 4.0):
            self.speed.addItem(f"{s:g}×", s)
        self.speed.setCurrentIndex(1)
        rb.addWidget(self.btn_play)
        rb.addWidget(self.slider, 1)
        rb.addWidget(self.time_lbl)
        rb.addWidget(self.speed)
        self.replay_bar.hide()
        center.addWidget(self.replay_bar)

        # Tira de escenas: cada cambio de página, scroll o ventana es una escena
        self.scene_list = QListWidget()
        self.scene_list.setViewMode(QListView.ViewMode.IconMode)
        self.scene_list.setFlow(QListView.Flow.LeftToRight)
        self.scene_list.setWrapping(False)
        self.scene_list.setMovement(QListView.Movement.Static)
        self.scene_list.setIconSize(QSize(160, 90))
        self.scene_list.setGridSize(QSize(184, 146))
        self.scene_list.setFixedHeight(166)
        self.scene_list.setWordWrap(True)
        self.scene_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.scene_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.scene_list.currentRowChanged.connect(self._on_scene_row)
        center.addWidget(self.scene_list)
        body.addLayout(center, 1)

        side = QVBoxLayout()
        side.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.k_fix = StatCard("Fijaciones")
        self.k_mean = StatCard("Fijación media")
        self.k_time = StatCard("Atención")
        self.k_cov = StatCard("Cobertura")
        for i, k in enumerate((self.k_fix, self.k_mean, self.k_time, self.k_cov)):
            grid.addWidget(k, i // 2, i % 2)
        side.addLayout(grid)

        aoi_card = Card(padding=14, spacing=8)
        row = QHBoxLayout()
        row.addWidget(label("Áreas de interés", "h2"), 1)
        self.btn_aoi = QPushButton(theme.icon("box"), "Dibujar")
        self.btn_aoi.setCheckable(True)
        self.btn_aoi.toggled.connect(self.canvas.set_drawing)
        row.addWidget(self.btn_aoi)
        aoi_card.lay.addLayout(row)
        aoi_card.lay.addWidget(label("Arrastra un rectángulo sobre la escena (botón, logo, titular…) "
                                     "para medir cuánto y cuándo se miró.", "faint", wrap=True))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["AOI", "1ª fij.", "Perman.", "%"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        aoi_card.lay.addWidget(self.table, 1)
        rm = QPushButton(theme.icon("trash", theme.MUTED, 16), "Quitar seleccionada")
        rm.setObjectName("ghost")
        rm.clicked.connect(self._remove_aoi)
        aoi_card.lay.addWidget(rm, 0, Qt.AlignmentFlag.AlignLeft)
        side.addWidget(aoi_card, 1)
        side_host = QWidget()
        side_host.setLayout(side)
        side_host.setFixedWidth(300)
        body.addWidget(side_host)

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(33)
        self.play_timer.timeout.connect(self._advance)
        self._play_t = 0.0

    # ------------------------------------------------------------ carga
    def load(self, path: str) -> None:
        self._stop_play()
        self.session = Session(Path(path))
        self._density_cache.clear()
        s = self.session
        m = s.metrics()
        mins, secs = divmod(int(m["duration_s"]), 60)
        self.title.setText(_session_title(s))
        acc = s.meta.get("accuracy_deg")
        self.subtitle.setText(
            f"{mins}:{secs:02d} min · {len(s.scenes)} escenas · {m['fixations']} fijaciones · "
            f"{m['valid_ratio'] * 100:.0f} % datos válidos" + (f" · precisión {acc:.1f}°" if acc else ""))
        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        for sc in s.scenes:
            fx = s.fixations_for(sc.id)
            item = QListWidgetItem()
            img = s.image(sc.id)
            thumb = QPixmap.fromImage(bgr_to_qimage(img)).scaled(
                QSize(160, 90), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            item.setIcon(QIcon(thumb))
            name = sc.title or f"Escena {sc.id + 1}"
            if len(name) > 22:
                name = name[:21] + "…"
            item.setText(f"{sc.id + 1}. {name}\n{sc.duration:.1f} s · {len(fx)} fij.")
            item.setToolTip(sc.title or f"Escena {sc.id + 1}")
            item.setData(Qt.ItemDataRole.UserRole, sc.id)
            self.scene_list.addItem(item)
        self.scene_list.blockSignals(False)
        main = s.main_scene()
        row = next((i for i, sc in enumerate(s.scenes) if sc.id == main), 0)
        if s.scenes:
            self.scene_list.setCurrentRow(row)
        else:
            self.scene_id = None
            self.canvas.set_image(None)

    def _on_scene_row(self, row: int) -> None:
        if row < 0 or self.session is None:
            return
        self._stop_play()
        self.scene_id = int(self.scene_list.item(row).data(Qt.ItemDataRole.UserRole))
        self._play_t = 0.0
        self._render()

    # ------------------------------------------------------------ render
    def _density(self) -> np.ndarray:
        assert self.session is not None and self.scene_id is not None
        if self.scene_id not in self._density_cache:
            self._density_cache[self.scene_id] = self.session.density(self.scene_id)
        return self._density_cache[self.scene_id]

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.replay_bar.setVisible(mode == "replay")
        if mode != "replay":
            self._stop_play()
        self._render()

    def _render(self) -> None:
        s, sid = self.session, self.scene_id
        if s is None or sid is None:
            return
        img = s.image(sid)
        cmap = self.cmap.currentData()
        if self.mode == "heatmap":
            out = heatmap_image(img, self._density(), cmap)
        elif self.mode == "scanpath":
            out = scanpath_image(img, s.fixations_for(sid))
        elif self.mode == "fog":
            out = fog_image(img, self._density())
        else:
            out = (img.astype(np.float32) * 0.55).astype(np.uint8)
        self.canvas.replay_trail, self.canvas.replay_fix = [], None
        self.canvas.set_image(bgr_to_qimage(out))
        if self.mode == "replay":
            self._update_replay()
        self._update_metrics()

    def _update_metrics(self) -> None:
        s, sid = self.session, self.scene_id
        if s is None or sid is None:
            return
        m = s.metrics(sid)
        self.k_fix.set(str(m["fixations"]), f"sacada media {m['mean_saccade_deg']:.1f}°")
        self.k_mean.set(f"{m['mean_fixation_ms']:.0f} ms")
        self.k_time.set(f"{m['fixation_time_s']:.1f} s", f"de {m['duration_s']:.1f} s en escena")
        self.k_cov.set(f"{m['coverage'] * 100:.0f} %", "del área visible")
        self.canvas.aois = s.aois.get(sid, [])
        self.canvas.update()
        stats = s.aoi_stats(sid)
        self.table.setRowCount(len(stats))
        for r, st in enumerate(stats):
            vals = [st["name"], "—" if st["ttff_s"] is None else f"{st['ttff_s']:.1f} s",
                    f"{st['dwell_s']:.1f} s", f"{st['share'] * 100:.0f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setForeground(QColor(AOI_COLORS[r % len(AOI_COLORS)]))
                self.table.setItem(r, c, it)

    # ------------------------------------------------------------ AOIs
    def _add_aoi(self, rect: QRectF) -> None:
        s, sid = self.session, self.scene_id
        if s is None or sid is None:
            return
        n = len(s.aois.get(sid, [])) + 1
        name, ok = QInputDialog.getText(self, "Nueva área de interés", "Nombre:", text=f"AOI {n}")
        if not ok:
            return
        s.aois.setdefault(sid, []).append(
            AOI(name.strip() or f"AOI {n}", rect.x(), rect.y(), rect.width(), rect.height()))
        s.save_aois()
        self._update_metrics()

    def _remove_aoi(self) -> None:
        s, sid = self.session, self.scene_id
        row = self.table.currentRow()
        if s is None or sid is None or row < 0:
            return
        del s.aois[sid][row]
        s.save_aois()
        self._update_metrics()

    # ------------------------------------------------------------ replay
    def _scene_bounds(self) -> tuple[float, float]:
        assert self.session is not None and self.scene_id is not None
        g = self.session.gaze[self.session.gaze["scene_id"] == self.scene_id]
        if not len(g):
            return 0.0, 0.0
        return float(g["t"].min()), float(g["t"].max())

    def _toggle_play(self) -> None:
        if self.play_timer.isActive():
            self._stop_play()
        else:
            t0, t1 = self._scene_bounds()
            if self._play_t >= t1 - t0:
                self._play_t = 0.0
            self.play_timer.start()
            self.btn_play.setIcon(theme.icon("pause"))

    def _stop_play(self) -> None:
        self.play_timer.stop()
        self.btn_play.setIcon(theme.icon("play"))

    def _seek(self, v: int) -> None:
        t0, t1 = self._scene_bounds()
        self._play_t = (t1 - t0) * v / 1000.0
        self._update_replay()

    def _advance(self) -> None:
        t0, t1 = self._scene_bounds()
        self._play_t += 0.033 * float(self.speed.currentData())
        if self._play_t >= t1 - t0:
            self._play_t = t1 - t0
            self._stop_play()
        self._update_replay()

    def _update_replay(self) -> None:
        s, sid = self.session, self.scene_id
        if s is None or sid is None:
            return
        t0, t1 = self._scene_bounds()
        t = t0 + self._play_t
        g = s.gaze_for(sid)
        win = g[(g["t"] <= t) & (g["t"] >= t - 0.7)]
        self.canvas.replay_trail = list(zip(win["x"].to_numpy(), win["y"].to_numpy()))
        fix = next((f for f in s.fixations_for(sid) if f.start <= t <= f.end), None)
        self.canvas.replay_fix = (fix.x, fix.y, t - fix.start) if fix else None
        span = max(t1 - t0, 1e-6)
        self.slider.blockSignals(True)
        self.slider.setValue(int(1000 * self._play_t / span))
        self.slider.blockSignals(False)
        self.time_lbl.setText(f"{self._play_t:.1f} / {span:.1f} s")
        self.canvas.update()

    # ------------------------------------------------------------ exportar
    def _export_html(self) -> None:
        if self.session is None:
            return
        out = report.export_html(self.session, self.session.path / "report.html", self.cmap.currentData())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        self.ctrl.toast(f"Reporte guardado en {out.relative_to(self.session.path.parent.parent)}")

    def _export_png(self) -> None:
        s, sid = self.session, self.scene_id
        if s is None or sid is None:
            return
        mode = self.mode if self.mode in ("heatmap", "scanpath", "fog") else "heatmap"
        default = s.path / f"{mode}_escena_{sid + 1}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar imagen", str(default), "PNG (*.png)")
        if not path:
            return
        import cv2

        img = s.image(sid)
        if mode == "fog":
            out = fog_image(img, self._density())
        elif mode == "scanpath":
            out = scanpath_image(img, s.fixations_for(sid))
        else:
            out = heatmap_image(img, self._density(), self.cmap.currentData())
        cv2.imwrite(path, out)
        self.ctrl.toast("Imagen exportada")

    def _open_folder(self) -> None:
        if self.session:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.path)))

    def _delete(self) -> None:
        if self.session is None:
            return
        if QMessageBox.question(self, "Eliminar sesión",
                                f"¿Eliminar la sesión {self.session.id} y todas sus capturas?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.session.delete()
        self.session = None
        self.ctrl.sessions_changed.emit()
        self._go_back()

    def _go_back(self) -> None:
        self._stop_play()
        self.btn_aoi.setChecked(False)
        self.back.emit()
