"""
AnnotateX - Annotation Canvas
QGraphicsView-based zoomable, pannable annotation canvas.
"""
from __future__ import annotations
import copy
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsItem, QGraphicsTextItem,
    QRubberBand, QSizePolicy, QApplication,
)
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QSizeF, QSize, QRect, pyqtSignal, QObject,
    QRunnable, QThreadPool,
)
from PyQt6.QtGui import (
    QPixmap, QPen, QBrush, QColor, QFont, QPainter,
    QTransform, QCursor, QKeyEvent,
)

from app.annotation import BoundingBox
from app.utils import hex_to_rgba

if TYPE_CHECKING:
    from app.project import Project

HANDLE_SIZE = 8
MIN_BOX_PX = 4  # minimum box size in pixels


class _ImageLoaderWorker(QRunnable):
    """Loads a QPixmap in a background thread."""

    class Signals(QObject):
        done = pyqtSignal(str, object)  # path, QPixmap

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _ImageLoaderWorker.Signals()

    def run(self):
        pm = QPixmap(self.path)
        self.signals.done.emit(self.path, pm)


class Handle(QGraphicsRectItem):
    """A resize handle on a bounding box."""
    def __init__(self, pos_type: str, parent=None):
        super().__init__(-HANDLE_SIZE/2, -HANDLE_SIZE/2, HANDLE_SIZE, HANDLE_SIZE, parent)
        self.pos_type = pos_type  # 'tl','tc','tr','ml','mr','bl','bc','br'
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor("#ffffff"), 1))
        self.setBrush(QBrush(QColor("#7c3aed")))
        self.setZValue(10)
        self._set_cursor()

    def _set_cursor(self):
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "tc": Qt.CursorShape.SizeVerCursor,
            "bc": Qt.CursorShape.SizeVerCursor,
            "ml": Qt.CursorShape.SizeHorCursor,
            "mr": Qt.CursorShape.SizeHorCursor,
        }
        self.setCursor(cursors.get(self.pos_type, Qt.CursorShape.ArrowCursor))


