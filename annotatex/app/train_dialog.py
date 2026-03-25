"""Training dialog for AnnotateX — multi-dataset merge + YOLO training."""
from __future__ import annotations

import shutil
import random
import yaml
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QSpinBox, QMessageBox, QProgressBar,
    QTextEdit, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QLineEdit, QAbstractItemView, QScrollArea, QSizePolicy,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette

# ── Palette ────────────────────────────────────────────────────────────────────
BG         = "#0d0d1a"
SURFACE    = "#13131f"
CARD       = "#1a1a2e"
CARD2      = "#1e1e30"
BORDER     = "#2a2a40"
BORDER2    = "#334155"
ACCENT     = "#7c3aed"
ACCENT_LT  = "#a78bfa"
ACCENT_DIM = "#3b1f6e"
TEXT       = "#e2e8f0"
TEXT_DIM   = "#94a3b8"
TEXT_MUTED = "#475569"
GREEN      = "#22c55e"
AMBER      = "#f59e0b"
RED        = "#ef4444"
RED_DIM    = "#7f1d1d"

DIALOG_STYLE = f"""
    QDialog {{
        background-color: {BG};
        color: {TEXT};
    }}
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QWidget#scroll_content {{
        background-color: transparent;
    }}
    QLabel {{
        color: {TEXT};
        background: transparent;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
        min-height: 22px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 8px;
    }}
    QComboBox::down-arrow {{
        width: 10px; height: 10px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {CARD};
        color: {TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT_DIM};
        selection-color: {ACCENT_LT};
        padding: 4px;
    }}
    QTableWidget {{
        background-color: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER};
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
    }}
    QTableWidget::item:selected {{
        background-color: {ACCENT_DIM};
        color: {ACCENT_LT};
    }}
    QHeaderView::section {{
        background-color: {CARD};
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 8px 10px;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }}
    QTextEdit {{
        background-color: {SURFACE};
        color: #86efac;
        border: 1px solid {BORDER};
        border-radius: 8px;
        font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
        font-size: 11px;
        padding: 8px;
    }}
    QScrollBar:vertical {{
        background: {SURFACE}; width: 6px; border: none; border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER2}; border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {SURFACE}; height: 6px; border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER2}; border-radius: 3px;
    }}
"""

def _card(radius=10) -> QWidget:
    """A styled card container widget."""
    w = QWidget()
    w.setStyleSheet(f"""
        QWidget {{
            background-color: {CARD};
            border: 1px solid {BORDER};
            border-radius: {radius}px;
        }}
    """)
    return w

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"""
        color: {TEXT_MUTED};
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
        background: transparent;
        border: none;
    """)
    return lbl

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; background: transparent; border: none;")
    return lbl

def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background-color: {BORDER}; border: none; max-height: 1px;")
    return f

