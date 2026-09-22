#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WF · 功函数绘图工作台
=====================

iOS / macOS 风格 PySide6 窗口（样式布局与 ``plot_Pdos`` 保持一致），
采用左右两栏布局：

    左栏 —— 图表（matplotlib 平面平均势曲线）
    右栏 —— 参数（数据源、关键数值、曲线参数、坐标轴范围、导出）

功函数绘图逻辑移植自 ``Web_Probe`` 后端 work_function 流程，
计算约定与 ``workfunction-bot`` 一致（LVHAR / LDIPOL / IDIPOL=3 → vaspkit 426）：
    Φ = V_vacuum − E_Fermi

数据来源（选择作业文件夹后自动查找）：
    PLANAR_AVERAGE.dat   平面平均势（必需）
    cmd.log              vaspkit 输出（E-fermi / Vacuum-Level / Work Function）
    OUTCAR / vasprun.xml 费米能级兜底
    POSCAR / CONTCAR     晶格 c 方向长度、原子数与化学式

运行：
    python wf_viewer.py
"""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import numpy as np

from PySide6.QtCore import QBuffer, QEvent, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QColorDialog,
                               QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

import matplotlib
matplotlib.use("QtAgg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei UI", "Microsoft YaHei",
                                           "SimHei", "PingFang SC", "Segoe UI",
                                           "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

from ui_kit import (LIGHT, DARK, THEME, Card, ComboBox, Switch, apply_theme,
                    field_label, hint_label)
from workfunction_core import is_workfunction_dir, load_workfunction


# ==========================================================================
# 路径 / 常量
# ==========================================================================
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RES_DIR = Path(getattr(sys, "_MEIPASS", str(APP_DIR)))
else:
    APP_DIR = Path(__file__).resolve().parent
    RES_DIR = APP_DIR

BASE_DIR = APP_DIR
APP_ICO = APP_DIR / "assets" / "app.ico"

PLOT_BG_DARK = "#1B1B1D"
PLOT_BG_LIGHT = "#FFFFFF"


# ==========================================================================
# 数值工具
# ==========================================================================
def _nice_range(lo, hi, pad=0.06):
    """把区间取整到“好看”的刻度，并留一点边距。"""
    lo, hi = float(lo), float(hi)
    if not np.isfinite(lo) or not np.isfinite(hi):
        return -1.0, 1.0
    if hi <= lo:
        lo, hi = lo - 1.0, hi + 1.0
    span = hi - lo
    lo -= span * pad
    hi += span * pad
    step = 10.0 ** math.floor(math.log10(max(span, 1e-9)))
    return (math.floor(lo / step) * step, math.ceil(hi / step) * step)


def _nice_tick(span):
    """根据区间宽度选一个合适的主刻度间距。"""
    span = abs(float(span))
    if not np.isfinite(span) or span <= 0:
        return None
    raw = span / 10.0
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= m * mag:
            return m * mag
    return 10.0 * mag


# ==========================================================================
# 应用图标（随机生成）
# ==========================================================================
def _fallback_color(tag):
    h = int(hashlib.md5(tag.encode("utf-8")).hexdigest()[:6], 16)
    r = max((h >> 16) & 0xFF, 80)
    g = max((h >> 8) & 0xFF, 80)
    b = max(h & 0xFF, 80)
    return f"#{r:02X}{g:02X}{b:02X}"


def make_random_app_icon(size=256):
    """随机生成一个个性化应用图标：渐变圆角底 + 波浪势能曲线图案。"""
    import random
    rng = random.Random()
    base_hue = rng.randint(0, 359)
    hue2 = (base_hue + rng.randint(40, 150)) % 360

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    margin = size * 0.05
    from PySide6.QtCore import QRectF, QPointF
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    radius = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor.fromHsv(base_hue, 190, 240))
    grad.setColorAt(1.0, QColor.fromHsv(hue2, 205, 180))
    p.fillPath(path, QBrush(grad))

    hl = QLinearGradient(rect.topLeft(),
                         QPointF(rect.left(), rect.center().y()))
    hl.setColorAt(0.0, QColor(255, 255, 255, 70))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(hl))

    # 平面平均势：两端平台 + 中间势垒谷
    white = QColor(255, 255, 255, 240)
    p.setPen(QPen(white, max(2.0, size * 0.028),
                  Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    w = rect.width()
    h = rect.height()
    x0, y0 = rect.left() + w * 0.12, rect.top() + h * 0.34
    x1, y1 = rect.left() + w * 0.88, rect.top() + h * 0.72
    wave = QPainterPath()
    n = 60
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        # 两端抬升的平台 + 中间平滑下降的形状
        near_edge = min(t, 1 - t)
        shape = 1.0 - math.exp(-3.2 * (near_edge ** 0.85))
        y = y1 + (y0 - y1) * shape
        if i == 0:
            wave.moveTo(x, y)
        else:
            wave.lineTo(x, y)
    p.drawPath(wave)

    # 两条水平参考线（E_F / V_vac）
    p.setPen(QPen(QColor(255, 255, 255, 150), size * 0.014, Qt.DashLine))
    p.drawLine(QPointF(x0, y0), QPointF(x1, y0))
    p.drawLine(QPointF(x0, y1), QPointF(x1, y1))

    p.setPen(QPen(QColor(255, 255, 255, 70), size * 0.012))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
    p.end()

    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pm.scaled(s, s, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation))
    return icon


def write_ico(pm, path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """把 QPixmap 写成多分辨率 .ico（PNG 负载）。"""
    import struct
    pngs = []
    for s in sizes:
        img = pm.scaled(s, s, Qt.KeepAspectRatio,
                        Qt.SmoothTransformation).toImage()
        buf = QBuffer()
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        pngs.append((s, bytes(buf.data())))
    n = len(pngs)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries = b""
    for s, data in pngs:
        wh = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32,
                               len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header)
        f.write(entries)
        for _, data in pngs:
            f.write(data)


# ==========================================================================
# 曲线画布
# ==========================================================================
class WorkFunctionView(FigureCanvasQTAgg):
    """matplotlib 画布：绘制平面平均势并标注 E_F / V_vac / Φ。"""

    def __init__(self, parent=None):
        self.figure = Figure(figsize=(6, 4), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.ax = self.figure.add_subplot(111)
        self._dark = False

    def set_theme(self, dark):
        self._dark = dark
        bg = PLOT_BG_DARK if dark else PLOT_BG_LIGHT
        self.figure.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        for spine in self.ax.spines.values():
            spine.set_color("#48484A" if dark else "#E3E3E8")
        self.ax.tick_params(colors="#98989D" if dark else "#6E6E73")
        self.ax.xaxis.label.set_color("#98989D" if dark else "#6E6E73")
        self.ax.yaxis.label.set_color("#98989D" if dark else "#6E6E73")
        self.ax.title.set_color("#F2F2F7" if dark else "#1C1C1E")

    def plot(self, data, *, efermi, vvac, work_function,
             xlim=None, ylim=None, xtick=None, ytick=None,
             line_color="#0A84FF", line_width=2.0,
             show_fermi=True, show_vac=True, show_phi=True,
             ann_fs=11.0,
             title="Planar Average Potential along z",
             xlabel="z (Angstrom)",
             ylabel="Planar Average Potential V(z) (eV)"):
        self.ax.clear()
        xs = data["z"]
        vs = data["potential"]

        self.ax.plot(xs, vs, color=line_color, linewidth=line_width, zorder=2)

        # 关键水平线
        if show_fermi:
            self.ax.axhline(efermi, color="#e11d48", linestyle="--",
                            linewidth=1.4, zorder=3)
        if show_vac:
            self.ax.axhline(vvac, color="#16a34a", linestyle="--",
                            linewidth=1.4, zorder=3)

        # 坐标轴范围先确定，用于放置右侧数值标签
        if xlim and xlim[0] is not None and xlim[1] is not None:
            self.ax.set_xlim(float(xlim[0]), float(xlim[1]))
        if ylim and ylim[0] is not None and ylim[1] is not None:
            self.ax.set_ylim(float(ylim[0]), float(ylim[1]))
        self.figure.canvas.draw_idle()
        x_left, x_right = self.ax.get_xlim()
        x_span = x_right - x_left
        tag_x = x_right - x_span * 0.015
        y_lo, y_hi = self.ax.get_ylim()
        dy = (y_hi - y_lo) * 0.03  # 文字位置稍稍高于对应参考线

        if show_fermi:
            self.ax.text(tag_x, efermi + dy, f"Fermi level = {efermi:.3f} eV",
                         fontsize=ann_fs, color="#b91c1c", fontweight="bold",
                         ha="right", va="center", zorder=5,
                         bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                   ec="#e11d48", alpha=0.92))
        if show_vac:
            self.ax.text(tag_x, vvac + dy, f"vacuum level = {vvac:.3f} eV",
                         fontsize=ann_fs, color="#15803d", fontweight="bold",
                         ha="right", va="center", zorder=5,
                         bbox=dict(boxstyle="round,pad=0.25", fc="white",
                                   ec="#16a34a", alpha=0.92))

        # 功函数双箭头（放在可视区间中部，避开右侧标签）
        if show_phi:
            x_mid = x_left + x_span * 0.42
            self.ax.annotate(
                "", xy=(x_mid, efermi), xytext=(x_mid, vvac),
                arrowprops=dict(arrowstyle="<->", color="#111827",
                                lw=1.6), zorder=4)
            self.ax.text(x_mid + x_span * 0.02, (efermi + vvac) / 2.0,
                         f"\u03a6 = {work_function:.3f} eV",
                         fontsize=ann_fs + 3, fontweight="bold",
                         color="#111827", va="center", zorder=5,
                         bbox=dict(boxstyle="round,pad=0.3", fc="white",
                                   ec="#111827", alpha=0.9))

        if xtick and xtick > 0:
            self.ax.xaxis.set_major_locator(MultipleLocator(xtick))
        if ytick and ytick > 0:
            self.ax.yaxis.set_major_locator(MultipleLocator(ytick))

        self.ax.set_title(title, fontsize=12, pad=10)
        self.ax.set_xlabel(xlabel, fontsize=10)
        self.ax.set_ylabel(ylabel, fontsize=10)
        self.ax.tick_params(labelsize=8)
        self.ax.grid(True, alpha=0.25, linestyle=":")
        self.set_theme(self._dark)
        self.figure.tight_layout(pad=0.8)
        self.draw()


# ==========================================================================
# 主窗口
# ==========================================================================
class MainWindow(QWidget):
    RESIZE_MARGIN = 6

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WF · 功函数绘图")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(1180, 720)
        self.app_icon = make_random_app_icon()
        self.setWindowIcon(self.app_icon)
        self._ensure_ico_file(self.app_icon)
        self._dark = False
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)
        self._switches = []
        self._shadow_pix = None
        self._shadow_key = None
        self.data = None
        self.job_dir = None
        self._img_ready = False
        self.plot_style = None

        self._build()
        self._rebuild_right()
        self._plot_curve()

    # ------------------------------------------------------------------
    # 窗口 / 阴影
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            wdg = obj
            if (isinstance(wdg, QLineEdit)
                    and isinstance(wdg.parentWidget(), QAbstractSpinBox)):
                wdg = wdg.parentWidget()
            if isinstance(wdg, (QAbstractSpinBox, QComboBox)):
                parent = obj.parentWidget()
                while parent is not None and not isinstance(parent, QScrollArea):
                    parent = parent.parentWidget()
                if parent is not None:
                    QApplication.sendEvent(parent.viewport(), event)
                return True
        return super().eventFilter(obj, event)

    def _install_wheel_guard(self):
        for sp in self.right_area.findChildren(QAbstractSpinBox):
            sp.installEventFilter(self)
            le = sp.lineEdit()
            if le is not None:
                le.installEventFilter(self)
        for cb in self.right_area.findChildren(QComboBox):
            cb.installEventFilter(self)

    @staticmethod
    def _ensure_ico_file(icon):
        ico = APP_ICO if APP_ICO.exists() else APP_DIR / "assets" / "app.ico"
        if ico.exists():
            return
        try:
            ico.parent.mkdir(parents=True, exist_ok=True)
            write_ico(icon.pixmap(256, 256), ico)
        except Exception:
            pass

    def _render_shadow(self, w, h, dark):
        pm = QPixmap(max(1, w), max(1, h))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtCore import QRectF
        m = 18
        rect = QRectF(m - 4, m - 2, w - 2 * m + 8, h - 2 * m + 8)
        base = QColor(0, 0, 0)
        layers = 16
        for i in range(layers, 0, -1):
            alpha = int(2.6 * (layers - i) / layers * (2.2 if dark else 1.6))
            grow = i * 0.9
            p.setBrush(QColor(base.red(), base.green(), base.blue(),
                              max(0, alpha)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect.adjusted(-grow, -grow + 2, grow, grow + 2),
                              16 + grow / 2, 16 + grow / 2)
        p.end()
        return pm

    def paintEvent(self, event):  # noqa: N802
        if self.isMaximized() or self.isFullScreen():
            super().paintEvent(event)
            return
        key = (self.width(), self.height(), self._dark)
        if self._shadow_pix is None or self._shadow_key != key:
            self._shadow_pix = self._render_shadow(self.width(), self.height(),
                                                   self._dark)
            self._shadow_key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._shadow_pix)
        p.end()
        super().paintEvent(event)

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            m = 0 if (self.isMaximized() or self.isFullScreen()) else 18
            self.outer.setContentsMargins(m, m, m, m)
            self.update()

    def _titlebar_press(self, event):
        if event.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def _titlebar_double(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build(self):
        from PySide6.QtCore import QRectF  # noqa: F401
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.outer = outer

        self.container = QFrame()
        self.container.setObjectName("Window")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_titlebar())

        self.right_area, self.right_lay = self._side_panel()
        self.right_footer = self._build_right_footer()
        right_col = QWidget()
        rcol = QVBoxLayout(right_col)
        rcol.setContentsMargins(0, 0, 0, 0)
        rcol.setSpacing(0)
        rcol.addWidget(self.right_area, 1)
        rcol.addWidget(self.right_footer, 0)

        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)
        mid.addWidget(self._page_plot(), 1)
        mid.addWidget(right_col, 0)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_actionbar())
        right.addLayout(mid, 1)
        right.addWidget(self._build_footer())

        wrap = QWidget()
        wrap.setLayout(right)
        root.addWidget(wrap, 1)

    def _build_titlebar(self):
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(48)
        bar.mousePressEvent = self._titlebar_press
        bar.mouseDoubleClickEvent = self._titlebar_double
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        for name, slot in (("TrafficClose", self.close),
                           ("TrafficMin", self.showMinimized),
                           ("TrafficMax", self._toggle_max)):
            btn = QPushButton()
            btn.setObjectName(name)
            btn.setFixedSize(12, 12)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        lay.addStretch(1)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setPixmap(self.app_icon.pixmap(22, 22))
        lay.addWidget(self.icon_label)
        self.app_name = QLabel("WF · 功函数绘图")
        self.app_name.setObjectName("AppName")
        lay.addWidget(self.app_name)
        lay.addStretch(1)

        self.theme_btn = QPushButton("\U0001F319")
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setFixedWidth(38)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("切换深色 / 浅色主题")
        self.theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self.theme_btn)
        return bar

    # ---- 动作栏 / 页脚 ----
    def _build_actionbar(self):
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 16, 24, 8)
        lay.setSpacing(10)
        self.page_title = QLabel("功函数曲线")
        self.page_title.setObjectName("H1")
        lay.addWidget(self.page_title)
        lay.addStretch(1)
        self.chip_phi = QLabel("\u03a6 = —")
        self.chip_phi.setObjectName("Chip")
        lay.addWidget(self.chip_phi)
        return bar

    def _build_footer(self):
        foot = QWidget()
        lay = QVBoxLayout(foot)
        lay.setContentsMargins(24, 6, 24, 16)
        lay.setSpacing(6)
        self.status = QLabel("请点击右侧「选择作业文件夹」加载功函数数据")
        self.status.setObjectName("Footer")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status.setMinimumWidth(0)
        lay.addWidget(self.status)
        return foot

    def _build_right_footer(self):
        box = QWidget()
        box.setFixedWidth(336)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 6, 12, 12)
        lay.setSpacing(8)
        self.btn_save_img = QPushButton("保存图片")
        self.btn_save_img.setObjectName("Secondary")
        self.btn_save_img.setCursor(Qt.PointingHandCursor)
        self.btn_save_img.setToolTip("把当前曲线保存为 300 dpi 图片")
        self.btn_save_img.clicked.connect(self._save_figure)
        lay.addWidget(self.btn_save_img, 1)
        box.setVisible(False)
        return box

    def _side_panel(self, width=336):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setFixedWidth(width)
        inner = QWidget()
        inner.setObjectName("PageInner")
        inner.setAttribute(Qt.WA_StyledBackground, True)
        area.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 4, 12, 12)
        lay.setSpacing(12)
        return area, lay

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

    # ---- 主页面 ----
    def _page_plot(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 2, 8, 12)
        v.setSpacing(10)
        holder = QFrame()
        holder.setObjectName("Card")
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(12, 12, 12, 12)
        self.wf_view = WorkFunctionView()
        hv.addWidget(self.wf_view, 1)
        v.addWidget(holder, 1)
        hint = QLabel("Φ = V_vacuum \u2212 E_Fermi · "
                      "数据来自 PLANAR_AVERAGE.dat / cmd.log")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)
        return page

    # ------------------------------------------------------------------
    # 右栏
    # ------------------------------------------------------------------
    def _rebuild_right(self):
        self._clear_layout(self.right_lay)
        self._switches = []
        self._right_source_card()
        self._right_value_card()
        self._right_curve_card()
        if getattr(self, "right_footer", None) is not None:
            self.right_footer.setVisible(True)
        self._install_wheel_guard()

    # ---- 右栏：数据源 ----
    def _right_source_card(self):
        card = Card("数据源")
        btn_dir = QPushButton("选择作业文件夹")
        btn_dir.setObjectName("Secondary")
        btn_dir.setCursor(Qt.PointingHandCursor)
        btn_dir.clicked.connect(self._pick_job_dir)
        card.add(btn_dir)

        self.lbl_source = QLabel()
        self.lbl_source.setObjectName("Hint")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setTextFormat(Qt.PlainText)
        self.lbl_source.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_source.setMinimumWidth(0)
        self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._update_source_label()
        card.add(self.lbl_source)
        card.add(hint_label("需要 PLANAR_AVERAGE.dat；E_F 可来自 "
                            "cmd.log / OUTCAR / vasprun.xml。"))
        self.right_lay.addWidget(card)

    def _update_source_label(self):
        if getattr(self, "lbl_source", None) is None:
            return

        def brk(s):
            return str(s).replace("\\", "\\\u200b").replace("/", "/\u200b")

        if not self.data:
            self.lbl_source.setText("尚未加载数据")
            return
        files = self.data["files"]

        def nm(p):
            return p.name if p else "（未找到）"

        self.lbl_source.setText(
            f"目录：{brk(self.job_dir)}\n"
            f"平面平均势：{nm(files.get('planar'))}\n"
            f"cmd.log：{nm(files.get('cmd.log'))}\n"
            f"OUTCAR：{nm(files.get('OUTCAR'))}\n"
            f"结构：{nm(files.get('POSCAR'))}")

    # ---- 右栏：关键数值 ----
    def _right_value_card(self):
        card = Card("关键数值")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        rows = [("功函数 \u03a6", f"{self.data['work_function']:.4f} eV"
                 if self.data else "—"),
                ("费米能级 E_F", f"{self.data['efermi']:.4f} eV"
                 if self.data else "—"),
                ("真空能级 V_vac", f"{self.data['v_vacuum']:.4f} eV"
                 if self.data else "—"),
                ("晶格 c", f"{self.data['c_length']:.4f} \u00c5"
                 if self.data and self.data.get("c_length") else "—")]
        for r, (k, val) in enumerate(rows):
            grid.addWidget(field_label(k, 96), r, 0)
            lab = QLabel(val)
            lab.setObjectName("Value")
            lab.setWordWrap(True)
            grid.addWidget(lab, r, 1)
        card.add_layout(grid)
        self.right_lay.addWidget(card)

    # ---- 右栏：曲线参数 ----
    def _right_curve_card(self):
        style = self._plot_style()
        card = Card("曲线参数")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)
        r = 0

        self.sp_xmin = self._spin(style["xmin"], -10000, 10000)
        self.sp_xmax = self._spin(style["xmax"], -10000, 10000)
        grid.addWidget(field_label("横轴区间", 78), r, 0)
        grid.addLayout(self._pair(self.sp_xmin, self.sp_xmax), r, 1)
        r += 1
        self.sp_xtick = self._spin(style["xtick"], 0.0, 5000.0, step=0.5)
        grid.addWidget(field_label("横轴刻度", 78), r, 0)
        grid.addWidget(self.sp_xtick, r, 1)
        r += 1

        self.sp_ymin = self._spin(style["ymin"], -1e5, 1e5, step=0.5)
        self.sp_ymax = self._spin(style["ymax"], -1e5, 1e5, step=0.5)
        grid.addWidget(field_label("纵轴区间", 78), r, 0)
        grid.addLayout(self._pair(self.sp_ymin, self.sp_ymax), r, 1)
        r += 1
        self.sp_ytick = self._spin(style["ytick"], 0.0, 1e5, step=0.5)
        grid.addWidget(field_label("纵轴刻度", 78), r, 0)
        grid.addWidget(self.sp_ytick, r, 1)
        r += 1

        # 费米能级 / 真空能级（可手动微调，Φ 随之更新）
        self.ed_fermi = QLineEdit(f"{style['efermi']:.4f}")
        self.ed_fermi.setFixedHeight(28)
        grid.addWidget(field_label("费米能级", 78), r, 0)
        grid.addWidget(self.ed_fermi, r, 1)
        r += 1
        self.ed_vac = QLineEdit(f"{style['vvac']:.4f}")
        self.ed_vac.setFixedHeight(28)
        grid.addWidget(field_label("真空能级", 78), r, 0)
        grid.addWidget(self.ed_vac, r, 1)
        r += 1

        self.sw_fermi = self._grid_switch(grid, r, "显示费米线",
                                          style["show_fermi"])
        r += 1
        self.sw_vac = self._grid_switch(grid, r, "显示真空线",
                                        style["show_vac"])
        r += 1
        self.sw_phi = self._grid_switch(grid, r, "显示功函数标注",
                                        style["show_phi"])
        r += 1

        grid.addWidget(field_label("曲线颜色", 78), r, 0)
        self.btn_line = self._color_button(style["line_color"], "line_color")
        grid.addWidget(self.btn_line, r, 1)
        r += 1
        self.sp_lw = self._spin(style["line_width"], 0.5, 10.0, step=0.5)
        grid.addWidget(field_label("线宽", 78), r, 0)
        grid.addWidget(self.sp_lw, r, 1)
        r += 1
        self.sp_fs = self._spin(style["ann_fs"], 6.0, 40.0, step=1.0)
        grid.addWidget(field_label("标注字号", 78), r, 0)
        grid.addWidget(self.sp_fs, r, 1)
        r += 1

        card.add_layout(grid)
        btn = QPushButton("重新绘制")
        btn.setObjectName("Primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._redraw)
        card.add(btn)
        self.right_lay.addWidget(card)

    # ---- 小工具 ----
    @staticmethod
    def _spin(value, lo, hi, step=0.5):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(4)
        sp.setSingleStep(step)
        sp.setValue(float(value))
        sp.setMinimumWidth(56)
        sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return sp

    @staticmethod
    def _pair(w1, w2):
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(w1)
        lay.addWidget(QLabel("~"), 0, Qt.AlignCenter)
        lay.addWidget(w2)
        return lay

    def _grid_switch(self, grid, row, text, value):
        sw = Switch()
        sw.setChecked(value, animate=False)
        sw.apply_theme(THEME)
        self._switches.append(sw)
        grid.addWidget(field_label(text, 78), row, 0)
        grid.addWidget(sw, row, 1, Qt.AlignLeft)
        return sw

    def _style_color_btn(self, btn, color):
        col = QColor(color)
        lum = col.red() * 0.299 + col.green() * 0.587 + col.blue() * 0.114
        btn.setText(str(color).upper())
        btn.setStyleSheet(
            "background:%s;color:%s;border:1px solid #00000033;"
            "border-radius:8px;padding:3px 8px;font-weight:600;"
            % (color, "#FFFFFF" if lum < 140 else "#1C1C1E"))

    def _color_button(self, color, key):
        btn = QPushButton()
        btn.setObjectName("Secondary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(28)
        self._style_color_btn(btn, color)
        btn.clicked.connect(lambda _=False, k=key, b=btn: self._pick_color(k, b))
        return btn

    def _pick_color(self, key, btn):
        cur = self._plot_style().get(key, "#0A84FF")
        dlg = QColorDialog(QColor(cur), self)
        dlg.setWindowTitle("选择颜色")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        if dlg.exec():
            c = dlg.currentColor()
            if c.isValid():
                self._plot_style()[key] = c.name()
                self._style_color_btn(btn, c.name())
                self._plot_curve()

    # ------------------------------------------------------------------
    # 数据装载
    # ------------------------------------------------------------------
    def _load_from(self, source):
        try:
            data = load_workfunction(source)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "加载失败", str(exc))
            self.status.setText(f"加载失败：{exc}")
            return
        self.data = data
        self.job_dir = Path(data["root"])
        self.plot_style = None
        self._img_ready = True
        self._update_source_label()
        self.chip_phi.setText(f"\u03a6 = {data['work_function']:.3f} eV")
        src = "cmd.log 检索" if data["wf_source"] == "cmd.log" else "程序计算"
        self.status.setText(
            f"已加载：{Path(source).name} · {len(data['z'])} 点 · "
            f"\u03a6 = {data['work_function']:.4f} eV（{src}）")
        self._rebuild_right()
        self._plot_curve()

    def _pick_job_dir(self):
        start = str(self.job_dir or BASE_DIR)
        d = QFileDialog.getExistingDirectory(
            self, "选择功函数作业文件夹（含 PLANAR_AVERAGE.dat）", start)
        if not d:
            return
        if not is_workfunction_dir(d):
            ret = QMessageBox.question(
                self, "未找到 PLANAR_AVERAGE.dat",
                "该目录下没有 PLANAR_AVERAGE.dat，仍尝试加载吗？",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self._load_from(d)

    # ------------------------------------------------------------------
    # 绘图
    # ------------------------------------------------------------------
    def _default_style(self):
        d = self.data
        z = d["z"]
        v = d["potential"]
        xmin = 0.0 if d.get("c_length") else min(z)
        xmax = d.get("c_length") or max(z)
        ymin, ymax = _nice_range(min(v + [d["efermi"]]),
                                 max(v + [d["v_vacuum"]]))
        return {
            "xmin": round(float(xmin), 3),
            "xmax": round(float(xmax), 3),
            "xtick": _nice_tick(xmax - xmin) or 5.0,
            "ymin": round(float(ymin), 3),
            "ymax": round(float(ymax), 3),
            "ytick": _nice_tick(ymax - ymin) or 2.0,
            "efermi": float(d["efermi"]),
            "vvac": float(d["v_vacuum"]),
            "show_fermi": True,
            "show_vac": True,
            "show_phi": True,
            "line_color": "#0A84FF",
            "line_width": 2.0,
            "ann_fs": 11.0,
            "title": "Planar Average Potential along z",
        }

    def _plot_style(self):
        if getattr(self, "plot_style", None) is None:
            self.plot_style = self._default_style() if self.data else {
                "xmin": 0.0, "xmax": 10.0, "xtick": 2.0,
                "ymin": -10.0, "ymax": 10.0, "ytick": 2.0,
                "efermi": 0.0, "vvac": 0.0, "show_fermi": True,
                "show_vac": True, "show_phi": True,
                "line_color": "#0A84FF", "line_width": 2.0,
                "ann_fs": 11.0,
                "title": "Planar Average Potential along z"}
        return self.plot_style

    def _read_style_from_controls(self):
        s = self._plot_style()
        s["xmin"] = self.sp_xmin.value()
        s["xmax"] = self.sp_xmax.value()
        s["xtick"] = self.sp_xtick.value()
        s["ymin"] = self.sp_ymin.value()
        s["ymax"] = self.sp_ymax.value()
        s["ytick"] = self.sp_ytick.value()
        try:
            s["efermi"] = float(self.ed_fermi.text())
        except ValueError:
            pass
        try:
            s["vvac"] = float(self.ed_vac.text())
        except ValueError:
            pass
        s["show_fermi"] = self.sw_fermi.isChecked()
        s["show_vac"] = self.sw_vac.isChecked()
        s["show_phi"] = self.sw_phi.isChecked()
        s["line_width"] = self.sp_lw.value()
        s["ann_fs"] = self.sp_fs.value()
        s["title"] = "Planar Average Potential along z"

    def _plot_curve(self):
        if not self.data:
            self.wf_view.ax.clear()
            self.wf_view.ax.text(0.5, 0.5, "请选择功函数作业文件夹以加载数据",
                                 ha="center", va="center", fontsize=13,
                                 color="#8A8A8E",
                                 transform=self.wf_view.ax.transAxes)
            self.wf_view.set_theme(self._dark)
            self.wf_view.draw()
            return
        s = self._plot_style()
        wf = s["vvac"] - s["efermi"]
        self.wf_view.set_theme(self._dark)
        self.wf_view.plot(
            self.data,
            efermi=s["efermi"], vvac=s["vvac"], work_function=wf,
            xlim=(s["xmin"], s["xmax"]), ylim=(s["ymin"], s["ymax"]),
            xtick=s["xtick"], ytick=s["ytick"],
            line_color=s["line_color"], line_width=s["line_width"],
            show_fermi=s["show_fermi"], show_vac=s["show_vac"],
            show_phi=s["show_phi"], ann_fs=s["ann_fs"], title=s["title"])
        self._img_ready = True
        self.chip_phi.setText(f"\u03a6 = {wf:.3f} eV")

    def _redraw(self):
        if not self.data:
            return
        self._read_style_from_controls()
        self._plot_curve()
        self.status.setText("已按当前参数重新绘制")

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def _save_figure(self):
        if not self.data or not self._img_ready:
            QMessageBox.information(self, "无可保存的图片",
                                    "当前还没有绘制曲线，请先加载数据。")
            return
        default = str((self.job_dir or APP_DIR) /
                      "work_function_planar_average.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存当前图片", default,
            "PNG 图片 (*.png);;PDF 文档 (*.pdf);;SVG 矢量图 (*.svg);;"
            "JPEG 图片 (*.jpg *.jpeg);;所有文件 (*)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        fig = self.wf_view.figure
        try:
            fig.savefig(path, dpi=300, facecolor=fig.get_facecolor())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.status.setText(f"已保存图片：{Path(path).name}")

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------
    def _toggle_theme(self):
        self._dark = not self._dark
        apply_theme(QApplication.instance(), DARK if self._dark else LIGHT)
        self.theme_btn.setText("\u2600\ufe0f" if self._dark else "\U0001F319")
        for sw in self._switches:
            try:
                sw.apply_theme(THEME)
            except RuntimeError:
                pass
        self.wf_view.set_theme(self._dark)
        self._plot_curve()
        self.update()


def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "wf.workfunction.studio.1")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("WF Viewer")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    apply_theme(app, LIGHT)
    win = MainWindow()
    app.setWindowIcon(win.app_icon)
    win.show()
    # 可选：命令行传入作业文件夹即可启动后自动加载
    #   python wf_viewer.py <作业文件夹>
    #   WF-Viewer.exe <作业文件夹>
    import os as _os
    for _arg in sys.argv[1:]:
        if not _arg.startswith("-") and Path(_arg).exists():
            win._load_from(_os.path.normpath(_arg))
            break
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