class AnnotationItem(QGraphicsRectItem):
    """A visual bounding box on the canvas."""

    def __init__(self, box: BoundingBox, color: str, label: str,
                 img_w: int, img_h: int, opacity: float = 0.15):
        x1, y1, x2, y2 = box.to_pixel(img_w, img_h)
        super().__init__(QRectF(x1, y1, x2 - x1, y2 - y1))
        self.box = box
        self.img_w = img_w
        self.img_h = img_h
        self.color_hex = color
        self._opacity = opacity
        self._selected = False
        self._label = label

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

        self._setup_appearance()
        self._handles: list[Handle] = []
        self._label_item: Optional[QGraphicsTextItem] = None
        self._create_label()

    # ── Appearance ────────────────────────────────────────────────────────────

    def _setup_appearance(self):
        r, g, b, _ = hex_to_rgba(self.color_hex)
        alpha = int(self._opacity * 255)
        fill = QColor(r, g, b, alpha)
        if self._selected:
            pen = QPen(QColor(r, g, b), 2.5, Qt.PenStyle.SolidLine)
        else:
            pen = QPen(QColor(r, g, b), 1.5, Qt.PenStyle.SolidLine)
        self.setPen(pen)
        self.setBrush(QBrush(fill))

    def _create_label(self):
        if self._label_item:
            if self._label_item.scene():
                self._label_item.scene().removeItem(self._label_item)
        r = self.rect()
        self._label_item = QGraphicsTextItem(self._label)
        font = QFont("Arial", 8)
        font.setBold(True)
        self._label_item.setFont(font)
        r2, g2, b2, _ = hex_to_rgba(self.color_hex)
        self._label_item.setDefaultTextColor(QColor(255, 255, 255))
        self._label_item.setPos(r.x(), r.y() - 18)
        self._label_item.setZValue(3)
        # Background for label
        if self.scene():
            self.scene().addItem(self._label_item)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._setup_appearance()
        self._update_handles()

    def update_label(self, label: str):
        self._label = label
        if self._label_item:
            self._label_item.setPlainText(label)

    def update_rect_from_box(self):
        x1, y1, x2, y2 = self.box.to_pixel(self.img_w, self.img_h)
        self.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
        self._update_label_pos()
        self._update_handles()

    def _update_label_pos(self):
        if self._label_item:
            r = self.rect()
            self._label_item.setPos(r.x(), r.y() - 18)

    # ── Handles ───────────────────────────────────────────────────────────────

    def _create_handles(self):
        self._remove_handles()
        r = self.rect()
        positions = {
            "tl": QPointF(r.left(), r.top()),
            "tc": QPointF(r.center().x(), r.top()),
            "tr": QPointF(r.right(), r.top()),
            "ml": QPointF(r.left(), r.center().y()),
            "mr": QPointF(r.right(), r.center().y()),
            "bl": QPointF(r.left(), r.bottom()),
            "bc": QPointF(r.center().x(), r.bottom()),
            "br": QPointF(r.right(), r.bottom()),
        }
        for ptype, pos in positions.items():
            h = Handle(ptype)
            h.setPos(pos)
            if self.scene():
                self.scene().addItem(h)
            self._handles.append(h)

    def _remove_handles(self):
        for h in self._handles:
            if h.scene():
                h.scene().removeItem(h)
        self._handles.clear()

    def _update_handles(self):
        if self._selected:
            if not self._handles:
                self._create_handles()
            else:
                r = self.rect()
                positions = [
                    QPointF(r.left(), r.top()),
                    QPointF(r.center().x(), r.top()),
                    QPointF(r.right(), r.top()),
                    QPointF(r.left(), r.center().y()),
                    QPointF(r.right(), r.center().y()),
                    QPointF(r.left(), r.bottom()),
                    QPointF(r.center().x(), r.bottom()),
                    QPointF(r.right(), r.bottom()),
                ]
                for h, pos in zip(self._handles, positions):
                    h.setPos(pos)
        else:
            self._remove_handles()

    def handle_at(self, scene_pos: QPointF) -> Optional[Handle]:
        for h in self._handles:
            if h.contains(h.mapFromScene(scene_pos)):
                return h
        return None

    def remove_from_scene(self):
        self._remove_handles()
        if self._label_item and self._label_item.scene():
            self._label_item.scene().removeItem(self._label_item)
        if self.scene():
            self.scene().removeItem(self)

    # ── Events ────────────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        if not self._selected:
            r, g, b, _ = hex_to_rgba(self.color_hex)
            pen = QPen(QColor(r, g, b), 2.0)
            self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._setup_appearance()
        super().hoverLeaveEvent(event)


# ── Undo/Redo ─────────────────────────────────────────────────────────────────

class AnnotationState:
    """Snapshot of annotations for one image (for undo/redo)."""
    def __init__(self, boxes: list[BoundingBox]):
        self.boxes = [copy.deepcopy(b) for b in boxes]


class UndoStack:
    def __init__(self, max_size: int = 50):
        self._undo: list[AnnotationState] = []
        self._redo: list[AnnotationState] = []
        self._max = max_size

    def push(self, state: AnnotationState):
        self._undo.append(state)
        if len(self._undo) > self._max:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> Optional[AnnotationState]:
        if self._undo:
            s = self._undo.pop()
            self._redo.append(s)
            return s
        return None

    def redo(self) -> Optional[AnnotationState]:
        if self._redo:
            s = self._redo.pop()
            self._undo.append(s)
            return s
        return None

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def clear(self):
        self._undo.clear()
        self._redo.clear()


# ── Canvas ────────────────────────────────────────────────────────────────────

