import threading
import time

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import config
from src.core.timing_debug import RuntimeTimingTracker, timing_debug_enabled
from src.core.tracking_start import (
    capture_tracking_start_pose,
    load_tracking_start_pose_record,
    resolve_tracking_start_pose_steps,
    rollback_tracking_start_pose,
    save_tracking_start_pose_from_angles,
    tracking_start_steps_to_degrees,
)
from src.gui.pose_control_logic import (
    build_pose_control_view_state,
    resolve_base_imu,
    build_tracking_start_display,
    calculate_pose_age_ms,
    should_skip_motor_update,
)
from src.utils.motor_math import rad_to_steps
from src.utils.retargeting import HeadRetargeter


class PoseControlWidget(QWidget):
    """
    Widget for managing AVP -> Robot Neck pose retargeting.
    Replaces the main loop in app.py.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.motor_controller = None
        self.avp_client = None
        self.camera_controller = None
        self.retargeter = HeadRetargeter()
        self.tracking_start_pose = resolve_tracking_start_pose_steps()
        self.tracking_start_record = load_tracking_start_pose_record()
        self.manual_adjust_active = False
        self._yaw_diagnostic_samples = []
        self._yaw_inactive = False
        self._yaw_inactive_reason = ""
        self._pose_fresh = False
        self._pose_reason = "idle"
        self._pose_age_ms = None
        self._last_pose_timestamp = None
        self._loop_dt_ms = None
        self._loop_rate_hz = 0.0
        self._last_loop_timestamp = None
        self._stale_pose_count = 0
        self._last_counted_pose_reason = None
        self._last_motor_command_timestamp = None
        self._motor_command_gap_ms = None
        self._last_command_targets_deg = {"yaw": None, "pitch": None}
        self._skipped_stale_commands = 0
        self._unchanged_target_skips = 0
        self._motor_write_errors = 0
        self._last_motor_write_error = None
        self._latest_head_targets_deg = {"yaw": 0.0, "pitch": 0.0}
        self._latest_robot_targets_deg = {"yaw": 0.0, "pitch": 0.0}
        self._runtime_lock = threading.Lock()
        self._control_stop_event = threading.Event()
        self._control_thread = None
        self._timing_debug_enabled = timing_debug_enabled()
        self._control_loop_timing = RuntimeTimingTracker(
            "pose_control_loop",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=20.0,
        )
        self._motor_write_timing = RuntimeTimingTracker(
            "motor_write",
            enabled=self._timing_debug_enabled,
            log_every_sec=5.0,
            slow_threshold_ms=10.0,
        )

        self.is_tracking = False
        self.init_ui()
        self.refresh_tracking_start_record()
        self.apply_view_state()

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_live_status)
        self.timer.setInterval(100)
        self.timer.start()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        grp_tracking = QGroupBox("Tracking Control")
        layout_tracking = QVBoxLayout()
        grp_tracking.setLayout(layout_tracking)

        self.btn_track = QPushButton("Start Tracking")
        self.btn_track.setCheckable(True)
        self.btn_track.setStyleSheet(
            "background-color: #2ecc71; color: white; height: 44px; "
            "font-weight: bold; font-size: 14px;"
        )
        self.btn_track.toggled.connect(self.toggle_tracking)
        layout_tracking.addWidget(self.btn_track)

        tracking_status = QGridLayout()
        tracking_status.addWidget(QLabel("Workflow Status:"), 0, 0)
        self.lbl_workflow_status = QLabel("Idle")
        tracking_status.addWidget(self.lbl_workflow_status, 0, 1)
        tracking_status.addWidget(QLabel("Motors:"), 1, 0)
        self.lbl_motor_ready = QLabel("Disconnected")
        tracking_status.addWidget(self.lbl_motor_ready, 1, 1)
        tracking_status.addWidget(QLabel("AVP Client:"), 1, 2)
        self.lbl_avp_ready = QLabel("Not Ready")
        tracking_status.addWidget(self.lbl_avp_ready, 1, 3)
        layout_tracking.addLayout(tracking_status)

        self.lbl_step_hint = QLabel("")
        self.lbl_step_hint.setWordWrap(True)
        layout_tracking.addWidget(self.lbl_step_hint)

        layout.addWidget(grp_tracking)

        grp_home = QGroupBox("Home Position Setup")
        layout_home = QVBoxLayout()
        grp_home.setLayout(layout_home)

        summary_grid = QGridLayout()
        summary_grid.addWidget(QLabel("Current Home Position:"), 0, 0)
        self.lbl_home_current = QLabel("-")
        summary_grid.addWidget(self.lbl_home_current, 0, 1)
        summary_grid.addWidget(QLabel("Source:"), 1, 0)
        self.lbl_home_source = QLabel("-")
        self.lbl_home_source.setWordWrap(True)
        summary_grid.addWidget(self.lbl_home_source, 1, 1)
        layout_home.addLayout(summary_grid)

        self.btn_toggle_home_setup = QPushButton("Set Home Position")
        self.btn_toggle_home_setup.setCheckable(True)
        self.btn_toggle_home_setup.toggled.connect(self.toggle_home_setup)
        layout_home.addWidget(self.btn_toggle_home_setup)

        self.home_setup_panel = QWidget()
        home_setup_layout = QVBoxLayout()
        self.home_setup_panel.setLayout(home_setup_layout)

        grp_manual_input = QGroupBox("Method A: Manual Angle Input")
        layout_manual_input = QFormLayout()
        grp_manual_input.setLayout(layout_manual_input)

        self.spin_initial_yaw = QDoubleSpinBox()
        self.spin_initial_yaw.setRange(config.YAW_LIMIT_DEG[0], config.YAW_LIMIT_DEG[1])
        self.spin_initial_yaw.setDecimals(1)
        self.spin_initial_yaw.setSingleStep(1.0)
        self.spin_initial_yaw.setToolTip("Saved tracking start yaw in degrees")
        layout_manual_input.addRow("Home Yaw (deg):", self.spin_initial_yaw)

        self.spin_initial_pitch = QDoubleSpinBox()
        self.spin_initial_pitch.setRange(config.PITCH_LIMIT_DEG[0], config.PITCH_LIMIT_DEG[1])
        self.spin_initial_pitch.setDecimals(1)
        self.spin_initial_pitch.setSingleStep(1.0)
        self.spin_initial_pitch.setToolTip("Saved tracking start pitch in degrees")
        layout_manual_input.addRow("Home Pitch (deg):", self.spin_initial_pitch)

        self.btn_save_home = QPushButton("Save Manual Input")
        self.btn_save_home.clicked.connect(self.save_manual_home_position)
        layout_manual_input.addRow(self.btn_save_home)

        grp_manual_adjust = QGroupBox("Method B: Manual Adjust")
        layout_manual_adjust = QVBoxLayout()
        grp_manual_adjust.setLayout(layout_manual_adjust)

        self.lbl_manual_adjust_hint = QLabel(
            "Release torque, move the neck by hand, then read the current motor pose."
        )
        self.lbl_manual_adjust_hint.setWordWrap(True)
        layout_manual_adjust.addWidget(self.lbl_manual_adjust_hint)

        manual_adjust_actions = QHBoxLayout()
        self.btn_release_torque = QPushButton("Release Torque")
        self.btn_release_torque.clicked.connect(self.release_torque_for_manual_adjust)
        manual_adjust_actions.addWidget(self.btn_release_torque)

        self.btn_capture_home = QPushButton("Read Motor Pose & Save")
        self.btn_capture_home.clicked.connect(self.capture_current_home_position)
        manual_adjust_actions.addWidget(self.btn_capture_home)
        layout_manual_adjust.addLayout(manual_adjust_actions)

        home_setup_layout.addWidget(grp_manual_input)
        home_setup_layout.addWidget(grp_manual_adjust)
        self.home_setup_panel.setVisible(False)
        layout_home.addWidget(self.home_setup_panel)

        layout.addWidget(grp_home)

        grp_calibration = QGroupBox("Calibration")
        layout_calibration = QVBoxLayout()
        grp_calibration.setLayout(layout_calibration)

        self.lbl_calibration_note = QLabel(
            "Calibration always moves the neck to the saved Home Position before capturing the center."
        )
        self.lbl_calibration_note.setWordWrap(True)
        layout_calibration.addWidget(self.lbl_calibration_note)

        calibration_actions = QHBoxLayout()
        btn_calib = QPushButton("Move To Home And Calibrate")
        btn_calib.clicked.connect(self.calibrate)
        calibration_actions.addWidget(btn_calib)

        btn_reset_calib = QPushButton("Reset Calibration")
        btn_reset_calib.clicked.connect(self.reset_calibration)
        calibration_actions.addWidget(btn_reset_calib)
        calibration_actions.addStretch()
        layout_calibration.addLayout(calibration_actions)

        layout.addWidget(grp_calibration)

        grp_status = QGroupBox("Real-time Pose Data")
        layout_status = QGridLayout()
        grp_status.setLayout(layout_status)
        layout_status.addWidget(QLabel("<b>Input (AVP)</b>"), 0, 1)
        layout_status.addWidget(QLabel("<b>Target (Robot)</b>"), 0, 2)
        layout_status.addWidget(QLabel("Yaw:"), 1, 0)
        self.lbl_head_yaw = QLabel("0.0°")
        layout_status.addWidget(self.lbl_head_yaw, 1, 1)
        self.lbl_robot_yaw = QLabel("0.0°")
        layout_status.addWidget(self.lbl_robot_yaw, 1, 2)
        layout_status.addWidget(QLabel("Pitch:"), 2, 0)
        self.lbl_head_pitch = QLabel("0.0°")
        layout_status.addWidget(self.lbl_head_pitch, 2, 1)
        self.lbl_robot_pitch = QLabel("0.0°")
        layout_status.addWidget(self.lbl_robot_pitch, 2, 2)
        layout.addWidget(grp_status)

        grp_advanced = QGroupBox("Advanced")
        layout_advanced = QVBoxLayout()
        grp_advanced.setLayout(layout_advanced)

        self.btn_toggle_advanced = QToolButton()
        self.btn_toggle_advanced.setText("Show Advanced Details")
        self.btn_toggle_advanced.setCheckable(True)
        self.btn_toggle_advanced.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_toggle_advanced.toggled.connect(self.toggle_advanced)
        layout_advanced.addWidget(self.btn_toggle_advanced)

        self.advanced_panel = QWidget()
        advanced_panel_layout = QGridLayout()
        self.advanced_panel.setLayout(advanced_panel_layout)
        advanced_panel_layout.addWidget(QLabel("Current Record (steps):"), 0, 0)
        self.lbl_current_steps = QLabel("-")
        advanced_panel_layout.addWidget(self.lbl_current_steps, 0, 1)
        advanced_panel_layout.addWidget(QLabel("Previous Record (steps):"), 1, 0)
        self.lbl_previous_steps = QLabel("-")
        advanced_panel_layout.addWidget(self.lbl_previous_steps, 1, 1)
        advanced_panel_layout.addWidget(QLabel("Record Path:"), 2, 0)
        self.lbl_record_path = QLabel("-")
        self.lbl_record_path.setWordWrap(True)
        advanced_panel_layout.addWidget(self.lbl_record_path, 2, 1)
        self.btn_rollback_home = QPushButton("Rollback Home")
        self.btn_rollback_home.clicked.connect(self.rollback_home_position)
        advanced_panel_layout.addWidget(self.btn_rollback_home, 3, 1)
        advanced_panel_layout.addWidget(QLabel("Pose Freshness:"), 4, 0)
        self.lbl_pose_freshness = QLabel("Unknown")
        self.lbl_pose_freshness.setWordWrap(True)
        advanced_panel_layout.addWidget(self.lbl_pose_freshness, 4, 1)
        advanced_panel_layout.addWidget(QLabel("Sample Age:"), 5, 0)
        self.lbl_pose_age = QLabel("-")
        advanced_panel_layout.addWidget(self.lbl_pose_age, 5, 1)
        advanced_panel_layout.addWidget(QLabel("Control Loop:"), 6, 0)
        self.lbl_loop_rate = QLabel("-")
        advanced_panel_layout.addWidget(self.lbl_loop_rate, 6, 1)
        advanced_panel_layout.addWidget(QLabel("Last Command Gap:"), 7, 0)
        self.lbl_motor_gap = QLabel("-")
        advanced_panel_layout.addWidget(self.lbl_motor_gap, 7, 1)
        advanced_panel_layout.addWidget(QLabel("Last Command Target:"), 8, 0)
        self.lbl_last_command = QLabel("-")
        self.lbl_last_command.setWordWrap(True)
        advanced_panel_layout.addWidget(self.lbl_last_command, 8, 1)
        self.advanced_panel.setVisible(False)
        layout_advanced.addWidget(self.advanced_panel)

        layout.addWidget(grp_advanced)
        layout.addStretch()

    def set_dependencies(self, motors, client, camera_controller=None):
        self.motor_controller = motors
        self.avp_client = client
        self.camera_controller = camera_controller
        self.apply_view_state()

    def export_tracking_runtime_state(self):
        return {
            "was_tracking": bool(self.is_tracking),
            "tracking_start_pose": dict(self.tracking_start_pose),
            "retargeter_state": {
                "yaw_offset": float(getattr(self.retargeter, "yaw_offset", 0.0)),
                "pitch_offset": float(getattr(self.retargeter, "pitch_offset", 0.0)),
                "calibrated": bool(getattr(self.retargeter, "calibrated", False)),
                "pending_calibration": bool(getattr(self.retargeter, "_pending_calibration", False)),
            },
        }

    def restore_tracking_runtime_state(self, state):
        state = dict(state or {})
        tracking_start_pose = state.get("tracking_start_pose")
        if isinstance(tracking_start_pose, dict):
            self.tracking_start_pose = dict(tracking_start_pose)

        retargeter_state = state.get("retargeter_state", {})
        self.retargeter.yaw_offset = float(retargeter_state.get("yaw_offset", self.retargeter.yaw_offset))
        self.retargeter.pitch_offset = float(retargeter_state.get("pitch_offset", self.retargeter.pitch_offset))
        self.retargeter.calibrated = bool(retargeter_state.get("calibrated", self.retargeter.calibrated))
        self.retargeter._pending_calibration = bool(
            retargeter_state.get("pending_calibration", self.retargeter._pending_calibration)
        )

        self._set_tracking_runtime_active(bool(state.get("was_tracking", False)))
        self.apply_view_state()

    def get_runtime_status(self):
        tracking_enabled = not self.manual_adjust_active
        tracking_block_reason = ""
        if self.manual_adjust_active:
            tracking_block_reason = "Finish manual adjust before starting tracking."
        with self._runtime_lock:
            return {
                "yaw_inactive": bool(self._yaw_inactive),
                "yaw_inactive_reason": self._yaw_inactive_reason,
                "tracking_enabled": tracking_enabled,
                "tracking_block_reason": tracking_block_reason,
                "manual_adjust_active": bool(self.manual_adjust_active),
                "pose_fresh": bool(self._pose_fresh),
                "pose_reason": self._pose_reason,
                "pose_age_ms": self._pose_age_ms,
                "last_pose_timestamp": self._last_pose_timestamp,
                "loop_dt_ms": self._loop_dt_ms,
                "loop_rate_hz": self._loop_rate_hz,
                "stale_pose_count": int(self._stale_pose_count),
                "last_motor_command_timestamp": self._last_motor_command_timestamp,
                "motor_command_gap_ms": self._motor_command_gap_ms,
                "last_command_targets_deg": dict(self._last_command_targets_deg),
                "skipped_stale_commands": int(self._skipped_stale_commands),
                "unchanged_target_skips": int(self._unchanged_target_skips),
                "motor_write_errors": int(self._motor_write_errors),
                "last_motor_write_error": self._last_motor_write_error,
                "control_thread_alive": bool(self._control_thread and self._control_thread.is_alive()),
                "timing": self.get_debug_timing_snapshot(),
            }

    def get_debug_timing_snapshot(self):
        return {
            "control_loop": self._control_loop_timing.snapshot(),
            "motor_write": self._motor_write_timing.snapshot(),
        }

    def refresh_live_status(self):
        with self._runtime_lock:
            head_yaw = self._latest_head_targets_deg.get("yaw", 0.0)
            head_pitch = self._latest_head_targets_deg.get("pitch", 0.0)
            robot_yaw = self._latest_robot_targets_deg.get("yaw", 0.0)
            robot_pitch = self._latest_robot_targets_deg.get("pitch", 0.0)
        self.lbl_head_yaw.setText(f"{head_yaw:.1f}°")
        self.lbl_head_pitch.setText(f"{head_pitch:.1f}°")
        self.lbl_robot_yaw.setText(f"{robot_yaw:.1f}°")
        self.lbl_robot_pitch.setText(f"{robot_pitch:.1f}°")
        self._refresh_tracking_diagnostics_labels()

    def get_manual_initial_pose(self):
        return {
            "yaw": float(self.spin_initial_yaw.value()),
            "pitch": float(self.spin_initial_pitch.value()),
        }

    def set_manual_initial_pose(self, yaw, pitch):
        self.spin_initial_yaw.setValue(float(yaw))
        self.spin_initial_pitch.setValue(float(pitch))

    def has_connected_motors(self):
        return bool(self.motor_controller and getattr(self.motor_controller, "connected", False))

    def refresh_tracking_start_record(self):
        self.tracking_start_record = load_tracking_start_pose_record()
        self.tracking_start_pose = dict(self.tracking_start_record["current"])

        current_deg = tracking_start_steps_to_degrees(self.tracking_start_record["current"])
        previous_deg = tracking_start_steps_to_degrees(self.tracking_start_record["previous"])
        display = build_tracking_start_display(
            current_pose=current_deg,
            previous_pose=previous_deg,
            path=self.tracking_start_record["path"],
            has_saved_record=self.tracking_start_record["has_saved_record"],
        )

        self.spin_initial_yaw.setValue(current_deg["yaw"])
        self.spin_initial_pitch.setValue(current_deg["pitch"])
        self.lbl_home_current.setText(display["current_text"])
        self.lbl_home_source.setText(display["source_text"])
        self.lbl_current_steps.setText(self.format_step_pose(self.tracking_start_record["current"]))
        self.lbl_previous_steps.setText(self.format_step_pose(self.tracking_start_record["previous"]))
        self.lbl_record_path.setText(display["source_text"])

    def apply_view_state(self):
        state = build_pose_control_view_state(
            motors_connected=self.has_connected_motors(),
            is_tracking=self.is_tracking,
            manual_adjust_active=self.manual_adjust_active,
        )

        self.lbl_workflow_status.setText(state["status_text"])
        self.lbl_step_hint.setText(state["step_message"])
        self.lbl_manual_adjust_hint.setText(state["step_message"])
        self.lbl_motor_ready.setText("Connected" if self.has_connected_motors() else "Disconnected")
        self.lbl_avp_ready.setText("Ready" if self.avp_client else "Not Ready")

        self.btn_release_torque.setEnabled(state["release_enabled"])
        self.btn_capture_home.setEnabled(state["capture_enabled"])
        self.btn_track.setEnabled(state["tracking_enabled"])

        status_colors = {
            "Disconnected": "#e67e22",
            "Manual Adjust": "#f1c40f",
            "Tracking": "#2ecc71",
            "Idle": "#3498db",
        }
        self.lbl_workflow_status.setStyleSheet(
            f"color: {status_colors.get(state['status_text'], '#ffffff')}; font-weight: bold;"
        )
        self._refresh_tracking_diagnostics_labels()

    def _set_tracking_runtime_active(self, active):
        self.is_tracking = bool(active)
        if hasattr(self.btn_track, "blockSignals"):
            self.btn_track.blockSignals(True)
        if self.is_tracking:
            self.btn_track.setChecked(True)
            self.btn_track.setText("Stop Tracking")
            self.btn_track.setStyleSheet(
                "background-color: #e74c3c; color: white; height: 44px; "
                "font-weight: bold; font-size: 14px;"
            )
            self._start_control_worker()
        else:
            self.btn_track.setChecked(False)
            self.btn_track.setText("Start Tracking")
            self.btn_track.setStyleSheet(
                "background-color: #2ecc71; color: white; height: 44px; "
                "font-weight: bold; font-size: 14px;"
            )
            self._stop_control_worker()
        if hasattr(self.btn_track, "blockSignals"):
            self.btn_track.blockSignals(False)
        self.apply_view_state()

    def _start_control_worker(self):
        worker = self._control_thread
        if worker and worker.is_alive():
            return
        self._control_stop_event.clear()
        self._control_thread = threading.Thread(
            target=self._control_loop_worker,
            name="pose-control-loop",
            daemon=True,
        )
        self._control_thread.start()

    def _stop_control_worker(self):
        self._control_stop_event.set()
        worker = self._control_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=0.5)
        self._control_thread = None

    def _control_loop_worker(self):
        interval_sec = 1.0 / max(1.0, float(getattr(config, "LOOP_RATE", 60)))
        while not self._control_stop_event.is_set():
            started = time.perf_counter()
            self.control_loop()
            sleep_time = interval_sec - (time.perf_counter() - started)
            if sleep_time > 0 and self._control_stop_event.wait(sleep_time):
                break

    def _update_yaw_diagnostic(self, yaw_target, pitch_target):
        self._yaw_diagnostic_samples.append((float(yaw_target), float(pitch_target)))
        if len(self._yaw_diagnostic_samples) > 30:
            self._yaw_diagnostic_samples = self._yaw_diagnostic_samples[-30:]

        if len(self._yaw_diagnostic_samples) < 10:
            self._yaw_inactive = False
            self._yaw_inactive_reason = ""
            return

        yaw_values = [sample[0] for sample in self._yaw_diagnostic_samples]
        pitch_values = [sample[1] for sample in self._yaw_diagnostic_samples]
        yaw_span = max(yaw_values) - min(yaw_values)
        pitch_span = max(pitch_values) - min(pitch_values)

        self._yaw_inactive = pitch_span > np.deg2rad(6.0) and yaw_span < np.deg2rad(2.0)
        if self._yaw_inactive:
            self._yaw_inactive_reason = "pitch_active_yaw_static"
        else:
            self._yaw_inactive_reason = ""

    def _record_loop_timing(self):
        now = time.time()
        with self._runtime_lock:
            if self._last_loop_timestamp is not None:
                self._loop_dt_ms = round(max(0.0, now - self._last_loop_timestamp) * 1000.0, 1)
                if self._loop_dt_ms > 0:
                    self._loop_rate_hz = round(1000.0 / self._loop_dt_ms, 2)
            self._last_loop_timestamp = now
        return now

    def _update_pose_diagnostics(self, pose_status):
        pose_status = dict(pose_status or {})
        reason = str(pose_status.get("reason", "") or "unknown")
        fresh = bool(pose_status.get("fresh", False))
        with self._runtime_lock:
            self._pose_fresh = fresh
            self._pose_reason = reason
            self._last_pose_timestamp = pose_status.get("last_sample_timestamp")
            self._pose_age_ms = calculate_pose_age_ms(
                pose_status=pose_status,
                monotonic_now=time.monotonic(),
                wall_now=time.time(),
            )

            if reason in {"stale_sample", "sample_missing", "streamer_initializing", "stream_established_waiting_first_sample"}:
                if self._last_counted_pose_reason != reason:
                    self._stale_pose_count += 1
                    self._last_counted_pose_reason = reason
            elif fresh:
                self._last_counted_pose_reason = None

    def _refresh_tracking_diagnostics_labels(self):
        with self._runtime_lock:
            freshness = "Fresh" if self._pose_fresh else "Not Fresh"
            reason = self._pose_reason or "unknown"
            pose_age_ms = self._pose_age_ms
            loop_dt_ms = self._loop_dt_ms
            loop_rate_hz = self._loop_rate_hz
            motor_command_gap_ms = self._motor_command_gap_ms
            yaw_target = self._last_command_targets_deg.get("yaw")
            pitch_target = self._last_command_targets_deg.get("pitch")
            stale_pose_count = self._stale_pose_count
        self.lbl_pose_freshness.setText(f"{freshness} | {reason}")
        self.lbl_pose_age.setText("-" if pose_age_ms is None else f"{pose_age_ms:.1f} ms")
        if loop_dt_ms is None:
            self.lbl_loop_rate.setText("-")
        else:
            self.lbl_loop_rate.setText(f"{loop_rate_hz:.2f} Hz | {loop_dt_ms:.1f} ms")
        if motor_command_gap_ms is None:
            self.lbl_motor_gap.setText("-")
        else:
            self.lbl_motor_gap.setText(f"{motor_command_gap_ms:.1f} ms")
        if yaw_target is None or pitch_target is None:
            self.lbl_last_command.setText("-")
        else:
            self.lbl_last_command.setText(
                f"Yaw {yaw_target:.1f} deg | Pitch {pitch_target:.1f} deg | Stale Count {stale_pose_count}"
            )

    def format_step_pose(self, pose_steps):
        return (
            f"Yaw {pose_steps['yaw_start_step']} | "
            f"Pitch {pose_steps['pitch_start_step']}"
        )

    def current_tracking_start_commands(self):
        return {
            config.YAW_MOTOR_ID: self.tracking_start_pose["yaw_start_step"],
            config.PITCH_MOTOR_ID: self.tracking_start_pose["pitch_start_step"],
        }

    def toggle_home_setup(self, checked):
        self.home_setup_panel.setVisible(checked)
        self.btn_toggle_home_setup.setText("Hide Home Setup" if checked else "Set Home Position")

    def toggle_advanced(self, checked):
        self.advanced_panel.setVisible(checked)
        self.btn_toggle_advanced.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.btn_toggle_advanced.setText(
            "Hide Advanced Details" if checked else "Show Advanced Details"
        )

    def close_home_setup(self):
        self.btn_toggle_home_setup.setChecked(False)

    def save_manual_home_position(self):
        saved = save_tracking_start_pose_from_angles(
            self.spin_initial_yaw.value(),
            self.spin_initial_pitch.value(),
        )
        self.manual_adjust_active = False
        self.refresh_tracking_start_record()
        self.apply_view_state()
        self.close_home_setup()
        pose_deg = tracking_start_steps_to_degrees(saved)
        QMessageBox.information(
            self,
            "Home Position Saved",
            (
                "Saved tracking start pose.\n"
                f"Yaw: {pose_deg['yaw']:.1f} deg\n"
                f"Pitch: {pose_deg['pitch']:.1f} deg"
            ),
        )

    def release_torque_for_manual_adjust(self):
        if self.is_tracking:
            self.btn_track.click()

        if not self.has_connected_motors():
            QMessageBox.warning(self, "Warning", "Motors not connected.")
            self.apply_view_state()
            return

        self.motor_controller.enable_torque(config.YAW_MOTOR_ID, False)
        self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, False)
        self.manual_adjust_active = True
        self.apply_view_state()

    def capture_current_home_position(self):
        if not self.has_connected_motors():
            QMessageBox.warning(self, "Warning", "Motors not connected.")
            return

        try:
            saved = capture_tracking_start_pose(self.motor_controller)
            self.motor_controller.enable_torque(config.YAW_MOTOR_ID, True)
            self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, True)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Warning", str(exc))
            return

        self.manual_adjust_active = False
        self.refresh_tracking_start_record()
        self.apply_view_state()
        self.close_home_setup()
        pose_deg = tracking_start_steps_to_degrees(saved)
        QMessageBox.information(
            self,
            "Home Position Saved",
            (
                "Captured current motor pose as tracking start pose.\n"
                f"Yaw: {pose_deg['yaw']:.1f} deg\n"
                f"Pitch: {pose_deg['pitch']:.1f} deg"
            ),
        )

    def rollback_home_position(self):
        restored = rollback_tracking_start_pose()
        self.manual_adjust_active = False
        self.refresh_tracking_start_record()
        self.apply_view_state()
        pose_deg = tracking_start_steps_to_degrees(restored)
        QMessageBox.information(
            self,
            "Home Position Rolled Back",
            (
                "Restored the previous tracking start pose.\n"
                f"Yaw: {pose_deg['yaw']:.1f} deg\n"
                f"Pitch: {pose_deg['pitch']:.1f} deg"
            ),
        )

    def toggle_tracking(self, checked):
        if checked and self.manual_adjust_active:
            self.btn_track.setChecked(False)
            return

        if checked:
            if self.motor_controller and self.motor_controller.connected and self.avp_client:

                def get_rad(mid):
                    steps = self.motor_controller.get_present_position(mid)
                    if steps is None:
                        return 0.0
                    return (steps - config.ZERO_POS) * (2 * np.pi / config.STEPS_PER_REV)

                r_yaw = get_rad(config.YAW_MOTOR_ID) / config.YAW_SCALE
                r_pitch = get_rad(config.PITCH_MOTOR_ID) / config.PITCH_SCALE

                avp_mat = None
                for _ in range(10):
                    avp_mat = self.avp_client.get_latest_head_pose_matrix()
                    if avp_mat is not None:
                        break
                    time.sleep(0.01)

                if avp_mat is not None:
                    base_imu = resolve_base_imu(
                        self.camera_controller,
                        getattr(config, "ENABLE_IMU_COMPENSATION", False),
                    )
                    self.retargeter.sync_with_robot_pose(
                        avp_mat,
                        r_yaw,
                        r_pitch,
                        base_imu_rpy=base_imu,
                    )

            self._set_tracking_runtime_active(True)
        else:
            self._set_tracking_runtime_active(False)

        self.apply_view_state()

    def control_loop(self):
        loop_started = time.perf_counter()
        self._record_loop_timing()
        if not self.avp_client:
            self._update_pose_diagnostics({"reason": "client_unavailable", "fresh": False, "last_sample_timestamp": None})
            self._control_loop_timing.record(
                (time.perf_counter() - loop_started) * 1000.0,
                now=time.time(),
                extra={"tracking": bool(self.is_tracking), "reason": "client_unavailable"},
            )
            return

        pose_data = self.avp_client.get_latest_head_pose_matrix()
        pose_status = self.avp_client.get_pose_status() if hasattr(self.avp_client, "get_pose_status") else {}
        self._update_pose_diagnostics(pose_status)
        if pose_data is None or not bool(pose_status.get("fresh", False)):
            if self.is_tracking and not bool(pose_status.get("fresh", False)):
                with self._runtime_lock:
                    self._skipped_stale_commands += 1
            self._control_loop_timing.record(
                (time.perf_counter() - loop_started) * 1000.0,
                now=time.time(),
                extra={"tracking": bool(self.is_tracking), "reason": pose_status.get("reason", "pose_missing")},
            )
            return

        base_imu = resolve_base_imu(
            self.camera_controller,
            getattr(config, "ENABLE_IMU_COMPENSATION", False),
        )

        yaw_target, pitch_target = self.retargeter.compute_neck_target(
            pose_data, base_imu_rpy=base_imu
        )
        self._update_yaw_diagnostic(yaw_target, pitch_target)

        yaw_cmd = yaw_target * config.YAW_SCALE
        pitch_cmd = pitch_target * config.PITCH_SCALE
        yaw_deg = np.rad2deg(yaw_cmd)
        pitch_deg = np.rad2deg(pitch_cmd)
        with self._runtime_lock:
            self._latest_head_targets_deg = {
                "yaw": round(np.rad2deg(yaw_target), 1),
                "pitch": round(np.rad2deg(pitch_target), 1),
            }
            self._latest_robot_targets_deg = {"yaw": round(yaw_deg, 1), "pitch": round(pitch_deg, 1)}

        if self.is_tracking and self.motor_controller:
            motor_commands = {}
            if config.YAW_LIMIT_DEG[0] <= yaw_deg <= config.YAW_LIMIT_DEG[1]:
                motor_commands[config.YAW_MOTOR_ID] = rad_to_steps(yaw_cmd)

            if config.PITCH_LIMIT_DEG[0] <= pitch_deg <= config.PITCH_LIMIT_DEG[1]:
                motor_commands[config.PITCH_MOTOR_ID] = rad_to_steps(pitch_cmd)

            if motor_commands:
                command_targets_deg = {"yaw": round(yaw_deg, 1), "pitch": round(pitch_deg, 1)}
                skip_update, skip_reason = should_skip_motor_update(
                    pose_status=pose_status,
                    is_tracking=self.is_tracking,
                    motor_commands=motor_commands,
                    last_command_targets_deg=self._last_command_targets_deg,
                    command_targets_deg=command_targets_deg,
                )
                if skip_update:
                    with self._runtime_lock:
                        if skip_reason == "stale_pose":
                            self._skipped_stale_commands += 1
                        elif skip_reason == "unchanged_target":
                            self._unchanged_target_skips += 1
                    self._control_loop_timing.record(
                        (time.perf_counter() - loop_started) * 1000.0,
                        now=time.time(),
                        extra={"tracking": bool(self.is_tracking), "pose_fresh": bool(self._pose_fresh), "skip": skip_reason},
                    )
                    return

                now = time.time()
                with self._runtime_lock:
                    if self._last_motor_command_timestamp is not None:
                        self._motor_command_gap_ms = round(max(0.0, now - self._last_motor_command_timestamp) * 1000.0, 1)
                    self._last_motor_command_timestamp = now
                    self._last_command_targets_deg = command_targets_deg
                write_started = time.perf_counter()
                write_result = None
                if hasattr(self.motor_controller, "set_goal_positions"):
                    write_result = self.motor_controller.set_goal_positions(motor_commands)
                else:
                    for mid, pos in motor_commands.items():
                        if hasattr(self.motor_controller, "set_goal_position"):
                            write_result = self.motor_controller.set_goal_position(mid, pos)
                if write_result is False:
                    with self._runtime_lock:
                        self._motor_write_errors += 1
                        self._last_motor_write_error = getattr(self.motor_controller, "last_write_error", "motor_write_failed")
                else:
                    with self._runtime_lock:
                        self._last_motor_write_error = None
                self._motor_write_timing.record(
                    (time.perf_counter() - write_started) * 1000.0,
                    now=time.time(),
                    extra={"commands": len(motor_commands)},
                )
        self._control_loop_timing.record(
            (time.perf_counter() - loop_started) * 1000.0,
            now=time.time(),
            extra={"tracking": bool(self.is_tracking), "pose_fresh": bool(self._pose_fresh)},
        )

    def calibrate(self):
        if self.is_tracking:
            self.btn_track.click()

        if self.manual_adjust_active and self.has_connected_motors():
            self.motor_controller.enable_torque(config.YAW_MOTOR_ID, True)
            self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, True)
            self.manual_adjust_active = False
            self.apply_view_state()

        self.refresh_tracking_start_record()
        home_pose_deg = tracking_start_steps_to_degrees(self.tracking_start_pose)
        home_steps = self.current_tracking_start_commands()

        if self.has_connected_motors():
            self.motor_controller.set_goal_positions(home_steps)
            self.lbl_robot_yaw.setText(f"{home_pose_deg['yaw']:.1f}°")
            self.lbl_robot_pitch.setText(f"{home_pose_deg['pitch']:.1f}°")
        else:
            QMessageBox.warning(
                self,
                "Warning",
                "Motors not connected. Calibration will only affect software offsets.",
            )

        msg = QMessageBox()
        msg.setWindowTitle("Initial Calibration")
        msg.setText(
            "<b>Step 1: Robot Centering</b><br>Motors have been moved to the saved Home position.<br><br>"
            "<b>Step 2: Alignment</b><br>Please look straight ahead and ensure the ZED camera is level.<br><br>"
            "Click <b>OK</b> to capture zero poses."
        )
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )

        if msg.exec() == QMessageBox.StandardButton.Ok:
            self.retargeter.trigger_calibration()
            self.btn_track.click()
            QMessageBox.information(self, "Success", "Calibration complete. Tracking started.")

    def reset_calibration(self):
        self.retargeter.reset_calibration()

    def shutdown(self):
        self._stop_control_worker()
