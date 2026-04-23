"""Dialogs for AnnotateX: export, settings, class assignment, new project, augmentation."""
from __future__ import annotations
import os
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QTextEdit, QProgressDialog, QProgressBar, QMessageBox, QListWidget,
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

    # Names we probe when auto-detecting a COCO annotation file
    _COCO_CANDIDATES = [
        "_annotations.coco.json",
        "_annotations.json",
        "annotations.json",
        "result.json",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(500)
        self.setMinimumHeight(400)

        self.result_folder: str = ""
        self.result_name: str = ""
        self.result_classes: list[str] = []
        self.result_import_labels: bool = False   # YOLO path
        self.result_coco_json: str = ""           # COCO path (takes priority)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

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
        self._folder_edit.setPlaceholderText("Select folder containing images…")
        self._folder_edit.setReadOnly(True)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_grp)

        # Image count
        self._img_count_lbl = QLabel("")
        self._img_count_lbl.setStyleSheet("color: #22c55e; font-size: 11px;")
        layout.addWidget(self._img_count_lbl)

        # ── COCO detection banner (hidden until a JSON is found) ──────────────
        self._coco_banner = QFrame()
        self._coco_banner.setStyleSheet(
            "QFrame { background: #052e16; border: 1px solid #166534; "
            "border-radius: 6px; padding: 4px; }"
        )
        coco_banner_layout = QVBoxLayout(self._coco_banner)
        coco_banner_layout.setContentsMargins(10, 8, 10, 8)
        coco_banner_layout.setSpacing(4)

        coco_title_row = QHBoxLayout()
        coco_icon = QLabel("✓  COCO annotations detected")
        coco_icon.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: bold;")
        coco_title_row.addWidget(coco_icon)
        coco_title_row.addStretch()
        # "Change…" lets the user override the auto-detected file
        self._coco_change_btn = QPushButton("Change file…")
        self._coco_change_btn.setFixedHeight(22)
        self._coco_change_btn.setStyleSheet(
            "QPushButton { background: #166534; color: #4ade80; border: none; "
            "border-radius: 3px; padding: 2px 8px; font-size: 10px; }"
            "QPushButton:hover { background: #15803d; }"
        )
        self._coco_change_btn.clicked.connect(self._change_coco_json)
        coco_title_row.addWidget(self._coco_change_btn)
        coco_banner_layout.addLayout(coco_title_row)

        self._coco_detail_lbl = QLabel("")
        self._coco_detail_lbl.setStyleSheet("color: #86efac; font-size: 10px;")
        self._coco_detail_lbl.setWordWrap(True)
        coco_banner_layout.addWidget(self._coco_detail_lbl)

        self._coco_banner.setVisible(False)
        layout.addWidget(self._coco_banner)

        # ── Initial classes (hidden when COCO supplies them) ──────────────────
        self._cls_grp = QGroupBox("Initial Classes (optional)")
        cls_layout = QVBoxLayout(self._cls_grp)
        cls_hint = QLabel("Enter one class per line — or leave blank and add them later:")
        cls_hint.setStyleSheet("color: #64748b; font-size: 10px;")
        cls_layout.addWidget(cls_hint)
        self._classes_edit = QTextEdit()
        self._classes_edit.setPlaceholderText("person\ncar\nbicycle\n…")
        self._classes_edit.setFixedHeight(90)
        self._classes_edit.setStyleSheet(
            "background-color: #0f172a; color: #e2e8f0; "
            "border: 1px solid #334155; border-radius: 4px; font-size: 11px;"
        )
        cls_layout.addWidget(self._classes_edit)
        layout.addWidget(self._cls_grp)

        # YOLO import checkbox (hidden when COCO is detected)
        self._import_labels_cb = QCheckBox("Import existing YOLO labels (if .txt files exist alongside images)")
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

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder:
            return
        self._folder_edit.setText(folder)

        from pathlib import Path
        from app.project import IMAGE_EXTENSIONS
        count = sum(1 for f in os.listdir(folder)
                    if Path(f).suffix.lower() in IMAGE_EXTENSIONS)
        self._img_count_lbl.setText(f"  {count} images found")

        # Auto-detect COCO JSON
        detected = self._find_coco_json(folder)
        self._apply_coco_json(detected)

    def _change_coco_json(self):
        """Let the user manually browse to a different COCO JSON."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select COCO JSON", self._folder_edit.text(),
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self._apply_coco_json(path)

    def _find_coco_json(self, folder: str) -> str:
        """Return the first matching COCO JSON path, or empty string."""
        for name in self._COCO_CANDIDATES:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return path
        return ""

    def _apply_coco_json(self, json_path: str):
        """Show or hide the COCO banner based on whether a JSON was found."""
        import json as _json
        from pathlib import Path

        if not json_path:
            self._coco_banner.setVisible(False)
            self._cls_grp.setVisible(True)
            self._cls_grp.setTitle("Initial Classes (optional)")
            self._import_labels_cb.setVisible(True)
            self._classes_edit.setReadOnly(False)
            self._classes_edit.setStyleSheet(
                "background-color: #0f172a; color: #e2e8f0; "
                "border: 1px solid #334155; border-radius: 4px; font-size: 11px;"
            )
            self._classes_edit.clear()
            self.result_coco_json = ""
            self.adjustSize()
            return

        # Parse just enough to show a meaningful preview
        try:
            with open(json_path, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:
            self._coco_banner.setVisible(False)
            self.result_coco_json = ""
            return

        unique_names = {cat["name"] for cat in data.get("categories", [])}
        img_count = len(data.get("images", []))
        ann_count = len(data.get("annotations", []))
        class_list = ", ".join(sorted(unique_names)) or "—"

        self._coco_detail_lbl.setText(
            f"{img_count} images  ·  {ann_count} annotations  ·  "
            f"{len(unique_names)} class{'es' if len(unique_names) != 1 else ''}: {class_list}\n"
            f"File: {Path(json_path).name}"
        )

        # Show classes read-only — they come from the JSON, user can't edit them
        self._classes_edit.setPlainText("\n".join(sorted(unique_names)))
        self._classes_edit.setReadOnly(True)
        self._classes_edit.setStyleSheet(
            "background-color: #0a1a0a; color: #4ade80; "
            "border: 1px solid #166534; border-radius: 4px; font-size: 11px;"
        )
        self._cls_grp.setTitle("Classes (from COCO file — read only)")

        self._coco_banner.setVisible(True)
        # Hide YOLO checkbox — COCO takes priority
        self._import_labels_cb.setVisible(False)
        self.result_coco_json = json_path
        self.adjustSize()

    def _create(self):
        folder = self._folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Error", "Please select a valid image folder.")
            return
        self.result_folder = folder
        self.result_name = self._name_edit.text().strip() or "My Dataset"
        raw = self._classes_edit.toPlainText().strip()
        self.result_classes = [l.strip() for l in raw.splitlines() if l.strip()]
        self.result_import_labels = (
            self._import_labels_cb.isChecked()
            and self._import_labels_cb.isVisible()
            and not self.result_coco_json
        )
        self.accept()


# ── Import COCO Dialog ────────────────────────────────────────────────────────

class ImportCocoDialog(QDialog):
    """
    Import a COCO-format dataset (e.g. exported from Roboflow) as a new project.

    The user selects the image folder.  The dialog auto-detects
    _annotations.coco.json inside that folder; the user can also browse to a
    different JSON file manually.  A live preview shows how many images,
    annotations and classes were found before the user commits to importing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import COCO Dataset")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(520)

        # Results filled on accept
        self.result_name: str = ""
        self.result_folder: str = ""
        self.result_json: str = ""

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Import COCO Dataset")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        hint = QLabel(
            "Imports a COCO JSON annotation file (e.g. from Roboflow) and creates "
            "a new AnnotateX project with all labels loaded and ready to review or edit."
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Project name ──────────────────────────────────────────────────────
        name_grp = QGroupBox("Project Name")
        name_layout = QHBoxLayout(name_grp)
        self._name_edit = QLineEdit("Imported Dataset")
        name_layout.addWidget(self._name_edit)
        layout.addWidget(name_grp)

        # ── Image folder ──────────────────────────────────────────────────────
        folder_grp = QGroupBox("Image Folder")
        folder_layout = QHBoxLayout(folder_grp)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select the folder containing the images…")
        self._folder_edit.setReadOnly(True)
        folder_layout.addWidget(self._folder_edit)
        browse_folder_btn = QPushButton("Browse…")
        browse_folder_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_folder_btn)
        layout.addWidget(folder_grp)

        # ── COCO JSON file ────────────────────────────────────────────────────
        json_grp = QGroupBox("COCO Annotation JSON")
        json_layout = QHBoxLayout(json_grp)
        self._json_edit = QLineEdit()
        self._json_edit.setPlaceholderText("Auto-detected from folder, or browse…")
        self._json_edit.setReadOnly(True)
        json_layout.addWidget(self._json_edit)
        browse_json_btn = QPushButton("Browse…")
        browse_json_btn.clicked.connect(self._browse_json)
        json_layout.addWidget(browse_json_btn)
        layout.addWidget(json_grp)

        # ── Preview panel ─────────────────────────────────────────────────────
        preview_grp = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_grp)
        self._preview_lbl = QLabel("Select a folder to see a preview.")
        self._preview_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._preview_lbl.setWordWrap(True)
        preview_layout.addWidget(self._preview_lbl)
        layout.addWidget(preview_grp)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._import_btn = QPushButton("Import")
        self._import_btn.setStyleSheet(PRIMARY_BTN)
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._do_import)
        btns.addWidget(self._import_btn)
        layout.addLayout(btns)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder:
            return
        self._folder_edit.setText(folder)
        # Auto-detect COCO JSON: look for common Roboflow names
        import os
        candidates = [
            "_annotations.coco.json",
            "annotations.json",
            "_annotations.json",
        ]
        for name in candidates:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                self._json_edit.setText(path)
                break
        self._refresh_preview()

    def _browse_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select COCO JSON File", self._folder_edit.text(),
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self._json_edit.setText(path)
            self._refresh_preview()

    def _refresh_preview(self):
        """Parse the JSON and update the preview label + Import button state."""
        import json as _json
        import os
        from pathlib import Path
        from app.project import IMAGE_EXTENSIONS

        folder = self._folder_edit.text().strip()
        json_path = self._json_edit.text().strip()

        if not folder or not json_path:
            self._preview_lbl.setText("Select a folder and JSON file to see a preview.")
            self._import_btn.setEnabled(False)
            return

        if not os.path.isdir(folder):
            self._preview_lbl.setText("Image folder not found.")
            self._import_btn.setEnabled(False)
            return

        if not os.path.isfile(json_path):
            self._preview_lbl.setText("JSON file not found.")
            self._import_btn.setEnabled(False)
            return

        # Count images in folder
        img_count = sum(
            1 for f in os.listdir(folder)
            if Path(f).suffix.lower() in IMAGE_EXTENSIONS
        )

        # Parse JSON for counts
        try:
            with open(json_path, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            self._preview_lbl.setText(f"Could not read JSON: {e}")
            self._import_btn.setEnabled(False)
            return

        # Deduplicate category names (mirrors load_coco_labels logic)
        unique_names: set[str] = set()
        for cat in data.get("categories", []):
            unique_names.add(cat["name"])

        json_img_count = len(data.get("images", []))
        ann_count = len(data.get("annotations", []))
        cls_count = len(unique_names)
        class_list = ", ".join(sorted(unique_names)) or "—"

        matched = sum(
            1 for img in data.get("images", [])
            if os.path.exists(os.path.join(folder, Path(img["file_name"]).name))
        )

        lines = [
            f"Images in folder: <b>{img_count}</b>",
            f"Images in JSON:   <b>{json_img_count}</b>  "
            f"(matched: <b style='color:#4ade80'>{matched}</b>)",
            f"Annotations:      <b>{ann_count}</b>",
            f"Classes ({cls_count}):    {class_list}",
        ]
        if matched == 0:
            lines.append(
                "<span style='color:#f87171'>⚠ No images matched — "
                "check that you selected the right folder.</span>"
            )
        self._preview_lbl.setText("<br>".join(lines))
        self._preview_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._import_btn.setEnabled(matched > 0)

    def _do_import(self):
        self.result_name = self._name_edit.text().strip() or "Imported Dataset"
        self.result_folder = self._folder_edit.text().strip()
        self.result_json = self._json_edit.text().strip()
        self.accept()


# ── Export Dialog ─────────────────────────────────────────────────────────────

class ExportWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, project, output_dir: str, fmt: str):
        super().__init__()
        self.project = project
        self.output_dir = output_dir
        self.fmt = fmt

    def run(self):
        try:
            from app.utils import export_yolo, export_coco
            if self.fmt == "yolo":
                # Always export flat (no split, no yaml) — split happens after augmentation
                stats = export_yolo(self.project, self.output_dir,
                                    split=None, generate_yaml=False)
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

        stats_lbl = QLabel(
            f"Project: {self.project.name}  |  "
            f"{self.project.annotated_count}/{self.project.total_count} images annotated  |  "
            f"{self.project.total_box_count} total boxes  |  "
            f"{len(self.project.classes)} classes"
        )
        stats_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        stats_lbl.setWordWrap(True)
        layout.addWidget(stats_lbl)

        hint = QLabel(
            "Exports a flat images/ + labels/ folder. You can augment and split\n"
            "the dataset in the next steps after export."
        )
        hint.setStyleSheet("color: #475569; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Format
        fmt_grp = QGroupBox("Format")
        fmt_layout = QVBoxLayout(fmt_grp)
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItem("YOLO (txt + classes.txt)", "yolo")
        self._fmt_combo.addItem("COCO JSON", "coco")
        fmt_layout.addWidget(self._fmt_combo)
        layout.addWidget(fmt_grp)

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

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self._out_edit.setText(folder)

    def _do_export(self):
        output_dir = self._out_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output directory.")
            return

        self._export_btn.setEnabled(False)
        self._export_btn.setText("Exporting…")

        fmt = self._fmt_combo.currentData()
        self._worker = ExportWorker(self.project, output_dir, fmt)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_export_done)
        self._worker.error.connect(self._on_export_error)
        self._thread.start()

    def _on_export_done(self, stats: dict):
        self._thread.quit()
        self._thread.wait()

        fmt = self._fmt_combo.currentData()
        output_dir = self._out_edit.text().strip()

        msg = (
            f"Export complete!\n\n"
            f"Images: {stats.get('images', 0)}\n"
            f"Annotations: {stats.get('annotations', 0)}\n"
            f"Classes: {stats.get('classes', 0)}"
        )

        # For YOLO exports: offer to continue into augmentation (→ then split)
        if fmt == "yolo":
            msg += "\n\nWould you like to augment this dataset now?"
            box = QMessageBox(self)
            box.setWindowTitle("Export Complete")
            box.setText(msg)
            box.setIcon(QMessageBox.Icon.Information)
            augment_btn = box.addButton("Augment Now", QMessageBox.ButtonRole.AcceptRole)
            skip_btn = box.addButton("Skip to Split", QMessageBox.ButtonRole.ActionRole)
            box.addButton("Done", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            self.accept()
            if clicked is augment_btn:
                dlg = AugmentDialog(self.project, self.parent(), prefill_output_dir=output_dir)
                dlg.exec()
            elif clicked is skip_btn:
                dlg = SplitDialog(self.parent(), prefill_folder=output_dir)
                dlg.exec()
        else:
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


# ── Augmentation Dialog ───────────────────────────────────────────────────────

class AugmentWorker(QObject):
    progress = pyqtSignal(int, int)   # current, total
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, project, output_dir: str, cfg, folder_mode: bool = False):
        super().__init__()
        self.project = project
        self.output_dir = output_dir
        self.cfg = cfg
        self.folder_mode = folder_mode

    def run(self):
        try:
            if self.folder_mode:
                from app.augmentation import augment_from_folder
                stats = augment_from_folder(
                    self.output_dir, self.cfg,
                    progress_cb=lambda cur, tot: self.progress.emit(cur, tot)
                )
            else:
                from app.augmentation import run_augmentation
                stats = run_augmentation(
                    self.project, self.output_dir, self.cfg,
                    progress_cb=lambda cur, tot: self.progress.emit(cur, tot)
                )
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))


