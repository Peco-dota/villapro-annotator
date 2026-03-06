"""Dialogs for AnnotateX: export, settings, class assignment, new project."""
from __future__ import annotations
import os
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QTextEdit, QProgressDialog, QMessageBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QSlider, QFrame,
    QWidget, QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont

if TYPE_CHECKING:
    from app.project import Project

DIALOG_STYLE = """
    QDialog {
        background-color: #1a1a2e;
        color: #e2e8f0;
    }
    QLabel {
        color: #e2e8f0;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background-color: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 4px;
        padding: 4px 6px;
    }
    QCheckBox {
        color: #e2e8f0;
    }
    QGroupBox {
        color: #64748b;
        border: 1px solid #334155;
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        color: #64748b;
        font-size: 10px;
    }
    QPushButton {
        background-color: #334155;
        color: #e2e8f0;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-size: 12px;
    }
    QPushButton:hover { background-color: #475569; }
    QPushButton:pressed { background-color: #1e293b; }
    QScrollBar:vertical {
        background: #0f172a; width: 6px; border: none;
    }
    QScrollBar::handle:vertical { background: #334155; border-radius: 3px; }
"""

PRIMARY_BTN = """
    QPushButton {
        background-color: #7c3aed;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-size: 12px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #6d28d9; }
    QPushButton:pressed { background-color: #5b21b6; }
"""


# ── Class Assignment Dialog ───────────────────────────────────────────────────

