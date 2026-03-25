"""Detection Service Manager dialog for VisionQ."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QFileDialog, QFormLayout, QWidget,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QCheckBox,
    QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject, Q_ARG
from PyQt6.QtGui import QFont

from app.detection_service import (
    get_registry, ServiceConfig,
    STATE_STOPPED, STATE_LOADING, STATE_RUNNING, STATE_ERROR,
)

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
    QCheckBox { color: #94a3b8; font-size: 12px; }
    QCheckBox::indicator {
        width: 14px; height: 14px;
        border: 1px solid #334155;
        border-radius: 3px;
        background: #0f172a;
    }
    QCheckBox::indicator:checked {
        background: #7c3aed;
        border-color: #7c3aed;
    }
    QTextEdit {
        background-color: #0a0f1e;
        color: #4ade80;
        border: 1px solid #1e293b;
        border-radius: 6px;
        font-family: monospace;
        font-size: 10px;
        padding: 4px 6px;
    }
"""

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _btn(label: str, color: str, hover: str, text_color: str = "white",
         border_color: str = "") -> QPushButton:
    b = QPushButton(label)
    border_css = f"border: 1px solid {border_color};" if border_color else "border: none;"
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
        QPushButton:disabled {{ background-color: #1e293b; color: #475569; border: none; }}
    """)
    return b


# ── Config dialog (add / edit / relaunch) ──────────────────────────────────────

class ServiceConfigDialog(QDialog):
    """Popup for entering or editing a service config."""

    def __init__(self, cfg: ServiceConfig | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Service")
        self.setMinimumWidth(440)
        self.setStyleSheet(_BASE)
        self._result_cfg: ServiceConfig | None = None
        self._build_ui(cfg)

    def _build_ui(self, cfg: ServiceConfig | None):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("New Service" if cfg is None else f"Edit — {cfg.name}")
        title.setStyleSheet("color: #a78bfa; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name = QLineEdit(cfg.name if cfg else "")
        self._name.setPlaceholderText("e.g. gate_1_in, gate_2_out…")
        if cfg:
            self._name.setEnabled(False)
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

        # Input
        self._in_host = QLineEdit(cfg.input_host if cfg else "0.0.0.0")
        form.addRow("Listen host:", self._in_host)
        self._in_port = QSpinBox()
        self._in_port.setRange(1024, 65535)
        self._in_port.setValue(cfg.input_port if cfg else 5050)
        form.addRow("Listen port:", self._in_port)

        hint = QLabel("Results are pushed to:")
        hint.setStyleSheet("color: #475569; font-size: 11px; margin-top: 4px;")
        form.addRow("", hint)

        # Output
        self._out_host = QLineEdit(cfg.output_host if cfg else "127.0.0.1")
        form.addRow("Output host:", self._out_host)
        self._out_port = QSpinBox()
        self._out_port.setRange(1, 65535)
        self._out_port.setValue(cfg.output_port if cfg else 6060)
        form.addRow("Output port:", self._out_port)

        # Auto-start
        self._auto_start = QCheckBox("Auto-start this service when VisionQ opens")
        self._auto_start.setChecked(cfg.auto_start if cfg else False)
        form.addRow("", self._auto_start)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = _btn("Cancel", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = _btn("▶  Save & Start", "#7c3aed", "#6d28d9")
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
        import os
        if not os.path.isfile(model):
            QMessageBox.warning(self, "Model Not Found",
                                f"Model file does not exist:\n{model}")
            return
        self._result_cfg = ServiceConfig(
            name=name,
            model_path=model,
            input_host=self._in_host.text().strip() or "0.0.0.0",
            input_port=self._in_port.value(),
            output_host=self._out_host.text().strip() or "127.0.0.1",
            output_port=self._out_port.value(),
            auto_start=self._auto_start.isChecked(),
        )
        self.accept()

    @property
    def result_config(self) -> ServiceConfig | None:
        return self._result_cfg


# ── Single service row ─────────────────────────────────────────────────────────

class ServiceRow(QFrame):
    """One row in the service manager table."""

    # Emitted from background thread via invokeMethod to trigger UI refresh
    _state_changed = pyqtSignal()

    def __init__(self, cfg: ServiceConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._registry = get_registry()
        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._spin)
        self._state_changed.connect(self._refresh)
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
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(6)

        # ── Top row ────────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #475569; font-size: 16px;")
        self._dot.setFixedWidth(20)
        top.addWidget(self._dot)

        name_lbl = QLabel(self._cfg.name)
        name_lbl.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: bold;")
        name_lbl.setFixedWidth(160)
        top.addWidget(name_lbl)

        self._ports_lbl = QLabel()
        self._ports_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        self._ports_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._update_ports_label()
        top.addWidget(self._ports_lbl, stretch=1)

        self._status_lbl = QLabel("Stopped")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self._status_lbl.setFixedWidth(80)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._status_lbl)

        self._start_btn = _btn("▶ Start", "#7c3aed", "#6d28d9")
        self._start_btn.setFixedWidth(80)
        self._start_btn.clicked.connect(self._start)
        top.addWidget(self._start_btn)

        self._stop_btn = _btn("■ Stop", "#dc2626", "#b91c1c")
        self._stop_btn.setFixedWidth(76)
        self._stop_btn.clicked.connect(self._stop)
        top.addWidget(self._stop_btn)

        self._relaunch_btn = _btn("↺ Relaunch", "#1e3a5f", "#1e4a7f", "#93c5fd", border_color="#1e4a7f")
        self._relaunch_btn.setFixedWidth(90)
        self._relaunch_btn.clicked.connect(self._relaunch)
        top.addWidget(self._relaunch_btn)

        self._edit_btn = _btn("✎ Edit", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        self._edit_btn.setFixedWidth(66)
        self._edit_btn.clicked.connect(self._edit)
        top.addWidget(self._edit_btn)

        self._remove_btn = _btn("✕", "#1e293b", "#450a0a", "#dc2626", border_color="#334155")
        self._remove_btn.setFixedWidth(30)
        self._remove_btn.clicked.connect(self._remove)
        top.addWidget(self._remove_btn)

        outer.addLayout(top)

        # ── Request log (collapsible) ──────────────────────────────────────
        log_toggle_row = QHBoxLayout()
        self._log_toggle = QPushButton("▶  Request log")
        self._log_toggle.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #334155; font-size: 10px;
                text-align: left; padding: 0; padding-left: 24px;
            }
            QPushButton:hover { color: #64748b; }
        """)
        self._log_toggle.setCheckable(True)
        self._log_toggle.setChecked(False)
        self._log_toggle.clicked.connect(self._toggle_log)
        log_toggle_row.addWidget(self._log_toggle)
        log_toggle_row.addStretch()
        outer.addLayout(log_toggle_row)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFixedHeight(110)
        self._log_box.setVisible(False)
        outer.addWidget(self._log_box)

    def _toggle_log(self, checked: bool):
        self._log_box.setVisible(checked)
        self._log_toggle.setText("▼  Request log" if checked else "▶  Request log")
        if checked:
            self._update_log_box()

    def _update_log_box(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            return
        entries = svc.get_log_entries()
        if not entries:
            return
        lines = [str(e) for e in reversed(entries)]  # newest first
        self._log_box.setPlainText("\n".join(lines))
        # scroll to top (newest)
        self._log_box.verticalScrollBar().setValue(0)

    def _update_ports_label(self):
        model_name = self._cfg.model_path.split("/")[-1] if self._cfg.model_path else "no model"
        auto = "  ⟳" if self._cfg.auto_start else ""
        self._ports_lbl.setText(
            f":{self._cfg.input_port}  →  {self._cfg.output_host}:{self._cfg.output_port}"
            f"   [{model_name}]{auto}"
        )

    def config(self) -> ServiceConfig:
        return self._cfg

    def refresh(self):
        self._refresh()
        if self._log_box.isVisible():
            self._update_log_box()

    def _refresh(self):
        state = self._registry.get_state(self._cfg.name)

        loading = state == STATE_LOADING
        running = state == STATE_RUNNING
        error   = state == STATE_ERROR

        self._start_btn.setEnabled(state in (STATE_STOPPED, STATE_ERROR))
        self._stop_btn.setEnabled(running or loading)
        self._relaunch_btn.setEnabled(state != STATE_LOADING)
        self._edit_btn.setEnabled(state in (STATE_STOPPED, STATE_ERROR))

        if running:
            self._dot.setStyleSheet("color: #4ade80; font-size: 16px;")
            self._status_lbl.setText("Running")
            self._status_lbl.setStyleSheet("color: #4ade80; font-size: 11px;")
            self._spinner_timer.stop()
        elif loading:
            self._dot.setStyleSheet("color: #fbbf24; font-size: 16px;")
            self._status_lbl.setStyleSheet("color: #fbbf24; font-size: 11px;")
            if not self._spinner_timer.isActive():
                self._spinner_timer.start(80)
        elif error:
            self._dot.setStyleSheet("color: #f87171; font-size: 16px;")
            self._status_lbl.setText("Error")
            self._status_lbl.setStyleSheet("color: #f87171; font-size: 11px;")
            self._spinner_timer.stop()
        else:
            self._dot.setStyleSheet("color: #475569; font-size: 16px;")
            self._status_lbl.setText("Stopped")
            self._status_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
            self._spinner_timer.stop()

    def _spin(self):
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
        self._status_lbl.setText(f"{_SPINNER_FRAMES[self._spinner_idx]} Loading")

    def _on_start_done(self, error: str):
        # Called from background thread — signal the UI thread
        self._state_changed.emit()
        if error:
            # Show error in UI thread via a one-shot timer
            QTimer.singleShot(0, lambda: self._show_start_error(error))

    def _show_start_error(self, error: str):
        svc = self._registry.get_service(self._cfg.name)
        err_detail = error
        if svc and svc.error_msg:
            err_detail = svc.error_msg
        QMessageBox.critical(self.window(), f"Failed to start '{self._cfg.name}'", err_detail)

    def _start(self):
        error = self._registry.start_async(self._cfg.name, self._on_start_done)
        if error:
            QMessageBox.critical(self.window(), "Cannot Start", error)
            return
        self._refresh()  # show loading state immediately

    def _stop(self):
        self._registry.stop(self._cfg.name)
        self._spinner_timer.stop()
        self._refresh()

    def _relaunch(self):
        cfg = self._registry.get_config(self._cfg.name) or self._cfg
        dlg = ServiceConfigDialog(cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()

        error = self._registry.restart_async(new_cfg.name, self._on_start_done)
        if error:
            QMessageBox.critical(self.window(), "Cannot Relaunch", error)
            return
        self._refresh()

    def _edit(self):
        dlg = ServiceConfigDialog(self._cfg, parent=self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_cfg = dlg.result_config
        if new_cfg is None:
            return
        self._registry.upsert_config(new_cfg)
        self._cfg = new_cfg
        self._update_ports_label()

    def _remove(self):
        state = self._registry.get_state(self._cfg.name)
        msg = f"Remove service '{self._cfg.name}'?"
        if state in (STATE_RUNNING, STATE_LOADING):
            msg += "\nIt is currently active and will be stopped."
        reply = QMessageBox.question(
            self.window(), "Remove Service", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._spinner_timer.stop()
        self._registry.remove_config(self._cfg.name)
        self.setParent(None)   # type: ignore
        self.deleteLater()


# ── Main dialog ────────────────────────────────────────────────────────────────

class DetectionDialog(QDialog):
    """Service manager: list, add, start, stop, relaunch, remove services."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Service Manager")
        self.setMinimumWidth(820)
        self.setMinimumHeight(480)
        self.setStyleSheet(_BASE)
        self._rows: list[ServiceRow] = []
        self._build_ui()
        self._load_existing()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
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
            "Each service listens on its own port and includes service_name in every JSON result.  "
            "Services marked ⟳ will auto-start when VisionQ opens."
        )
        sub.setStyleSheet("color: #475569; font-size: 11px;")
        sub.setWordWrap(True)
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
        col_row.addWidget(_col("PORT  →  OUTPUT   [MODEL]"), 1)
        col_row.addWidget(_col("STATUS", 80))
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
        self._empty_lbl = QLabel(
            "No services configured yet.\nClick  ＋ Add Service  to create one."
        )
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
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._update_empty()

    def _update_empty(self):
        self._rows = [r for r in self._rows if r.parent() is not None]
        has_rows = bool(self._rows)
        self._empty_lbl.setVisible(not has_rows)
        self._scroll.setVisible(has_rows)

    def _add_service(self):
        dlg = ServiceConfigDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = dlg.result_config
        if cfg is None:
            return
        existing = [r.config().name for r in self._rows if r.parent() is not None]
        if cfg.name in existing:
            QMessageBox.warning(self, "Duplicate Name",
                                f"A service named '{cfg.name}' already exists.")
            return
        get_registry().upsert_config(cfg)
        self._add_row(cfg)
        # auto-start the new one
        self._rows[-1]._start()

    def _refresh_all(self):
        self._update_empty()
        for row in self._rows:
            if row.parent() is not None:
                row.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
