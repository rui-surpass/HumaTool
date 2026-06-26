from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import config
from src.gui.ui_state import derive_dashboard_state


class StatusCard(QGroupBox):
    def __init__(self, title, subtitle, parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.label_state = QLabel("Unknown")
        self.label_state.setObjectName("statusValue")
        self.label_detail = QLabel(subtitle)
        self.label_detail.setWordWrap(True)

        layout.addWidget(self.label_state)
        layout.addWidget(self.label_detail)

    def set_status(self, state_text, detail_text):
        self.label_state.setText(state_text)
        self.label_detail.setText(detail_text)


class DashboardWidget(QWidget):
    check_avp_requested = pyqtSignal()
    connect_avp_requested = pyqtSignal()
    disconnect_avp_requested = pyqtSignal()
    retry_avp_requested = pyqtSignal()
    connect_camera_requested = pyqtSignal()
    disconnect_camera_requested = pyqtSignal()
    connect_motor_requested = pyqtSignal()
    disconnect_motor_requested = pyqtSignal()
    start_stream_requested = pyqtSignal()
    stop_stream_requested = pyqtSignal()
    toggle_tracking_requested = pyqtSignal()
    calibrate_requested = pyqtSignal()
    recovery_action_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_cards = {}
        self._stream_action = "start"
        self._tracking_action = "start"
        self._recovery_action = "connect_avp"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout()
        self.setLayout(root)

        self.grp_overview = QGroupBox("System Overview")
        overview_layout = QVBoxLayout()
        self.grp_overview.setLayout(overview_layout)
        self.label_title = QLabel("RobotNeck AVP Dashboard")
        self.label_title.setObjectName("dashboardTitle")
        self.label_badge = QLabel("Idle")
        self.label_badge.setObjectName("dashboardBadge")
        self.label_severity = QLabel("Status Level: Blocked")
        self.label_severity.setObjectName("dashboardSeverity")
        self.label_summary = QLabel("Waiting for manual AVP connection.")
        self.label_summary.setWordWrap(True)
        self.label_next_step = QLabel("Connect AVP first.")
        self.label_next_step.setWordWrap(True)
        overview_layout.addWidget(self.label_title)
        overview_layout.addWidget(self.label_badge)
        overview_layout.addWidget(self.label_severity)
        overview_layout.addWidget(self.label_summary)
        overview_layout.addWidget(self.label_next_step)
        root.addWidget(self.grp_overview)

        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout()
        actions_group.setLayout(actions_layout)

        device_group = QGroupBox("Device Actions")
        device_layout = QHBoxLayout()
        device_group.setLayout(device_layout)
        self.btn_toggle_motor = QPushButton("Connect Motor")
        self.btn_toggle_camera = QPushButton("Connect Camera")
        self.btn_toggle_avp = QPushButton("Connect AVP")
        self.btn_toggle_motor.clicked.connect(self._emit_motor_action)
        self.btn_toggle_camera.clicked.connect(self._emit_camera_action)
        self.btn_toggle_avp.clicked.connect(self._emit_avp_action)
        device_layout.addWidget(self.btn_toggle_motor)
        device_layout.addWidget(self.btn_toggle_camera)
        device_layout.addWidget(self.btn_toggle_avp)
        actions_layout.addWidget(device_group)

        runtime_group = QGroupBox("Runtime Actions")
        runtime_layout = QHBoxLayout()
        runtime_group.setLayout(runtime_layout)
        self.btn_start_stream = QPushButton("Start Stream")
        self.btn_toggle_tracking = QPushButton("Start Tracking")
        self.btn_calibrate = QPushButton("Move To Home And Calibrate")
        self.btn_start_stream.clicked.connect(self._emit_stream_action)
        self.btn_toggle_tracking.clicked.connect(self._emit_tracking_action)
        self.btn_calibrate.clicked.connect(self.calibrate_requested.emit)
        runtime_layout.addWidget(self.btn_start_stream)
        runtime_layout.addWidget(self.btn_toggle_tracking)
        runtime_layout.addWidget(self.btn_calibrate)
        actions_layout.addWidget(runtime_group)
        root.addWidget(actions_group)

        cards_group = QGroupBox("System Status")
        cards_layout = QGridLayout()
        cards_group.setLayout(cards_layout)
        specs = [
            ("avp", "AVP", "Head pose source"),
            ("camera", "Camera", "ZED connection"),
            ("motor", "Motor", "Neck motors"),
            ("stream", "Stream", "VisionPro stream"),
            ("tracking", "Tracking", "Runtime status"),
        ]
        for index, (key, title, subtitle) in enumerate(specs):
            card = StatusCard(title, subtitle)
            cards_layout.addWidget(card, index // 3, index % 3)
            self.status_cards[key] = card
        root.addWidget(cards_group)

        self.grp_guidance = QGroupBox("Recommended Next Step")
        guidance_layout = QVBoxLayout()
        self.grp_guidance.setLayout(guidance_layout)
        self.label_recovery_title = QLabel("AVP not connected")
        self.label_recovery_title.setObjectName("recoveryTitle")
        self.label_recovery_detail = QLabel("Connect AVP first.")
        self.label_recovery_detail.setWordWrap(True)
        self.btn_recovery_action = QPushButton("Connect AVP")
        self.btn_recovery_action.clicked.connect(self._emit_recovery_action)
        guidance_layout.addWidget(self.label_recovery_title)
        guidance_layout.addWidget(self.label_recovery_detail)
        guidance_layout.addWidget(self.btn_recovery_action)
        root.addWidget(self.grp_guidance)

        self.grp_avp = QGroupBox("AVP Details")
        avp_layout = QVBoxLayout()
        self.grp_avp.setLayout(avp_layout)

        self.btn_toggle_avp_details = QPushButton("Show AVP Details")
        self.btn_toggle_avp_details.clicked.connect(self.toggle_avp_details)
        avp_layout.addWidget(self.btn_toggle_avp_details)

        self.avp_details_panel = QWidget()
        avp_details_panel_layout = QVBoxLayout()
        self.avp_details_panel.setLayout(avp_details_panel_layout)
        self.avp_details_panel.setVisible(False)

        avp_settings = QGridLayout()
        avp_settings.addWidget(QLabel("AVP IP"), 0, 0)
        self.input_avp_ip = QLineEdit(getattr(config, "AVP_IP", ""))
        avp_settings.addWidget(self.input_avp_ip, 0, 1)
        self.chk_auto_reconnect = QCheckBox("Auto Reconnect")
        avp_settings.addWidget(self.chk_auto_reconnect, 1, 0, 1, 2)
        avp_details_panel_layout.addLayout(avp_settings)

        avp_buttons = QGridLayout()
        self.btn_retry_avp = QPushButton("Retry AVP")
        self.btn_check_avp = QPushButton("Check AVP")
        self.btn_retry_avp.clicked.connect(self.retry_avp_requested.emit)
        self.btn_check_avp.clicked.connect(self.check_avp_requested.emit)
        avp_buttons.addWidget(self.btn_retry_avp, 0, 0)
        avp_buttons.addWidget(self.btn_check_avp, 0, 1)
        avp_details_panel_layout.addLayout(avp_buttons)

        self.label_avp_runtime = QLabel("State: idle")
        self.label_avp_runtime.setWordWrap(True)
        self.label_avp_detail = QLabel("Manual first connection is required.")
        self.label_avp_detail.setWordWrap(True)
        avp_details_panel_layout.addWidget(self.label_avp_runtime)
        avp_details_panel_layout.addWidget(self.label_avp_detail)
        avp_layout.addWidget(self.avp_details_panel)
        root.addWidget(self.grp_avp)
        root.addStretch()

    def set_avp_settings(self, ip, auto_reconnect):
        self.input_avp_ip.setText(str(ip))
        self.chk_auto_reconnect.setChecked(bool(auto_reconnect))

    def get_avp_settings(self):
        return {
            "ip": self.input_avp_ip.text().strip(),
            "auto_reconnect": self.chk_auto_reconnect.isChecked(),
        }

    def update_avp_runtime(self, runtime, pose_status=None, tracking_runtime=None):
        state = runtime.get("state", "idle")
        ip = runtime.get("ip", "")
        session_mode = runtime.get("session_mode", "tracking_only")
        error = runtime.get("last_error")
        mode_label = "AVP + Stream" if session_mode == "streaming" else "AVP Only"
        self.label_avp_runtime.setText(f"State: {state} | Mode: {mode_label} | IP: {ip}")
        pose_status = dict(pose_status or {})
        tracking_runtime = dict(tracking_runtime or {})
        pose_reason = pose_status.get("reason", "idle")
        pose_fresh = bool(pose_status.get("fresh", False))
        age_sec = pose_status.get("state_age_sec", 0.0)
        pose_age_ms = tracking_runtime.get("pose_age_ms")
        detail_parts = [
            f"Pose: {'Fresh' if pose_fresh else 'Not Fresh'}",
            f"Reason: {pose_reason}",
        ]
        if pose_age_ms is not None:
            detail_parts.append(f"Age: {pose_age_ms:.1f} ms")
        elif age_sec:
            detail_parts.append(f"Age: {age_sec:.2f} s")
        if tracking_runtime.get("loop_rate_hz") is not None:
            detail_parts.append(f"Loop: {tracking_runtime.get('loop_rate_hz', 0.0):.2f} Hz")
        if tracking_runtime.get("stale_pose_count") is not None:
            detail_parts.append(f"Stale Count: {tracking_runtime.get('stale_pose_count', 0)}")
        self.label_avp_detail.setText(error or " | ".join(detail_parts) or "Manual first connection is required.")

    def toggle_avp_details(self):
        expanded = not self.avp_details_panel.isVisible()
        self.avp_details_panel.setVisible(expanded)
        self.btn_toggle_avp_details.setText(
            "Hide AVP Details" if expanded else "Show AVP Details"
        )

    def update_system_snapshot(self, snapshot):
        dashboard_state = derive_dashboard_state(snapshot)

        self.status_cards["avp"].set_status(
            "Ready" if snapshot.pose_sample_valid else ("Connected" if snapshot.avp_connected else "Offline"),
            snapshot.pose_sample_reason or ("Head pose available." if snapshot.pose_sample_valid else "Waiting for AVP."),
        )
        self.status_cards["camera"].set_status(
            "Connected" if snapshot.camera_connected else "Disconnected",
            "ZED camera is online." if snapshot.camera_connected else "Camera is not connected.",
        )
        self.status_cards["motor"].set_status(
            "Connected" if snapshot.motor_connected else "Disconnected",
            "Motors are connected." if snapshot.motor_connected else "Motors are not connected.",
        )
        self.status_cards["stream"].set_status(
            "Running" if snapshot.streaming else "Stopped",
            "VisionPro stream is active." if snapshot.streaming else "VisionPro stream is stopped.",
        )
        self.status_cards["tracking"].set_status(
            "Tracking" if snapshot.tracking else "Idle",
            (
                "Yaw looks inactive in the current session."
                if snapshot.yaw_inactive
                else snapshot.last_warning or ("Tracking is running." if snapshot.tracking else "Tracking is idle.")
            ),
        )

        self.label_badge.setText(dashboard_state.hero_label)
        self.label_severity.setText(f"Status Level: {dashboard_state.severity_label}")
        self.label_summary.setText(dashboard_state.summary)
        self.label_next_step.setText(dashboard_state.next_step)
        self.grp_guidance.setTitle(f"Recommended Next Step [{dashboard_state.severity_label}]")
        self.label_badge.setText(f"{dashboard_state.severity_label} | {dashboard_state.hero_label}")
        self.btn_toggle_motor.setText(dashboard_state.motor_action_label)
        self.btn_toggle_motor.setEnabled(dashboard_state.motor_action_enabled)
        self.btn_toggle_motor.setToolTip(dashboard_state.motor_action_reason)
        self.btn_toggle_avp.setText(dashboard_state.avp_action_label)
        self.btn_toggle_avp.setEnabled(dashboard_state.avp_action_enabled)
        self.btn_toggle_avp.setToolTip(dashboard_state.avp_action_reason)
        self.btn_toggle_camera.setText("Connect Camera" if dashboard_state.connect_camera_enabled else "Disconnect Camera")
        self.btn_toggle_camera.setEnabled(True)
        self.btn_toggle_camera.setToolTip(dashboard_state.connect_camera_reason)
        self._stream_action = dashboard_state.stream_action
        self.btn_start_stream.setText(dashboard_state.stream_action_label)
        self.btn_start_stream.setEnabled(dashboard_state.stream_action_enabled)
        self.btn_start_stream.setToolTip(dashboard_state.stream_action_reason)
        self._tracking_action = dashboard_state.tracking_action
        self.btn_toggle_tracking.setText(dashboard_state.tracking_action_label)
        self.btn_toggle_tracking.setEnabled(dashboard_state.tracking_action_enabled)
        self.btn_toggle_tracking.setToolTip(dashboard_state.tracking_action_reason)
        self.btn_calibrate.setText(dashboard_state.calibrate_action_label)
        self.btn_calibrate.setEnabled(dashboard_state.calibrate_action_enabled)
        self.btn_calibrate.setToolTip(dashboard_state.calibrate_action_reason)
        self._recovery_action = dashboard_state.recovery_action
        self.label_recovery_title.setText(dashboard_state.recovery_title)
        self.label_recovery_detail.setText(dashboard_state.recovery_detail)
        self.btn_recovery_action.setText(dashboard_state.recovery_action_label)
        self.btn_recovery_action.setEnabled(dashboard_state.recovery_action_enabled)
        self.btn_recovery_action.setToolTip(dashboard_state.recovery_detail)
        self.btn_recovery_action.setVisible(dashboard_state.recovery_button_visible)

    def _emit_motor_action(self):
        if self.btn_toggle_motor.text().startswith("Disconnect"):
            self.disconnect_motor_requested.emit()
            return
        self.connect_motor_requested.emit()

    def _emit_camera_action(self):
        if self.btn_toggle_camera.text().startswith("Disconnect"):
            self.disconnect_camera_requested.emit()
            return
        self.connect_camera_requested.emit()

    def _emit_avp_action(self):
        if self.btn_toggle_avp.text().startswith("Disconnect"):
            self.disconnect_avp_requested.emit()
            return
        self.connect_avp_requested.emit()

    def _emit_stream_action(self):
        if self._stream_action == "stop":
            self.stop_stream_requested.emit()
            return
        self.start_stream_requested.emit()

    def _emit_tracking_action(self):
        self.toggle_tracking_requested.emit()

    def _emit_recovery_action(self):
        self.recovery_action_requested.emit(self._recovery_action)
