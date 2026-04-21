#!/usr/bin/env python3
"""AnnotateX - YOLO Dataset Annotation Tool.

Entry point: shows welcome screen, then opens main window.
"""
import sys
import os
import logging

log = logging.getLogger("visionq")

# Ensure 'app' imports resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFrame, QFileDialog, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

from app.utils import load_recent_projects, add_recent_project, remove_recent_project
from app.project import Project


WELCOME_STYLE = """
    QWidget#welcome {
        background-color: #0f0f1a;
    }
    QLabel {
        color: #e2e8f0;
    }
    QPushButton {
        background-color: #1e293b;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 8px;
        font-size: 13px;
        padding: 10px 20px;
        text-align: left;
    }
    QPushButton:hover {
        background-color: #263347;
        border-color: #7c3aed;
    }
    QPushButton:pressed {
        background-color: #1e1b4b;
    }
    QListWidget {
        background-color: #0f172a;
        color: #94a3b8;
        border: 1px solid #1e293b;
        border-radius: 6px;
        font-size: 11px;
        outline: none;
    }
    QListWidget::item {
        padding: 6px 10px;
        border-bottom: 1px solid #1e293b;
    }
    QListWidget::item:selected {
        background-color: #1e1b4b;
        color: #a78bfa;
    }
    QListWidget::item:hover {
        background-color: #1e293b;
    }
"""


def _primary_btn_style() -> str:
    return """
        QPushButton {
            background-color: #7c3aed;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            padding: 12px 24px;
            text-align: center;
        }
        QPushButton:hover { background-color: #6d28d9; }
        QPushButton:pressed { background-color: #5b21b6; }
    """


