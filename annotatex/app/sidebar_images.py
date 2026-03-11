"""Left sidebar: scrollable image thumbnail list with annotation badges."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QSizePolicy, QFrame,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QObject, QRunnable, QThreadPool
from PyQt6.QtGui import QPixmap, QColor, QPainter, QBrush, QPen, QFont

from app.utils import generate_thumbnail

if TYPE_CHECKING:
    from app.project import Project

THUMB_SIZE = 80
ITEM_H = 100


class ThumbnailWorker(QRunnable):
    """Worker to load a thumbnail in background."""

    class Signals(QObject):
        done = pyqtSignal(str, object)  # filename, QPixmap or None

    def __init__(self, path: str, filename: str):
        super().__init__()
        self.path = path
        self.filename = filename
        self.signals = ThumbnailWorker.Signals()

    def run(self):
        pm = generate_thumbnail(self.path, THUMB_SIZE)
        self.signals.done.emit(self.filename, pm)


class ImageThumbnailItem(QWidget):
    """Custom widget for each image row in the list."""

    def __init__(self, filename: str, index: int, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.index = index
        self._box_count = 0
        self._status = "unannotated"  # unannotated / annotated

        self.setFixedHeight(ITEM_H)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Status indicator bar (left)
        self._status_bar = QFrame()
        self._status_bar.setFixedWidth(4)
        self._status_bar.setMinimumHeight(THUMB_SIZE)
        self._status_bar.setStyleSheet("background-color: #475569; border-radius: 2px;")
        layout.addWidget(self._status_bar)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: #1e293b; border: 1px solid #334155; border-radius: 4px;"
        )
        placeholder = self._make_placeholder()
        self._thumb_label.setPixmap(placeholder)
        layout.addWidget(self._thumb_label)

        # Info
        info = QVBoxLayout()
        info.setSpacing(2)

        # Filename (truncated)
        name = self.filename if len(self.filename) <= 20 else "…" + self.filename[-17:]
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        self._name_label.setWordWrap(False)
        info.addWidget(self._name_label)

        # Index
        self._idx_label = QLabel(f"#{self.index + 1}")
        self._idx_label.setStyleSheet("color: #64748b; font-size: 10px;")
        info.addWidget(self._idx_label)

        # Box count badge
        self._badge_label = QLabel("0 boxes")
        self._badge_label.setStyleSheet(
            "color: #94a3b8; font-size: 10px; "
            "background-color: #1e293b; border-radius: 8px; padding: 1px 5px;"
        )
        info.addWidget(self._badge_label)
        info.addStretch()

        layout.addLayout(info)
        layout.addStretch()

    def _make_placeholder(self) -> QPixmap:
        pm = QPixmap(THUMB_SIZE, THUMB_SIZE)
        pm.fill(QColor("#1e293b"))
        return pm

    def set_thumbnail(self, pm: Optional[QPixmap]):
        if pm:
            self._thumb_label.setPixmap(pm)

    def update_status(self, box_count: int):
        self._box_count = box_count
        self._badge_label.setText(f"{box_count} box{'es' if box_count != 1 else ''}")
        if box_count > 0:
            self._status = "annotated"
            self._status_bar.setStyleSheet(
                "background-color: #22c55e; border-radius: 2px;"
            )
            self._badge_label.setStyleSheet(
                "color: #22c55e; font-size: 10px; "
                "background-color: #052e16; border-radius: 8px; padding: 1px 5px;"
            )
        else:
            self._status = "unannotated"
            self._status_bar.setStyleSheet(
                "background-color: #475569; border-radius: 2px;"
            )
            self._badge_label.setStyleSheet(
                "color: #94a3b8; font-size: 10px; "
                "background-color: #1e293b; border-radius: 8px; padding: 1px 5px;"
            )

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet(
                "background-color: #1e1b4b; border: 1px solid #7c3aed; border-radius: 6px;"
            )
        else:
            self.setStyleSheet(
                "background-color: transparent; border: 1px solid transparent; border-radius: 6px;"
            )


class ImageSidebar(QWidget):
    """Left panel: image list with thumbnails."""

    image_selected = pyqtSignal(int)  # index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional["Project"] = None
        self._items: list[ImageThumbnailItem] = []
        self._list_items: list[QListWidgetItem] = []
        self._active_index: int = -1
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(4)

        self.setFixedWidth(200)
        self.setStyleSheet("background-color: #16213e;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("  IMAGES")
        header.setFixedHeight(36)
        header.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: bold; "
            "background-color: #0f172a; letter-spacing: 1px;"
            "border-bottom: 1px solid #1e293b;"
        )
        layout.addWidget(header)

        # List
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                background-color: #16213e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 2px;
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
        """)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list)

    def load_project(self, project: "Project"):
        self._project = project
        self._list.clear()
        self._items.clear()
        self._list_items.clear()
        self._active_index = -1

        for i, fn in enumerate(project.images):
            widget = ImageThumbnailItem(fn, i)
            ia = project.annotations.get(fn)
            if ia:
                widget.update_status(ia.box_count)

            item = QListWidgetItem(self._list)
            item.setSizeHint(QSize(200, ITEM_H))
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)
            self._items.append(widget)
            self._list_items.append(item)

            # Async thumbnail
            path = project.image_path(fn)
            worker = ThumbnailWorker(path, fn)
            worker.signals.done.connect(self._on_thumbnail_ready)
            self._pool.start(worker)

    def set_current_index(self, index: int):
        if 0 <= index < len(self._items):
            # Deactivate only the previously active item
            if 0 <= self._active_index < len(self._items):
                self._items[self._active_index].set_active(False)
            self._active_index = index
            self._items[index].set_active(True)
            # Block signal to avoid recursive navigation
            self._list.blockSignals(True)
            self._list.setCurrentRow(index)
            self._list.blockSignals(False)
            self._list.scrollToItem(self._list_items[index])

    def refresh_item(self, filename: str):
        """Refresh annotation badge for one image."""
        if not self._project:
            return
        try:
            idx = self._project.images.index(filename)
        except ValueError:
            return
        if idx < len(self._items):
            ia = self._project.annotations.get(filename)
            self._items[idx].update_status(ia.box_count if ia else 0)

    def refresh_all_badges(self):
        if not self._project:
            return
        for i, fn in enumerate(self._project.images):
            if i < len(self._items):
                ia = self._project.annotations.get(fn)
                self._items[i].update_status(ia.box_count if ia else 0)

    def _on_thumbnail_ready(self, filename: str, pm):
        if not self._project:
            return
        try:
            idx = self._project.images.index(filename)
        except ValueError:
            return
        if idx < len(self._items):
            self._items[idx].set_thumbnail(pm)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.image_selected.emit(row)
