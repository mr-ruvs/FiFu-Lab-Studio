"""
Interactive Kinematic Drawing Canvas Widget for Movimiento Libre / Free Motion.
Supports x(t) freehand, v(t) linear anchor segments, a(t) piecewise step segments,
forward-in-time validation (t_{i+1} >= t_i), and correct Dark / Light theme rendering.
"""

from PySide6.QtWidgets import QWidget, QToolTip
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QPainterPath
import numpy as np
from typing import List, Tuple, Optional


def _cum_trapezoid(y: np.ndarray, x: np.ndarray, initial: float = 0.0) -> np.ndarray:
    """
    Pure NumPy cumulative trapezoidal integration.
    Fully replaces scipy.integrate.cumulative_trapezoid without requiring scipy.
    """
    if len(y) == 0:
        return np.array([], dtype=float)
    if len(y) == 1:
        return np.array([initial], dtype=float)
    dt = np.diff(x)
    trap = 0.5 * (y[:-1] + y[1:]) * dt
    res = np.empty(len(y), dtype=float)
    res[0] = initial
    res[1:] = initial + np.cumsum(trap)
    return res


class KinematicCanvasWidget(QWidget):
    """Custom QWidget canvas for kinematic profile drawing."""

    points_updated = Signal(object)
    warning_triggered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.draw_mode: str = "x(t)"
        self.t_max: float = 10.0
        self.expand_negative: bool = False
        self.theme_mode: str = "dark"

        # Raw user points drawn in normalized canvas coordinates:
        # t_norm in [0..1] (left to right)
        # val_norm in [0..1] (bottom to top if expand_negative=False, or [-1..1] if expand_negative=True)
        self._raw_points: List[QPointF] = []
        self._is_drawing: bool = False

        self.setMinimumHeight(260)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._apply_style()

    def set_theme_mode(self, mode: str):
        self.theme_mode = mode
        self._apply_style()
        self.update()

    def _apply_style(self):
        if self.theme_mode == "dark":
            self.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px;")
        else:
            self.setStyleSheet("background-color: #ffffff; border: 1px solid #d0d7de; border-radius: 6px;")

    def set_draw_mode(self, mode: str):
        self.draw_mode = mode
        self.clear_canvas()

    def set_t_max(self, val: float):
        self.t_max = max(1.0, val)
        self._emit_sampled_kinematics()
        self.update()

    def set_expand_negative(self, expand: bool):
        self.expand_negative = expand
        self.update()

    def clear_canvas(self):
        self._raw_points.clear()
        self._is_drawing = False
        self._emit_sampled_kinematics()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            t_norm, val_norm = self._pixel_to_norm(pos.x(), pos.y())

            if self._raw_points:
                last_t = self._raw_points[-1].x()
                if t_norm < last_t - 0.005:
                    QToolTip.showText(
                        self.mapToGlobal(event.position().toPoint()),
                        "Error: No se puede dibujar hacia la izquierda (t_{i+1} >= t_i)",
                        self
                    )
                    self.warning_triggered.emit("Intento de dibujo hacia atrás rechazado (t < t_último).")
                    return

            self._is_drawing = True
            new_p = QPointF(t_norm, val_norm)

            if self.draw_mode == "x(t)":
                self._raw_points.append(new_p)
            elif self.draw_mode == "v(t)":
                # Linear segment anchoring
                self._raw_points.append(new_p)
            elif self.draw_mode == "a(t)":
                # Piecewise step anchoring: horizontal then vertical
                if self._raw_points:
                    last_p = self._raw_points[-1]
                    step_mid = QPointF(t_norm, last_p.y())
                    self._raw_points.append(step_mid)
                self._raw_points.append(new_p)

            self._emit_sampled_kinematics()
            self.update()

    def mouseMoveEvent(self, event):
        if self._is_drawing and event.buttons() & Qt.LeftButton:
            pos = event.position()
            t_norm, val_norm = self._pixel_to_norm(pos.x(), pos.y())

            if self._raw_points:
                last_t = self._raw_points[-1].x()
                if t_norm < last_t:
                    return

            if self.draw_mode == "x(t)":
                self._raw_points.append(QPointF(t_norm, val_norm))
                self._emit_sampled_kinematics()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_drawing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 40
        plot_rect = QRectF(margin, 25, w - margin - 20, h - 55)

        is_dark = (self.theme_mode == "dark")
        grid_pen = QPen(QColor("#21262d" if is_dark else "#e1e4e8"), 1, Qt.DashLine)
        axis_pen = QPen(QColor("#58a6ff" if is_dark else "#0969da"), 2)
        text_color = QColor("#8b949e" if is_dark else "#57606a")
        accent_color = QColor("#00f0ff" if is_dark else "#0969da")

        # Grid lines
        painter.setPen(grid_pen)
        grid_cols = 10
        grid_rows = 6

        for i in range(grid_cols + 1):
            x = plot_rect.left() + i * (plot_rect.width() / grid_cols)
            painter.drawLine(int(x), int(plot_rect.top()), int(x), int(plot_rect.bottom()))

        for j in range(grid_rows + 1):
            y = plot_rect.top() + j * (plot_rect.height() / grid_rows)
            painter.drawLine(int(plot_rect.left()), int(y), int(plot_rect.right()), int(y))

        # Axes
        painter.setPen(axis_pen)
        painter.drawLine(int(plot_rect.left()), int(plot_rect.top()), int(plot_rect.left()), int(plot_rect.bottom()))

        zero_y_pixel = plot_rect.top() + plot_rect.height() / 2.0 if self.expand_negative else plot_rect.bottom()
        painter.drawLine(int(plot_rect.left()), int(zero_y_pixel), int(plot_rect.right()), int(zero_y_pixel))

        # Labels
        axis_font = QFont("Segoe UI", 9)
        if axis_font.pointSize() <= 0:
            axis_font.setPointSize(9)
        painter.setFont(axis_font)
        painter.setPen(text_color)
        painter.drawText(int(plot_rect.left() - 10), int(plot_rect.bottom() + 20), "0 s")
        painter.drawText(int(plot_rect.right() - 20), int(plot_rect.bottom() + 20), f"{self.t_max:.1f} s")

        mode_str = f"Modo de dibujo: {self.draw_mode} (Haz clic para anclar segmentos) - Restricción: t_(i+1) >= t_i"
        painter.setPen(accent_color)
        painter.drawText(int(plot_rect.left() + 10), int(plot_rect.top() - 6), mode_str)

        if not self._raw_points:
            painter.setPen(QColor("#6e7681" if is_dark else "#8c959f"))
            hint_msg = ("Haz clic punto a punto para anclar segmentos cinemáticos en v(t) o a(t)..."
                        if self.draw_mode in ("v(t)", "a(t)") else
                        "Haz clic y arrastra hacia la derecha para dibujar la curva x(t)...")
            painter.drawText(plot_rect, Qt.AlignCenter, hint_msg)
            return

        # Render Trajectory
        path = QPainterPath()
        first = True

        for p_norm in self._raw_points:
            px, py = self._norm_to_pixel(p_norm, plot_rect)
            if first:
                path.moveTo(px, py)
                first = False
            else:
                path.lineTo(px, py)

        curve_color = (
            QColor("#00f0ff" if is_dark else "#0969da") if self.draw_mode == "x(t)" else
            QColor("#10b981" if is_dark else "#1a7f37") if self.draw_mode == "v(t)" else
            QColor("#a855f7" if is_dark else "#8250df")
        )
        painter.setPen(QPen(curve_color, 3))
        painter.drawPath(path)

        # Node points
        painter.setBrush(QBrush(curve_color))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        for p_norm in self._raw_points:
            px, py = self._norm_to_pixel(p_norm, plot_rect)
            painter.drawEllipse(QPointF(px, py), 4, 4)

    def _pixel_to_norm(self, px: float, py: float) -> Tuple[float, float]:
        w = self.width()
        h = self.height()
        margin = 40
        plot_w = w - margin - 20
        plot_h = h - 55

        t_norm = max(0.0, min(1.0, (px - margin) / max(1.0, plot_w)))

        # Y normalization mapping:
        # In screen coords, top is py = 25, bottom is py = 25 + plot_h
        # Top = 1.0, Bottom = 0.0 (if expand_negative=False)
        # Top = 1.0, Middle = 0.0, Bottom = -1.0 (if expand_negative=True)
        rel_y = (py - 25) / max(1.0, plot_h) # 0.0 at top, 1.0 at bottom
        rel_y = max(0.0, min(1.0, rel_y))

        if self.expand_negative:
            val_norm = 1.0 - 2.0 * rel_y  # [1.0 at top .. -1.0 at bottom]
        else:
            val_norm = 1.0 - rel_y        # [1.0 at top .. 0.0 at bottom]

        return t_norm, val_norm

    def _norm_to_pixel(self, p_norm: QPointF, plot_rect: QRectF) -> Tuple[float, float]:
        px = plot_rect.left() + p_norm.x() * plot_rect.width()
        val = p_norm.y()

        if self.expand_negative:
            # val in [-1.0 .. 1.0]
            rel_y = (1.0 - val) / 2.0
        else:
            # val in [0.0 .. 1.0]
            rel_y = 1.0 - val

        py = plot_rect.top() + rel_y * plot_rect.height()
        return px, py

    def _emit_sampled_kinematics(self):
        if not self._raw_points:
            self.points_updated.emit(np.zeros((0, 4)))
            return

        sorted_pts = sorted(self._raw_points, key=lambda pt: pt.x())
        times_norm = np.array([pt.x() for pt in sorted_pts])
        vals_norm = np.array([pt.y() for pt in sorted_pts])

        t_uniform = np.linspace(0.0, self.t_max, 100)
        t_sample_norm = t_uniform / self.t_max

        primary_val = np.interp(t_sample_norm, times_norm, vals_norm)

        if self.draw_mode == "x(t)":
            x_arr = primary_val * 2.0
            v_arr = np.gradient(x_arr, t_uniform)
            a_arr = np.gradient(v_arr, t_uniform)
        elif self.draw_mode == "v(t)":
            v_arr = primary_val * 0.8
            x_arr = _cum_trapezoid(v_arr, t_uniform, initial=0.0)
            a_arr = np.gradient(v_arr, t_uniform)
        else:
            a_arr = primary_val * 0.5
            v_arr = _cum_trapezoid(a_arr, t_uniform, initial=0.0)
            x_arr = _cum_trapezoid(v_arr, t_uniform, initial=0.0)

        data_matrix = np.column_stack([t_uniform, x_arr, v_arr, a_arr])
        self.points_updated.emit(data_matrix)
