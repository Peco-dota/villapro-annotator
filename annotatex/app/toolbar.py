"""Top toolbar for AnnotateX."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QToolBar, QWidget, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QButtonGroup, QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QFont, QAction

ICON_SIZE = 20
BTN_SIZE = 34


def _make_icon_btn(text: str, tooltip: str, checkable: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setToolTip(tooltip)
    btn.setCheckable(checkable)
    btn.setFixedSize(BTN_SIZE, BTN_SIZE)
    btn.setStyleSheet("""
        QPushButton {
            background-color: transparent;
            color: #94a3b8;
            border: 1px solid transparent;
            border-radius: 6px;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #1e293b;
            color: #e2e8f0;
            border: 1px solid #334155;
        }
        QPushButton:checked {
            background-color: #1e1b4b;
            color: #a78bfa;
            border: 1px solid #7c3aed;
        }
        QPushButton:pressed {
            background-color: #312e81;
        }
    """)
    return btn


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet("color: #1e293b;")
    f.setFixedWidth(1)
    return f


class AnnotateXToolbar(QWidget):
    """Custom toolbar widget (not QToolBar) for full style control."""

    # Signals
    go_home = pyqtSignal()
    tool_select = pyqtSignal()
    tool_draw = pyqtSignal()
    zoom_in = pyqtSignal()
    zoom_out = pyqtSignal()
    zoom_fit = pyqtSignal()
    zoom_100 = pyqtSignal()
    undo = pyqtSignal()
    redo = pyqtSignal()
    save = pyqtSignal()
    export = pyqtSignal()
    augment = pyqtSignal()
    train = pyqtSignal()
    detect = pyqtSignal()
    prev_image = pyqtSignal()
    next_image = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("background-color: #0f172a; border-bottom: 1px solid #1e293b;")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        # Back to welcome
        back_btn = _make_icon_btn("←", "Back to Welcome Screen")
        back_btn.clicked.connect(self.go_home)
        layout.addWidget(back_btn)
        layout.addWidget(_sep())

        # Logo / app name
        logo = QLabel("◈ VisionQ")
        logo.setStyleSheet(
            "color: #a78bfa; font-size: 16px; font-weight: bold; "
            "letter-spacing: 1px; padding-right: 12px;"
        )
        layout.addWidget(logo)
        layout.addWidget(_sep())

        # ── Tool group ────────────────────────────────────────────────────────
        self._select_btn = _make_icon_btn("⬚", "Select / Move (V)", checkable=True)
        self._draw_btn = _make_icon_btn("⬜", "Draw Rectangle (R)", checkable=True)
        self._draw_btn.setChecked(True)  # default

        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_group.addButton(self._select_btn)
        self._tool_group.addButton(self._draw_btn)

        self._select_btn.clicked.connect(self.tool_select)
        self._draw_btn.clicked.connect(self.tool_draw)

        layout.addWidget(QLabel("<small style='color:#334155'>TOOLS</small>"))
        layout.addWidget(self._select_btn)
        layout.addWidget(self._draw_btn)
        layout.addWidget(_sep())

        # ── Zoom group ────────────────────────────────────────────────────────
        zoom_in_btn = _make_icon_btn("＋", "Zoom In (+)")
        zoom_out_btn = _make_icon_btn("－", "Zoom Out (-)")
        zoom_fit_btn = _make_icon_btn("⊡", "Fit to Window (F)")
        zoom_100_btn = _make_icon_btn("1:1", "Zoom to 100%")
        zoom_100_btn.setFixedWidth(40)

        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_fit_btn.clicked.connect(self.zoom_fit)
        zoom_100_btn.clicked.connect(self.zoom_100)

        layout.addWidget(QLabel("<small style='color:#334155'>ZOOM</small>"))
        layout.addWidget(zoom_out_btn)
        layout.addWidget(zoom_in_btn)
        layout.addWidget(zoom_fit_btn)
        layout.addWidget(zoom_100_btn)
        layout.addWidget(_sep())

        # ── Edit group ────────────────────────────────────────────────────────
        undo_btn = _make_icon_btn("↩", "Undo (Ctrl+Z)")
        redo_btn = _make_icon_btn("↪", "Redo (Ctrl+Y)")
        undo_btn.clicked.connect(self.undo)
        redo_btn.clicked.connect(self.redo)
        layout.addWidget(QLabel("<small style='color:#334155'>EDIT</small>"))
        layout.addWidget(undo_btn)
        layout.addWidget(redo_btn)
        layout.addWidget(_sep())

        # ── Navigation ────────────────────────────────────────────────────────
        prev_btn = _make_icon_btn("◄", "Previous Image (A / ←)")
        next_btn = _make_icon_btn("►", "Next Image (D / →)")
        prev_btn.clicked.connect(self.prev_image)
        next_btn.clicked.connect(self.next_image)
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)

        # Spacer
        layout.addStretch()

        # ── Save + Export ─────────────────────────────────────────────────────
        save_btn = _make_icon_btn("💾", "Save Project (Ctrl+S)")
        save_btn.setFixedWidth(42)
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)

        export_btn = QPushButton("⬆  Export")
        export_btn.setFixedHeight(BTN_SIZE)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #6d28d9; }
            QPushButton:pressed { background-color: #5b21b6; }
        """)
        export_btn.setToolTip("Export Dataset")
        export_btn.clicked.connect(self.export)
        layout.addWidget(export_btn)

        augment_btn = QPushButton("✦  Augment")
        augment_btn.setFixedHeight(BTN_SIZE)
        augment_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f766e;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #0d9488; }
            QPushButton:pressed { background-color: #0f5a55; }
        """)
        augment_btn.setToolTip("Augment Dataset")
        augment_btn.clicked.connect(self.augment)
        layout.addWidget(augment_btn)

        train_btn = QPushButton("▶  Train")
        train_btn.setFixedHeight(BTN_SIZE)
        train_btn.setStyleSheet("""
            QPushButton {
                background-color: #b45309;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #d97706; }
            QPushButton:pressed { background-color: #92400e; }
        """)
        train_btn.setToolTip("Train YOLO Model")
        train_btn.clicked.connect(self.train)
        layout.addWidget(train_btn)

        self._detect_btn = QPushButton("⚡  Service Manager")
        self._detect_btn.setFixedHeight(BTN_SIZE)
        self._detect_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e7490;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #0891b2; }
            QPushButton:pressed { background-color: #0c4a6e; }
        """)
        self._detect_btn.setToolTip("Service Manager")
        self._detect_btn.clicked.connect(self.detect)
        layout.addWidget(self._detect_btn)

    def set_detection_running(self, running: bool):
        """Update detect button appearance based on service state."""
        if running:
            self._detect_btn.setStyleSheet("""
                QPushButton {
                    background-color: #166534;
                    color: #4ade80;
                    border: 1px solid #4ade80;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 14px;
                }
                QPushButton:hover { background-color: #15803d; }
            """)
            self._detect_btn.setText("⚡  Service Manager ●")
        else:
            self._detect_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0e7490;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 14px;
                }
                QPushButton:hover { background-color: #0891b2; }
                QPushButton:pressed { background-color: #0c4a6e; }
            """)
            self._detect_btn.setText("⚡  Service Manager")

    def set_tool(self, tool: str):
        if tool == "select":
            self._select_btn.setChecked(True)
        else:
            self._draw_btn.setChecked(True)
