import threading
import time
import types

import src.hardware.motor as motor_module
from src.hardware.motor import MotorController


class CallTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def enter(self, name):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(name)
            self.entered.set()
        self.release.wait(timeout=1.0)

    def exit(self):
        with self.lock:
            self.active -= 1


def build_fake_dxl(tracker):
    class FakePortHandler:
        def __init__(self, port):
            self.port = port
            self.is_open = False
            self.closed = False

        def openPort(self):
            self.is_open = True
            return True

        def setBaudRate(self, baudrate):
            self.baudrate = baudrate
            return True

        def closePort(self):
            self.closed = True
            self.is_open = False

    class FakePacketHandler:
        def __init__(self, protocol_version):
            self.protocol_version = protocol_version

        def _read_value(self, addr):
            values = {
                132: 2048,
                128: 12,
                126: 33,
                144: 120,
                146: 41,
            }
            return values.get(addr, 0)

        def read1ByteTxRx(self, port_handler, motor_id, addr):
            tracker.enter("read1ByteTxRx")
            try:
                return self._read_value(addr), 0, 0
            finally:
                tracker.exit()

        def read2ByteTxRx(self, port_handler, motor_id, addr):
            tracker.enter("read2ByteTxRx")
            try:
                return self._read_value(addr), 0, 0
            finally:
                tracker.exit()

        def read4ByteTxRx(self, port_handler, motor_id, addr):
            tracker.enter("read4ByteTxRx")
            try:
                return self._read_value(addr), 0, 0
            finally:
                tracker.exit()

        def write1ByteTxRx(self, port_handler, motor_id, addr, value):
            return 0, 0

        def write2ByteTxRx(self, port_handler, motor_id, addr, value):
            return 0, 0

        def write4ByteTxRx(self, port_handler, motor_id, addr, value):
            return 0, 0

        def reboot(self, port_handler, motor_id):
            return 0, 0

        def ping(self, port_handler, motor_id):
            return 321, 0, 0

        def getTxRxResult(self, result):
            return f"[TxRxResult] {result}"

        def getRxPacketError(self, error):
            return f"[RxPacketError] {error}"

    class FakeGroupSyncWrite:
        def __init__(self, port_handler, packet_handler, addr, length):
            self.port_handler = port_handler
            self.packet_handler = packet_handler
            self.addr = addr
            self.length = length
            self.params = []

        def clearParam(self):
            self.params = []

        def addParam(self, motor_id, param_list):
            self.params.append((motor_id, list(param_list)))
            return True

        def txPacket(self):
            tracker.enter("txPacket")
            try:
                return 0
            finally:
                tracker.exit()

    return types.SimpleNamespace(
        COMM_SUCCESS=0,
        PortHandler=FakePortHandler,
        PacketHandler=FakePacketHandler,
        GroupSyncWrite=FakeGroupSyncWrite,
    )


def make_controller(monkeypatch, tracker):
    fake_dxl = build_fake_dxl(tracker)
    monkeypatch.setattr(motor_module, "dxl", fake_dxl)
    controller = MotorController("/dev/ttyUSB0", 57600)
    assert controller.connected is True
    return controller


def test_motor_controller_serializes_read_and_write(monkeypatch):
    tracker = CallTracker()
    controller = make_controller(monkeypatch, tracker)

    read_result = {}
    write_result = {}

    def read_worker():
        read_result["value"] = controller.read_detailed_status(1)

    def write_worker():
        write_result["value"] = controller.set_goal_positions({1: 2300})

    read_thread = threading.Thread(target=read_worker)
    write_thread = threading.Thread(target=write_worker)

    read_thread.start()
    assert tracker.entered.wait(timeout=1.0) is True

    write_thread.start()
    time.sleep(0.05)

    assert tracker.max_active == 1

    tracker.release.set()
    read_thread.join(timeout=1.0)
    write_thread.join(timeout=1.0)

    assert read_result["value"]["position"] == 2048
    assert write_result["value"] is True
    assert tracker.active == 0


def test_motor_controller_close_marks_disconnected(monkeypatch):
    tracker = CallTracker()
    controller = make_controller(monkeypatch, tracker)

    controller.close()

    assert controller.connected is False
    assert controller.set_goal_positions({1: 2048}) is False
    assert controller.last_write_error == "motor_not_connected"