class ClassAssignDialog(QDialog):
    """Popup to assign a class after drawing a box."""

    def __init__(self, classes, current_class_id: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign Class")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(280)
        self.selected_class_id = current_class_id
        self._build_ui(classes, current_class_id)

    def _build_ui(self, classes, current_class_id: int):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel("Select class for this annotation:")
        lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(lbl)

        self._combo = QComboBox()
        for cls in classes:
            self._combo.addItem(cls.name, cls.id)
        # Select current
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == current_class_id:
                self._combo.setCurrentIndex(i)
                break
        layout.addWidget(self._combo)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(PRIMARY_BTN)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

    def _accept(self):
        self.selected_class_id = self._combo.currentData()
        self.accept()


# ── New Project Wizard ────────────────────────────────────────────────────────

class NewProjectDialog(QDialog):
    """Wizard to create a new project."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(480)
        self.setMinimumHeight(400)

        self.result_folder: str = ""
        self.result_name: str = ""
        self.result_classes: list[str] = []
        self.result_save_path: str = ""

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Title
        title = QLabel("New Annotation Project")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        # Project name
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._name_edit = QLineEdit("My Dataset")
        form.addRow("Project Name:", self._name_edit)
        layout.addLayout(form)

        # Image folder
        folder_grp = QGroupBox("Image Folder")
        folder_layout = QHBoxLayout(folder_grp)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select folder containing images...")
        self._folder_edit.setReadOnly(True)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_grp)

        # Image count label
        self._img_count_lbl = QLabel("")
        self._img_count_lbl.setStyleSheet("color: #22c55e; font-size: 11px;")
        layout.addWidget(self._img_count_lbl)

        # Initial classes
        cls_grp = QGroupBox("Initial Classes (optional)")
        cls_layout = QVBoxLayout(cls_grp)
        cls_hint = QLabel("Enter one class per line:")
        cls_hint.setStyleSheet("color: #64748b; font-size: 10px;")
        cls_layout.addWidget(cls_hint)
        self._classes_edit = QTextEdit()
        self._classes_edit.setPlaceholderText("person\ncar\nbicycle\n...")
        self._classes_edit.setFixedHeight(100)
        self._classes_edit.setStyleSheet(
            "background-color: #0f172a; color: #e2e8f0; "
            "border: 1px solid #334155; border-radius: 4px; font-size: 11px;"
        )
        cls_layout.addWidget(self._classes_edit)
        layout.addWidget(cls_grp)

        # Import existing YOLO labels option
        self._import_labels_cb = QCheckBox("Import existing YOLO labels (if .txt files exist)")
        self._import_labels_cb.setChecked(True)
        layout.addWidget(self._import_labels_cb)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        create_btn = QPushButton("Create Project")
        create_btn.setStyleSheet(PRIMARY_BTN)
        create_btn.clicked.connect(self._create)
        btns.addWidget(create_btn)
        layout.addLayout(btns)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            self._folder_edit.setText(folder)
            # Count images
            from pathlib import Path
            from app.project import IMAGE_EXTENSIONS
            count = sum(1 for f in os.listdir(folder)
                        if Path(f).suffix.lower() in IMAGE_EXTENSIONS)
            self._img_count_lbl.setText(f"✓ Found {count} images")

    def _create(self):
        folder = self._folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Error", "Please select a valid image folder.")
            return
        self.result_folder = folder
        self.result_name = self._name_edit.text().strip() or "My Dataset"
        raw = self._classes_edit.toPlainText().strip()
        self.result_classes = [l.strip() for l in raw.splitlines() if l.strip()]
        self.result_import_labels = self._import_labels_cb.isChecked()
        self.accept()


# ── Export Dialog ─────────────────────────────────────────────────────────────

class ExportWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, project, output_dir: str, fmt: str,
                 split: Optional[dict], generate_yaml: bool):
        super().__init__()
        self.project = project
        self.output_dir = output_dir
        self.fmt = fmt
        self.split = split
        self.generate_yaml = generate_yaml

    def run(self):
        try:
            from app.utils import export_yolo, export_coco
            if self.fmt == "yolo":
                stats = export_yolo(self.project, self.output_dir,
                                    self.split, self.generate_yaml)
            else:
                stats = export_coco(self.project, self.output_dir)
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))


class ExportDialog(QDialog):
    """Export dataset dialog."""

    def __init__(self, project: "Project", parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Export Dataset")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Export Dataset")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        # Stats summary
        stats_lbl = QLabel(
            f"Project: {self.project.name}  |  "
            f"{self.project.annotated_count}/{self.project.total_count} images annotated  |  "
            f"{self.project.total_box_count} total boxes  |  "
            f"{len(self.project.classes)} classes"
        )
        stats_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        stats_lbl.setWordWrap(True)
        layout.addWidget(stats_lbl)

        # Format
        fmt_grp = QGroupBox("Format")
        fmt_layout = QVBoxLayout(fmt_grp)
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItem("YOLO (txt + classes.txt)", "yolo")
        self._fmt_combo.addItem("COCO JSON", "coco")
        self._fmt_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_layout.addWidget(self._fmt_combo)
        layout.addWidget(fmt_grp)

        # YOLO options
        self._yolo_grp = QGroupBox("YOLO Options")
        yolo_layout = QVBoxLayout(self._yolo_grp)

        self._split_cb = QCheckBox("Split into train/val/test")
        self._split_cb.setChecked(True)
        self._split_cb.toggled.connect(self._on_split_toggled)
        yolo_layout.addWidget(self._split_cb)

        split_form = QFormLayout()
        split_form.setSpacing(4)
        self._train_spin = QSpinBox()
        self._train_spin.setRange(1, 98)
        self._train_spin.setValue(80)
        self._train_spin.setSuffix("%")
        split_form.addRow("Train:", self._train_spin)

        self._val_spin = QSpinBox()
        self._val_spin.setRange(1, 49)
        self._val_spin.setValue(10)
        self._val_spin.setSuffix("%")
        split_form.addRow("Val:", self._val_spin)

        self._test_spin = QSpinBox()
        self._test_spin.setRange(0, 49)
        self._test_spin.setValue(10)
        self._test_spin.setSuffix("%")
        split_form.addRow("Test:", self._test_spin)
        yolo_layout.addLayout(split_form)

        self._yaml_cb = QCheckBox("Generate data.yaml (YOLOv8)")
        self._yaml_cb.setChecked(True)
        yolo_layout.addWidget(self._yaml_cb)
        layout.addWidget(self._yolo_grp)

        # Output directory
        out_grp = QGroupBox("Output Directory")
        out_layout = QHBoxLayout(out_grp)
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Select output folder...")
        self._out_edit.setReadOnly(True)
        out_layout.addWidget(self._out_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        layout.addWidget(out_grp)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._export_btn = QPushButton("Export")
        self._export_btn.setStyleSheet(PRIMARY_BTN)
        self._export_btn.clicked.connect(self._do_export)
        btns.addWidget(self._export_btn)
        layout.addLayout(btns)

    def _on_format_changed(self, idx: int):
        self._yolo_grp.setVisible(self._fmt_combo.currentData() == "yolo")

    def _on_split_toggled(self, checked: bool):
        self._train_spin.setEnabled(checked)
        self._val_spin.setEnabled(checked)
        self._test_spin.setEnabled(checked)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self._out_edit.setText(folder)

    def _do_export(self):
        output_dir = self._out_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output directory.")
            return

        fmt = self._fmt_combo.currentData()
        split = None
        if fmt == "yolo" and self._split_cb.isChecked():
            t = self._train_spin.value() / 100
            v = self._val_spin.value() / 100
            e = self._test_spin.value() / 100
            total = t + v + e
            split = {
                "train": t / total,
                "val": v / total,
                "test": e / total,
            }

        generate_yaml = self._yaml_cb.isChecked() if fmt == "yolo" else False

        # Run in thread
        self._export_btn.setEnabled(False)
        self._export_btn.setText("Exporting…")

        self._worker = ExportWorker(self.project, output_dir, fmt, split, generate_yaml)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_export_done)
        self._worker.error.connect(self._on_export_error)
        self._thread.start()

    def _on_export_done(self, stats: dict):
        self._thread.quit()
        self._thread.wait()
        msg = (
            f"Export complete!\n\n"
            f"Images: {stats.get('images', 0)}\n"
            f"Annotations: {stats.get('annotations', 0)}\n"
            f"Classes: {stats.get('classes', 0)}"
        )
        QMessageBox.information(self, "Export Complete", msg)
        self.accept()

    def _on_export_error(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._export_btn.setEnabled(True)
        self._export_btn.setText("Export")
        QMessageBox.critical(self, "Export Error", f"Export failed:\n{err}")


# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, project: "Project", parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Settings")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(380)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        # Auto-save interval
        self._autosave_spin = QSpinBox()
        self._autosave_spin.setRange(1, 50)
        self._autosave_spin.setValue(self.project.settings.get("auto_save_interval", 5))
        self._autosave_spin.setSuffix(" images")
        form.addRow("Auto-save every:", self._autosave_spin)

        # Annotation opacity
        self._opacity_spin = QDoubleSpinBox()
        self._opacity_spin.setRange(0.05, 0.5)
        self._opacity_spin.setSingleStep(0.05)
        self._opacity_spin.setValue(self.project.settings.get("annotation_opacity", 0.15))
        form.addRow("Box fill opacity:", self._opacity_spin)

        # Crosshair
        self._crosshair_cb = QCheckBox()
        self._crosshair_cb.setChecked(self.project.settings.get("crosshair", False))
        form.addRow("Crosshair cursor:", self._crosshair_cb)

        # Canvas BG
        self._bg_edit = QLineEdit(self.project.settings.get("canvas_bg", "#2a2a2a"))
        form.addRow("Canvas background:", self._bg_edit)

        layout.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        ok_btn = QPushButton("Save")
        ok_btn.setStyleSheet(PRIMARY_BTN)
        ok_btn.clicked.connect(self._save)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

    def _save(self):
        self.project.settings["auto_save_interval"] = self._autosave_spin.value()
        self.project.settings["annotation_opacity"] = self._opacity_spin.value()
        self.project.settings["crosshair"] = self._crosshair_cb.isChecked()
        self.project.settings["canvas_bg"] = self._bg_edit.text().strip()
        self.project.modified = True
        self.accept()
