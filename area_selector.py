import sys
from enum import Enum
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor, QGuiApplication
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QLabel, QApplication

class DragMode(Enum):
    NONE = 0
    CREATING = 1
    MOVING = 2
    RESIZE_TL = 3
    RESIZE_TR = 4
    RESIZE_BL = 5
    RESIZE_BR = 6
    RESIZE_T = 7
    RESIZE_B = 8
    RESIZE_L = 9
    RESIZE_R = 10

class FloatingToolBar(QWidget):
    confirm_clicked = pyqtSignal()
    start_rec_clicked = pyqtSignal()
    cancel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(24, 24, 24, 240);
                border: 1px solid #444;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #2979FF;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2962FF;
            }
            QPushButton#btn_rec {
                background-color: #D32F2F;
            }
            QPushButton#btn_rec:hover {
                background-color: #B71C1C;
            }
            QPushButton#btn_cancel {
                background-color: #424242;
            }
            QPushButton#btn_cancel:hover {
                background-color: #616161;
            }
            QLabel {
                color: #00E676;
                font-weight: bold;
                font-family: Consolas, sans-serif;
                font-size: 12px;
                border: none;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.lbl_info = QLabel("1280 x 720")
        
        self.btn_confirm = QPushButton("✔ 確認範圍")
        self.btn_start_rec = QPushButton("🔴 直接錄影")
        self.btn_start_rec.setObjectName("btn_rec")
        self.btn_cancel = QPushButton("✖ 取消")
        self.btn_cancel.setObjectName("btn_cancel")

        layout.addWidget(self.lbl_info)
        layout.addWidget(self.btn_confirm)
        layout.addWidget(self.btn_start_rec)
        layout.addWidget(self.btn_cancel)

        self.btn_confirm.clicked.connect(self.confirm_clicked.emit)
        self.btn_start_rec.clicked.connect(self.start_rec_clicked.emit)
        self.btn_cancel.clicked.connect(self.cancel_clicked.emit)

    def update_info(self, w: int, h: int, x: int, y: int):
        self.lbl_info.setText(f" {w}x{h} (X:{x}, Y:{y}) ")

class AreaSelectorOverlay(QWidget):
    area_selected = pyqtSignal(int, int, int, int)           # x, y, w, h
    start_rec_requested = pyqtSignal(int, int, int, int)    # x, y, w, h

    HANDLE_SIZE = 10

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        self.start_point = QPoint()
        self.drag_mode = DragMode.NONE
        self.selection_rect = QRect()
        self.drag_start_rect = QRect()
        self.drag_start_mouse = QPoint()

        # Floating Toolbar Widget
        self.toolbar = FloatingToolBar(self)
        self.toolbar.hide()
        self.toolbar.confirm_clicked.connect(self.on_confirm)
        self.toolbar.start_rec_clicked.connect(self.on_start_rec)
        self.toolbar.cancel_clicked.connect(self.close)

        self.update_virtual_geometry()

    def update_virtual_geometry(self):
        screen_geo = QRect()
        for screen in QGuiApplication.screens():
            screen_geo = screen_geo.united(screen.geometry())
        self.setGeometry(screen_geo)

    def get_handles(self) -> dict:
        if self.selection_rect.isNull() or not self.selection_rect.isValid():
            return {}

        r = self.selection_rect
        hs = self.HANDLE_SIZE
        half_hs = hs // 2

        return {
            DragMode.RESIZE_TL: QRect(r.left() - half_hs, r.top() - half_hs, hs, hs),
            DragMode.RESIZE_TR: QRect(r.right() - half_hs, r.top() - half_hs, hs, hs),
            DragMode.RESIZE_BL: QRect(r.left() - half_hs, r.bottom() - half_hs, hs, hs),
            DragMode.RESIZE_BR: QRect(r.right() - half_hs, r.bottom() - half_hs, hs, hs),
            DragMode.RESIZE_T:  QRect(r.center().x() - half_hs, r.top() - half_hs, hs, hs),
            DragMode.RESIZE_B:  QRect(r.center().x() - half_hs, r.bottom() - half_hs, hs, hs),
            DragMode.RESIZE_L:  QRect(r.left() - half_hs, r.center().y() - half_hs, hs, hs),
            DragMode.RESIZE_R:  QRect(r.right() - half_hs, r.center().y() - half_hs, hs, hs),
        }

    def hit_test(self, pos: QPoint) -> DragMode:
        handles = self.get_handles()
        for mode, rect in handles.items():
            if rect.contains(pos):
                return mode

        if self.selection_rect.contains(pos):
            return DragMode.MOVING

        return DragMode.NONE

    def update_cursor_for_mode(self, mode: DragMode):
        cursor_map = {
            DragMode.RESIZE_TL: Qt.CursorShape.SizeFDiagCursor,
            DragMode.RESIZE_BR: Qt.CursorShape.SizeFDiagCursor,
            DragMode.RESIZE_TR: Qt.CursorShape.SizeBDiagCursor,
            DragMode.RESIZE_BL: Qt.CursorShape.SizeBDiagCursor,
            DragMode.RESIZE_T:  Qt.CursorShape.SizeVerCursor,
            DragMode.RESIZE_B:  Qt.CursorShape.SizeVerCursor,
            DragMode.RESIZE_L:  Qt.CursorShape.SizeHorCursor,
            DragMode.RESIZE_R:  Qt.CursorShape.SizeHorCursor,
            DragMode.MOVING:    Qt.CursorShape.SizeAllCursor,
            DragMode.NONE:      Qt.CursorShape.CrossCursor,
        }
        self.setCursor(QCursor(cursor_map.get(mode, Qt.CursorShape.CrossCursor)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            
            if self.selection_rect.isValid() and not self.selection_rect.isNull():
                hit_mode = self.hit_test(pos)
                if hit_mode != DragMode.NONE:
                    self.drag_mode = hit_mode
                    self.drag_start_mouse = pos
                    self.drag_start_rect = QRect(self.selection_rect)
                    return

            # Start creating new selection rectangle
            self.start_point = pos
            self.drag_mode = DragMode.CREATING
            self.selection_rect = QRect(pos, QSize(0, 0))
            self.toolbar.hide()
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self.drag_mode == DragMode.CREATING:
            x1 = min(self.start_point.x(), pos.x())
            y1 = min(self.start_point.y(), pos.y())
            x2 = max(self.start_point.x(), pos.x())
            y2 = max(self.start_point.y(), pos.y())
            w = max(100, x2 - x1)
            h = max(100, y2 - y1)
            # Enforce even dimensions
            w = w if w % 2 == 0 else w - 1
            h = h if h % 2 == 0 else h - 1
            self.selection_rect = QRect(x1, y1, w, h)
            self.update()

        elif self.drag_mode == DragMode.MOVING:
            dx = pos.x() - self.drag_start_mouse.x()
            dy = pos.y() - self.drag_start_mouse.y()
            new_rect = QRect(self.drag_start_rect)
            new_rect.translate(dx, dy)
            self.selection_rect = new_rect
            self.update_toolbar_position()
            self.update()

        elif self.drag_mode in (
            DragMode.RESIZE_TL, DragMode.RESIZE_TR, DragMode.RESIZE_BL, DragMode.RESIZE_BR,
            DragMode.RESIZE_T, DragMode.RESIZE_B, DragMode.RESIZE_L, DragMode.RESIZE_R
        ):
            r = QRect(self.drag_start_rect)
            dx = pos.x() - self.drag_start_mouse.x()
            dy = pos.y() - self.drag_start_mouse.y()

            left, right, top, bottom = r.left(), r.right(), r.top(), r.bottom()

            if self.drag_mode in (DragMode.RESIZE_TL, DragMode.RESIZE_BL, DragMode.RESIZE_L):
                left = min(r.right() - 100, r.left() + dx)
            if self.drag_mode in (DragMode.RESIZE_TR, DragMode.RESIZE_BR, DragMode.RESIZE_R):
                right = max(r.left() + 100, r.right() + dx)
            if self.drag_mode in (DragMode.RESIZE_TL, DragMode.RESIZE_TR, DragMode.RESIZE_T):
                top = min(r.bottom() - 100, r.top() + dy)
            if self.drag_mode in (DragMode.RESIZE_BL, DragMode.RESIZE_BR, DragMode.RESIZE_B):
                bottom = max(r.top() + 100, r.bottom() + dy)

            w = right - left
            h = bottom - top
            w = w if w % 2 == 0 else w - 1
            h = h if h % 2 == 0 else h - 1

            self.selection_rect = QRect(left, top, w, h)
            self.update_toolbar_position()
            self.update()

        else:
            # Hover mode cursor updating
            if self.selection_rect.isValid():
                hit_mode = self.hit_test(pos)
                self.update_cursor_for_mode(hit_mode)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_mode != DragMode.NONE:
                self.drag_mode = DragMode.NONE
                if self.selection_rect.width() >= 100 and self.selection_rect.height() >= 100:
                    self.update_toolbar_position()
                    self.toolbar.show()
                self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.on_confirm()

    def update_toolbar_position(self):
        if self.selection_rect.isNull():
            return
        
        self.toolbar.adjustSize()
        tb_w = self.toolbar.width()
        tb_h = self.toolbar.height()

        r = self.selection_rect
        # Position toolbar centered at the bottom of selection rect
        tb_x = r.x() + (r.width() - tb_w) // 2
        tb_y = r.bottom() + 8

        # If near bottom boundary, place above rectangle
        if tb_y + tb_h > self.height() - 10:
            tb_y = r.top() - tb_h - 8

        self.toolbar.move(tb_x, tb_y)
        
        geo = self.geometry()
        gx = r.x() + geo.x()
        gy = r.y() + geo.y()
        self.toolbar.update_info(r.width(), r.height(), gx, gy)

    def get_global_coordinates(self):
        r = self.selection_rect
        geo = self.geometry()
        gx = r.x() + geo.x()
        gy = r.y() + geo.y()
        w = r.width()
        h = r.height()

        # Convert logical screen coordinates to physical pixels using Device Pixel Ratio (DPI Scale)
        screen = QGuiApplication.screenAt(QPoint(gx, gy)) or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        phys_x = int(round(gx * dpr))
        phys_y = int(round(gy * dpr))
        phys_w = int(round(w * dpr))
        phys_h = int(round(h * dpr))

        # Enforce even dimensions for FFmpeg encoder compatibility
        phys_w = phys_w if phys_w % 2 == 0 else phys_w - 1
        phys_h = phys_h if phys_h % 2 == 0 else phys_h - 1

        return phys_x, phys_y, phys_w, phys_h

    def on_confirm(self):
        if self.selection_rect.isValid():
            gx, gy, w, h = self.get_global_coordinates()
            self.area_selected.emit(gx, gy, w, h)
        self.close()

    def on_start_rec(self):
        if self.selection_rect.isValid():
            gx, gy, w, h = self.get_global_coordinates()
            self.start_rec_requested.emit(gx, gy, w, h)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw dark semi-transparent overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 130))

        if not self.selection_rect.isNull() and self.selection_rect.isValid():
            # Clear selection rectangle inner area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, Qt.GlobalColor.transparent)

            # Draw green bounding border
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            border_pen = QPen(QColor(0, 230, 118), 2, Qt.PenStyle.SolidLine)
            painter.setPen(border_pen)
            painter.drawRect(self.selection_rect)

            # Draw 8 handle control nodes (4 corners + 4 edges)
            handles = self.get_handles()
            handle_pen = QPen(QColor(255, 255, 255), 1.5)
            handle_brush = QBrush(QColor(0, 230, 118))
            
            painter.setPen(handle_pen)
            painter.setBrush(handle_brush)
            
            for handle_rect in handles.values():
                painter.drawRect(handle_rect)