class AugmentDialog(QDialog):
    """Dataset augmentation dialog — shown after annotation is complete."""

    def __init__(self, project: "Project", parent=None, prefill_output_dir: str = ""):
        super().__init__(parent)
        self.project = project
        self._prefill_output_dir = prefill_output_dir
        # folder_mode=True when launched from the export pipeline:
        # we augment the already-exported folder in-place rather than re-reading from the project.
        self._folder_mode = bool(prefill_output_dir)
        self.setWindowTitle("Augment Dataset")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(520)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title + summary
        title = QLabel("Dataset Augmentation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        annotated = self.project.annotated_count
        total = self.project.total_count
        summary = QLabel(
            f"{annotated}/{total} images annotated  |  "
            f"{self.project.total_box_count} boxes  |  "
            f"{len(self.project.classes)} classes"
        )
        summary.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(summary)

        # ── Flip ─────────────────────────────────────────────────────────────
        flip_grp = QGroupBox("Flip")
        flip_layout = QHBoxLayout(flip_grp)
        self._flip_h = QCheckBox("Horizontal (mirror left/right)")
        self._flip_h.setChecked(True)
        self._flip_v = QCheckBox("Vertical (mirror top/bottom)")
        flip_layout.addWidget(self._flip_h)
        flip_layout.addWidget(self._flip_v)
        layout.addWidget(flip_grp)

        # ── Color ─────────────────────────────────────────────────────────────
        color_grp = QGroupBox("Color Adjustments")
        color_form = QFormLayout(color_grp)
        color_form.setSpacing(6)

        self._brightness_cb = QCheckBox()
        self._brightness_cb.setChecked(True)
        self._brightness_min = QDoubleSpinBox()
        self._brightness_min.setRange(0.1, 1.0)
        self._brightness_min.setSingleStep(0.1)
        self._brightness_min.setValue(0.6)
        self._brightness_max = QDoubleSpinBox()
        self._brightness_max.setRange(1.0, 2.0)
        self._brightness_max.setSingleStep(0.1)
        self._brightness_max.setValue(1.4)
        brightness_row = QHBoxLayout()
        brightness_row.addWidget(self._brightness_cb)
        brightness_row.addWidget(QLabel("Range:"))
        brightness_row.addWidget(self._brightness_min)
        brightness_row.addWidget(QLabel("–"))
        brightness_row.addWidget(self._brightness_max)
        color_form.addRow("Brightness:", brightness_row)

        self._contrast_cb = QCheckBox()
        self._contrast_cb.setChecked(True)
        self._contrast_min = QDoubleSpinBox()
        self._contrast_min.setRange(0.1, 1.0)
        self._contrast_min.setSingleStep(0.1)
        self._contrast_min.setValue(0.6)
        self._contrast_max = QDoubleSpinBox()
        self._contrast_max.setRange(1.0, 2.0)
        self._contrast_max.setSingleStep(0.1)
        self._contrast_max.setValue(1.4)
        contrast_row = QHBoxLayout()
        contrast_row.addWidget(self._contrast_cb)
        contrast_row.addWidget(QLabel("Range:"))
        contrast_row.addWidget(self._contrast_min)
        contrast_row.addWidget(QLabel("–"))
        contrast_row.addWidget(self._contrast_max)
        color_form.addRow("Contrast:", contrast_row)

        self._saturation_cb = QCheckBox()
        self._saturation_cb.setChecked(True)
        self._saturation_min = QDoubleSpinBox()
        self._saturation_min.setRange(0.0, 1.0)
        self._saturation_min.setSingleStep(0.1)
        self._saturation_min.setValue(0.5)
        self._saturation_max = QDoubleSpinBox()
        self._saturation_max.setRange(1.0, 3.0)
        self._saturation_max.setSingleStep(0.1)
        self._saturation_max.setValue(1.5)
        saturation_row = QHBoxLayout()
        saturation_row.addWidget(self._saturation_cb)
        saturation_row.addWidget(QLabel("Range:"))
        saturation_row.addWidget(self._saturation_min)
        saturation_row.addWidget(QLabel("–"))
        saturation_row.addWidget(self._saturation_max)
        color_form.addRow("Saturation:", saturation_row)

        layout.addWidget(color_grp)

        # ── Noise / Blur ──────────────────────────────────────────────────────
        noise_grp = QGroupBox("Noise & Blur")
        noise_form = QFormLayout(noise_grp)
        noise_form.setSpacing(6)

        self._blur_cb = QCheckBox()
        self._blur_radius = QDoubleSpinBox()
        self._blur_radius.setRange(0.5, 5.0)
        self._blur_radius.setSingleStep(0.5)
        self._blur_radius.setValue(1.5)
        blur_row = QHBoxLayout()
        blur_row.addWidget(self._blur_cb)
        blur_row.addWidget(QLabel("Radius:"))
        blur_row.addWidget(self._blur_radius)
        noise_form.addRow("Gaussian Blur:", blur_row)

        self._noise_cb = QCheckBox()
        self._noise_std = QSpinBox()
        self._noise_std.setRange(1, 60)
        self._noise_std.setValue(15)
        noise_row = QHBoxLayout()
        noise_row.addWidget(self._noise_cb)
        noise_row.addWidget(QLabel("Std:"))
        noise_row.addWidget(self._noise_std)
        noise_form.addRow("Gaussian Noise:", noise_row)

        layout.addWidget(noise_grp)

        # ── Rotation ──────────────────────────────────────────────────────────
        rot_grp = QGroupBox("Rotation")
        rot_layout = QHBoxLayout(rot_grp)
        self._rotation_cb = QCheckBox("Enable")
        self._rotation_deg = QSpinBox()
        self._rotation_deg.setRange(1, 45)
        self._rotation_deg.setValue(15)
        self._rotation_deg.setSuffix("°")
        rot_layout.addWidget(self._rotation_cb)
        rot_layout.addWidget(QLabel("Max angle ±"))
        rot_layout.addWidget(self._rotation_deg)
        rot_layout.addStretch()
        layout.addWidget(rot_grp)

        # ── Output options ────────────────────────────────────────────────────
        out_grp = QGroupBox("Output Options")
        out_form = QFormLayout(out_grp)
        out_form.setSpacing(6)

        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 10)
        self._copies_spin.setValue(2)
        self._copies_spin.setSuffix(" per image")
        out_form.addRow("Augmented copies:", self._copies_spin)

        self._only_annotated_cb = QCheckBox("Only augment annotated images")
        self._only_annotated_cb.setChecked(True)
        out_form.addRow("", self._only_annotated_cb)

        self._include_originals_cb = QCheckBox("Include original images in output")
        self._include_originals_cb.setChecked(True)
        out_form.addRow("", self._include_originals_cb)

        layout.addWidget(out_grp)

        # ── Output directory ──────────────────────────────────────────────────
        if self._folder_mode:
            # In folder mode the target folder is already known — show it locked.
            dir_grp = QGroupBox("Dataset Folder (augmenting in-place)")
            dir_layout = QVBoxLayout(dir_grp)
            folder_lbl = QLabel(self._prefill_output_dir)
            folder_lbl.setStyleSheet("color: #a78bfa; font-size: 11px;")
            folder_lbl.setWordWrap(True)
            dir_layout.addWidget(folder_lbl)
            hint_lbl = QLabel("Augmented copies will be added into the images/ and labels/ folders alongside the originals.")
            hint_lbl.setStyleSheet("color: #475569; font-size: 10px;")
            hint_lbl.setWordWrap(True)
            dir_layout.addWidget(hint_lbl)
            self._out_edit = QLineEdit(self._prefill_output_dir)
            self._out_edit.setVisible(False)   # hidden — only used internally
        else:
            dir_grp = QGroupBox("Output Directory")
            dir_layout = QHBoxLayout(dir_grp)
            self._out_edit = QLineEdit()
            self._out_edit.setPlaceholderText("Select output folder…")
            self._out_edit.setReadOnly(True)
            dir_layout.addWidget(self._out_edit)
            browse_btn = QPushButton("Browse…")
            browse_btn.clicked.connect(self._browse_output)
            dir_layout.addWidget(browse_btn)
        layout.addWidget(dir_grp)

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                height: 16px;
            }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 3px; }
        """)
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(self._status_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self._cancel_btn)
        self._run_btn = QPushButton("Run Augmentation")
        self._run_btn.setStyleSheet(PRIMARY_BTN)
        self._run_btn.clicked.connect(self._run)
        btns.addWidget(self._run_btn)
        layout.addLayout(btns)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self._out_edit.setText(folder)

    def _build_config(self):
        from app.augmentation import AugConfig
        return AugConfig(
            flip_horizontal=self._flip_h.isChecked(),
            flip_vertical=self._flip_v.isChecked(),
            brightness=self._brightness_cb.isChecked(),
            brightness_range=(self._brightness_min.value(), self._brightness_max.value()),
            contrast=self._contrast_cb.isChecked(),
            contrast_range=(self._contrast_min.value(), self._contrast_max.value()),
            saturation=self._saturation_cb.isChecked(),
            saturation_range=(self._saturation_min.value(), self._saturation_max.value()),
            blur=self._blur_cb.isChecked(),
            blur_radius=self._blur_radius.value(),
            noise=self._noise_cb.isChecked(),
            noise_std=self._noise_std.value(),
            rotation=self._rotation_cb.isChecked(),
            rotation_degrees=float(self._rotation_deg.value()),
            copies_per_image=self._copies_spin.value(),
            only_annotated=self._only_annotated_cb.isChecked(),
            output_original=self._include_originals_cb.isChecked(),
        )

    def _run(self):
        output_dir = self._out_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output directory.")
            return

        cfg = self._build_config()

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Running…")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress.setMaximum(0)  # indeterminate until first progress tick

        self._worker = AugmentWorker(
            self.project, output_dir, cfg, folder_mode=self._folder_mode
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, current: int, total: int):
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._status_lbl.setText(f"Processing image {current}/{total}…")

    def _on_done(self, stats: dict):
        self._thread.quit()
        self._thread.wait()

        total_out = stats.get('original', 0) + stats.get('augmented', 0)
        msg = (
            f"Augmentation complete!\n\n"
            f"Original images: {stats.get('original', 0)}\n"
            f"Augmented images: {stats.get('augmented', 0)}\n"
            f"Skipped: {stats.get('skipped', 0)}\n\n"
            f"Total in folder: {total_out} images"
        )

        if self._folder_mode:
            # Offer to split now that the dataset is enriched
            msg += "\n\nWould you like to split this dataset into train / val / test now?"
            box = QMessageBox(self)
            box.setWindowTitle("Augmentation Complete")
            box.setText(msg)
            box.setIcon(QMessageBox.Icon.Information)
            split_btn = box.addButton("Split Now", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Done", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            self.accept()
            if box.clickedButton() is split_btn:
                dlg = SplitDialog(self.parent(), prefill_folder=self._out_edit.text().strip())
                dlg.exec()
        else:
            QMessageBox.information(self, "Augmentation Complete", msg)
            self.accept()

    def _on_error(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Run Augmentation")
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Augmentation Error", f"Failed:\n{err}")


# ── Split Dialog ──────────────────────────────────────────────────────────────

class SplitWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, folder: str, split: dict, generate_yaml: bool):
        super().__init__()
        self.folder = folder
        self.split = split
        self.generate_yaml = generate_yaml

    def run(self):
        try:
            from app.utils import split_dataset
            stats = split_dataset(self.folder, self.split, self.generate_yaml)
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))


class SplitDialog(QDialog):
    """
    Partition a flat YOLO dataset folder (images/ + labels/) into
    train / val / test subfolders and write data.yaml.

    Can be opened standalone from the menu or chained after augmentation.
    """

    def __init__(self, parent=None, prefill_folder: str = ""):
        super().__init__(parent)
        self._prefill_folder = prefill_folder
        self.setWindowTitle("Split Dataset")
        self.setStyleSheet(DIALOG_STYLE)
        self.setFixedWidth(460)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Split Dataset")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        hint = QLabel(
            "Partitions images/ and labels/ into train / val / test subfolders "
            "and generates data.yaml ready for YOLOv8 training.\n"
            "Files are moved (not copied), so no extra disk space is needed."
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Dataset folder picker
        folder_grp = QGroupBox("Dataset Folder")
        folder_layout = QHBoxLayout(folder_grp)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select the exported dataset folder…")
        self._folder_edit.setReadOnly(True)
        if self._prefill_folder:
            self._folder_edit.setText(self._prefill_folder)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_grp)

        # Split ratios
        split_grp = QGroupBox("Split Ratios")
        split_form = QFormLayout(split_grp)
        split_form.setSpacing(6)

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
        split_form.addRow("Test (0 = skip):", self._test_spin)

        self._yaml_cb = QCheckBox("Generate data.yaml  (required for YOLOv8 training)")
        self._yaml_cb.setChecked(True)
        split_form.addRow("", self._yaml_cb)
        layout.addWidget(split_grp)

        # Progress (indeterminate — split is fast, just moving files)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 0)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: #0f172a; border: 1px solid #334155;
                border-radius: 4px; height: 16px;
            }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 3px; }
        """)
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(self._status_lbl)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._run_btn = QPushButton("Split Dataset")
        self._run_btn.setStyleSheet(PRIMARY_BTN)
        self._run_btn.clicked.connect(self._run)
        btns.addWidget(self._run_btn)
        layout.addLayout(btns)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder")
        if folder:
            self._folder_edit.setText(folder)

    def _run(self):
        folder = self._folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "Error", "Please select the dataset folder.")
            return

        t = self._train_spin.value() / 100
        v = self._val_spin.value() / 100
        e = self._test_spin.value() / 100
        total = t + v + (e if e > 0 else 0)
        split: dict = {"train": t / total, "val": v / total}
        if e > 0:
            split["test"] = e / total

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Splitting…")
        self._progress.setVisible(True)
        self._status_lbl.setText("Moving files into subfolders…")

        self._worker = SplitWorker(folder, split, self._yaml_cb.isChecked())
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, stats: dict):
        self._thread.quit()
        self._thread.wait()
        lines = [
            f"Train: {stats.get('train', 0)} images",
            f"Val:   {stats.get('val', 0)} images",
        ]
        if stats.get('test', 0):
            lines.append(f"Test:  {stats.get('test', 0)} images")
        lines.append(f"\nTotal: {stats.get('total', 0)} images")
        if self._yaml_cb.isChecked():
            lines.append("\ndata.yaml written — ready for training!")
        QMessageBox.information(self, "Split Complete",
                                "Split complete!\n\n" + "\n".join(lines))
        self.accept()

    def _on_error(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Split Dataset")
        self._progress.setVisible(False)
        self._status_lbl.setText("")
        QMessageBox.critical(self, "Split Error", f"Split failed:\n{err}")


# ── Batch Export Dialog ────────────────────────────────────────────────────────

class BatchExportWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, project_paths: list, output_dir: str,
                 split: Optional[dict], generate_yaml: bool, aug_cfg):
        super().__init__()
        self.project_paths = project_paths
        self.output_dir = output_dir
        self.split = split
        self.generate_yaml = generate_yaml
        self.aug_cfg = aug_cfg

    def run(self):
        try:
            from app.utils import batch_export_yolo
            stats = batch_export_yolo(
                self.project_paths, self.output_dir,
                split=self.split,
                generate_yaml=self.generate_yaml,
                aug_cfg=self.aug_cfg,
                progress_cb=lambda cur, tot: self.progress.emit(cur, tot),
            )
            self.finished.emit(stats)
        except Exception as e:
            import traceback
            self.error.emit(traceback.format_exc())