def _primary_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {ACCENT};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 24px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: #6d28d9; }}
        QPushButton:pressed {{ background-color: #5b21b6; }}
        QPushButton:disabled {{ background-color: {ACCENT_DIM}; color: #6b4fa0; }}
    """)
    return btn

def _ghost_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: transparent;
            color: {TEXT_DIM};
            border: 1px solid {BORDER2};
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background-color: {CARD2};
            color: {TEXT};
            border-color: {TEXT_MUTED};
        }}
    """)
    return btn

def _danger_btn(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {RED_DIM};
            color: #fca5a5;
            border: 1px solid #991b1b;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 12px;
        }}
        QPushButton:hover {{ background-color: #991b1b; color: white; }}
        QPushButton:disabled {{ opacity: 0.5; }}
    """)
    return btn

def _small_btn(text: str, color=BORDER2) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: {TEXT_DIM};
            border: none;
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 11px;
        }}
        QPushButton:hover {{ background-color: {BORDER2}; color: {TEXT}; }}
    """)
    return btn

PROGRESS_STYLE = f"""
    QProgressBar {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 6px;
        height: 8px;
        text-align: center;
        font-size: 10px;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #7c3aed, stop:1 #a78bfa);
        border-radius: 5px;
    }}
"""

PROGRESS_STYLE_LABELED = f"""
    QProgressBar {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 6px;
        height: 20px;
        text-align: center;
        font-size: 11px;
        color: {TEXT};
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #7c3aed, stop:1 #a78bfa);
        border-radius: 5px;
    }}
"""

# ── Dataset entry ─────────────────────────────────────────────────────────────

class DatasetEntry:
    def __init__(self, folder: str):
        self.folder = folder
        self.name = Path(folder).name
        self.classes: list[str] = []
        self.image_count: int = 0
        self.label_count: int = 0
        self.error: Optional[str] = None
        self._scan()

    def _scan(self):
        folder = Path(self.folder)
        data_yaml = folder / "data.yaml"
        classes_txt = folder / "classes.txt"

        if data_yaml.exists():
            try:
                with open(data_yaml) as f:
                    d = yaml.safe_load(f)
                names = d.get("names", [])
                if isinstance(names, dict):
                    names = [names[k] for k in sorted(names.keys())]
                self.classes = [str(n) for n in names]
            except Exception as e:
                self.error = f"Bad data.yaml: {e}"
        elif classes_txt.exists():
            try:
                self.classes = [l.strip() for l in classes_txt.read_text().splitlines() if l.strip()]
            except Exception as e:
                self.error = f"Bad classes.txt: {e}"

        img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        search_dirs = [folder]
        for sub in ["images", "train/images", "val/images", "test/images", "train", "val", "test"]:
            p = folder / sub
            if p.is_dir():
                search_dirs.append(p)

        seen_img, seen_lbl = set(), set()
        for d in search_dirs:
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.suffix.lower() in img_exts and str(f) not in seen_img:
                    self.image_count += 1
                    seen_img.add(str(f))
                elif f.suffix.lower() == ".txt" and f.name != "classes.txt" and str(f) not in seen_lbl:
                    self.label_count += 1
                    seen_lbl.add(str(f))

        if self.image_count == 0:
            self.error = "No images found"


# ── Workers ───────────────────────────────────────────────────────────────────

class MergeWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, datasets, class_mapping, unified_classes, output_dir, train_pct, val_pct):
        super().__init__()
        self.datasets = datasets
        self.class_mapping = class_mapping
        self.unified_classes = unified_classes
        self.output_dir = output_dir
        self.train_pct = train_pct
        self.val_pct = val_pct

    def run(self):
        try:
            self._merge()
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _merge(self):
        out = Path(self.output_dir)
        img_dir = out / "images"
        lbl_dir = out / "labels"
        for split in ["train", "val"]:
            (img_dir / split).mkdir(parents=True, exist_ok=True)
            (lbl_dir / split).mkdir(parents=True, exist_ok=True)

        class_id_map = {name: i for i, name in enumerate(self.unified_classes)}
        img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        all_pairs = []

        self.progress.emit("Scanning datasets…")
        for ds_idx, ds in enumerate(self.datasets):
            folder = Path(ds.folder)
            search_dirs = [folder]
            for sub in ["images", "train/images", "val/images", "test/images", "train", "val", "test"]:
                p = folder / sub
                if p.is_dir():
                    search_dirs.append(p)

            seen = set()
            for d in search_dirs:
                if not d.is_dir():
                    continue
                for img_file in d.iterdir():
                    if img_file.suffix.lower() not in img_exts or str(img_file) in seen:
                        continue
                    seen.add(str(img_file))
                    lbl = None
                    for c in [
                        img_file.with_suffix(".txt"),
                        img_file.parent.parent / "labels" / img_file.with_suffix(".txt").name,
                        folder / "labels" / img_file.with_suffix(".txt").name,
                    ]:
                        if c.exists() and c.name != "classes.txt":
                            lbl = c
                            break
                    all_pairs.append((img_file, lbl, ds_idx))

        total = len(all_pairs)
        if total == 0:
            self.error.emit("No images found in any dataset.")
            return

        random.shuffle(all_pairs)
        n_train = int(total * self.train_pct)
        train_pairs, val_pairs = all_pairs[:n_train], all_pairs[n_train:]
        self.progress.emit(f"Merging {total} images → train: {len(train_pairs)}, val: {len(val_pairs)}")

        for split_name, pairs in [("train", train_pairs), ("val", val_pairs)]:
            for i, (img_path, lbl_path, ds_idx) in enumerate(pairs):
                stem = f"ds{ds_idx}_{img_path.stem}"
                shutil.copy2(img_path, img_dir / split_name / (stem + img_path.suffix))
                dest_lbl = lbl_dir / split_name / (stem + ".txt")
                if lbl_path and lbl_path.exists():
                    new_lines = []
                    for line in lbl_path.read_text().splitlines():
                        parts = line.strip().split()
                        if not parts:
                            continue
                        old_id = int(parts[0])
                        if old_id >= len(self.datasets[ds_idx].classes):
                            continue
                        old_name = self.datasets[ds_idx].classes[old_id]
                        mapped = self.class_mapping.get((ds_idx, old_name), old_name)
                        if mapped not in class_id_map:
                            continue
                        new_lines.append(f"{class_id_map[mapped]} {' '.join(parts[1:])}")
                    dest_lbl.write_text("\n".join(new_lines))
                else:
                    dest_lbl.write_text("")
                if i % 50 == 0:
                    self.progress.emit(f"Copying {split_name}: {i+1}/{len(pairs)}…")

        data_yaml_path = out / "data.yaml"
        with open(data_yaml_path, "w") as f:
            yaml.dump({
                "path": str(out.resolve()),
                "train": "images/train",
                "val": "images/val",
                "nc": len(self.unified_classes),
                "names": self.unified_classes,
            }, f, default_flow_style=False, allow_unicode=True)

        self.progress.emit(f"Done — {len(train_pairs)} train, {len(val_pairs)} val images merged.")
        self.finished.emit(str(data_yaml_path))


def _detect_device() -> str:
    """Return a human-readable string describing the training device."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory // (1024 ** 2)
            return f"CUDA  —  {name} ({mem} MB)"
        if torch.backends.mps.is_available():
            return "MPS  —  Apple Silicon GPU"
        return "CPU  —  no GPU detected"
    except Exception:
        return "unknown (torch not available)"


class TrainWorker(QObject):
    log = pyqtSignal(str)
    epoch_progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model_path, data_yaml, epochs, batch, imgsz, output_dir, run_name):
        super().__init__()
        self.model_path = model_path
        self.data_yaml = data_yaml
        self.epochs = epochs
        self.batch = batch
        self.imgsz = imgsz
        self.output_dir = output_dir
        self.run_name = run_name
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            from ultralytics import YOLO
        except ImportError:
            self.error.emit("ultralytics not installed.\n\nRun:  pip install ultralytics")
            return

        self.log.emit(f"Model  : {self.model_path}")
        self.log.emit(f"Dataset: {self.data_yaml}")
        self.log.emit(f"Config : {self.epochs} epochs  batch={self.batch}  imgsz={self.imgsz}")
        self.log.emit(f"Device : {_detect_device()}")
        self.log.emit("─" * 52)

        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.error.emit(f"Failed to load model:\n{e}")
            return

        total = self.epochs
        worker_ref = self

        def on_epoch_end(trainer):
            ep = trainer.epoch + 1
            m = trainer.metrics or {}
            try:
                bl = trainer.loss_items[0].item()
                cl = trainer.loss_items[1].item() if len(trainer.loss_items) > 1 else 0
            except Exception:
                bl = cl = 0
            map50    = m.get("metrics/mAP50(B)", 0)
            map5095  = m.get("metrics/mAP50-95(B)", 0)
            worker_ref.log.emit(
                f"[{ep:>3}/{total}]  box={bl:.4f}  cls={cl:.4f}  "
                f"mAP50={map50:.4f}  mAP50-95={map5095:.4f}"
            )
            worker_ref.epoch_progress.emit(ep, total)
            if worker_ref._stop_requested:
                trainer.stop = True

        model.add_callback("on_train_epoch_end", on_epoch_end)
        model.add_callback("on_train_start", lambda t: worker_ref.log.emit("Training started…"))

        try:
            model.train(
                data=self.data_yaml, epochs=self.epochs, batch=self.batch,
                imgsz=self.imgsz, pretrained=True, patience=15,
                project=self.output_dir, name=self.run_name,
                exist_ok=True, verbose=False,
            )
            best = Path(self.output_dir) / self.run_name / "weights" / "best.pt"
            if not best.exists():
                for pt in Path(self.output_dir).rglob("best.pt"):
                    best = pt
                    break
            self.log.emit("─" * 52)
            self.log.emit(f"Complete!  Best weights → {best}")
            self.finished.emit(str(best) if best.exists() else "")
        except Exception as e:
            if self._stop_requested:
                self.log.emit("Stopped by user.")
                self.finished.emit("")
            else:
                import traceback
                self.error.emit(f"{e}\n\n{traceback.format_exc()}")


# ── Class mapping table ───────────────────────────────────────────────────────

class ClassMappingTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        hint = QLabel(
            "If two datasets use different names for the same object "
            "(e.g. \"car\" vs \"vehicle\"), type the same name in the Merge As column."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Dataset", "Original class", "Merge as", "Labels"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 70)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(self._table.styleSheet() + f"""
            QTableWidget {{ alternate-background-color: {CARD2}; }}
        """)
        layout.addWidget(self._table)

    def populate(self, datasets: list[DatasetEntry]):
        self._table.setRowCount(0)
        self._datasets = datasets
        for ds_idx, ds in enumerate(datasets):
            for cls_name in ds.classes:
                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setRowHeight(row, 36)

                ds_item = QTableWidgetItem(ds.name)
                ds_item.setForeground(QColor(TEXT_MUTED))
                self._table.setItem(row, 0, ds_item)

                orig_item = QTableWidgetItem(cls_name)
                orig_item.setForeground(QColor(TEXT))
                orig_item.setData(Qt.ItemDataRole.UserRole, (ds_idx, cls_name))
                self._table.setItem(row, 1, orig_item)

                edit = QLineEdit(cls_name)
                edit.setStyleSheet(f"""
                    QLineEdit {{
                        background-color: {ACCENT_DIM};
                        color: {ACCENT_LT};
                        border: 1px solid #4c2a8a;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 12px;
                        font-weight: bold;
                    }}
                    QLineEdit:focus {{ border-color: {ACCENT}; }}
                """)
                self._table.setCellWidget(row, 2, edit)

                count_item = QTableWidgetItem(str(ds.label_count))
                count_item.setForeground(QColor(TEXT_MUTED))
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 3, count_item)

    def get_mapping(self) -> tuple[dict, list[str]]:
        mapping, unified = {}, set()
        for row in range(self._table.rowCount()):
            orig_item = self._table.item(row, 1)
            if not orig_item:
                continue
            key = orig_item.data(Qt.ItemDataRole.UserRole)
            widget = self._table.cellWidget(row, 2)
            new_name = widget.text().strip() if widget else ""
            if not new_name:
                new_name = key[1]
            mapping[key] = new_name
            unified.add(new_name)
        return mapping, sorted(unified)


# ── Dataset card ──────────────────────────────────────────────────────────────

class DatasetCard(QWidget):
    remove_requested = pyqtSignal(object)  # emits self

    def __init__(self, entry: DatasetEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setStyleSheet(f"""
            QWidget#card {{
                background-color: {CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        self.setObjectName("card")
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Status dot
        dot = QLabel("●")
        color = GREEN if not self.entry.error else AMBER
        dot.setStyleSheet(f"color: {color}; font-size: 14px; background: transparent; border: none;")
        layout.addWidget(dot)

        # Info block
        info = QVBoxLayout()
        info.setSpacing(2)

        name_lbl = QLabel(self.entry.name)
        name_lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        info.addWidget(name_lbl)

        path_lbl = QLabel(self.entry.folder)
        path_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        path_lbl.setWordWrap(False)
        info.addWidget(path_lbl)

        layout.addLayout(info, stretch=1)

        # Stats chips
        for label, value in [
            ("images", str(self.entry.image_count)),
            ("labels", str(self.entry.label_count)),
            ("classes", str(len(self.entry.classes))),
        ]:
            chip = self._chip(value, label)
            layout.addWidget(chip)

        # Remove button
        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(28, 28)
        rm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 14px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {RED_DIM};
                color: #fca5a5;
                border-color: #991b1b;
            }}
        """)
        rm_btn.setToolTip("Remove dataset")
        rm_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(rm_btn)

    def _chip(self, value: str, label: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"""
            QWidget {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        h = QVBoxLayout(w)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(0)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"color: {ACCENT_LT}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_lbl = QLabel(label)
        lbl_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        lbl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(val_lbl)
        h.addWidget(lbl_lbl)
        return w


# ── Pill tab bar replacement ──────────────────────────────────────────────────

class PillTabBar(QWidget):
    tab_changed = pyqtSignal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._btns: list[QPushButton] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        bg = QWidget()
        bg.setStyleSheet(f"""
            QWidget {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        bg_layout = QHBoxLayout(bg)
        bg_layout.setContentsMargins(4, 4, 4, 4)
        bg_layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {TEXT_MUTED};
                    border: none;
                    border-radius: 7px;
                    padding: 8px 22px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:checked {{
                    background-color: {ACCENT};
                    color: white;
                }}
                QPushButton:hover:!checked {{
                    background-color: {CARD2};
                    color: {TEXT};
                }}
            """)
            self._group.addButton(btn, i)
            bg_layout.addWidget(btn)
            self._btns.append(btn)

        self._group.idClicked.connect(self.tab_changed)
        layout.addWidget(bg)
        layout.addStretch()

    def set_tab(self, idx: int):
        if 0 <= idx < len(self._btns):
            self._btns[idx].setChecked(True)


# ── Datasets page ─────────────────────────────────────────────────────────────

class DatasetsPage(QWidget):
    datasets_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._datasets: list[DatasetEntry] = []
        self._cards: list[DatasetCard] = []
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setObjectName("scroll_content")
        content.setStyleSheet("background: transparent; border: none;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 6, 0)
        self._content_layout.setSpacing(16)

        # ── Section: datasets ─────────────────────────────────────────────────
        ds_header = QHBoxLayout()
        ds_lbl = _section_label("Datasets")
        ds_header.addWidget(ds_lbl)
        ds_header.addStretch()
        add_btn = _primary_btn("+ Add Dataset")
        add_btn.setStyleSheet(add_btn.styleSheet() + "padding: 7px 18px; font-size: 12px;")
        add_btn.clicked.connect(self._add_dataset)
        ds_header.addWidget(add_btn)
        self._content_layout.addLayout(ds_header)

        hint = QLabel(
            "Add exported YOLO dataset folders from any project. "
            "Each folder should contain images/ and labels/ subfolders."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        self._content_layout.addWidget(hint)

        # Cards container
        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: transparent; border: none;")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)

        # Empty state
        self._empty_lbl = QLabel("No datasets added yet.\nClick '+ Add Dataset' to get started.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: 12px;
            background-color: {SURFACE};
            border: 1px dashed {BORDER2};
            border-radius: 10px;
            padding: 30px;
        """)
        self._cards_layout.addWidget(self._empty_lbl)
        self._content_layout.addWidget(self._cards_widget)

        # Summary bar
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        self._content_layout.addWidget(self._summary_lbl)

        self._content_layout.addWidget(_divider())

        # ── Section: class mapping ────────────────────────────────────────────
        self._content_layout.addWidget(_section_label("Class Mapping"))

        self._mapping = ClassMappingTable()
        self._content_layout.addWidget(self._mapping)

        self._content_layout.addWidget(_divider())

        # ── Section: split ────────────────────────────────────────────────────
        self._content_layout.addWidget(_section_label("Train / Val Split"))

        split_card = _card(8)
        split_layout = QHBoxLayout(split_card)
        split_layout.setContentsMargins(16, 12, 16, 12)
        split_layout.setSpacing(20)

        for label, attr, default in [("Train", "_train_spin", 80), ("Val", "_val_spin", 20)]:
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent; border: none;")
            spin = QSpinBox()
            spin.setRange(5, 95)
            spin.setValue(default)
            spin.setSuffix("%")
            spin.setFixedWidth(90)
            setattr(self, attr, spin)
            col.addWidget(lbl)
            col.addWidget(spin)
            split_layout.addLayout(col)

        split_layout.addStretch()

        split_hint = QLabel("Images will be randomly split across train and val sets.")
        split_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        split_hint.setWordWrap(True)
        split_layout.addWidget(split_hint, stretch=1)

        self._content_layout.addWidget(split_card)
        self._content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _add_dataset(self):
        folder = QFileDialog.getExistingDirectory(self, "Select YOLO Dataset Folder")
        if not folder:
            return
        for ds in self._datasets:
            if ds.folder == folder:
                QMessageBox.information(self, "Already Added", "This folder is already in the list.")
                return
        entry = DatasetEntry(folder)
        if entry.error and entry.image_count == 0:
            QMessageBox.warning(self, "Dataset Error",
                                f"Could not load dataset:\n{folder}\n\n{entry.error}")
            return
        self._datasets.append(entry)
        self._add_card(entry)
        self._mapping.populate(self._datasets)
        self._refresh_summary()
        self.datasets_changed.emit()

    def _add_card(self, entry: DatasetEntry):
        self._empty_lbl.setVisible(False)
        card = DatasetCard(entry)
        card.remove_requested.connect(self._remove_card)
        self._cards_layout.addWidget(card)
        self._cards.append(card)

    def _remove_card(self, card: DatasetCard):
        self._datasets.remove(card.entry)
        self._cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        if not self._datasets:
            self._empty_lbl.setVisible(True)
        self._mapping.populate(self._datasets)
        self._refresh_summary()
        self.datasets_changed.emit()

    def _refresh_summary(self):
        n = len(self._datasets)
        if n == 0:
            self._summary_lbl.setText("")
            return
        total_img = sum(d.image_count for d in self._datasets)
        total_lbl = sum(d.label_count for d in self._datasets)
        self._summary_lbl.setText(
            f"{n} dataset{'s' if n > 1 else ''}  ·  {total_img} images  ·  {total_lbl} labeled"
        )

    def get_datasets(self):
        return self._datasets

    def get_split(self):
        t = self._train_spin.value() / 100
        return t, 1.0 - t

    def get_class_mapping(self):
        return self._mapping.get_mapping()


# ── Training config page ──────────────────────────────────────────────────────

class TrainingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(16)

        # ── Model ─────────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Model"))

        model_card = _card(8)
        model_inner = QVBoxLayout(model_card)
        model_inner.setContentsMargins(16, 14, 16, 14)
        model_inner.setSpacing(10)

        self._model_combo = QComboBox()
        self._model_combo.addItem("YOLO26n  —  Nano (fastest, less accurate)", "yolo26n.pt")
        self._model_combo.addItem("YOLO26s  —  Small (good balance)", "yolo26s.pt")
        self._model_combo.addItem("YOLO26m  —  Medium", "yolo26m.pt")
        self._model_combo.addItem("YOLO26l  —  Large", "yolo26l.pt")
        self._model_combo.addItem("YOLO26x  —  XLarge (most accurate, slowest)", "yolo26x.pt")
        self._model_combo.addItem("Custom .pt file…", "__custom__")
        self._model_combo.setCurrentIndex(1)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_inner.addWidget(self._model_combo)

        custom_row = QHBoxLayout()
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("Path to custom .pt weights file…")
        self._custom_edit.setReadOnly(True)
        custom_row.addWidget(self._custom_edit)
        self._browse_model_btn = _small_btn("Browse…")
        self._browse_model_btn.clicked.connect(self._browse_model)
        custom_row.addWidget(self._browse_model_btn)
        model_inner.addLayout(custom_row)
        self._custom_edit.setVisible(False)
        self._browse_model_btn.setVisible(False)

        layout.addWidget(model_card)

        # ── Hyperparameters ────────────────────────────────────────────────────
        layout.addWidget(_section_label("Hyperparameters"))

        hp_card = _card(8)
        hp_inner = QVBoxLayout(hp_card)
        hp_inner.setContentsMargins(16, 14, 16, 14)
        hp_inner.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        for label, attr, lo, hi, val, suffix in [
            ("Epochs", "_epochs_spin", 1, 500, 50, ""),
            ("Batch size", "_batch_spin", 1, 64, 8, ""),
        ]:
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(_field_label(label))
            spin = QSpinBox()
            spin.setRange(lo, hi)
            spin.setValue(val)
            if suffix:
                spin.setSuffix(suffix)
            setattr(self, attr, spin)
            col.addWidget(spin)
            row1.addLayout(col)

        col_sz = QVBoxLayout()
        col_sz.setSpacing(4)
        col_sz.addWidget(_field_label("Image size"))
        self._imgsz_combo = QComboBox()
        for sz in [320, 416, 512, 640, 768, 1024]:
            self._imgsz_combo.addItem(str(sz) + " px", sz)
        self._imgsz_combo.setCurrentIndex(2)
        col_sz.addWidget(self._imgsz_combo)
        row1.addLayout(col_sz)
        row1.addStretch()
        hp_inner.addLayout(row1)

        layout.addWidget(hp_card)

        # ── Device indicator ──────────────────────────────────────────────────
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_icon = QLabel("Device:")
        dev_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        dev_row.addWidget(dev_icon)
        self._device_lbl = QLabel(_detect_device())
        self._device_lbl.setStyleSheet(
            f"color: {GREEN}; font-size: 11px; font-weight: bold; "
            f"background: #0f2318; border: 1px solid #166534; "
            f"border-radius: 4px; padding: 2px 8px;"
        )
        dev_row.addWidget(self._device_lbl)
        dev_row.addStretch()
        layout.addLayout(dev_row)

        # ── Output ────────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Output"))

        out_card = _card(8)
        out_inner = QVBoxLayout(out_card)
        out_inner.setContentsMargins(16, 14, 16, 14)
        out_inner.setSpacing(10)

        row_name = QHBoxLayout()
        row_name.setSpacing(12)
        col_name = QVBoxLayout()
        col_name.setSpacing(4)
        col_name.addWidget(_field_label("Run name"))
        self._run_name_edit = QLineEdit("my_training")
        col_name.addWidget(self._run_name_edit)
        row_name.addLayout(col_name, stretch=1)
        out_inner.addLayout(row_name)

        col_dir = QVBoxLayout()
        col_dir.setSpacing(4)
        col_dir.addWidget(_field_label("Output folder (weights saved here)"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setPlaceholderText("Select output folder…")
        self._out_dir_edit.setReadOnly(True)
        dir_row.addWidget(self._out_dir_edit)
        browse_btn = _small_btn("Browse…")
        browse_btn.clicked.connect(self._browse_output)
        dir_row.addWidget(browse_btn)
        col_dir.addLayout(dir_row)
        out_inner.addLayout(col_dir)

        layout.addWidget(out_card)
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _on_model_changed(self, idx: int):
        is_custom = self._model_combo.currentData() == "__custom__"
        self._custom_edit.setVisible(is_custom)
        self._browse_model_btn.setVisible(is_custom)

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Weights", "", "PyTorch (*.pt)")
        if path:
            self._custom_edit.setText(path)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._out_dir_edit.setText(folder)

    def get_config(self) -> dict:
        data = self._model_combo.currentData()
        return {
            "model_path": self._custom_edit.text().strip() if data == "__custom__" else data,
            "epochs": self._epochs_spin.value(),
            "batch": self._batch_spin.value(),
            "imgsz": self._imgsz_combo.currentData(),
            "run_name": self._run_name_edit.text().strip() or "my_training",
            "output_dir": self._out_dir_edit.text().strip(),
        }

    def validate(self) -> Optional[str]:
        cfg = self.get_config()
        if not cfg["model_path"]:
            return "Please select a model."
        if not cfg["output_dir"]:
            return "Please select an output folder."
        return None


# ── Main dialog ───────────────────────────────────────────────────────────────

class TrainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Train YOLO Model")
        self.setStyleSheet(DIALOG_STYLE)
        self.setMinimumSize(780, 720)
        self.resize(840, 780)

        self._merge_thread: Optional[QThread] = None
        self._train_thread: Optional[QThread] = None
        self._train_worker: Optional[TrainWorker] = None

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header banner ─────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a0533,
                    stop:0.5 #1e1040,
                    stop:1 #0d0d1a
                );
                border-bottom: 1px solid {BORDER};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        icon_lbl = QLabel("▶")
        icon_lbl.setStyleSheet(f"color: {ACCENT_LT}; font-size: 22px; background: transparent; border: none;")
        h_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("Train YOLO Model")
        title_lbl.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        sub_lbl = QLabel("Combine multiple labeled datasets and train in one click")
        sub_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        h_layout.addLayout(title_col, stretch=1)

        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background-color: {BG};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 0)
        body_layout.setSpacing(16)

        # Pill tabs
        self._tab_bar = PillTabBar(["  Datasets  ", "  Training Config  "])
        self._tab_bar.tab_changed.connect(self._switch_tab)
        body_layout.addWidget(self._tab_bar)

        # Page stack
        self._stack = QWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")
        self._stack_layout = QVBoxLayout(self._stack)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)
        self._stack_layout.setSpacing(0)

        self._ds_page = DatasetsPage()
        self._train_page = TrainingPage()
        self._stack_layout.addWidget(self._ds_page)
        self._stack_layout.addWidget(self._train_page)
        self._train_page.setVisible(False)

        body_layout.addWidget(self._stack, stretch=1)
        root.addWidget(body, stretch=1)

        # ── Status + log panel ────────────────────────────────────────────────
        log_panel = QWidget()
        log_panel.setStyleSheet(f"""
            QWidget {{
                background-color: {SURFACE};
                border-top: 1px solid {BORDER};
            }}
        """)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(24, 14, 24, 0)
        log_layout.setSpacing(8)

        status_row = QHBoxLayout()
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent; border: none;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()

        self._epoch_lbl = QLabel("")
        self._epoch_lbl.setStyleSheet(f"color: {ACCENT_LT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        status_row.addWidget(self._epoch_lbl)
        log_layout.addLayout(status_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(PROGRESS_STYLE)
        self._progress.setVisible(False)
        log_layout.addWidget(self._progress)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFixedHeight(120)
        self._log_edit.setPlaceholderText("Training output will appear here…")
        log_layout.addWidget(self._log_edit)

        root.addWidget(log_panel)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(64)
        footer.setStyleSheet(f"""
            QWidget {{
                background-color: {SURFACE};
                border-top: 1px solid {BORDER};
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 0)
        footer_layout.setSpacing(10)

        self._close_btn = _ghost_btn("Close")
        self._close_btn.clicked.connect(self._safe_close)
        footer_layout.addWidget(self._close_btn)

        footer_layout.addStretch()

        self._stop_btn = _danger_btn("Stop Training")
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._stop_training)
        footer_layout.addWidget(self._stop_btn)

        self._action_btn = _primary_btn("⚡  Merge & Start Training")
        self._action_btn.setMinimumWidth(220)
        self._action_btn.clicked.connect(self._start)
        footer_layout.addWidget(self._action_btn)

        root.addWidget(footer)

    def _switch_tab(self, idx: int):
        self._ds_page.setVisible(idx == 0)
        self._train_page.setVisible(idx == 1)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start(self):
        datasets = self._ds_page.get_datasets()
        if not datasets:
            QMessageBox.warning(self, "No Datasets",
                                "Add at least one dataset in the Datasets tab.")
            self._tab_bar.set_tab(0)
            self._switch_tab(0)
            return

        err = self._train_page.validate()
        if err:
            QMessageBox.warning(self, "Config Incomplete", err)
            self._tab_bar.set_tab(1)
            self._switch_tab(1)
            return

        cfg = self._train_page.get_config()

        merge_dir = QFileDialog.getExistingDirectory(
            self, "Select Folder for Merged Dataset"
        )
        if not merge_dir:
            return

        self._action_btn.setEnabled(False)
        self._action_btn.setText("Working…")
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._set_status("Merging datasets…")
        self._log_edit.clear()

        mapping, unified = self._ds_page.get_class_mapping()
        train_pct, val_pct = self._ds_page.get_split()

        self._merge_worker = MergeWorker(datasets, mapping, unified, merge_dir, train_pct, val_pct)
        self._merge_thread = QThread()
        self._merge_worker.moveToThread(self._merge_thread)
        self._merge_thread.started.connect(self._merge_worker.run)
        self._merge_worker.progress.connect(self._set_status)
        self._merge_worker.finished.connect(lambda p: self._on_merge_done(p, cfg))
        self._merge_worker.error.connect(self._on_merge_error)
        self._merge_thread.start()

    def _on_merge_done(self, yaml_path: str, cfg: dict):
        self._merge_thread.quit()
        self._merge_thread.wait()
        self._set_status(f"Merged → {yaml_path}")
        self._log_append(f"Dataset merged: {yaml_path}")
        self._log_append("Starting training…\n")
        self._start_training(yaml_path, cfg)

    def _on_merge_error(self, err: str):
        self._merge_thread.quit()
        self._merge_thread.wait()
        self._progress.setVisible(False)
        self._action_btn.setEnabled(True)
        self._action_btn.setText("⚡  Merge & Start Training")
        self._set_status("Merge failed.")
        QMessageBox.critical(self, "Merge Error", f"Failed to merge datasets:\n\n{err}")

    def _start_training(self, data_yaml: str, cfg: dict):
        self._progress.setRange(0, cfg["epochs"])
        self._progress.setValue(0)
        self._stop_btn.setVisible(True)

        self._train_worker = TrainWorker(
            cfg["model_path"], data_yaml, cfg["epochs"],
            cfg["batch"], cfg["imgsz"], cfg["output_dir"], cfg["run_name"],
        )
        self._train_thread = QThread()
        self._train_worker.moveToThread(self._train_thread)
        self._train_thread.started.connect(self._train_worker.run)
        self._train_worker.log.connect(self._log_append)
        self._train_worker.epoch_progress.connect(self._on_epoch)
        self._train_worker.finished.connect(self._on_train_done)
        self._train_worker.error.connect(self._on_train_error)
        self._train_thread.start()

    def _on_epoch(self, current: int, total: int):
        self._progress.setRange(0, total)
        self._progress.setValue(current)
        self._epoch_lbl.setText(f"Epoch {current} / {total}")
        self._set_status(f"Training — epoch {current}/{total}")

    def _on_train_done(self, best_path: str):
        self._train_thread.quit()
        self._train_thread.wait()
        self._stop_btn.setVisible(False)
        self._action_btn.setEnabled(True)
        self._action_btn.setText("⚡  Merge & Start Training")
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._epoch_lbl.setText("Complete")
        self._set_status("Training finished!")
        if best_path:
            QMessageBox.information(
                self, "Training Complete",
                f"Training complete!\n\nBest weights saved to:\n{best_path}"
            )

    def _on_train_error(self, err: str):
        self._train_thread.quit()
        self._train_thread.wait()
        self._stop_btn.setVisible(False)
        self._action_btn.setEnabled(True)
        self._action_btn.setText("⚡  Merge & Start Training")
        self._set_status("Training failed.")
        QMessageBox.critical(self, "Training Error", f"Training failed:\n\n{err}")

    def _stop_training(self):
        if self._train_worker:
            self._train_worker.stop()
            self._stop_btn.setEnabled(False)
            self._log_append("\nStop requested — finishing current epoch…")

    def _set_status(self, text: str):
        self._status_lbl.setText(text)

    def _log_append(self, text: str):
        self._log_edit.append(text)
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _safe_close(self):
        if self._train_thread and self._train_thread.isRunning():
            reply = QMessageBox.question(
                self, "Training in Progress",
                "Training is still running. Stop it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._stop_training()
            self._train_thread.quit()
            self._train_thread.wait(3000)
        self.accept()

    def closeEvent(self, event):
        if self._train_thread and self._train_thread.isRunning():
            event.ignore()
            self._safe_close()
        else:
            event.accept()