class WelcomeScreen(QWidget):
    """Splash / welcome screen shown on startup."""

    new_project_requested = pyqtSignal()
    open_project_requested = pyqtSignal()
    recent_project_requested = pyqtSignal(str)
    batch_export_requested = pyqtSignal()
    train_requested = pyqtSignal()
    detect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcome")
        self.setStyleSheet(WELCOME_STYLE)
        self.setMinimumSize(700, 500)
        self._build_ui()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._update_service_indicator)
        self._poll_timer.start(1000)

    def _build_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setStyleSheet("background-color: #1a1a2e;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(30, 40, 30, 40)
        left_layout.setSpacing(16)

        # Logo
        logo = QLabel("◈ VisionQ")
        logo.setStyleSheet(
            "color: #a78bfa; font-size: 28px; font-weight: bold; letter-spacing: 2px;"
        )
        left_layout.addWidget(logo)

        tagline = QLabel("Object Detection Tool")
        tagline.setStyleSheet("color: #475569; font-size: 12px; line-height: 1.5;")
        left_layout.addWidget(tagline)

        left_layout.addSpacing(20)

        # New project
        new_btn = QPushButton("  ✦  New Project")
        new_btn.setStyleSheet(_primary_btn_style())
        new_btn.clicked.connect(self.new_project_requested)
        left_layout.addWidget(new_btn)

        # Open project
        open_btn = QPushButton("  📂  Open Project…")
        open_btn.clicked.connect(self.open_project_requested)
        left_layout.addWidget(open_btn)

        left_layout.addSpacing(8)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #1e293b;")
        left_layout.addWidget(div)

        left_layout.addSpacing(4)

        # Merge datasets
        batch_btn = QPushButton("  📦  Merge Datasets…")
        batch_btn.clicked.connect(self.batch_export_requested)
        left_layout.addWidget(batch_btn)

        # Train
        train_btn = QPushButton("  🚀  Train YOLO Model…")
        train_btn.clicked.connect(self.train_requested)
        left_layout.addWidget(train_btn)

        # Detection service
        detect_btn = QPushButton("  ⚡  Service Manager…")
        detect_btn.clicked.connect(self.detect_requested)
        left_layout.addWidget(detect_btn)

        left_layout.addStretch()

        # Service indicator (clickable when running)
        self._service_indicator = QPushButton("● Service stopped")
        self._service_indicator.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #334155;
                font-size: 11px;
                text-align: left;
                padding: 0;
            }
            QPushButton:hover { color: #64748b; }
        """)
        self._service_indicator.setCursor(Qt.CursorShape.ArrowCursor)
        self._service_indicator.clicked.connect(self.detect_requested)
        left_layout.addWidget(self._service_indicator)

        # Version
        ver = QLabel("v1.0.0")
        ver.setStyleSheet("color: #1e293b; font-size: 10px;")
        left_layout.addWidget(ver)

        main.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("background-color: #0f0f1a;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(30, 40, 30, 40)
        right_layout.setSpacing(12)

        recent_hdr = QLabel("RECENT PROJECTS")
        recent_hdr.setStyleSheet(
            "color: #475569; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        right_layout.addWidget(recent_hdr)

        self._recent_list = QListWidget()
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_click)
        self._recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recent_list.customContextMenuRequested.connect(self._on_recent_context_menu)
        right_layout.addWidget(self._recent_list)

        open_recent_btn = QPushButton("Open Selected")
        open_recent_btn.setFixedHeight(34)
        open_recent_btn.clicked.connect(self._open_selected_recent)
        right_layout.addWidget(open_recent_btn)

        # Feature list
        right_layout.addSpacing(16)
        features_lbl = QLabel(
            "✓  YOLO & COCO export\n"
            "✓  Keyboard-driven workflow\n"
            "✓  Undo / Redo stack\n"
            "✓  Auto-save\n"
            "✓  Multi-class support\n"
            "✓  Zoomable canvas"
        )
        features_lbl.setStyleSheet("color: #334155; font-size: 11px; line-height: 1.8;")
        right_layout.addWidget(features_lbl)

        main.addWidget(right, stretch=1)

        self._load_recent()

    def _load_recent(self):
        self._recent_list.clear()
        recent = load_recent_projects()
        if not recent:
            item = QListWidgetItem("No recent projects")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._recent_list.addItem(item)
            return
        for path in recent:
            name = os.path.basename(path).replace(".annotatex", "")
            item = QListWidgetItem(f"{name}\n{path}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._recent_list.addItem(item)

    def _on_recent_double_click(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.recent_project_requested.emit(path)

    def _open_selected_recent(self):
        item = self._recent_list.currentItem()
        if item:
            self._on_recent_double_click(item)

    def _on_recent_context_menu(self, pos):
        item = self._recent_list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
            }
            QMenu::item:selected { background-color: #7c3aed; }
        """)
        open_act = menu.addAction("Open Project")
        menu.addSeparator()
        remove_act = menu.addAction("Remove from Recents")
        delete_act = menu.addAction("Delete Project File…")

        action = menu.exec(self._recent_list.mapToGlobal(pos))
        if action == open_act:
            self.recent_project_requested.emit(path)
        elif action == remove_act:
            remove_recent_project(path)
            self._load_recent()
        elif action == delete_act:
            self._delete_project_file(path)

    def _update_service_indicator(self):
        from app.detection_service import get_registry
        if get_registry().any_running():
            self._service_indicator.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #4ade80;
                    font-size: 11px;
                    text-align: left;
                    padding: 0;
                }
                QPushButton:hover { color: #86efac; text-decoration: underline; }
            """)
            self._service_indicator.setText("● Service running  (click to manage)")
            self._service_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._service_indicator.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #334155;
                    font-size: 11px;
                    text-align: left;
                    padding: 0;
                }
                QPushButton:hover { color: #64748b; }
            """)
            self._service_indicator.setText("● Service stopped")
            self._service_indicator.setCursor(Qt.CursorShape.ArrowCursor)

    def _delete_project_file(self, path: str):
        name = os.path.basename(path)
        reply = QMessageBox.warning(
            self,
            "Delete Project",
            f"Delete '{name}' from disk?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete file:\n{e}")
            return
        remove_recent_project(path)
        self._load_recent()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VisionQ")
    app.setOrganizationName("VisionQ")

    # Dark palette for native widgets
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#16213e"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1e293b"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e2e8f0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#7c3aed"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    # Font — pick first available system font
    from PyQt6.QtGui import QFontDatabase
    _available = QFontDatabase.families()
    _chosen = next(
        (f for f in ["SF Pro Text", "Helvetica Neue", "Segoe UI", "Ubuntu", "Arial"]
         if f in _available),
        "Arial"
    )
    font = QFont(_chosen, 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # Lazy import of MainWindow (only after Qt app is started)
    from app.main_window import MainWindow

    main_win: MainWindow = None  # type: ignore

    def show_welcome():
        # Ensure recent projects list is always fresh when returning home.
        welcome._load_recent()
        welcome.show()

    def open_main(project: Project):
        nonlocal main_win
        welcome.hide()
        main_win = MainWindow()
        main_win._load_project(project)
        main_win.home_requested.connect(show_welcome)
        main_win.showMaximized()

    def on_new_project():
        from app.dialogs import NewProjectDialog
        dlg = NewProjectDialog(welcome)
        if dlg.exec() != NewProjectDialog.DialogCode.Accepted:
            return
        project = Project()
        project.name = dlg.result_name
        project.image_folder = dlg.result_folder
        for name in dlg.result_classes:
            project.add_class(name)
        project.scan_images()
        if hasattr(dlg, 'result_import_labels') and dlg.result_import_labels:
            project.load_yolo_labels()
        # Save
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            welcome, "Save Project", dlg.result_name + ".annotatex",
            "AnnotateX Project (*.annotatex)"
        )
        if path:
            project.save(path)
            add_recent_project(path)
        open_main(project)

    def on_open_project():
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            welcome, "Open Project", "", "AnnotateX Project (*.annotatex)"
        )
        if path:
            on_recent_project(path)

    def on_recent_project(path: str):
        if not os.path.exists(path):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(welcome, "File Not Found",
                                f"Project file not found:\n{path}")
            return
        try:
            project = Project.load(path)
            add_recent_project(path)
            open_main(project)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(welcome, "Error", f"Failed to open project:\n{e}")

    def on_batch_export():
        from app.dialogs import BatchExportDialog
        dlg = BatchExportDialog(welcome)
        dlg.exec()

    def on_train():
        from app.train_dialog import TrainDialog
        dlg = TrainDialog(welcome)
        dlg.exec()

    def on_detect():
        from app.detection_dialog import DetectionDialog
        dlg = DetectionDialog(welcome)
        dlg.exec()

    # Graceful shutdown — stop all detection services and receivers before Qt tears down.
    # This is a last-resort safety net; MainWindow.closeEvent already does this for the
    # normal close path.  This covers the welcome-screen close and any edge cases.
    def _on_quit():
        try:
            welcome._poll_timer.stop()
        except Exception:
            pass
        try:
            from app.detection_service import get_registry
            get_registry().stop_all()
        except Exception:
            pass
        try:
            from app.result_receiver import get_receiver
            get_receiver().stop()
        except Exception:
            pass

    app.aboutToQuit.connect(_on_quit)

    welcome = WelcomeScreen()
    welcome.new_project_requested.connect(on_new_project)
    welcome.open_project_requested.connect(on_open_project)
    welcome.recent_project_requested.connect(on_recent_project)
    welcome.batch_export_requested.connect(on_batch_export)
    welcome.train_requested.connect(on_train)
    welcome.detect_requested.connect(on_detect)

    # Auto-start services marked for auto-start
    from app.detection_service import get_registry
    get_registry().auto_start_services(
        lambda name, err: log.warning(f"Auto-start failed for '{name}': {err}") if err else None
    )

    # If a project path was passed as CLI arg, open directly
    if len(sys.argv) > 1 and sys.argv[1].endswith(".annotatex"):
        on_recent_project(sys.argv[1])
    else:
        welcome.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
