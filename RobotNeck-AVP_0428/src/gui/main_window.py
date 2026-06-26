import json
import time

import cv2
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import config
from src.core.avp_connection import load_avp_connection_settings, save_avp_connection_settings
from src.core.avp_session import AVPSessionCoordinator
from src.core.camera_controller import CameraController
from src.core.client import AVPClient
from src.core.diagnostic_capture import DiagnosticCaptureSession, diagnostic_capture_enabled
from src.core.mock_client import MockAVPClient
from src.core.timing_debug import RuntimeTimingTracker, camera_diagnostics_enabled, timing_debug_enabled
from src.gui.camera_panel_logic import precheck_rtp_stream_request
from src.gui.camera_param import CameraParamWidget
from src.gui.dashboard import DashboardWidget
from src.gui.dynamixel_debug import DxlDebugWidget
from src.gui.pose_control import PoseControlWidget
from src.gui.teleop_stream import TeleopStreamWidget
from src.gui.ui_state import SystemSnapshot


class MainWindow(QMainWindow):
    """
    Main Window - RobotNeck-AVP Control Center.
    Dashboard-first layout with manual AVP connection flow.
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("RobotNeck-AVP Control Center")
        self.resize(1200, 850)

        self.client = None
        self.avp_session_coordinator = AVPSessionCoordinator(
            client_factory=lambda ip: self._create_client(ip)
        )
        self.camera_controller = CameraController()
        self.motor_controller = None
        self.last_camera_diag_update = 0.0
        self._last_warning_message = ""
        self._timing_debug_enabled = timing_debug_enabled()
        self._camera_diag_enabled = camera_diagnostics_enabled()
        self._diag_capture = DiagnosticCaptureSession(enabled=diagnostic_capture_enabled())
        self._last_diag_capture_at = 0.0
        self._update_loop_timing = RuntimeTimingTracker(
            "main_window_update_loop",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )
        self._camera_read_timing = RuntimeTimingTracker(
            "camera_read",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )
        self._camera_diag_timing = RuntimeTimingTracker(
            "camera_diagnostics",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )

        self.init_ui()
        self.apply_styles()
        self._load_avp_settings()
        self.propagate_dependencies()
        self.refresh_camera_diagnostics(force=True)
        self.refresh_system_snapshot()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(33)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.dashboard_widget = DashboardWidget()
        self.pose_widget = PoseControlWidget()
        self.camera_widget = CameraParamWidget()
        self.teleop_widget = TeleopStreamWidget()
        self.dxl_debug = DxlDebugWidget()

        self.tabs.addTab(self.dashboard_widget, "Dashboard")
        self.tabs.addTab(self.pose_widget, "Pose Control")
        self.tabs.addTab(self.camera_widget, "ZED-M Camera")
        self.tabs.addTab(self.teleop_widget, "VisionPro Stream")
        self.tabs.addTab(self.dxl_debug, "Dynamixel Debug")
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.camera_widget.param_changed.connect(self.on_cam_param_changed)
        self.camera_widget.auto_exposure_toggled.connect(self.on_cam_auto_exp)
        self.camera_widget.auto_wb_toggled.connect(self.on_cam_auto_wb)
        self.camera_widget.confidence_changed.connect(self.on_cam_confidence)
        self.camera_widget.disparity_changed.connect(self.on_cam_disparity)
        self.camera_widget.capture_mode_changed.connect(self.on_cam_mode)
        self.camera_widget.focus_changed.connect(self.on_cam_focus)
        self.camera_widget.auto_focus_toggled.connect(self.on_cam_auto_focus)
        self.camera_widget.rtp_stream_requested.connect(self.on_rtp_stream_requested)
        if hasattr(self.camera_widget, "camera_connection_requested"):
            self.camera_widget.camera_connection_requested.connect(self.on_camera_connection_requested)

        self.teleop_widget.start_stream_requested.connect(self.start_stream)
        self.teleop_widget.stop_stream_requested.connect(self.stop_stream)
        self.teleop_widget.restart_stream_requested.connect(self.restart_stream)
        self.dxl_debug.motor_connected.connect(self.on_motor_connection_changed)

        self.dashboard_widget.connect_avp_requested.connect(self.connect_avp_from_dashboard)
        self.dashboard_widget.disconnect_avp_requested.connect(self.disconnect_avp_from_dashboard)
        self.dashboard_widget.retry_avp_requested.connect(self.retry_avp_from_dashboard)
        self.dashboard_widget.check_avp_requested.connect(self.check_avp_from_dashboard)
        self.dashboard_widget.connect_camera_requested.connect(self.connect_camera_from_dashboard)
        if hasattr(self.dashboard_widget, "disconnect_camera_requested"):
            self.dashboard_widget.disconnect_camera_requested.connect(self.disconnect_camera_from_dashboard)
        if hasattr(self.dashboard_widget, "connect_motor_requested"):
            self.dashboard_widget.connect_motor_requested.connect(self.connect_motor_from_dashboard)
        if hasattr(self.dashboard_widget, "disconnect_motor_requested"):
            self.dashboard_widget.disconnect_motor_requested.connect(self.disconnect_motor_from_dashboard)
        self.dashboard_widget.start_stream_requested.connect(self.start_stream_from_dashboard)
        self.dashboard_widget.stop_stream_requested.connect(self.stop_stream)
        self.dashboard_widget.toggle_tracking_requested.connect(self.toggle_tracking_from_dashboard)
        if hasattr(self.dashboard_widget, "calibrate_requested"):
            self.dashboard_widget.calibrate_requested.connect(self.calibrate_from_dashboard)
        self.dashboard_widget.recovery_action_requested.connect(self.handle_dashboard_recovery_action)

        global_group = QWidget()
        global_layout = QHBoxLayout()
        global_group.setLayout(global_layout)

        self.btn_load = QPushButton("Load Config")
        self.btn_load.clicked.connect(self.load_config)
        self.btn_save = QPushButton("Save Config")
        self.btn_save.clicked.connect(self.save_config)
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        self.btn_quit.clicked.connect(self.close)

        global_layout.addWidget(self.btn_load)
        global_layout.addWidget(self.btn_save)
        global_layout.addStretch()
        global_layout.addWidget(self.btn_quit)
        main_layout.addWidget(global_group)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_cam_status = QPushButton("Camera: Disconnected")
        self.lbl_cam_status.setFlat(True)
        self.lbl_cam_status.setStyleSheet("color: red; border: none; font-weight: bold;")
        self.lbl_cam_status.clicked.connect(self.reconnect_camera)

        self.lbl_motor_status = QPushButton("Motors: Disconnected")
        self.lbl_motor_status.setFlat(True)
        self.lbl_motor_status.setStyleSheet("color: red; border: none; font-weight: bold;")

        self.status_bar.addPermanentWidget(self.lbl_motor_status)
        self.status_bar.addPermanentWidget(self.lbl_cam_status)

    def apply_styles(self):
        style = """
        QMainWindow, QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-family: "Segoe UI", "Roboto", Helvetica, Arial, sans-serif;
        }
        QTabWidget::pane {
            border: 1px solid #444;
            background: #333;
        }
        QTabBar::tab {
            background: #444;
            color: #aaa;
            padding: 8px 12px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #333;
            color: #fff;
            font-weight: bold;
            border-bottom: 2px solid #3498db;
        }
        QPushButton {
            background-color: #444;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 5px;
            color: #eee;
        }
        QPushButton:hover {
            background-color: #555;
            border-color: #888;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #222;
            color: #fff;
            border: 1px solid #555;
            padding: 4px;
            border-radius: 3px;
        }
        """
        self.setStyleSheet(style)

    def _load_avp_settings(self):
        settings = load_avp_connection_settings()
        self.dashboard_widget.set_avp_settings(
            ip=settings.get("ip", getattr(config, "AVP_IP", "")),
            auto_reconnect=settings.get("auto_reconnect", False),
        )

    def _create_client(self, ip):
        if config.MOCK_AVP:
            return MockAVPClient(ip)
        return AVPClient(ip)

    def on_motor_connection_changed(self, controller):
        self.motor_controller = controller
        if controller:
            self.lbl_motor_status.setText("Motors: Connected")
            self.lbl_motor_status.setStyleSheet("color: #2ecc71; border: none; font-weight: bold;")
        else:
            self.lbl_motor_status.setText("Motors: Disconnected")
            self.lbl_motor_status.setStyleSheet("color: red; border: none; font-weight: bold;")

        self.propagate_dependencies()
        self.refresh_system_snapshot()

    def propagate_dependencies(self):
        self.pose_widget.set_dependencies(self.motor_controller, self.client, self.camera_controller)

    def _attach_switched_client(self, client):
        self.client = client
        self.propagate_dependencies()

    def _current_avp_switch_settings(self):
        current_status = self._avp_connection_status()
        settings = self.dashboard_widget.get_avp_settings()
        return (
            current_status.get("ip") or settings.get("ip") or getattr(config, "AVP_IP", ""),
            bool(settings.get("auto_reconnect", False)),
        )

    def _avp_connection_status(self):
        if self.client and hasattr(self.client, "get_connection_status"):
            return self.client.get_connection_status()
        return {
            "state": "idle",
            "ip": "",
            "auto_reconnect": False,
            "session_mode": "tracking_only",
            "last_error": None,
            "state_age_sec": 0.0,
            "last_sample_timestamp": None,
            "has_ever_received_pose": False,
        }

    def _avp_pose_status(self):
        if self.client and hasattr(self.client, "get_pose_status"):
            return self.client.get_pose_status()
        return {"valid": False, "reason": "idle", "fresh": False}

    def refresh_system_snapshot(self):
        connection_status = self._avp_connection_status()
        pose_status = self._avp_pose_status()
        pose_runtime = self.pose_widget.get_runtime_status() if hasattr(self.pose_widget, "get_runtime_status") else {}
        avp_connected = connection_status.get("state") in {
            "connecting",
            "connected_waiting_first_sample",
            "ready",
            "reconnecting",
        }
        snapshot = SystemSnapshot(
            avp_connected=avp_connected,
            camera_connected=bool(self.camera_controller.is_connected),
            motor_connected=bool(self.motor_controller and getattr(self.motor_controller, "connected", False)),
            streaming=bool(getattr(self.teleop_widget, "is_streaming", False)),
            tracking=bool(getattr(self.pose_widget, "is_tracking", False)),
            avp_session_mode=connection_status.get("session_mode", "tracking_only"),
            pose_sample_valid=bool(pose_status.get("valid", False)),
            pose_sample_reason=pose_status.get("reason", ""),
            tracking_blocked=not bool(pose_runtime.get("tracking_enabled", True)),
            tracking_block_reason=pose_runtime.get("tracking_block_reason", ""),
            yaw_inactive=bool(pose_runtime.get("yaw_inactive", False)),
            last_warning=pose_runtime.get("yaw_inactive_reason") or self._last_warning_message,
        )
        self.dashboard_widget.update_system_snapshot(snapshot)
        self.dashboard_widget.update_avp_runtime(connection_status, pose_status=pose_status, tracking_runtime=pose_runtime)
        return snapshot

    def refresh_camera_diagnostics(self, force=False):
        if not self._camera_diag_enabled:
            return
        now = time.time()
        min_interval = 0.25
        if bool(getattr(self.teleop_widget, "is_streaming", False)) and bool(getattr(self.pose_widget, "is_tracking", False)):
            min_interval = 1.0
        if not force and now - self.last_camera_diag_update < min_interval:
            return
        timing_started = time.perf_counter()
        self.last_camera_diag_update = now

        if self.camera_controller.is_connected:
            self.lbl_cam_status.setText("Camera: Connected")
            self.lbl_cam_status.setStyleSheet("color: #2ecc71; border: none; font-weight: bold;")
            if hasattr(self.camera_widget, "set_connected"):
                self.camera_widget.set_connected(True)
        else:
            self.lbl_cam_status.setText("Camera: Disconnected")
            self.lbl_cam_status.setStyleSheet("color: red; border: none; font-weight: bold;")
            if hasattr(self.camera_widget, "set_connected"):
                self.camera_widget.set_connected(False)

        if hasattr(self.camera_widget, "update_runtime"):
            self.camera_widget.update_runtime(
                device_info=self.camera_controller.get_device_info(),
                sensor_snapshot=self.camera_controller.get_sensor_snapshot(),
                health_status=self.camera_controller.get_health_status(),
                streaming_status=self.camera_controller.get_streaming_status(),
            )
        self._camera_diag_timing.record(
            (time.perf_counter() - timing_started) * 1000.0,
            now=time.time(),
            extra={"force": bool(force)},
        )

    def _show_runtime_message(self, message):
        self._last_warning_message = message
        self.status_bar.showMessage(message)

    def _show_recoverable_issue(self, message):
        self._show_runtime_message(message)
        self.refresh_system_snapshot()

    def get_debug_timing_snapshot(self):
        return {
            "update_loop": self._update_loop_timing.snapshot(),
            "camera_read": self._camera_read_timing.snapshot(),
            "camera_diagnostics": self._camera_diag_timing.snapshot(),
        }

    def connect_avp_from_dashboard(self):
        settings = self.dashboard_widget.get_avp_settings()
        ip = settings.get("ip") or getattr(config, "AVP_IP", "")
        auto_reconnect = bool(settings.get("auto_reconnect", False))
        save_avp_connection_settings(ip, auto_reconnect)
        if self.client is None:
            self.client = self._create_client(ip)
        self.client.connect(ip=ip, auto_reconnect=auto_reconnect, session_mode="tracking_only")
        self.propagate_dependencies()
        self._show_runtime_message(f"Connecting AVP client: {ip}")
        self.refresh_system_snapshot()

    def disconnect_avp_from_dashboard(self):
        if self.client:
            self.client.disconnect()
        self._show_runtime_message("AVP client disconnected.")
        self.refresh_system_snapshot()

    def retry_avp_from_dashboard(self):
        if self.client is None:
            return self.connect_avp_from_dashboard()
        self.client.retry_now()
        self._show_runtime_message("Manual AVP reconnect requested.")
        self.refresh_system_snapshot()

    def check_avp_from_dashboard(self):
        pose_status = self._avp_pose_status()
        reason = pose_status.get("reason", "idle")
        if pose_status.get("valid"):
            self._show_runtime_message("AVP pose input is valid.")
        else:
            self._show_runtime_message(f"AVP status: {reason}")
        self.refresh_system_snapshot()

    def connect_camera_from_dashboard(self):
        self.on_camera_connection_requested(True)

    def disconnect_camera_from_dashboard(self):
        self.on_camera_connection_requested(False)

    def connect_motor_from_dashboard(self):
        if hasattr(self.dxl_debug, "request_connection"):
            self.dxl_debug.request_connection(True)
        elif hasattr(self.dxl_debug, "toggle_connection"):
            self.dxl_debug.toggle_connection()
        self._show_runtime_message("Motor connection requested from Dashboard.")
        self.refresh_system_snapshot()

    def disconnect_motor_from_dashboard(self):
        if hasattr(self.dxl_debug, "request_connection"):
            self.dxl_debug.request_connection(False)
        elif hasattr(self.dxl_debug, "toggle_connection"):
            self.dxl_debug.toggle_connection()
        self._show_runtime_message("Motor disconnect requested from Dashboard.")
        self.refresh_system_snapshot()

    def start_stream_from_dashboard(self):
        self.start_stream()

    def toggle_tracking_from_dashboard(self):
        if not hasattr(self.pose_widget, "toggle_tracking"):
            return
        was_tracking = bool(getattr(self.pose_widget, "is_tracking", False))
        target_state = not was_tracking
        runtime = self.pose_widget.get_runtime_status() if hasattr(self.pose_widget, "get_runtime_status") else {}
        if target_state and not bool(runtime.get("tracking_enabled", True)):
            reason = runtime.get("tracking_block_reason", "") or "Tracking is temporarily unavailable."
            self._show_recoverable_issue(f"Dashboard tracking blocked: {reason}")
            return

        if hasattr(self.pose_widget, "btn_track") and hasattr(self.pose_widget.btn_track, "click"):
            if hasattr(self.pose_widget.btn_track, "isEnabled") and not self.pose_widget.btn_track.isEnabled():
                reason = runtime.get("tracking_block_reason", "") or "Tracking button is disabled."
                self._show_recoverable_issue(f"Dashboard tracking blocked: {reason}")
                return
            self.pose_widget.btn_track.click()
        else:
            self.pose_widget.toggle_tracking(target_state)

        is_tracking = bool(getattr(self.pose_widget, "is_tracking", False))
        if is_tracking == was_tracking:
            reason = runtime.get("tracking_block_reason", "") or "Pose Control did not change tracking state."
            self._show_recoverable_issue(f"Dashboard tracking blocked: {reason}")
            return

        self._show_runtime_message(
            "Tracking started from Dashboard." if is_tracking else "Tracking stopped from Dashboard."
        )
        self.refresh_system_snapshot()

    def calibrate_from_dashboard(self):
        if hasattr(self.pose_widget, "calibrate"):
            self.pose_widget.calibrate()
        self._show_runtime_message("Calibration started from Dashboard.")
        self.refresh_system_snapshot()

    def handle_dashboard_recovery_action(self, action):
        recovery_actions = {
            "connect_avp": self.connect_avp_from_dashboard,
            "check_avp": self.check_avp_from_dashboard,
            "retry_avp": self.retry_avp_from_dashboard,
            "connect_camera": self.connect_camera_from_dashboard,
            "disconnect_camera": self.disconnect_camera_from_dashboard,
            "connect_motor": self.connect_motor_from_dashboard,
            "disconnect_motor": self.disconnect_motor_from_dashboard,
            "start_stream": self.start_stream_from_dashboard,
            "stop_stream": self.stop_stream,
            "toggle_tracking": self.toggle_tracking_from_dashboard,
        }
        callback = recovery_actions.get(action)
        if callback is None:
            self._show_runtime_message(f"Unknown dashboard recovery action: {action}")
            return
        callback()

    def on_cam_param_changed(self, name, value):
        if name == "EXPOSURE":
            self.camera_controller.set_exposure(value)
        elif name == "WHITEBALANCE":
            self.camera_controller.set_whitebalance(value)
        elif name == "GAIN":
            self.camera_controller.set_gain(value)

    def on_cam_auto_exp(self, enabled):
        self.camera_controller.set_auto_exposure(enabled)

    def on_cam_auto_wb(self, enabled):
        self.camera_controller.set_auto_whitebalance(enabled)

    def on_cam_confidence(self, value):
        self.camera_controller.set_confidence_threshold(value)

    def on_cam_disparity(self, value):
        self.camera_controller.set_disparity_range(value)

    def on_cam_mode(self, mode):
        self.camera_controller.set_view_mode(mode)

    def on_cam_focus(self, value):
        self.camera_controller.set_focus(value)

    def on_cam_auto_focus(self, enabled):
        self.camera_controller.set_auto_focus(enabled)

    def on_rtp_stream_requested(self, enabled, codec, bitrate, port):
        decision = precheck_rtp_stream_request(
            has_camera=self.camera_controller.is_connected,
            requested_enabled=enabled,
        )
        if not decision["accepted"]:
            if hasattr(self.camera_widget, "set_rtp_stream_ui_state"):
                self.camera_widget.set_rtp_stream_ui_state(decision["ui_state"]["checked"])
            if decision["warning"]:
                self._show_recoverable_issue(f"RTP stream blocked: {decision['warning']}")
            return

        try:
            if enabled:
                if not self.camera_controller.enable_streaming(codec=codec, bitrate=bitrate, port=port):
                    raise RuntimeError("Failed to start ZED SDK RTP streaming.")
                self._show_runtime_message(f"RTP Streaming Started ({codec} @ {port})")
            else:
                self.camera_controller.disable_streaming()
                self._show_runtime_message("RTP Streaming Stopped")
        except Exception as exc:
            self._show_runtime_message(f"RTP streaming error: {exc}")
            QMessageBox.critical(self, "Error", f"RTP Streaming Error: {exc}")
            if hasattr(self.camera_widget, "set_rtp_stream_ui_state"):
                self.camera_widget.set_rtp_stream_ui_state(False)
        finally:
            self.refresh_camera_diagnostics(force=True)
            self.refresh_system_snapshot()

    def on_camera_connection_requested(self, should_connect):
        try:
            if should_connect:
                res, fps, _, _, _ = self.teleop_widget.get_config()
                camera = self.camera_controller.open_camera(resolution=res, fps=fps)
                if camera is None:
                    raise RuntimeError("Failed to open camera.")
                self._show_runtime_message("Camera connected.")
            else:
                if self.teleop_widget.is_streaming:
                    self.stop_stream()
                self.camera_controller.close_camera()
                self._show_runtime_message("Camera disconnected.")
        except Exception as exc:
            self._show_runtime_message(f"Camera connection error: {exc}")
            QMessageBox.critical(self, "Error", f"Camera connection error: {exc}")
        finally:
            if not self.camera_controller.is_connected and hasattr(self.camera_widget, "clear_preview"):
                self.camera_widget.clear_preview()
            self.refresh_camera_diagnostics(force=True)
            self.refresh_system_snapshot()

    def _avp_ready_for_stream(self):
        if not self.client:
            return False, "AVP client is not ready yet."
        state = self._avp_connection_status().get("state", "idle")
        if state != "ready":
            return False, f"AVP client is {state}."
        return True, ""

    def start_stream(self):
        if not self.client:
            self._show_recoverable_issue("VisionPro stream start skipped: AVP client is not ready yet.")
            self.teleop_widget.set_streaming_state(False)
            return False

        connection_status = self._avp_connection_status()
        avp_connectable_states = {
            "connecting",
            "connected_waiting_first_sample",
            "ready",
            "reconnecting",
        }
        connection_state = connection_status.get("state", "idle")
        if connection_state not in avp_connectable_states:
            self._show_recoverable_issue(
                f"VisionPro stream start blocked: AVP session is not connected ({connection_state})."
            )
            self.teleop_widget.set_streaming_state(False)
            return False

        if connection_status.get("session_mode", "tracking_only") != "streaming":
            ip, auto_reconnect = self._current_avp_switch_settings()
            result = self._switch_avp_mode_with_diag(
                current_client=self.client,
                target_mode="streaming",
                ip=ip,
                auto_reconnect=auto_reconnect,
                export_runtime_state=getattr(self.pose_widget, "export_tracking_runtime_state", None),
                restore_runtime_state=getattr(self.pose_widget, "restore_tracking_runtime_state", None),
                stop_tracking=(
                    (lambda: self.pose_widget.toggle_tracking(False))
                    if getattr(self.pose_widget, "is_tracking", False)
                    else None
                ),
                attach_client=self._attach_switched_client,
            )
            if not result.success:
                self._show_recoverable_issue(f"VisionPro stream switch failed: {result.reason}")
                self.teleop_widget.set_streaming_state(False)
                return False

        ready, reason = self._avp_ready_for_stream()
        if not ready and hasattr(self.client, "streamer"):
            if getattr(self.client, "streamer", None) is None:
                self._show_recoverable_issue(f"VisionPro stream start blocked: {reason}")
                self.teleop_widget.set_streaming_state(False)
                return False

        res, fps, bitrate, stereo, latency = self.teleop_widget.get_config()
        if not self.camera_controller.is_connected:
            camera = self.camera_controller.open_camera(resolution=res, fps=fps)
            if camera is None:
                self._show_runtime_message("VisionPro stream start failed: camera open failed.")
                QMessageBox.critical(self, "Error", "Failed to open camera.")
                self.teleop_widget.set_streaming_state(False)
                return False

        try:
            self.client.start_video_stream(
                frame_source=self.camera_controller,
                resolution=res,
                fps=fps,
                bitrate=bitrate,
                stereo=stereo,
                latency=latency,
            )
            self.teleop_widget.set_streaming_state(True)
            if hasattr(self.camera_widget, "update_info"):
                self.camera_widget.update_info(res, fps)
            self._show_runtime_message("VisionPro stream started.")
            self.refresh_camera_diagnostics(force=True)
            self.refresh_system_snapshot()
            return True
        except Exception as exc:
            self._show_runtime_message(f"VisionPro stream start failed: {exc}")
            QMessageBox.critical(self, "Error", f"Failed to start stream: {exc}")
            self.teleop_widget.set_streaming_state(False)
            return False

    def stop_stream(self):
        if not self.client:
            self._show_runtime_message("VisionPro stream stop skipped: no AVP client.")
            self.teleop_widget.set_streaming_state(False)
            self.refresh_camera_diagnostics(force=True)
            self.refresh_system_snapshot()
            return False

        connection_status = self._avp_connection_status()
        if connection_status.get("session_mode", "tracking_only") == "streaming":
            ip, auto_reconnect = self._current_avp_switch_settings()
            result = self._switch_avp_mode_with_diag(
                current_client=self.client,
                target_mode="tracking_only",
                ip=ip,
                auto_reconnect=auto_reconnect,
                export_runtime_state=getattr(self.pose_widget, "export_tracking_runtime_state", None),
                restore_runtime_state=getattr(self.pose_widget, "restore_tracking_runtime_state", None),
                stop_tracking=(
                    (lambda: self.pose_widget.toggle_tracking(False))
                    if getattr(self.pose_widget, "is_tracking", False)
                    else None
                ),
                attach_client=self._attach_switched_client,
            )
            if not result.success:
                self._show_recoverable_issue(f"VisionPro stream stop failed: {result.reason}")
                self.refresh_camera_diagnostics(force=True)
                return False
        else:
            self.client.stop_video_stream()

        self.teleop_widget.set_streaming_state(False)
        self._show_runtime_message("VisionPro stream stopped. AVP tracking remains available.")
        self.refresh_camera_diagnostics(force=True)
        self.refresh_system_snapshot()
        return True

    def restart_stream(self, res, fps, bitrate, stereo, latency):
        if not self.client:
            self._show_runtime_message("VisionPro stream restart skipped: no AVP client.")
            return
        if not self.camera_controller.is_connected:
            camera = self.camera_controller.open_camera(resolution=res, fps=fps)
            if camera is None:
                self._show_runtime_message("VisionPro stream restart failed: camera open failed.")
                QMessageBox.critical(self, "Error", "Failed to open camera for stream restart.")
                self.teleop_widget.set_streaming_state(False)
                return
        self.client.restart_video_stream(
            frame_source=self.camera_controller,
            resolution=res,
            fps=fps,
            bitrate=bitrate,
            stereo=stereo,
            latency=latency,
        )
        self.teleop_widget.set_streaming_state(True)
        self._show_runtime_message("VisionPro stream restarted.")
        self.refresh_camera_diagnostics(force=True)
        self.refresh_system_snapshot()

    def reconnect_camera(self):
        self._show_runtime_message("Reconnecting camera...")
        res, fps, _, _, _ = self.teleop_widget.get_config()
        self.camera_controller.close_camera()
        self.camera_controller.open_camera(resolution=res, fps=fps)
        self.refresh_camera_diagnostics(force=True)
        self.refresh_system_snapshot()

    def update_loop(self):
        loop_started = time.perf_counter()
        current_index = self.tabs.currentIndex()
        if self.camera_controller.is_connected and current_index == 2:
            read_started = time.perf_counter()
            ret, frame = self.camera_controller.read()
            self._camera_read_timing.record(
                (time.perf_counter() - read_started) * 1000.0,
                now=time.time(),
                extra={"target": "camera_tab"},
            )
            if ret and frame is not None and hasattr(self.camera_widget, "update_preview"):
                self.camera_widget.update_preview(frame)
            elif hasattr(self.camera_widget, "set_preview_status"):
                self.camera_widget.set_preview_status("NO CAMERA SIGNAL")
        if self.camera_controller.is_connected and current_index == 3 and self.teleop_widget.is_streaming:
            read_started = time.perf_counter()
            ret, frame = self.camera_controller.read()
            self._camera_read_timing.record(
                (time.perf_counter() - read_started) * 1000.0,
                now=time.time(),
                extra={"target": "teleop_tab"},
            )
            if ret and frame is not None:
                if self.teleop_widget.chk_mirror.isChecked():
                    frame = cv2.flip(frame, 1)
                if self.teleop_widget.chk_rotate.isChecked():
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                self.teleop_widget.update_frame(frame)
        if self._camera_diag_enabled:
            self.refresh_camera_diagnostics()
        self.refresh_system_snapshot()
        self._record_diagnostic_snapshot()
        self._update_loop_timing.record(
            (time.perf_counter() - loop_started) * 1000.0,
            now=time.time(),
            extra={
                "camera_connected": bool(self.camera_controller.is_connected),
                "streaming": bool(getattr(self.teleop_widget, "is_streaming", False)),
                "tab": current_index,
            },
        )

    def _record_diagnostic_snapshot(self):
        if not getattr(self._diag_capture, "enabled", False):
            return
        now = time.time()
        if now - self._last_diag_capture_at < 1.0:
            return
        self._last_diag_capture_at = now
        pose_runtime = self.pose_widget.get_runtime_status() if hasattr(self.pose_widget, "get_runtime_status") else {}
        client_timing = self.client.get_debug_timing_snapshot() if self.client and hasattr(self.client, "get_debug_timing_snapshot") else {}
        payload = {
            "session_mode": self._avp_connection_status().get("session_mode", "tracking_only"),
            "pose_fresh": bool(pose_runtime.get("pose_fresh", False)),
            "pose_reason": pose_runtime.get("pose_reason", ""),
            "pose_age_ms": pose_runtime.get("pose_age_ms"),
            "loop_rate_hz": pose_runtime.get("loop_rate_hz"),
            "motor_command_gap_ms": pose_runtime.get("motor_command_gap_ms"),
            "tracking": bool(getattr(self.pose_widget, "is_tracking", False)),
            "streaming": bool(getattr(self.teleop_widget, "is_streaming", False)),
            "avp_repeated_head_matrix_count": client_timing.get("repeated_head_matrix_count", 0),
            "avp_repeated_source_timestamp_count": client_timing.get("repeated_source_timestamp_count", 0),
            "avp_source_update_rate_hz": client_timing.get("source_update_rate_hz", 0.0),
            "avp_receive_rate_hz": client_timing.get("receive_rate_hz", 0.0),
            "avp_sample_sequence": client_timing.get("sample_sequence", 0),
            "skipped_stale_commands": pose_runtime.get("skipped_stale_commands", 0),
            "unchanged_target_skips": pose_runtime.get("unchanged_target_skips", 0),
            "motor_write_errors": pose_runtime.get("motor_write_errors", 0),
            "last_motor_write_error": pose_runtime.get("last_motor_write_error"),
            "camera": self.camera_controller.get_capture_stats() if hasattr(self.camera_controller, "get_capture_stats") else {},
            "timing": {
                "update_loop": self._update_loop_timing.snapshot(),
                "camera_read": self._camera_read_timing.snapshot(),
                "camera_diagnostics": self._camera_diag_timing.snapshot(),
                "control_loop": (pose_runtime.get("timing", {}) or {}).get("control_loop", {}),
                "motor_write": (pose_runtime.get("timing", {}) or {}).get("motor_write", {}),
                "avp_read": client_timing.get("avp_read", {}),
                "video_callback": client_timing.get("video_callback", {}),
            },
        }
        self._diag_capture.record_snapshot("app_snapshot", payload, now=now)

    def _record_avp_switch_event(self, name, payload):
        if not getattr(self._diag_capture, "enabled", False):
            return
        event_payload = dict(payload or {})
        event_payload["name"] = name
        self._diag_capture.record_snapshot("avp_switch_event", event_payload, now=time.time())

    def _switch_avp_mode_with_diag(self, **kwargs):
        try:
            return self.avp_session_coordinator.switch_mode(
                emit_event=self._record_avp_switch_event,
                **kwargs
            )
        except TypeError as exc:
            if "emit_event" not in str(exc):
                raise
            return self.avp_session_coordinator.switch_mode(**kwargs)

    def save_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Config", "", "JSON Files (*.json)")
        if path:
            avp_settings = self.dashboard_widget.get_avp_settings()
            initial_pose = (
                self.pose_widget.get_manual_initial_pose()
                if hasattr(self.pose_widget, "get_manual_initial_pose")
                else dict(getattr(config, "INITIAL_POSE", {"yaw": 0.0, "pitch": 0.0}))
            )
            data = {
                "mock_avp": config.MOCK_AVP,
                "mock_motors": config.MOCK_MOTORS,
                "avp": {
                    "ip": avp_settings.get("ip", ""),
                    "auto_reconnect": bool(avp_settings.get("auto_reconnect", False)),
                },
                "initial_pose": {
                    "yaw": float(initial_pose.get("yaw", 0.0)),
                    "pitch": float(initial_pose.get("pitch", 0.0)),
                },
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=4)
            self._show_runtime_message(f"Config saved to {path}")

    def load_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json)")
        if path:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            avp_settings = data.get("avp", {})
            if avp_settings:
                ip = avp_settings.get("ip", getattr(config, "AVP_IP", ""))
                auto_reconnect = bool(avp_settings.get("auto_reconnect", False))
                self.dashboard_widget.set_avp_settings(ip=ip, auto_reconnect=auto_reconnect)
                config.AVP_IP = ip

            initial_pose = data.get("initial_pose", {})
            if initial_pose:
                yaw = float(initial_pose.get("yaw", getattr(config, "INITIAL_POSE", {}).get("yaw", 0.0)))
                pitch = float(initial_pose.get("pitch", getattr(config, "INITIAL_POSE", {}).get("pitch", 0.0)))
                config.INITIAL_POSE = {"yaw": yaw, "pitch": pitch}
                if hasattr(self.pose_widget, "set_manual_initial_pose"):
                    self.pose_widget.set_manual_initial_pose(yaw, pitch)

            self._show_runtime_message(f"Config loaded from {path}")

    def on_tab_changed(self, index):
        if index == 4:
            self.dxl_debug.start_monitoring()
        else:
            self.dxl_debug.stop_monitoring()

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Stop all streams and disconnect motors?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if getattr(self.pose_widget, "is_tracking", False):
                self.pose_widget.toggle_tracking(False)
            if hasattr(self.pose_widget, "shutdown"):
                self.pose_widget.shutdown()
            if self.teleop_widget.is_streaming:
                self.stop_stream()
            self.camera_controller.close_camera()
            if self.client:
                self.client.close()
            self._diag_capture.close()
            self.dxl_debug.clean_shutdown()
            event.accept()
        else:
            event.ignore()
