"""Detection Service Manager dialog for VisionQ."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QFileDialog, QFormLayout, QWidget,
    QScrollArea, QFrame, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from app.detection_service import get_registry, ServiceConfig

# ── Shared styles ──────────────────────────────────────────────────────────────

_BASE = """
    QDialog, QWidget {
        background-color: #1a1a2e;
        color: #e2e8f0;
    }
    QLabel { color: #94a3b8; font-size: 12px; }
    QLineEdit, QSpinBox {
        background-color: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }
    QLineEdit:focus, QSpinBox:focus { border: 1px solid #7c3aed; }
    QSpinBox::up-button, QSpinBox::down-button {
        background-color: #1e293b; border: none; width: 16px;
    }
    QScrollArea { background: transparent; border: none; }
"""

def _btn(label: str, color: str, hover: str, text_color: str = "white",
         border: str = "none", border_color: str = "") -> QPushButton:
    b = QPushButton(label)
    border_css = f"border: 1px solid {border_color};" if border_color else f"border: {border};"
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: {text_color};
            {border_css}
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 5px 12px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:disabled {{ background-color: #1e293b; color: #475569; }}
    """)
    return b


# ── Config dialog (add / edit / relaunch) ──────────────────────────────────────

class ServiceConfigDialog(QDialog):
    """Small popup for entering / editing a service config."""

    def __init__(self, cfg: ServiceConfig | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Service")
        self.setMinimumWidth(420)
        self.setStyleSheet(_BASE)
        self._result_cfg: ServiceConfig | None = None
        self._build_ui(cfg)

    def _build_ui(self, cfg: ServiceConfig | None):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Configure Service" if cfg is None else f"Edit — {cfg.name}")
        title.setStyleSheet("color: #a78bfa; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name = QLineEdit(cfg.name if cfg else "")
        self._name.setPlaceholderText("e.g. gate_1_in, gate_2_out…")
        if cfg:
            self._name.setEnabled(False)  # name is the key, can't rename a running-or-saved svc
        form.addRow("Name:", self._name)

        # Model
        model_row = QHBoxLayout()
        self._model = QLineEdit(cfg.model_path if cfg else "")
        self._model.setPlaceholderText("Path to .pt weights file…")
        browse = _btn("Browse…", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse.setFixedWidth(72)
        browse.clicked.connect(self._browse)
        model_row.addWidget(self._model)
        model_row.addWidget(browse)
        form.addRow("Model:", model_row)

        # Input host/port
        self._in_host = QLineEdit(cfg.input_host if cfg else "0.0.0.0")
        form.addRow("Listen host:", self._in_host)
        self._in_port = QSpinBox()
        self._in_port.setRange(1024, 65535)
        self._in_port.setValue(cfg.input_port if cfg else 5050)
        form.addRow("Listen port:", self._in_port)

        # Divider hint
        hint = QLabel("Results are pushed to:")
        hint.setStyleSheet("color: #475569; font-size: 11px; margin-top: 4px;")
        form.addRow("", hint)

        # Output host/port
        self._out_host = QLineEdit(cfg.output_host if cfg else "127.0.0.1")
        form.addRow("Output host:", self._out_host)
        self._out_port = QSpinBox()
        self._out_port.setRange(1, 65535)
        self._out_port.setValue(cfg.output_port if cfg else 6060)
        form.addRow("Output port:", self._out_port)

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = _btn("Cancel", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        label = "Save & Start" if cfg is None else "Save & Start"
        ok = _btn(f"▶  {label}", "#7c3aed", "#6d28d9")
        ok.clicked.connect(self._accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Weights", "", "YOLO Weights (*.pt)"
        )
        if path:
            self._model.setText(path)

    def _accept(self):
        name = self._name.text().strip()
        model = self._model.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Service name is required.")
            return
        if not model:
            QMessageBox.warning(self, "Validation", "Model path is required.")
            return
        self._result_cfg = ServiceConfig(
            name=name,
            model_path=model,
            input_host=self._in_host.text().strip() or "0.0.0.0",
            input_port=self._in_port.value(),
            output_host=self._out_host.text().strip() or "127.0.0.1",
            output_port=self._out_port.value(),
        )
        self.accept()

    @property
    def result_config(self) -> ServiceConfig | None:
        return self._result_cfg


# ── Single service row ─────────────────────────────────────────────────────────

class ServiceRow(QFrame):
    """One row in the service table representing a single configured service."""

    def __init__(self, cfg: ServiceConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._registry = get_registry()
        self._log_lines: list[str] = []
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        # ── Top row: dot + name + ports summary + buttons ──────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #475569; font-size: 16px;")
        self._dot.setFixedWidth(18)
        top.addWidget(self._dot)

        # Name
        name_lbl = QLabel(self._cfg.name)
        name_lbl.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        name_lbl.setFixedWidth(160)
        top.addWidget(name_lbl)

        # Ports summary
        self._ports_lbl = QLabel()
        self._ports_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        self._ports_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_ports_label()
        top.addWidget(self._ports_lbl, stretch=1)

        # Status text
        self._status_lbl = QLabel("Stopped")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._status_lbl.setFixedWidth(70)
        top.addWidget(self._status_lbl)

        # Buttons
        self._start_btn = _btn("▶ Start", "#7c3aed", "#6d28d9")
        self._start_btn.setFixedWidth(80)
        self._start_btn.clicked.connect(self._start)
        top.addWidget(self._start_btn)

        self._stop_btn = _btn("■ Stop", "#dc2626", "#b91c1c")
        self._stop_btn.setFixedWidth(80)
        self._stop_btn.clicked.connect(self._stop)
        top.addWidget(self._stop_btn)

        self._relaunch_btn = _btn("↺ Relaunch", "#1e3a5f", "#1e4a7f", "#93c5fd", border_color="#1e4a7f")
        self._relaunch_btn.setFixedWidth(90)
        self._relaunch_btn.clicked.connect(self._relaunch)
        top.addWidget(self._relaunch_btn)

        self._edit_btn = _btn("✎ Edit", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        self._edit_btn.setFixedWidth(70)
        self._edit_btn.clicked.connect(self._edit)
        top.addWidget(self._edit_btn)

        self._remove_btn = _btn("✕", "#1e293b", "#450a0a", "#dc2626", border_color="#334155")
        self._remove_btn.setFixedWidth(32)
        self._remove_btn.clicked.connect(self._remove)
        top.addWidget(self._remove_btn)

        outer.addLayout(top)

        # ── Log line (single line, collapsible) ────────────────────────────
        self._log_lbl = QLabel("")
        self._log_lbl.setStyleSheet("color: #4ade80; font-size: 10px; font-family: monospace; padding-left: 28px;")
        self._log_lbl.setWordWrap(False)
        outer.addWidget(self._log_lbl)

    def _update_ports_label(self):
        self._ports_lbl.setText(
            f":{self._cfg.input_port}  →  {self._cfg.output_host}:{self._cfg.output_port}"
            f"   [{self._cfg.model_path.split('/')[-1]}]"
        )

    def _log(self, msg: str):
        self._log_lines.append(msg)
        self._log_lbl.setText(msg)

    def config(self) -> ServiceConfig:
        return self._cfg

    def update_config(self, cfg: ServiceConfig):
        self._cfg = cfg
        self._update_ports_label()

    def refresh(self):
        self._refresh()

    def _refresh(self):
        running = self._registry.is_running(self._cfg.name)
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._relaunch_btn.setEnabled(True)
        self._edit_btn.setEnabled(not running)

        if running:
            self._dot.setStyleSheet("color: #4ade80; font-size: 16px;")
            self._status_lbl.setText("Running")
            self._status_lbl.setStyleSheet("color: #4ade80; font-size: 11px;")
        else:
            self._dot.setStyleSheet("color: #475569; font-size: 16px;")
            self._status_lbl.setText("Stopped")
            self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")

    def _start(self):
        self._log(f"Loading model and starting on port {self._cfg.input_port}…")
        error = self._registry.start(self._cfg.name)
        if error:
            self._log(f"Error: {error}")
        else:
            self._log(f"Running — POST images to :{self._cfg.input_port}/detect")
        self._refresh()

    def _stop(self):
        self._registry.stop(self._cfg.name)
        self._log("Stopped.")
        self._refresh()

    def _relaunch(self):
        cfg = self._registry.get_config(self._cfg.name)
        dlg = ServiceConfigDialog(cfg or self._cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        # Stop old instance, save new config, start fresh
        self._registry.stop(self._cfg.name)
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()
        self._log(f"Restarting with new config on port {new_cfg.input_port}…")
        error = self._registry.start(new_cfg.name)
        if error:
            self._log(f"Error: {error}")
        else:
            self._log(f"Running — POST images to :{new_cfg.input_port}/detect")
        self._refresh()

    def _edit(self):
        """Edit config while stopped."""
        dlg = ServiceConfigDialog(self._cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()
        self._log("Config saved. Press Start to run.")

    def _remove(self):
        running = self._registry.is_running(self._cfg.name)
        msg = f"Remove service '{self._cfg.name}'?"
        if running:
            msg += "\nIt is currently running and will be stopped."
        reply = QMessageBox.question(
            self.window(), "Remove Service", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._registry.remove_config(self._cfg.name)
        # Signal parent to remove this row
        self.setParent(None)  # type: ignore
        self.deleteLater()


# ── Main dialog ────────────────────────────────────────────────────────────────

class DetectionDialog(QDialog):
    """Service manager: lists all configured services, allows add/start/stop/relaunch/remove."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Service Manager")
        self.setMinimumWidth(780)
        self.setMinimumHeight(460)
        self.setStyleSheet(_BASE)
        self._rows: list[ServiceRow] = []
        self._build_ui()
        self._load_existing()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("⚡  Service Manager")
        title.setStyleSheet("color: #a78bfa; font-size: 16px; font-weight: bold;")
        hdr.addWidget(title)
        hdr.addStretch()

        add_btn = _btn("＋  Add Service", "#064e3b", "#065f46", "#34d399", border_color="#065f46")
        add_btn.clicked.connect(self._add_service)
        hdr.addWidget(add_btn)

        layout.addLayout(hdr)

        sub = QLabel(
            "Each service listens on its own port and includes service_name in every JSON result."
        )
        sub.setStyleSheet("color: #475569; font-size: 11px;")
        layout.addWidget(sub)

        # Column headers
        col_hdr = QWidget()
        col_hdr.setStyleSheet("background: transparent;")
        col_row = QHBoxLayout(col_hdr)
        col_row.setContentsMargins(46, 0, 14, 0)
        col_row.setSpacing(0)

        def _col(text, width=None):
            l = QLabel(text)
            l.setStyleSheet("color: #334155; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
            if width:
                l.setFixedWidth(width)
            return l

        col_row.addWidget(_col("NAME", 160))
        col_row.addWidget(_col("PORTS  →  OUTPUT   [MODEL]"), 1)
        col_row.addWidget(_col("STATUS", 70))
        col_row.addStretch()
        layout.addWidget(col_hdr)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.addStretch()

        self._scroll.setWidget(self._rows_container)
        layout.addWidget(self._scroll, stretch=1)

        # Empty state
        self._empty_lbl = QLabel("No services configured yet.\nClick  ＋ Add Service  to create one.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #334155; font-size: 13px; line-height: 1.8;")
        layout.addWidget(self._empty_lbl)

        # Footer
        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = _btn("Close", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        layout.addLayout(foot)

    def _load_existing(self):
        for cfg in get_registry().get_configs():
            self._add_row(cfg)
        self._update_empty()

    def _add_row(self, cfg: ServiceConfig):
        row = ServiceRow(cfg)
        self._rows.append(row)
        insert_idx = self._rows_layout.count() - 1  # before stretch
        self._rows_layout.insertWidget(insert_idx, row)
        self._update_empty()

    def _update_empty(self):
        # Clean up deleted rows
        self._rows = [r for r in self._rows if r.parent() is not None]
        has_rows = len(self._rows) > 0
        self._empty_lbl.setVisible(not has_rows)
        self._scroll.setVisible(has_rows)

    def _add_service(self):
        dlg = ServiceConfigDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = dlg.result_config
        if cfg is None:
            return
        # Check duplicate name
        existing_names = [r.config().name for r in self._rows if r.parent() is not None]
        if cfg.name in existing_names:
            QMessageBox.warning(self, "Duplicate Name",
                                f"A service named '{cfg.name}' already exists.")
            return
        get_registry().upsert_config(cfg)
        self._add_row(cfg)
        # Auto-start
        row = self._rows[-1]
        row._start()

    def _refresh_all(self):
        self._update_empty()
        for row in self._rows:
            if row.parent() is not None:
                row.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
