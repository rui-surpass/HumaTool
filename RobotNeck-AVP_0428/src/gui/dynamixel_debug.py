import sys
import time
from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QComboBox, QPushButton, QLineEdit, QSlider, QMessageBox, QTextBrowser,
    QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from config import config
from src.hardware.motor import MotorController
from src.hardware.mock_motor import MockMotorController

class DxlDebugWidget(QWidget):
    """
    Widget for debugging Dynamixel Motors (Connect, Monitor, Control, Param Tuning).
    """
    motor_connected = pyqtSignal(object) # Emits MotorController instance or None

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.motor_controller = None
        self.monitoring = False
        self.mock_mode = False
        self._monitor_page_active = False
        
        self.init_ui()
        
        # Monitor Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.setInterval(50) # 50ms polling

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # 1. Connection Group
        grp_conn = QGroupBox("Connection")
        layout_conn = QHBoxLayout()
        grp_conn.setLayout(layout_conn)
        
        layout_conn.addWidget(QLabel("Port:"))
        self.combo_port = QComboBox()
        self.combo_port.addItems([config.DYNAMIXEL_PORT, "/dev/ttyUSB1", "COM3"])
        self.combo_port.setEditable(True)
        layout_conn.addWidget(self.combo_port)
        
        layout_conn.addWidget(QLabel("Baud:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems([str(config.BAUDRATE), "115200", "1000000", "57600"])
        layout_conn.addWidget(self.combo_baud)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setCheckable(True)
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.btn_connect.setStyleSheet("background-color: #e74c3c; color: white;") # Start Red (Disconnected)
        layout_conn.addWidget(self.btn_connect)
        
        main_layout.addWidget(grp_conn)

        # 2. Status Monitor Group
        grp_status = QGroupBox("Motor Status Monitor")
        layout_status = QGridLayout()
        grp_status.setLayout(layout_status)
        
        # Header
        layout_status.addWidget(QLabel("<b>Param</b>"), 0, 0)
        layout_status.addWidget(QLabel(f"<b>ID {config.YAW_MOTOR_ID} (Yaw)</b>"), 0, 1)
        layout_status.addWidget(QLabel(f"<b>ID {config.PITCH_MOTOR_ID} (Pitch)</b>"), 0, 2)
        
        # Rows: Position, Velocity, Current, Voltage, Temp
        self.labels_status = {}
        params = ["Position (deg)", "Velocity (rpm)", "Load (mA)", "Voltage (V)", "Temp (°C)"]
        for i, param in enumerate(params):
            row = i + 1
            layout_status.addWidget(QLabel(param), row, 0)
            
            lbl_yaw = QLineEdit("N/A")
            lbl_yaw.setReadOnly(True)
            lbl_pitch = QLineEdit("N/A")
            lbl_pitch.setReadOnly(True)
            
            layout_status.addWidget(lbl_yaw, row, 1)
            layout_status.addWidget(lbl_pitch, row, 2)
            
            self.labels_status[f"YAW_{i}"] = lbl_yaw
            self.labels_status[f"PITCH_{i}"] = lbl_pitch
            
        main_layout.addWidget(grp_status)

        # 3. Manual Control Group
        grp_control = QGroupBox("Manual Control")
        layout_control = QGridLayout()
        grp_control.setLayout(layout_control)
        
        # Jog Buttons
        btn_left = QPushButton("Left (Yaw+)")
        btn_right = QPushButton("Right (Yaw-)")
        btn_up = QPushButton("Up (Pitch-)")
        btn_down = QPushButton("Down (Pitch+)")
        
        # Wiring Jog
        btn_left.clicked.connect(lambda: self.jog(config.YAW_MOTOR_ID, 1))
        btn_right.clicked.connect(lambda: self.jog(config.YAW_MOTOR_ID, -1))
        btn_up.clicked.connect(lambda: self.jog(config.PITCH_MOTOR_ID, -1)) # Pitch direction depends on install
        btn_down.clicked.connect(lambda: self.jog(config.PITCH_MOTOR_ID, 1))

        layout_control.addWidget(btn_left, 0, 0)
        layout_control.addWidget(btn_right, 0, 1)
        layout_control.addWidget(btn_up, 1, 0)
        layout_control.addWidget(btn_down, 1, 1)

        # Torque Switch
        self.chk_torque = QCheckBox("Enable Torque")
        # Wiring Torque
        self.chk_torque.toggled.connect(self.on_torque_toggled)
        layout_control.addWidget(self.chk_torque, 0, 2, 1, 2)

        # Step Size
        layout_control.addWidget(QLabel("Step:"), 1, 2)
        self.combo_step = QComboBox()
        self.combo_step.addItems(["1 deg", "5 deg", "10 deg"])
        layout_control.addWidget(self.combo_step, 1, 3, 1, 2)
        
        # Absolute Move
        layout_control.addWidget(QLabel("Goal:"), 2, 0)
        self.input_goal = QLineEdit("0")
        layout_control.addWidget(self.input_goal, 2, 1)
        self.btn_go = QPushButton("GO")
        self.btn_go.clicked.connect(self.on_btn_go)
        layout_control.addWidget(self.btn_go, 2, 2)
        
        # Speed Slider
        layout_control.addWidget(QLabel("Speed (RPM):"), 3, 0)
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(0, 100)
        self.slider_speed.setValue(20) # Safe default
        self.slider_speed.sliderReleased.connect(self.update_motor_params)
        layout_control.addWidget(self.slider_speed, 3, 1, 1, 3)
        self.lbl_speed = QLabel("20 RPM")
        self.slider_speed.valueChanged.connect(lambda v: self.lbl_speed.setText(f"{v} RPM"))
        layout_control.addWidget(self.lbl_speed, 3, 4)

        main_layout.addWidget(grp_control)

        # 4. Param Tuning (PID + Torque Limit)
        grp_param = QGroupBox("Parameter Tuning")
        layout_param = QGridLayout()
        grp_param.setLayout(layout_param)
        
        # PID Sliders
        self.pid_sliders = {}
        for i, val in enumerate(["P", "I", "D"]):
            layout_param.addWidget(QLabel(f"{val} Gain:"), i, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 2000)
            if val == "P": slider.setValue(600)
            elif val == "I": slider.setValue(50)
            elif val == "D": slider.setValue(50)
            slider.sliderReleased.connect(self.update_motor_params)
            layout_param.addWidget(slider, i, 1)
            lbl = QLabel(str(slider.value()))
            slider.valueChanged.connect(lambda v, l=lbl: l.setText(str(v)))
            layout_param.addWidget(lbl, i, 2)
            self.pid_sliders[val] = slider

        # Torque Limit
        layout_param.addWidget(QLabel("Torque Limit (%):"), 3, 0)
        self.slider_torque = QSlider(Qt.Orientation.Horizontal)
        self.slider_torque.setRange(0, 100)
        self.slider_torque.setValue(100)
        self.slider_torque.sliderReleased.connect(self.update_motor_params)
        layout_param.addWidget(self.slider_torque, 3, 1)
        self.lbl_torque = QLabel("100%")
        self.slider_torque.valueChanged.connect(lambda v: self.lbl_torque.setText(f"{v}%"))
        layout_param.addWidget(self.lbl_torque, 3, 2)

        main_layout.addWidget(grp_param)

        # 5. Reset / Alarm
        grp_reset = QGroupBox("System & Alarm")
        layout_reset = QHBoxLayout()
        grp_reset.setLayout(layout_reset)
        
        self.btn_reset_zero = QPushButton("Zero Reset")
        self.btn_reset_zero.setStyleSheet("background-color: #e67e22; color: white;")
        self.btn_reset_zero.clicked.connect(self.on_reset_zero)
        
        self.btn_reboot = QPushButton("Reboot Motors")
        self.btn_reboot.setStyleSheet("background-color: #c0392b; color: white;")
        self.btn_reboot.clicked.connect(self.on_reboot)

        layout_reset.addWidget(self.btn_reset_zero)
        layout_reset.addWidget(self.btn_reboot)
        
        self.txt_alarm = QTextBrowser()
        self.txt_alarm.setMaximumHeight(60)
        layout_reset.addWidget(self.txt_alarm)
        
        main_layout.addWidget(grp_reset)

        self.apply_styles()

    def apply_styles(self):
        # Additional specific styles if needed
        pass

    def toggle_connection(self):
        if self.btn_connect.isChecked():
            # Connect
            port = self.combo_port.currentText()
            baud = int(self.combo_baud.currentText())
            try:
                if config.MOCK_MOTORS:
                    self.motor_controller = MockMotorController(port, baud)
                    self.txt_alarm.append("Connected to MOCK Motor Controller.")
                else:
                    self.motor_controller = MotorController(port, baud)
                
                if self.motor_controller.connected:
                    self.btn_connect.setText("Disconnect")
                    self.btn_connect.setStyleSheet("background-color: #2ecc71; color: white;")
                    self.txt_alarm.append("Connected successfully.")
                    
                    self.motor_connected.emit(self.motor_controller)

                    # Safety Init: Profile Acceleration to prevent Jerk
                    # Vel=0 (Max/Infinite), Acc=20 (Smooth)
                    safe_acc = 20 
                    safe_vel = 0
                    self.motor_controller.set_profile(config.YAW_MOTOR_ID, safe_vel, safe_acc)
                    self.motor_controller.set_profile(config.PITCH_MOTOR_ID, safe_vel, safe_acc)
                    
                    # Apply Default PID
                    self.motor_controller.set_pid(config.YAW_MOTOR_ID, 600, 50, 50)
                    self.motor_controller.set_pid(config.PITCH_MOTOR_ID, 600, 50, 50)
                    
                    self.txt_alarm.append(f"Safety Profile (Acc={safe_acc}) & PID (600/50/50) Applied")

                    # Init Defaults
                    self.chk_torque.setChecked(True) # Auto enable torque
                    # Actual enable called by signal or here? 
                    # Toggling check triggers signal if connected. 
                    # But if we just setChecked(True), let's ensure it fires or calls logic.
                    # Since controller connected just now, we should explicit call or rely on signal?
                    # Safer to explicit call if signal blocked, but signal is fine.
                    # self.on_torque_toggled(True) will be called if signal connected? 
                    # Yes, setChecked emits toggled if changed. Default is False?
                    # Let's verify defaults. QCheckBox default is unchecked.
                    self._sync_monitoring_timer()
                    
                else:
                    self.btn_connect.setChecked(False)
                    self.txt_alarm.append("Failed to connect (SDK Error).")
                    
            except Exception as e:
                self.btn_connect.setChecked(False)
                self.txt_alarm.append(f"Connection Exception: {e}")
        else:
            # Disconnect
            self._stop_monitoring_timer()
            
            # Auto Disable Torque
            if self.motor_controller:
                try:
                    self.motor_controller.enable_torque(config.YAW_MOTOR_ID, False)
                    self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, False)
                    self.txt_alarm.append("Torque Disabled before disconnect.")
                except:
                    pass
                self.motor_controller.close()
                self.motor_controller = None
            
            self.chk_torque.setChecked(False) # Reset UI
            self.motor_connected.emit(None) # Notify disconnection
            self.btn_connect.setText("Connect")
            self.btn_connect.setStyleSheet("background-color: #e74c3c; color: white;")
            self.txt_alarm.append("Disconnected.")

    def request_connection(self, should_connect):
        target = bool(should_connect)
        if bool(self.btn_connect.isChecked()) == target:
            return
        self.btn_connect.setChecked(target)
        self.toggle_connection()

    def start_monitoring(self):
        """Start status polling if connected."""
        self._monitor_page_active = True
        self._sync_monitoring_timer()

    def stop_monitoring(self):
        """Stop status polling."""
        self._monitor_page_active = False
        self._stop_monitoring_timer()

    def _stop_monitoring_timer(self):
        self.monitoring = False
        self.timer.stop()

    def _sync_monitoring_timer(self):
        should_run = bool(
            self._monitor_page_active
            and self.motor_controller
            and self.motor_controller.connected
        )
        self.monitoring = should_run
        if should_run:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def update_status(self):
        if not self.motor_controller: return
        
        for mid, prefix in [(config.YAW_MOTOR_ID, "YAW"), (config.PITCH_MOTOR_ID, "PITCH")]:
            status = self.motor_controller.read_detailed_status(mid)
            if status:
                # 0: Position
                steps = status['position']
                # Convert steps to degrees (approx) relative to zero
                # 0-4096 => 0-360. Zero at 2048.
                deg = (steps - 2048) * (360.0 / 4096.0)
                self.labels_status[f"{prefix}_0"].setText(f"{deg:.1f}° ({steps})")
                
                # 1: Velocity
                self.labels_status[f"{prefix}_1"].setText(f"{status['velocity']:.1f}")
                
                # 2: Current
                self.labels_status[f"{prefix}_2"].setText(f"{status['current']:.0f}")
                
                # 3: Voltage
                self.labels_status[f"{prefix}_3"].setText(f"{status['voltage']:.1f}")
                
                # 4: Temp
                temp = status['temperature']
                lbl_temp = self.labels_status[f"{prefix}_4"]
                lbl_temp.setText(f"{temp} °C")
                if temp > 60:
                    lbl_temp.setStyleSheet("background-color: red; color: white;")
                else:
                    lbl_temp.setStyleSheet("")
    
    def jog(self, motor_id, direction):
        if not self.motor_controller: return
        step_text = self.combo_step.currentText()
        step_deg = int(step_text.split(' ')[0])
        
        current_pos = self.motor_controller.get_present_position(motor_id)
        if current_pos is None: return
        
        # Convert deg to steps
        step_delta = int(step_deg * (4096.0 / 360.0)) * direction
        target_pos = current_pos + step_delta
        
        self.motor_controller.set_goal_positions({motor_id: target_pos})
        self.txt_alarm.append(f"Jog ID {motor_id} to {target_pos}")

    def on_btn_go(self):
        if not self.motor_controller: return
        try:
            val = float(self.input_goal.text())
            # Clamp
            if val < -90: val = -90
            if val > 90: val = 90
            
            # Convert to steps
            # 2048 + deg * (4096/360)
            target_yaw = 2048 + (val * 4096.0 / 360.0)
            target_pitch = 2048 + (val * 4096.0 / 360.0) # Simple both move for test
            
            # Smart move: only move checked/selected? 
            # For now move Yaw to target
            self.motor_controller.set_goal_positions({
                config.YAW_MOTOR_ID: int(target_yaw)
            })
            self.txt_alarm.append(f"Moving One to {val} deg")
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid Angle")

    def update_motor_params(self):
        if not self.motor_controller: return
        
        # PID
        p = self.pid_sliders["P"].value()
        i = self.pid_sliders["I"].value()
        d = self.pid_sliders["D"].value()
        
        self.motor_controller.set_pid(config.YAW_MOTOR_ID, p, i, d)
        self.motor_controller.set_pid(config.PITCH_MOTOR_ID, p, i, d)
        
        # Torque Limit
        limit = self.slider_torque.value()
        # Map 0-100% to 0-885 (Goal PWM limit usually around 885 max for X series)
        pwm_limit = int(limit * 885 / 100)
        self.motor_controller.set_goal_pwm(config.YAW_MOTOR_ID, pwm_limit)
        self.motor_controller.set_goal_pwm(config.PITCH_MOTOR_ID, pwm_limit)
        
        # Speed Profile
        rpm = self.slider_speed.value()
        # Convert RPM to internal unit? 
        # Unit is 0.229 RPM. 
        vel_unit = int(rpm / 0.229)
        # Use safer acceleration (e.g. 50) instead of 200
        acc_val = 50 
        self.motor_controller.set_profile(config.YAW_MOTOR_ID, vel_unit, acc_val)
        self.motor_controller.set_profile(config.PITCH_MOTOR_ID, vel_unit, acc_val)
        
        self.txt_alarm.append(f"Params Updated: PID={p}/{i}/{d}, Speed={rpm}rpm")

    def on_reset_zero(self):
        if not self.motor_controller: return
        self.motor_controller.set_goal_positions({
            config.YAW_MOTOR_ID: 2048,
            config.PITCH_MOTOR_ID: 2048
        })
        self.txt_alarm.append("Zero Reset Triggered.")

    def on_reboot(self):
        if not self.motor_controller: return
        self.motor_controller.reboot(config.YAW_MOTOR_ID)
        self.motor_controller.reboot(config.PITCH_MOTOR_ID)
        self.txt_alarm.append("Reboot Command Sent.")

    def on_torque_toggled(self, checked):
        if not self.motor_controller: return
        
        self.motor_controller.enable_torque(config.YAW_MOTOR_ID, checked)
        self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, checked)
        
        state = "Enabled" if checked else "Disabled"
        self.txt_alarm.append(f"Torque {state}.")

    def clean_shutdown(self):
        """Safely shut down: Stop Monitoring -> Disable Torque -> Close Port."""
        self._stop_monitoring_timer() # CRITICAL: Stop timer before closing port
        
        if self.motor_controller and self.motor_controller.connected:
            try:
                # Auto Disable Torque (User Request)
                self.motor_controller.enable_torque(config.YAW_MOTOR_ID, False)
                self.motor_controller.enable_torque(config.PITCH_MOTOR_ID, False)
                print("[DxlDebug] Torque Disabled on Shutdown.")
            except Exception as e:
                print(f"[DxlDebug] Error disabling torque on shutdown: {e}")
            
            self.motor_controller.close()
            self.motor_controller = None
            print("[DxlDebug] Port Closed.")
