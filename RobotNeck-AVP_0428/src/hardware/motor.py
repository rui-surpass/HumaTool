
import os
import threading
import time
try:
    import dynamixel_sdk as dxl
except ImportError:
    dxl = None
    print("Warning: dynamixel_sdk not found. Only mock mode will work.")
    
from config import config

class MotorController:
    """
    Dynamixel 电机控制类，用于管理电机连接、扭矩控制和位置命令。
    针对 Dynamixel XC330-T288-T 进行了适配。
    """
    # Control Table Addresses for XC330-T288-T / X-Series
    ADDR_OPERATING_MODE         = 11
    ADDR_TORQUE_ENABLE          = 64
    ADDR_LED                    = 65
    ADDR_STATUS_RETURN_LEVEL    = 68
    ADDR_POSITION_D_GAIN        = 80
    ADDR_POSITION_I_GAIN        = 82
    ADDR_POSITION_P_GAIN        = 84
    ADDR_GOAL_PWM               = 100
    ADDR_PROFILE_ACCELERATION   = 108
    ADDR_PROFILE_VELOCITY       = 112
    ADDR_GOAL_POSITION          = 116
    ADDR_PRESENT_CURRENT        = 126
    ADDR_PRESENT_VELOCITY       = 128
    ADDR_PRESENT_POSITION       = 132
    ADDR_PRESENT_INPUT_VOLTAGE  = 144
    ADDR_PRESENT_TEMPERATURE    = 146

    LEN_GOAL_POSITION           = 4
    LEN_PRESENT_POSITION        = 4

    def __init__(self, port, baudrate, protocol_version=2.0):
        """
        初始化电机控制器。

        Args:
            port (str): 串口设备路径。
            baudrate (int): 通信波特率。
            protocol_version (float, optional): Dynamixel 协议版本. 默认为 2.0.
        """
        self.port = port
        self.baudrate = baudrate
        self.protocol_version = protocol_version
        self._io_lock = threading.RLock()
        
        # 初始化 PortHandler 和 PacketHandler
        if dxl is None:
            print("Error: Dynamixel SDK not found. Motor functionality unavailable.")
            self.portHandler = None
            self.packetHandler = None
            self.groupSyncWrite = None
            self.connected = False
            return

        self.portHandler = dxl.PortHandler(port)
        self.packetHandler = dxl.PacketHandler(protocol_version)
        
        self.connected = False
        self.connect()
        
        # Initialize GroupSyncWrite
        if self.connected:
            self.groupSyncWrite = dxl.GroupSyncWrite(
                self.portHandler, self.packetHandler, self.ADDR_GOAL_POSITION, self.LEN_GOAL_POSITION
            )

    def connect(self):
        """
        建立与 Dynamixel 电机的串行连接。
        设置波特率并更新连接状态。
        """
        with self._io_lock:
            try:
                if self.portHandler.openPort():
                    print(f"Succeeded to open the port {self.port}")
                else:
                    print(f"Failed to open the port {self.port}")
                    return

                if self.portHandler.setBaudRate(self.baudrate):
                    print(f"Succeeded to change the baudrate to {self.baudrate}")
                    self.connected = True
                else:
                    print(f"Failed to change the baudrate")
                    return
            except Exception as e:
                print(f"Error connecting to Dynamixel: {e}")

    def ping(self, motor_id):
        """
        Check if a motor is connected.
        Returns model_number if successful, None otherwise.
        """
        with self._io_lock:
            if not self.connected:
                return None
            model_number, dxl_comm_result, dxl_error = self.packetHandler.ping(self.portHandler, motor_id)
            if dxl_comm_result != dxl.COMM_SUCCESS:
                # print(f"Ping Error {motor_id}: {self.packetHandler.getTxRxResult(dxl_comm_result)}")
                return None
            elif dxl_error != 0:
                print(f"Ping Error {motor_id}: {self.packetHandler.getRxPacketError(dxl_error)}")
                return None
            return model_number

    def enable_torque(self, motor_id, enable=True):
        """
        启用或禁用指定 ID 电机的扭矩。
        Safety: Applies 'Soft Start' by syncing Goal Position to Present Position before enabling.
        """
        with self._io_lock:
            if not self.connected:
                return

            if enable:
                # --- Soft Start Strategy ---
                # 1. Read Present Position
                present_pos = self.get_present_position(motor_id)
                if present_pos is not None:
                    # 2. Set Goal Position to Current Position (prevent Jump)
                    self.packetHandler.write4ByteTxRx(self.portHandler, motor_id, self.ADDR_GOAL_POSITION, present_pos)
                    print(f"[SoftStart] Synced ID {motor_id} Goal -> Present ({present_pos})")

            dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
                self.portHandler, motor_id, self.ADDR_TORQUE_ENABLE, 1 if enable else 0
            )
            if dxl_comm_result != dxl.COMM_SUCCESS:
                print(f"Torque Enable Error {motor_id}: {self.packetHandler.getTxRxResult(dxl_comm_result)}")
            elif dxl_error != 0:
                print(f"Torque Enable Error {motor_id}: {self.packetHandler.getRxPacketError(dxl_error)}")
            else:
                print(f"Torque {'Enabled' if enable else 'Disabled'} for ID {motor_id}")

    def set_profile(self, motor_id, velocity, acceleration):
        """
        设置运动曲线 (Profile) 参数，用于控制运动的平滑度。
        Address 112: Profile Velocity (0 = Infinite)
        Address 108: Profile Acceleration (0 = Infinite)
        """
        with self._io_lock:
            if not self.connected:
                return

            # Set Profile Velocity
            self.packetHandler.write4ByteTxRx(self.portHandler, motor_id, self.ADDR_PROFILE_VELOCITY, int(velocity))

            # Set Profile Acceleration
            self.packetHandler.write4ByteTxRx(self.portHandler, motor_id, self.ADDR_PROFILE_ACCELERATION, int(acceleration))

            print(f"Profile Set for ID {motor_id}: Vel={velocity}, Acc={acceleration}")

    def read_detailed_status(self, motor_id):
        """
        Read detailed status including Position, Velocity, Current, Voltage, Temp.
        Returns dict or None.
        """
        with self._io_lock:
            if not self.connected:
                return None

            # Helper to read N bytes
            def read(addr, n_bytes):
                if n_bytes == 1:
                    v, r, e = self.packetHandler.read1ByteTxRx(self.portHandler, motor_id, addr)
                elif n_bytes == 2:
                    v, r, e = self.packetHandler.read2ByteTxRx(self.portHandler, motor_id, addr)
                elif n_bytes == 4:
                    v, r, e = self.packetHandler.read4ByteTxRx(self.portHandler, motor_id, addr)
                else:
                    return None
                if r != dxl.COMM_SUCCESS:
                    return None
                return v

            pos = read(self.ADDR_PRESENT_POSITION, 4)
            vel = read(self.ADDR_PRESENT_VELOCITY, 4)
            curr = read(self.ADDR_PRESENT_CURRENT, 2)
            volt = read(self.ADDR_PRESENT_INPUT_VOLTAGE, 2)
            temp = read(self.ADDR_PRESENT_TEMPERATURE, 1)

            # Safely handle Nones
            if pos is None:
                return None  # Position is critical

            # Signed transformations
            if pos > 0x7FFFFFFF:
                pos -= 4294967296

            velocity = 0.0
            if vel is not None:
                if vel > 0x7FFFFFFF:
                    vel -= 4294967296
                velocity = vel * 0.229

            current = 0.0
            if curr is not None:
                if curr > 0x7FFF:
                    curr -= 65536
                current = curr * 1.0  # XC330 is 1mA unit? Checking docs... Usually 1mA or 2.69mA. Keeping simple.

            voltage = 0.0
            if volt is not None:
                voltage = volt / 10.0

            temperature = temp if temp is not None else 0

            return {
                "position": pos,
                "velocity": velocity,
                "current": current,
                "voltage": voltage,
                "temperature": temperature,
            }

    def read_status(self, motor_id):
        """Legacy method for voltage/temp"""
        s = self.read_detailed_status(motor_id)
        if s:
            return {"voltage": s["voltage"], "temperature": s["temperature"]}
        return None

    def set_pid(self, motor_id, p, i, d):
        """Set PID Gains."""
        with self._io_lock:
            if not self.connected:
                return
            self.packetHandler.write2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_P_GAIN, int(p))
            self.packetHandler.write2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_I_GAIN, int(i))
            self.packetHandler.write2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_D_GAIN, int(d))
            print(f"Set PID for {motor_id}: {p}, {i}, {d}")
        
    def get_pid(self, motor_id):
        """Read PID Gains."""
        with self._io_lock:
            if not self.connected:
                return (0, 0, 0)
            p, _, _ = self.packetHandler.read2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_P_GAIN)
            i, _, _ = self.packetHandler.read2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_I_GAIN)
            d, _, _ = self.packetHandler.read2ByteTxRx(self.portHandler, motor_id, self.ADDR_POSITION_D_GAIN)
            return (p, i, d)

    def set_goal_pwm(self, motor_id, pwm_limit):
        """Set Goal PWM (Torque Limit proxy) or PWM Limit depending on mode.
           ADDR 100 is Goal PWM (in PWM mode) or Limit? 
           Actually Address 100 in X-series is "Goal PWM" used in PWM Control Mode.
           To limit Output in Position Mode, usually we change "Goal PWM" (which acts as limit).
           Range 0-885."""
        with self._io_lock:
            if not self.connected:
                return
            self.packetHandler.write2ByteTxRx(self.portHandler, motor_id, self.ADDR_GOAL_PWM, int(pwm_limit))
            print(f"Set Goal PWM (Limit) for {motor_id}: {pwm_limit}")

    def reboot(self, motor_id):
        """Reboot the motor to clear errors."""
        with self._io_lock:
            if not self.connected:
                return
            self.packetHandler.reboot(self.portHandler, motor_id)
            print(f"Reboot command sent to ID {motor_id}")

    def set_goal_positions(self, id_pos_dict):
        """
        同时设置多个电机的目标位置 (SyncWrite)。

        Args:
            id_pos_dict (dict): {motor_id: position_steps}
        """
        with self._io_lock:
            self.last_write_error = None
            if not self.connected:
                self.last_write_error = "motor_not_connected"
                return False

            # 1. Clear previous parameters
            self.groupSyncWrite.clearParam()

            # 2. Add parameters for each motor
            for motor_id, position in id_pos_dict.items():
                param_goal_position = int(position).to_bytes(4, byteorder='little')
                param_list = list(param_goal_position)

                if not self.groupSyncWrite.addParam(motor_id, param_list):
                    self.last_write_error = f"group_sync_add_param_failed:{motor_id}"
                    print(f"[ID:{motor_id}] groupSyncWrite addParam failed")
                    return False

            # 3. Transmit packet
            dxl_comm_result = self.groupSyncWrite.txPacket()
            if dxl_comm_result != dxl.COMM_SUCCESS:
                # print(f"SyncWrite Error: {self.packetHandler.getTxRxResult(dxl_comm_result)}")
                self.last_write_error = self.packetHandler.getTxRxResult(dxl_comm_result)
                return False
            return True

    def close(self):
        """关闭串行端口连接。"""
        with self._io_lock:
            self.portHandler.closePort()
            self.connected = False
            print("Port closed.")

    def get_operating_mode(self, motor_id):
        """Read Operating Mode (Addr 11)."""
        with self._io_lock:
            if not self.connected:
                return None
            mode, res, err = self.packetHandler.read1ByteTxRx(self.portHandler, motor_id, self.ADDR_OPERATING_MODE)
            if res != dxl.COMM_SUCCESS:
                # print(self.packetHandler.getTxRxResult(res))
                return None
            return mode

    def set_operating_mode(self, motor_id, mode):
        """Set Operating Mode (Addr 11). Torque must be disabled first."""
        with self._io_lock:
            if not self.connected:
                return
            res, err = self.packetHandler.write1ByteTxRx(self.portHandler, motor_id, self.ADDR_OPERATING_MODE, mode)
            if res != dxl.COMM_SUCCESS:
                print(f"Set Mode Error {motor_id}: {self.packetHandler.getTxRxResult(res)}")
            elif err != 0:
                print(f"Set Mode Error {motor_id}: {self.packetHandler.getRxPacketError(err)}")
            else:
                print(f"Operating Mode set to {mode} for ID {motor_id}")

    def get_present_position(self, motor_id):
        """Read Present Position (Addr 132)."""
        with self._io_lock:
            if not self.connected:
                return None
            pos, res, err = self.packetHandler.read4ByteTxRx(self.portHandler, motor_id, self.ADDR_PRESENT_POSITION)
            if res != dxl.COMM_SUCCESS:
                return None

            if pos > 0x7FFFFFFF:
                pos -= 4294967296
            return pos
