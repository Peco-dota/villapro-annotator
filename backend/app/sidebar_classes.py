"""Right sidebar: Classes panel + per-image Annotations panel."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QScrollArea,
    QFrame, QAbstractItemView, QSizePolicy, QColorDialog,
    QMessageBox, QMenu,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QIcon, QFont

from app.annotation import BoundingBox, ClassDef
from app.utils import generate_class_colors

if TYPE_CHECKING:
    from app.project import Project

PANEL_WIDTH = 220


def _color_swatch(color: str, size: int = 16) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return pm


class ClassRow(QWidget):
    """One row in the classes list."""

    color_changed = pyqtSignal(int, str)   # cls_id, new_color
    name_changed = pyqtSignal(int, str)    # cls_id, new_name
    delete_requested = pyqtSignal(int)     # cls_id

    def __init__(self, cls_def: ClassDef, count: int = 0, parent=None):
        super().__init__(parent)
        self.cls_def = cls_def
        self._build_ui(count)

    def _build_ui(self, count: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Color swatch button
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(20, 20)
        self._color_btn.setStyleSheet(
            f"background-color: {self.cls_def.color}; border-radius: 4px; border: 1px solid #475569;"
        )
        self._color_btn.setToolTip("Click to change color")
        self._color_btn.clicked.connect(self._pick_color)
        layout.addWidget(self._color_btn)

        # Name label (editable on double-click)
        self._name = QLabel(self.cls_def.name)
        self._name.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name)

        # Count badge
        self._count_label = QLabel(str(count))
        self._count_label.setStyleSheet(
            "color: #64748b; font-size: 10px; min-width: 18px; text-align: right;"
        )
        layout.addWidget(self._count_label)

        # Delete button
        del_btn = QPushButton("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(
            "color: #ef4444; background: transparent; border: none; font-size: 14px; font-weight: bold;"
        )
        del_btn.setToolTip("Delete class")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.cls_def.id))
        layout.addWidget(del_btn)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.cls_def.color), self, "Choose Class Color")
        if color.isValid():
            self.cls_def.color = color.name()
            self._color_btn.setStyleSheet(
                f"background-color: {self.cls_def.color}; border-radius: 4px; border: 1px solid #475569;"
            )
            self.color_changed.emit(self.cls_def.id, self.cls_def.color)

    def update_count(self, count: int):
        self._count_label.setText(str(count))

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("background-color: #1e1b4b; border-radius: 4px;")
        else:
            self.setStyleSheet("background-color: transparent;")


class AnnotationRow(QWidget):
    """One row in the annotation list for the current image."""

    selected = pyqtSignal(str)    # box_id
    deleted = pyqtSignal(str)     # box_id

    def __init__(self, box: BoundingBox, class_name: str, color: str, parent=None):
        super().__init__(parent)
        self.box = box
        self._build_ui(class_name, color)

    def _build_ui(self, class_name: str, color: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Color chip
        chip = QLabel()
        chip.setFixedSize(12, 12)
        chip.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
        layout.addWidget(chip)

        # Class name + coords
        x1, y1, x2, y2 = self.box.to_pixel(1, 1)  # normalized view
        label = f"{class_name}"
        self._label = QLabel(label)
        self._label.setStyleSheet("color: #e2e8f0; font-size: 10px;")
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._label)

        # YOLO coords mini label
        coords = f"cx:{self.box.cx:.2f} w:{self.box.w:.2f}"
        coord_lbl = QLabel(coords)
        coord_lbl.setStyleSheet("color: #475569; font-size: 9px;")
        layout.addWidget(coord_lbl)

        # Delete
        del_btn = QPushButton("×")
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet(
            "color: #ef4444; background: transparent; border: none; font-size: 12px; font-weight: bold;"
        )
        del_btn.clicked.connect(lambda: self.deleted.emit(self.box.id))
        layout.addWidget(del_btn)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.selected.emit(self.box.id)
        super().mousePressEvent(event)

    def set_highlighted(self, highlighted: bool):
        if highlighted:
            self.setStyleSheet("background-color: #1e1b4b; border-radius: 4px;")
        else:
            self.setStyleSheet("background-color: transparent;")


class ClassesSidebar(QWidget):
    """Right panel: classes + annotations."""

    class_selected = pyqtSignal(int)           # cls_id
    class_added = pyqtSignal(str)              # class name
    class_deleted = pyqtSignal(int)            # cls_id
    class_color_changed = pyqtSignal(int, str) # cls_id, color
    box_selected = pyqtSignal(str)             # box_id
    box_deleted = pyqtSignal(str)              # box_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional["Project"] = None
        self._active_class_id: int = 0
        self._class_rows: dict[int, tuple[QListWidgetItem, ClassRow]] = {}
        self._ann_rows: dict[str, tuple[QListWidgetItem, AnnotationRow]] = {}

        self.setFixedWidth(PANEL_WIDTH)
        self.setStyleSheet("background-color: #16213e;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Classes section ───────────────────────────────────────────────────
        cls_header = QLabel("  CLASSES")
        cls_header.setFixedHeight(36)
        cls_header.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: bold; "
            "background-color: #0f172a; letter-spacing: 1px;"
            "border-bottom: 1px solid #1e293b;"
        )
        layout.addWidget(cls_header)

        # Add class input
        add_row = QHBoxLayout()
        add_row.setContentsMargins(6, 6, 6, 4)
        add_row.setSpacing(4)
        self._class_input = QLineEdit()
        self._class_input.setPlaceholderText("New class name...")
        self._class_input.setStyleSheet(
            "background-color: #0f172a; color: #e2e8f0; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 6px; font-size: 11px;"
        )
        self._class_input.returnPressed.connect(self._add_class)
        add_row.addWidget(self._class_input)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setStyleSheet(
            "background-color: #7c3aed; color: white; border: none; "
            "border-radius: 4px; font-size: 16px; font-weight: bold;"
        )
        add_btn.setToolTip("Add class (Enter)")
        add_btn.clicked.connect(self._add_class)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        # Hint
        hint = QLabel("  Press 1-9 to select class")
        hint.setStyleSheet("color: #334155; font-size: 9px; padding-bottom: 2px;")
        layout.addWidget(hint)

        # Class list
        self._class_list = QListWidget()
        self._class_list.setFixedHeight(180)
        self._class_list.setStyleSheet(self._list_style())
        self._class_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._class_list.currentRowChanged.connect(self._on_class_row_changed)
        layout.addWidget(self._class_list)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #1e293b;")
        layout.addWidget(sep)

        # ── Annotations section ───────────────────────────────────────────────
        ann_header = QLabel("  ANNOTATIONS")
        ann_header.setFixedHeight(36)
        ann_header.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: bold; "
            "background-color: #0f172a; letter-spacing: 1px;"
            "border-bottom: 1px solid #1e293b;"
        )
        layout.addWidget(ann_header)

        self._ann_list = QListWidget()
        self._ann_list.setStyleSheet(self._list_style())
        self._ann_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._ann_list)

    def _list_style(self) -> str:
        return """
            QListWidget {
                background-color: #16213e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 1px;
            }
            QListWidget::item:selected {
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #0f172a;
                width: 6px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 3px;
            }
        """

    # ── Public API ────────────────────────────────────────────────────────────

    def load_project(self, project: "Project"):
        self._project = project
        self.refresh_classes()

    def refresh_classes(self):
        if not self._project:
            return
        self._class_list.clear()
        self._class_rows.clear()
        for cls in self._project.classes:
            count = self._project.class_annotation_count(cls.id)
            row_widget = ClassRow(cls, count)
            row_widget.color_changed.connect(self._on_color_changed)
            row_widget.delete_requested.connect(self._on_delete_class)
            item = QListWidgetItem(self._class_list)
            item.setSizeHint(QSize(PANEL_WIDTH, 30))
            self._class_list.addItem(item)
            self._class_list.setItemWidget(item, row_widget)
            self._class_rows[cls.id] = (item, row_widget)

        # Restore active class highlight
        self._highlight_active_class()

    def refresh_annotations(self):
        """Reload annotation list for current image."""
        self._ann_list.clear()
        self._ann_rows.clear()
        if not self._project:
            return
        ia = self._project.current_annotation()
        if not ia:
            return
        for box in ia.boxes:
            cls = self._project.get_class(box.class_id)
            name = cls.name if cls else str(box.class_id)
            color = cls.color if cls else "#7c3aed"
            row_widget = AnnotationRow(box, name, color)
            row_widget.selected.connect(self.box_selected)
            row_widget.deleted.connect(self.box_deleted)
            item = QListWidgetItem(self._ann_list)
            item.setSizeHint(QSize(PANEL_WIDTH, 30))
            self._ann_list.addItem(item)
            self._ann_list.setItemWidget(item, row_widget)
            self._ann_rows[box.id] = (item, row_widget)

    def set_active_class(self, cls_id: int):
        self._active_class_id = cls_id
        self._highlight_active_class()

    def highlight_box(self, box_id: Optional[str]):
        for bid, (item, row) in self._ann_rows.items():
            row.set_highlighted(bid == box_id)

    def update_class_counts(self):
        if not self._project:
            return
        for cls_id, (item, row) in self._class_rows.items():
            count = self._project.class_annotation_count(cls_id)
            row.update_count(count)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_class(self):
        name = self._class_input.text().strip()
        if not name:
            return
        self._class_input.clear()
        self.class_added.emit(name)

    def _on_class_row_changed(self, row: int):
        if not self._project or row < 0 or row >= len(self._project.classes):
            return
        cls = self._project.classes[row]
        self._active_class_id = cls.id
        self._highlight_active_class()
        self.class_selected.emit(cls.id)

    def _on_color_changed(self, cls_id: int, color: str):
        if self._project:
            self._project.modified = True
        self.class_color_changed.emit(cls_id, color)

    def _on_delete_class(self, cls_id: int):
        if not self._project:
            return
        count = self._project.class_annotation_count(cls_id)
        if count > 0:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Delete Class",
                f"This class has {count} annotation(s). Delete anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.class_deleted.emit(cls_id)

    def _highlight_active_class(self):
        for cls_id, (item, row) in self._class_rows.items():
            row.set_active(cls_id == self._active_class_id)
