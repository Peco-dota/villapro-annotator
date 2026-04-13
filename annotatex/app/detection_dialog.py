"""Detection Service Manager dialog for VisionQ."""
from __future__ import annotations

import webbrowser

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDoubleSpinBox, QFileDialog, QFormLayout, QWidget,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QCheckBox,
    QTextEdit, QMenu, QGroupBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QAction

from app.detection_service import (
    get_registry, ServiceConfig,
    STATE_STOPPED, STATE_LOADING, STATE_RUNNING, STATE_ERROR,
)
from app.result_receiver import get_receiver

# ── Shared styles ──────────────────────────────────────────────────────────────

_BASE = """
    QDialog, QWidget {
        background-color: #1a1a2e;
        color: #e2e8f0;
    }
    QLabel { color: #94a3b8; font-size: 12px; }
    QLineEdit, QSpinBox, QDoubleSpinBox {
        background-color: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #7c3aed; }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
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
    QGroupBox {
        color: #64748b;
        font-size: 11px;
        font-weight: bold;
        border: 1px solid #1e293b;
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 6px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        left: 10px;
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
        self.setMinimumWidth(480)
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

        layout.addLayout(form)

        # ── Input source group ─────────────────────────────────────────────────
        input_group = QGroupBox("Input Source")
        input_group.setStyleSheet(_BASE)
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)
        input_layout.setContentsMargins(10, 14, 10, 10)

        self._rtsp_chk = QCheckBox("Use RTSP camera stream (instead of HTTP endpoint)")
        self._rtsp_chk.setChecked(cfg.rtsp_enabled if cfg else False)
        self._rtsp_chk.toggled.connect(self._on_rtsp_toggled)
        input_layout.addWidget(self._rtsp_chk)

        # HTTP section
        self._http_widget = QWidget()
        self._http_widget.setStyleSheet("background: transparent;")
        http_form = QFormLayout(self._http_widget)
        http_form.setSpacing(8)
        http_form.setContentsMargins(0, 4, 0, 0)
        http_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._in_host = QLineEdit(cfg.input_host if cfg else "0.0.0.0")
        http_form.addRow("Listen host:", self._in_host)
        self._in_port = QSpinBox()
        self._in_port.setRange(1024, 65535)
        self._in_port.setValue(cfg.input_port if cfg else 5050)
        http_form.addRow("Listen port:", self._in_port)

        input_layout.addWidget(self._http_widget)

        # RTSP section
        self._rtsp_widget = QWidget()
        self._rtsp_widget.setStyleSheet("background: transparent;")
        rtsp_form = QFormLayout(self._rtsp_widget)
        rtsp_form.setSpacing(8)
        rtsp_form.setContentsMargins(0, 4, 0, 0)
        rtsp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._rtsp_user = QLineEdit(cfg.rtsp_user if cfg else "admin")
        self._rtsp_user.setPlaceholderText("Camera username")
        rtsp_form.addRow("Username:", self._rtsp_user)

        self._rtsp_pass = QLineEdit(cfg.rtsp_password if cfg else "")
        self._rtsp_pass.setPlaceholderText("Camera password")
        self._rtsp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        rtsp_form.addRow("Password:", self._rtsp_pass)

        self._rtsp_ip = QLineEdit(cfg.rtsp_ip if cfg else "192.168.1.1")
        self._rtsp_ip.setPlaceholderText("e.g. 192.168.78.7")
        rtsp_form.addRow("Camera IP:", self._rtsp_ip)

        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(cfg.rtsp_port if cfg else 554)
        rtsp_form.addRow("RTSP port:", self._rtsp_port)

        self._rtsp_channel = QLineEdit(cfg.rtsp_channel if cfg else "Streaming/Channels/102")
        self._rtsp_channel.setPlaceholderText("e.g. Streaming/Channels/102")
        rtsp_form.addRow("Channel path:", self._rtsp_channel)

        self._rtsp_interval = QDoubleSpinBox()
        self._rtsp_interval.setRange(0.05, 10.0)
        self._rtsp_interval.setSingleStep(0.05)
        self._rtsp_interval.setDecimals(2)
        self._rtsp_interval.setSuffix(" s")
        self._rtsp_interval.setValue(cfg.rtsp_interval if cfg else 0.25)
        rtsp_form.addRow("Frame interval:", self._rtsp_interval)

        # URL preview
        self._url_preview = QLabel()
        self._url_preview.setStyleSheet(
            "color: #475569; font-size: 10px; font-family: monospace; "
            "background: #0a0f1e; border-radius: 4px; padding: 4px 6px;"
        )
        self._url_preview.setWordWrap(True)
        rtsp_form.addRow("Stream URL:", self._url_preview)

        # Update preview on any RTSP field change
        for widget in (self._rtsp_user, self._rtsp_pass, self._rtsp_ip, self._rtsp_channel):
            widget.textChanged.connect(self._update_url_preview)
        self._rtsp_port.valueChanged.connect(self._update_url_preview)

        input_layout.addWidget(self._rtsp_widget)
        layout.addWidget(input_group)

        # ── Output group ───────────────────────────────────────────────────────
        output_group = QGroupBox("Result Output")
        output_group.setStyleSheet(_BASE)
        out_form = QFormLayout(output_group)
        out_form.setSpacing(8)
        out_form.setContentsMargins(10, 14, 10, 10)
        out_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        hint = QLabel("Detection results (JSON) are pushed via HTTP POST to:")
        hint.setStyleSheet("color: #475569; font-size: 11px;")
        out_form.addRow("", hint)

        self._out_host = QLineEdit(cfg.output_host if cfg else "127.0.0.1")
        out_form.addRow("Output host:", self._out_host)
        self._out_port = QSpinBox()
        self._out_port.setRange(1, 65535)
        self._out_port.setValue(cfg.output_port if cfg else 6060)
        out_form.addRow("Output port:", self._out_port)

        layout.addWidget(output_group)

        # ── Detection settings group ───────────────────────────────────────────
        det_group = QGroupBox("Detection Settings")
        det_group.setStyleSheet(_BASE)
        det_form = QFormLayout(det_group)
        det_form.setSpacing(8)
        det_form.setContentsMargins(10, 14, 10, 10)
        det_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._conf_threshold = QDoubleSpinBox()
        self._conf_threshold.setRange(0.01, 1.0)
        self._conf_threshold.setSingleStep(0.05)
        self._conf_threshold.setDecimals(2)
        self._conf_threshold.setValue(cfg.conf_threshold if cfg else 0.5)
        det_form.addRow("Confidence threshold:", self._conf_threshold)

        self._report_only_with_direction = QCheckBox(
            "Report only when car detected with known direction"
        )
        self._report_only_with_direction.setChecked(
            cfg.report_only_with_direction if cfg else False
        )
        det_form.addRow("", self._report_only_with_direction)

        self._save_frames = QCheckBox("Save frames locally")
        self._save_frames.setChecked(cfg.save_frames if cfg else True)
        self._save_frames.toggled.connect(self._on_save_frames_toggled)
        det_form.addRow("", self._save_frames)

        frames_dir_row = QHBoxLayout()
        from app.detection_service import _FRAMES_DIR
        self._frames_dir = QLineEdit(cfg.frames_dir if cfg else _FRAMES_DIR)
        self._frames_dir.setPlaceholderText("Folder for saved frames")
        frames_dir_row.addWidget(self._frames_dir)
        browse_frames = _btn("Browse", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        browse_frames.setFixedWidth(70)
        browse_frames.clicked.connect(self._browse_frames_dir)
        frames_dir_row.addWidget(browse_frames)
        det_form.addRow("Frames folder:", frames_dir_row)

        self._on_save_frames_toggled(self._save_frames.isChecked())

        layout.addWidget(det_group)

        # Auto-start
        self._auto_start = QCheckBox("Auto-start this service when VisionQ opens")
        self._auto_start.setChecked(cfg.auto_start if cfg else False)
        layout.addWidget(self._auto_start)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = _btn("Cancel", "#1e293b", "#334155", "#94a3b8", border_color="#334155")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = _btn("▶  Save & Start", "#7c3aed", "#6d28d9")
        ok.clicked.connect(self._accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        # Initial state
        self._on_rtsp_toggled(self._rtsp_chk.isChecked())
        self._update_url_preview()

    def _on_rtsp_toggled(self, checked: bool):
        self._http_widget.setVisible(not checked)
        self._rtsp_widget.setVisible(checked)

    def _on_save_frames_toggled(self, checked: bool):
        self._frames_dir.setEnabled(checked)

    def _browse_frames_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Frames Folder", self._frames_dir.text()
        )
        if folder:
            self._frames_dir.setText(folder)

    def _update_url_preview(self):
        user = self._rtsp_user.text().strip()
        password = self._rtsp_pass.text()
        ip = self._rtsp_ip.text().strip()
        port = self._rtsp_port.value()
        channel = self._rtsp_channel.text().strip().lstrip("/")
        auth = f"{user}:{password}@" if user else ""
        url = f"rtsp://{auth}{ip}:{port}/{channel}"
        self._url_preview.setText(url)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Weights", "", "YOLO Weights (*.pt)"
        )
        if path:
            self._model.setText(path)

    def _accept(self):
        name = self._name.text().strip()
        model = self._model.text().strip()
        rtsp = self._rtsp_chk.isChecked()

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

        if rtsp:
            if not self._rtsp_ip.text().strip():
                QMessageBox.warning(self, "Validation", "Camera IP address is required.")
                return
            if not self._rtsp_user.text().strip():
                QMessageBox.warning(self, "Validation", "Camera username is required.")
                return

        self._result_cfg = ServiceConfig(
            name=name,
            model_path=model,
            input_host=self._in_host.text().strip() or "0.0.0.0",
            input_port=self._in_port.value(),
            output_host=self._out_host.text().strip() or "127.0.0.1",
            output_port=self._out_port.value(),
            auto_start=self._auto_start.isChecked(),
            rtsp_enabled=rtsp,
            rtsp_user=self._rtsp_user.text().strip(),
            rtsp_password=self._rtsp_pass.text(),
            rtsp_ip=self._rtsp_ip.text().strip(),
            rtsp_port=self._rtsp_port.value(),
            rtsp_channel=self._rtsp_channel.text().strip().lstrip("/"),
            rtsp_interval=self._rtsp_interval.value(),
            conf_threshold=self._conf_threshold.value(),
            report_only_with_direction=self._report_only_with_direction.isChecked(),
            save_frames=self._save_frames.isChecked(),
            frames_dir=self._frames_dir.text().strip(),
        )
        self.accept()

    @property
    def result_config(self) -> ServiceConfig | None:
        return self._result_cfg


# ── Single service row ─────────────────────────────────────────────────────────

class ServiceRow(QFrame):
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
        self._status_lbl.setFixedWidth(72)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._status_lbl)

        self._start_btn = _btn("▶  Start", "#7c3aed", "#6d28d9")
        self._start_btn.setFixedWidth(82)
        self._start_btn.clicked.connect(self._start)
        top.addWidget(self._start_btn)

        self._stop_btn = _btn("■  Stop", "#dc2626", "#b91c1c")
        self._stop_btn.setFixedWidth(76)
        self._stop_btn.clicked.connect(self._stop)
        top.addWidget(self._stop_btn)

        self._more_btn = QPushButton("⋯")
        self._more_btn.setFixedWidth(34)
        self._more_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
                padding: 3px 0;
            }
            QPushButton:hover { background-color: #334155; color: #e2e8f0; }
            QPushButton::menu-indicator { width: 0; }
        """)
        more_menu = QMenu(self._more_btn)
        more_menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item { padding: 7px 18px; border-radius: 4px; font-size: 12px; }
            QMenu::item:selected { background-color: #7c3aed; }
            QMenu::separator { height: 1px; background: #334155; margin: 3px 8px; }
        """)
        self._act_relaunch = more_menu.addAction("↺  Relaunch")
        self._act_relaunch.triggered.connect(self._relaunch)
        self._act_edit = more_menu.addAction("✎  Edit config")
        self._act_edit.triggered.connect(self._edit)
        more_menu.addSeparator()
        self._act_remove = more_menu.addAction("✕  Remove")
        self._act_remove.triggered.connect(self._remove)
        self._more_btn.setMenu(more_menu)
        top.addWidget(self._more_btn)

        outer.addLayout(top)

        # ── Request log (collapsible) ──────────────────────────────────────
        log_toggle_row = QHBoxLayout()
        self._log_toggle = QPushButton("▶  Detection log")
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
        self._log_toggle.setText("▼  Detection log" if checked else "▶  Detection log")
        if checked:
            self._update_log_box()

    def _update_log_box(self):
        svc = self._registry.get_service(self._cfg.name)
        if svc is None:
            return
        entries = svc.get_log_entries()
        if not entries:
            return
        lines = [str(e) for e in reversed(entries)]
        self._log_box.setPlainText("\n".join(lines))
        self._log_box.verticalScrollBar().setValue(0)

    def _update_ports_label(self):
        model_name = self._cfg.model_path.split("/")[-1].split("\\")[-1] if self._cfg.model_path else "no model"
        auto = "  ⟳" if self._cfg.auto_start else ""
        if self._cfg.rtsp_enabled:
            source = f"rtsp://{self._cfg.rtsp_ip}:{self._cfg.rtsp_port}/…"
            self._ports_lbl.setText(
                f"📷 {source}  →  {self._cfg.output_host}:{self._cfg.output_port}"
                f"   [{model_name}]{auto}"
            )
        else:
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
        self._act_relaunch.setEnabled(state != STATE_LOADING)
        self._act_edit.setEnabled(state in (STATE_STOPPED, STATE_ERROR))

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
        self._state_changed.emit()
        if error:
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
        self._refresh()

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

_RECV_HOST = "127.0.0.1"
_RECV_PORT = 6060


class DetectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Service Manager")
        self.setMinimumWidth(860)
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
            "Each service runs YOLO detection and pushes JSON results to the configured output.  "
            "Input can be an HTTP endpoint or a live RTSP camera stream.  "
            "Services marked ⟳ auto-start when VisionQ opens."
        )
        sub.setStyleSheet("color: #475569; font-size: 11px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

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
        col_row.addWidget(_col("SOURCE  →  OUTPUT   [MODEL]"), 1)
        col_row.addWidget(_col("STATUS", 80))
        layout.addWidget(col_hdr)

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

        self._empty_lbl = QLabel(
            "No services configured yet.\nClick  ＋ Add Service  to create one."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #334155; font-size: 13px; line-height: 1.8;")
        layout.addWidget(self._empty_lbl)

        # ── Result receiver bar ────────────────────────────────────────────
        recv_bar = QFrame()
        recv_bar.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)
        recv_layout = QHBoxLayout(recv_bar)
        recv_layout.setContentsMargins(12, 8, 12, 8)
        recv_layout.setSpacing(10)

        recv_icon = QLabel("📡")
        recv_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        recv_layout.addWidget(recv_icon)

        self._recv_status = QLabel(f"Result receiver — http://{_RECV_HOST}:{_RECV_PORT}")
        self._recv_status.setStyleSheet("color: #475569; font-size: 11px; background: transparent; border: none;")
        recv_layout.addWidget(self._recv_status)
        recv_layout.addStretch()

        self._recv_start_btn = _btn("▶  Start receiver", "#064e3b", "#065f46", "#34d399", border_color="#065f46")
        self._recv_start_btn.clicked.connect(self._start_receiver)
        recv_layout.addWidget(self._recv_start_btn)

        self._recv_stop_btn = _btn("■  Stop", "#dc2626", "#b91c1c")
        self._recv_stop_btn.clicked.connect(self._stop_receiver)
        recv_layout.addWidget(self._recv_stop_btn)

        self._recv_open_btn = _btn("🌐  Open in browser", "#1e3a5f", "#1e4a7f", "#60a5fa", border_color="#1e4a7f")
        self._recv_open_btn.clicked.connect(self._open_browser)
        recv_layout.addWidget(self._recv_open_btn)

        layout.addWidget(recv_bar)
        self._refresh_receiver()

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
        alive = []
        for r in self._rows:
            try:
                if r.parent() is not None:
                    alive.append(r)
            except RuntimeError:
                pass
        self._rows = alive
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
        self._rows[-1]._start()

    def _refresh_receiver(self):
        running = get_receiver().is_running
        self._recv_start_btn.setVisible(not running)
        self._recv_stop_btn.setVisible(running)
        self._recv_open_btn.setEnabled(running)
        if running:
            self._recv_status.setText(
                f"Result receiver running — http://{_RECV_HOST}:{_RECV_PORT}"
            )
            self._recv_status.setStyleSheet("color: #4ade80; font-size: 11px; background: transparent; border: none;")
        else:
            self._recv_status.setText(
                f"Result receiver stopped — http://{_RECV_HOST}:{_RECV_PORT}"
            )
            self._recv_status.setStyleSheet("color: #475569; font-size: 11px; background: transparent; border: none;")

    def _start_receiver(self):
        err = get_receiver().start(host=_RECV_HOST, port=_RECV_PORT)
        if err:
            QMessageBox.critical(self, "Result Receiver Error", err)
        else:
            self._refresh_receiver()
            self._open_browser()

    def _stop_receiver(self):
        get_receiver().stop()
        self._refresh_receiver()

    def _open_browser(self):
        webbrowser.open(f"http://{_RECV_HOST}:{_RECV_PORT}")

    def _refresh_all(self):
        self._update_empty()
        for row in self._rows:
            if row.parent() is not None:
                row.refresh()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