class BatchExportDialog(QDialog):
    """Export + optionally augment multiple projects into one unified dataset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge Datasets — Multiple Projects")
        self.setStyleSheet(DIALOG_STYLE)
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Merge Datasets — Multiple Projects")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #a78bfa;")
        layout.addWidget(title)

        hint = QLabel(
            "Add two or more .annotatex project files. All images and annotations\n"
            "will be merged into one dataset with unified class IDs (matched by name)."
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(hint)

        # ── Project list ──────────────────────────────────────────────────────
        proj_grp = QGroupBox("Projects")
        proj_layout = QVBoxLayout(proj_grp)

        self._proj_list = QListWidget()
        self._proj_list.setFixedHeight(130)
        self._proj_list.setStyleSheet(
            "QListWidget { background: #0f172a; color: #e2e8f0; "
            "border: 1px solid #334155; border-radius: 4px; font-size: 11px; }"
            "QListWidget::item:selected { background: #334155; }"
        )
        proj_layout.addWidget(self._proj_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Project…")
        add_btn.clicked.connect(self._add_projects)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        self._proj_count_lbl = QLabel("0 projects")
        self._proj_count_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._proj_count_lbl)
        proj_layout.addLayout(btn_row)
        layout.addWidget(proj_grp)

        # ── Split options ─────────────────────────────────────────────────────
        split_grp = QGroupBox("Train / Val / Test Split")
        split_form = QFormLayout(split_grp)
        split_form.setSpacing(4)

        self._split_cb = QCheckBox("Enable split")
        self._split_cb.setChecked(True)
        self._split_cb.toggled.connect(self._on_split_toggled)
        split_form.addRow("", self._split_cb)

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

        self._yaml_cb = QCheckBox("Generate data.yaml (YOLOv8)")
        self._yaml_cb.setChecked(True)
        split_form.addRow("", self._yaml_cb)
        layout.addWidget(split_grp)

        # ── Augmentation toggle ───────────────────────────────────────────────
        aug_grp = QGroupBox("Augmentation (optional)")
        aug_top = QVBoxLayout(aug_grp)

        self._aug_cb = QCheckBox("Enable augmentation")
        self._aug_cb.setChecked(False)
        self._aug_cb.toggled.connect(self._on_aug_toggled)
        aug_top.addWidget(self._aug_cb)

        # Inner scroll area for aug options
        self._aug_widget = QWidget()
        aug_inner = QFormLayout(self._aug_widget)
        aug_inner.setSpacing(5)

        self._flip_h = QCheckBox("Horizontal flip")
        self._flip_h.setChecked(True)
        aug_inner.addRow("Flip:", self._flip_h)

        self._flip_v = QCheckBox("Vertical flip")
        aug_inner.addRow("", self._flip_v)

        self._brightness_cb = QCheckBox("Brightness")
        self._brightness_cb.setChecked(True)
        aug_inner.addRow("Color:", self._brightness_cb)

        self._contrast_cb = QCheckBox("Contrast")
        self._contrast_cb.setChecked(True)
        aug_inner.addRow("", self._contrast_cb)

        self._saturation_cb = QCheckBox("Saturation")
        self._saturation_cb.setChecked(True)
        aug_inner.addRow("", self._saturation_cb)

        self._rotation_cb = QCheckBox("Rotation ±")
        self._rotation_deg = QSpinBox()
        self._rotation_deg.setRange(1, 45)
        self._rotation_deg.setValue(15)
        self._rotation_deg.setSuffix("°")
        rot_row = QHBoxLayout()
        rot_row.addWidget(self._rotation_cb)
        rot_row.addWidget(self._rotation_deg)
        rot_row.addStretch()
        aug_inner.addRow("Rotation:", rot_row)

        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 10)
        self._copies_spin.setValue(2)
        self._copies_spin.setSuffix(" per image")
        aug_inner.addRow("Copies:", self._copies_spin)

        self._only_annotated_cb = QCheckBox("Only augment annotated images")
        self._only_annotated_cb.setChecked(True)
        aug_inner.addRow("", self._only_annotated_cb)

        self._include_originals_cb = QCheckBox("Include originals in output")
        self._include_originals_cb.setChecked(True)
        aug_inner.addRow("", self._include_originals_cb)

        self._aug_widget.setVisible(False)
        aug_top.addWidget(self._aug_widget)
        layout.addWidget(aug_grp)

        # ── Output directory ──────────────────────────────────────────────────
        out_grp = QGroupBox("Output Directory")
        out_layout = QHBoxLayout(out_grp)
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Select output folder…")
        self._out_edit.setReadOnly(True)
        out_layout.addWidget(self._out_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        layout.addWidget(out_grp)

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: #0f172a; border: 1px solid #334155;
                border-radius: 4px; height: 16px;
            }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 3px; }
        """)
        layout.addWidget(self._progress)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(self._status_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        self._run_btn = QPushButton("Export")
        self._run_btn.setStyleSheet(PRIMARY_BTN)
        self._run_btn.clicked.connect(self._run)
        btns.addWidget(self._run_btn)
        layout.addLayout(btns)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_split_toggled(self, checked: bool):
        self._train_spin.setEnabled(checked)
        self._val_spin.setEnabled(checked)
        self._test_spin.setEnabled(checked)

    def _on_aug_toggled(self, checked: bool):
        self._aug_widget.setVisible(checked)
        self.adjustSize()

    def _add_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Project Files", "",
            "AnnotateX Projects (*.annotatex);;All Files (*)"
        )
        existing = {self._proj_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self._proj_list.count())}
        for p in paths:
            if p not in existing:
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(p)
                self._proj_list.addItem(item)
        self._update_count()

    def _remove_selected(self):
        for item in self._proj_list.selectedItems():
            self._proj_list.takeItem(self._proj_list.row(item))
        self._update_count()

    def _update_count(self):
        n = self._proj_list.count()
        self._proj_count_lbl.setText(f"{n} project{'s' if n != 1 else ''}")

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self._out_edit.setText(folder)

    def _build_aug_config(self):
        from app.augmentation import AugConfig
        return AugConfig(
            flip_horizontal=self._flip_h.isChecked(),
            flip_vertical=self._flip_v.isChecked(),
            brightness=self._brightness_cb.isChecked(),
            contrast=self._contrast_cb.isChecked(),
            saturation=self._saturation_cb.isChecked(),
            rotation=self._rotation_cb.isChecked(),
            rotation_degrees=float(self._rotation_deg.value()),
            copies_per_image=self._copies_spin.value(),
            only_annotated=self._only_annotated_cb.isChecked(),
            output_original=self._include_originals_cb.isChecked(),
        )

    def _run(self):
        project_paths = [
            self._proj_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._proj_list.count())
        ]
        if len(project_paths) < 2:
            QMessageBox.warning(self, "Error", "Please add at least 2 project files.")
            return
        output_dir = self._out_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output directory.")
            return

        split = None
        if self._split_cb.isChecked():
            t = self._train_spin.value() / 100
            v = self._val_spin.value() / 100
            e = self._test_spin.value() / 100
            total = t + v + e
            split = {"train": t / total, "val": v / total, "test": e / total}

        aug_cfg = self._build_aug_config() if self._aug_cb.isChecked() else None

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Exporting…")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress.setMaximum(100)

        self._worker = BatchExportWorker(
            project_paths, output_dir, split,
            self._yaml_cb.isChecked(), aug_cfg
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
        self._status_lbl.setText(f"Processing image {current}/{total}…")

    def _on_done(self, stats: dict):
        self._thread.quit()
        self._thread.wait()
        msg = (
            f"Dataset merge complete!\n\n"
            f"Projects merged: {stats.get('projects', 0)}\n"
            f"Original images: {stats.get('images', 0)}\n"
            f"Augmented images: {stats.get('augmented', 0)}\n"
            f"Total annotations: {stats.get('annotations', 0)}\n"
            f"Unified classes: {stats.get('classes', 0)}"
        )
        QMessageBox.information(self, "Done", msg)
        self.accept()

    def _on_error(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Export")
        QMessageBox.critical(self, "Merge Datasets Error", f"Export failed:\n{err}")