class AnnotationCanvas(QGraphicsView):
    """
    Central annotation canvas. Handles:
    - Image display
    - Bounding box drawing (click+drag)
    - Box selection, move, resize
    - Zoom / pan
    - Undo/Redo
    """

    # Signals
    box_created = pyqtSignal(object)          # BoundingBox (needs class assignment)
    box_selected = pyqtSignal(object)         # BoundingBox or None
    box_deleted = pyqtSignal(str)             # box id
    box_changed = pyqtSignal(object)          # BoundingBox (moved/resized)
    annotations_changed = pyqtSignal()        # any change to annotations
    zoom_changed = pyqtSignal(float)          # zoom factor
    right_click_box = pyqtSignal(object, object)  # BoundingBox, QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # State
        self._project: Optional["Project"] = None
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._annotation_items: dict[str, AnnotationItem] = {}  # box_id -> item
        self._selected_ids: list[str] = []
        self._current_class_id: int = 0
        self._tool: str = "draw"  # "select" or "draw"

        # Draw state
        self._drawing: bool = False
        self._draw_start: Optional[QPointF] = None
        self._draw_rect_item: Optional[QGraphicsRectItem] = None

        # Resize/Move state
        self._resize_handle: Optional[Handle] = None
        self._resize_item: Optional[AnnotationItem] = None
        self._resize_start_pos: Optional[QPointF] = None
        self._resize_start_rect: Optional[QRectF] = None
        self._move_item: Optional[AnnotationItem] = None
        self._move_start_pos: Optional[QPointF] = None
        self._move_start_rect: Optional[QRectF] = None

        # Pan state
        self._panning: bool = False
        self._pan_start: Optional[QPointF] = None

        # Undo/redo
        self._undo_stack = UndoStack()
        self._undo_baseline: Optional[AnnotationState] = None

        # Settings
        self._opacity: float = 0.15
        self._bg_color: str = "#2a2a2a"
        self._crosshair: bool = False
        self._img_w: int = 0
        self._img_h: int = 0
        self._pending_path: str = ""

        self._setup_view()

    def _setup_view(self):
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(self._bg_color)))
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_project(self, project: "Project"):
        self._project = project
        self._opacity = project.settings.get("annotation_opacity", 0.15)
        self._bg_color = project.settings.get("canvas_bg", "#2a2a2a")
        self._crosshair = project.settings.get("crosshair", False)
        self.setBackgroundBrush(QBrush(QColor(self._bg_color)))

    def load_image(self, path: str):
        """Load an image onto the canvas asynchronously."""
        self._pending_path = path
        # Clear immediately so the old image doesn't linger
        self._clear_annotations()
        self._scene.clear()
        self._annotation_items.clear()
        self._selected_ids.clear()
        self._undo_stack.clear()
        self._pixmap_item = None
        self._img_w = 0
        self._img_h = 0

        worker = _ImageLoaderWorker(path)
        worker.signals.done.connect(self._on_image_loaded)
        QThreadPool.globalInstance().start(worker)

    def _on_image_loaded(self, path: str, pm: QPixmap):
        """Called on main thread when the background loader finishes."""
        # Discard if user navigated away before this finished
        if path != self._pending_path:
            return
        if pm.isNull():
            return

        self._pixmap_item = QGraphicsPixmapItem(pm)
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._img_w = pm.width()
        self._img_h = pm.height()

        self._render_annotations()
        self.fit_to_window()

    def reload_annotations(self):
        """Re-render annotations from project data without reloading the image."""
        self._clear_annotations()
        self._render_annotations()

    def set_tool(self, tool: str):
        """'select' or 'draw'"""
        self._tool = tool
        if tool == "select":
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def set_current_class(self, cls_id: int):
        self._current_class_id = cls_id

    def set_opacity(self, opacity: float):
        self._opacity = opacity
        for item in self._annotation_items.values():
            item._opacity = opacity
            item._setup_appearance()

    def select_box(self, box_id: Optional[str], multi: bool = False):
        if not multi:
            for bid in list(self._selected_ids):
                item = self._annotation_items.get(bid)
                if item:
                    item.set_selected(False)
            self._selected_ids.clear()

        if box_id and box_id in self._annotation_items:
            item = self._annotation_items[box_id]
            if box_id not in self._selected_ids:
                self._selected_ids.append(box_id)
                item.set_selected(True)
            box = self._get_box_by_id(box_id)
            self.box_selected.emit(box)
        else:
            self.box_selected.emit(None)

    def delete_selected(self):
        if not self._selected_ids:
            return
        self._push_undo()
        ia = self._project.current_annotation() if self._project else None
        for bid in list(self._selected_ids):
            item = self._annotation_items.pop(bid, None)
            if item:
                item.remove_from_scene()
            if ia:
                ia.boxes = [b for b in ia.boxes if b.id != bid]
            self.box_deleted.emit(bid)
        self._selected_ids.clear()
        if self._project:
            self._project.modified = True
        self.annotations_changed.emit()

    def undo(self):
        if not self._undo_stack.can_undo():
            return
        # Save current as redo target
        ia = self._project.current_annotation() if self._project else None
        if ia:
            curr = AnnotationState(ia.boxes)
            state = self._undo_stack.undo()
            if state:
                self._undo_stack._redo.append(curr)
                ia.boxes = copy.deepcopy(state.boxes)
                self._selected_ids.clear()
                self.reload_annotations()
                if self._project:
                    self._project.modified = True
                self.annotations_changed.emit()

    def redo(self):
        if not self._undo_stack.can_redo():
            return
        ia = self._project.current_annotation() if self._project else None
        if ia:
            curr = AnnotationState(ia.boxes)
            state = self._undo_stack.redo()
            if state:
                self._undo_stack._undo.append(curr)
                ia.boxes = copy.deepcopy(state.boxes)
                self._selected_ids.clear()
                self.reload_annotations()
                if self._project:
                    self._project.modified = True
                self.annotations_changed.emit()

    def fit_to_window(self):
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_changed.emit(self.transform().m11())

    def zoom_in(self):
        self.scale(1.25, 1.25)
        self.zoom_changed.emit(self.transform().m11())

    def zoom_out(self):
        self.scale(0.8, 0.8)
        self.zoom_changed.emit(self.transform().m11())

    def zoom_100(self):
        self.setTransform(QTransform())
        self.zoom_changed.emit(1.0)

    def current_zoom(self) -> float:
        return self.transform().m11()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_annotations(self):
        if not self._project or not self._img_w:
            return
        ia = self._project.current_annotation()
        if not ia:
            return
        for box in ia.boxes:
            self._add_annotation_item(box)

    def _add_annotation_item(self, box: BoundingBox) -> AnnotationItem:
        color = "#7c3aed"
        label = str(box.class_id)
        if self._project:
            cls = self._project.get_class(box.class_id)
            if cls:
                color = cls.color
                label = cls.name
                if box.confidence is not None:
                    label += f" {box.confidence:.2f}"

        item = AnnotationItem(box, color, label, self._img_w, self._img_h, self._opacity)
        self._scene.addItem(item)
        item._create_label()  # adds label to scene internally once item has a scene
        self._annotation_items[box.id] = item
        return item

    def _clear_annotations(self):
        for item in self._annotation_items.values():
            item.remove_from_scene()
        self._annotation_items.clear()
        self._selected_ids.clear()

    def _get_box_by_id(self, box_id: str) -> Optional[BoundingBox]:
        if not self._project:
            return None
        ia = self._project.current_annotation()
        if not ia:
            return None
        for b in ia.boxes:
            if b.id == box_id:
                return b
        return None

    def update_annotation_item(self, box_id: str):
        """Refresh a specific annotation item (e.g. after class change)."""
        item = self._annotation_items.get(box_id)
        box = self._get_box_by_id(box_id)
        if item and box and self._project:
            cls = self._project.get_class(box.class_id)
            if cls:
                item.color_hex = cls.color
                item._label = cls.name
                item._setup_appearance()
                item.update_label(cls.name)

    # ── Undo helpers ──────────────────────────────────────────────────────────

    def _push_undo(self):
        ia = self._project.current_annotation() if self._project else None
        if ia:
            self._undo_stack.push(AnnotationState(ia.boxes))

    # ── Mouse events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        # Middle mouse = pan
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # Space+LMB = pan (handled via key tracking)
        if hasattr(self, '_space_pressed') and self._space_pressed:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            # Right-click: context on box
            item = self._item_at(scene_pos)
            if item:
                box = self._get_box_by_id(item.box.id)
                if box:
                    self.right_click_box.emit(box, event.globalPosition().toPoint())
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._tool == "draw":
                self._start_drawing(scene_pos)
            elif self._tool == "select":
                self._start_select_or_move(scene_pos, event.modifiers())

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        if self._drawing and self._draw_start is not None:
            self._update_drawing(scene_pos)
        elif self._resize_handle and self._resize_item:
            self._update_resize(scene_pos)
        elif self._move_item and self._move_start_pos:
            self._update_move(scene_pos)

        # Cursor update in select mode
        if self._tool == "select" and not self._resize_handle and not self._move_item:
            self._update_cursor_for_pos(scene_pos)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or self._panning:
            self._panning = False
            self._pan_start = None
            if self._tool == "draw":
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._drawing:
                self._finish_drawing()
            elif self._resize_handle:
                self._finish_resize()
            elif self._move_item:
                self._finish_move()

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.scale(factor, factor)
            self.zoom_changed.emit(self.transform().m11())
            event.accept()
        else:
            super().wheelEvent(event)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _start_drawing(self, scene_pos: QPointF):
        if not self._img_w:
            return
        self._drawing = True
        self._draw_start = scene_pos
        pen = QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine)
        self._draw_rect_item = QGraphicsRectItem(QRectF(scene_pos, QSizeF(0, 0)))
        self._draw_rect_item.setPen(pen)
        self._draw_rect_item.setBrush(QBrush(QColor(255, 255, 255, 20)))
        self._draw_rect_item.setZValue(5)
        self._scene.addItem(self._draw_rect_item)

    def _update_drawing(self, scene_pos: QPointF):
        if self._draw_rect_item and self._draw_start:
            r = QRectF(self._draw_start, scene_pos).normalized()
            self._draw_rect_item.setRect(r)

    def _finish_drawing(self):
        self._drawing = False
        if self._draw_rect_item:
            r = self._draw_rect_item.rect()
            self._scene.removeItem(self._draw_rect_item)
            self._draw_rect_item = None

            # Check minimum size
            if r.width() < MIN_BOX_PX or r.height() < MIN_BOX_PX:
                return

            # Clamp to image
            r = r.intersected(QRectF(0, 0, self._img_w, self._img_h))
            if r.width() < MIN_BOX_PX or r.height() < MIN_BOX_PX:
                return

            box = BoundingBox.from_pixel(
                r.left(), r.top(), r.right(), r.bottom(),
                self._img_w, self._img_h,
                self._current_class_id
            )
            if box.is_valid():
                self.box_created.emit(box)

    # ── Select / Move / Resize ────────────────────────────────────────────────

    def _start_select_or_move(self, scene_pos: QPointF, modifiers):
        multi = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        # Check handles first (for already-selected items)
        for bid in self._selected_ids:
            item = self._annotation_items.get(bid)
            if item:
                h = item.handle_at(scene_pos)
                if h:
                    self._resize_handle = h
                    self._resize_item = item
                    self._resize_start_pos = scene_pos
                    self._resize_start_rect = QRectF(item.rect())
                    self._push_undo()
                    return

        # Check for box click
        item = self._item_at(scene_pos)
        if item:
            if item.box.id not in self._selected_ids:
                self.select_box(item.box.id, multi)
            # Start move
            self._move_item = item
            self._move_start_pos = scene_pos
            self._move_start_rect = QRectF(item.rect())
            self._push_undo()
        else:
            if not multi:
                self.select_box(None)

    def _update_move(self, scene_pos: QPointF):
        if not self._move_item or not self._move_start_pos or not self._move_start_rect:
            return
        delta = scene_pos - self._move_start_pos
        new_rect = self._move_start_rect.translated(delta)
        # Clamp to image
        new_rect = self._clamp_rect(new_rect)
        self._move_item.setRect(new_rect)
        self._move_item._update_label_pos()
        self._move_item._update_handles()
        # Update box data
        self._update_box_from_rect(self._move_item)

    def _finish_move(self):
        if self._move_item:
            self._update_box_from_rect(self._move_item)
            box = self._get_box_by_id(self._move_item.box.id)
            if box and self._project:
                self._project.modified = True
                self.box_changed.emit(box)
                self.annotations_changed.emit()
        self._move_item = None
        self._move_start_pos = None
        self._move_start_rect = None

    def _update_resize(self, scene_pos: QPointF):
        if not self._resize_handle or not self._resize_item or not self._resize_start_rect:
            return
        r = QRectF(self._resize_start_rect)
        pt = self._resize_handle.pos_type

        dx = scene_pos.x() - (self._resize_start_pos.x() if self._resize_start_pos else scene_pos.x())
        dy = scene_pos.y() - (self._resize_start_pos.y() if self._resize_start_pos else scene_pos.y())

        if "l" in pt:
            r.setLeft(min(r.left() + dx, r.right() - MIN_BOX_PX))
        if "r" in pt:
            r.setRight(max(r.right() + dx, r.left() + MIN_BOX_PX))
        if "t" in pt:
            r.setTop(min(r.top() + dy, r.bottom() - MIN_BOX_PX))
        if "b" in pt:
            r.setBottom(max(r.bottom() + dy, r.top() + MIN_BOX_PX))
        if pt == "tc":
            r.setTop(min(r.top() + dy, r.bottom() - MIN_BOX_PX))
        if pt == "bc":
            r.setBottom(max(r.bottom() + dy, r.top() + MIN_BOX_PX))
        if pt == "ml":
            r.setLeft(min(r.left() + dx, r.right() - MIN_BOX_PX))
        if pt == "mr":
            r.setRight(max(r.right() + dx, r.left() + MIN_BOX_PX))

        r = self._clamp_rect(r)
        self._resize_item.setRect(r)
        self._resize_item._update_label_pos()
        self._resize_item._update_handles()
        self._update_box_from_rect(self._resize_item)

    def _finish_resize(self):
        if self._resize_item:
            self._update_box_from_rect(self._resize_item)
            box = self._get_box_by_id(self._resize_item.box.id)
            if box and self._project:
                self._project.modified = True
                self.box_changed.emit(box)
                self.annotations_changed.emit()
        self._resize_handle = None
        self._resize_item = None
        self._resize_start_pos = None
        self._resize_start_rect = None

    def _update_box_from_rect(self, item: AnnotationItem):
        r = item.rect()
        item.box.cx = (r.center().x()) / self._img_w
        item.box.cy = (r.center().y()) / self._img_h
        item.box.w = r.width() / self._img_w
        item.box.h = r.height() / self._img_h

    def _clamp_rect(self, r: QRectF) -> QRectF:
        x = max(0.0, r.x())
        y = max(0.0, r.y())
        w = min(r.width(), self._img_w - x)
        h = min(r.height(), self._img_h - y)
        return QRectF(x, y, max(w, MIN_BOX_PX), max(h, MIN_BOX_PX))

    def _item_at(self, scene_pos: QPointF) -> Optional[AnnotationItem]:
        """Find topmost AnnotationItem at position."""
        items = self._scene.items(scene_pos)
        for item in items:
            if isinstance(item, AnnotationItem):
                return item
        return None

    def _update_cursor_for_pos(self, scene_pos: QPointF):
        # Check handles
        for bid in self._selected_ids:
            item = self._annotation_items.get(bid)
            if item:
                h = item.handle_at(scene_pos)
                if h:
                    self.setCursor(h.cursor())
                    return

        item = self._item_at(scene_pos)
        if item:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Key events ────────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        if key == Qt.Key.Key_Space:
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
            self.delete_selected()
        elif key == Qt.Key.Key_Escape:
            self.select_box(None)
        elif key == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif key == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.redo()
        elif key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            self.zoom_in()
        elif key == Qt.Key.Key_Minus:
            self.zoom_out()
        elif key == Qt.Key.Key_F:
            self.fit_to_window()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self._space_pressed = False
            if self._tool == "draw":
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    # ── Public helper: commit a new box ──────────────────────────────────────

    def commit_box(self, box: BoundingBox):
        """Called after class assignment dialog to add the box."""
        if not self._project:
            return
        self._push_undo()
        ia = self._project.current_annotation()
        if ia is None:
            return
        ia.boxes.append(box)
        self._add_annotation_item(box)
        self.select_box(box.id)
        self._project.modified = True
        self.annotations_changed.emit()
