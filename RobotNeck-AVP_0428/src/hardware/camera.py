import config.config as config
import numpy as np

from src.utils.rotation import quaternion_to_euler_yxz

try:
    import cv2

    HAS_OPENCV = True
except ImportError:
    cv2 = None
    HAS_OPENCV = False

try:
    import pyzed.sl as sl

    HAS_ZED_SDK = True
except ImportError:
    sl = None
    HAS_ZED_SDK = False


def _resolution_text(width, height):
    return f"{int(width)}x{int(height)}"


def _camera_capabilities(
    supports_manual_focus=False,
    supports_auto_focus=False,
    supports_depth_controls=False,
    supports_sensor_snapshot=False,
    supports_health_status=False,
    supports_streaming=False,
):
    return {
        "supports_manual_focus": bool(supports_manual_focus),
        "supports_auto_focus": bool(supports_auto_focus),
        "supports_depth_controls": bool(supports_depth_controls),
        "supports_sensor_snapshot": bool(supports_sensor_snapshot),
        "supports_health_status": bool(supports_health_status),
        "supports_streaming": bool(supports_streaming),
    }


def _default_device_info(
    backend,
    connected,
    sdk_available,
    model,
    serial_number,
    firmware_version,
    sensors_firmware_version,
    resolution,
    fps,
    capabilities,
):
    return {
        "backend": backend,
        "connected": bool(connected),
        "sdk_available": bool(sdk_available),
        "model": model,
        "serial_number": serial_number,
        "firmware_version": firmware_version,
        "sensors_firmware_version": sensors_firmware_version,
        "resolution": resolution,
        "fps": fps,
        "capabilities": dict(capabilities),
    }


def _default_sensor_snapshot(backend, supported):
    return {
        "backend": backend,
        "supported": bool(supported),
        "imu": {
            "available": False,
            "fresh": False,
            "rpy_rad": None,
            "angular_velocity_dps": None,
            "linear_acceleration_mps2": None,
        },
        "magnetometer": {
            "available": False,
            "fresh": False,
            "field_ut": None,
        },
        "barometer": {
            "available": False,
            "fresh": False,
            "pressure_hpa": None,
        },
    }


def _default_health_status(backend, supported):
    return {
        "backend": backend,
        "supported": bool(supported),
        "enabled": False,
        "low_image_quality": False,
        "low_lighting": False,
        "low_depth_reliability": False,
        "low_motion_sensors_reliability": False,
        "last_grab_status": "UNAVAILABLE",
    }


def _default_streaming_status(backend, supported):
    return {
        "backend": backend,
        "supported": bool(supported),
        "enabled": False,
        "codec": "N/A",
        "bitrate_kbps": 0,
        "port": 0,
        "last_error": "",
    }


def _vector_to_list(values):
    if values is None:
        return None
    return [float(v) for v in values]


if HAS_ZED_SDK:
    class TimestampHandler:
        """
        Helper class to handle sensor timestamps to ensure fresh data.
        Ref: zed-sdk-master/tutorials/7_sensor_data/python/sensor_data.py
        """

        def __init__(self):
            self.t_imu = sl.Timestamp()
            self.t_baro = sl.Timestamp()
            self.t_mag = sl.Timestamp()

        def is_new(self, sensor):
            if isinstance(sensor, sl.IMUData):
                new_ = sensor.timestamp.get_microseconds() > self.t_imu.get_microseconds()
                if new_:
                    self.t_imu = sensor.timestamp
                return new_
            if isinstance(sensor, sl.MagnetometerData):
                new_ = sensor.timestamp.get_microseconds() > self.t_mag.get_microseconds()
                if new_:
                    self.t_mag = sensor.timestamp
                return new_
            if isinstance(sensor, sl.BarometerData):
                new_ = sensor.timestamp.get_microseconds() > self.t_baro.get_microseconds()
                if new_:
                    self.t_baro = sensor.timestamp
                return new_
            return False


if HAS_ZED_SDK:
    class ZEDCameraWrapper:
        """
        ZED SDK wrapper for image capture, runtime settings, sensors and health state.
        """

        def __init__(self, fps=30, resolution_str=sl.RESOLUTION.AUTO, camera_id=0, target_width=0, target_height=0):
            self.zed = sl.Camera()
            self.init_params = sl.InitParameters()
            self.init_params.sdk_verbose = 1
            self.width = target_width
            self.height = target_height

            res_map = {
                "HD720": sl.RESOLUTION.HD720,
                "HD1080": sl.RESOLUTION.HD1080,
                "HD2K": sl.RESOLUTION.HD2K,
                "VGA": sl.RESOLUTION.VGA,
            }
            self.init_params.camera_resolution = res_map.get(resolution_str, sl.RESOLUTION.AUTO)
            self.init_params.camera_fps = fps
            self.init_params.coordinate_units = sl.UNIT.METER
            self.init_params.coordinate_system = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Y_UP
            if hasattr(self.init_params, "enable_image_validity_check"):
                self.init_params.enable_image_validity_check = 1

            self.runtime_parameters = sl.RuntimeParameters()
            self.sensors_data = sl.SensorsData()
            self.ts_handler = TimestampHandler()
            self.image_left = sl.Mat()
            self.image_right = sl.Mat()
            self.view_mode = sl.VIEW.SIDE_BY_SIDE
            self.is_opened = False
            self.last_grab_status = "NOT_STARTED"
            self.supports_manual_focus = hasattr(sl.VIDEO_SETTINGS, "FOCUS")
            self.supports_auto_focus = hasattr(sl.VIDEO_SETTINGS, "FOCUS_AUTO")
            self.last_sensor_snapshot = _default_sensor_snapshot("zed_sdk", True)
            self.last_health_status = _default_health_status("zed_sdk", hasattr(self.zed, "getHealthStatus"))
            self.streaming_status = _default_streaming_status("zed_sdk", True)
            self.open()

        def open(self):
            target_fps = self.init_params.camera_fps
            fallback_fps_list = [60, 30, 15]
            if target_fps in fallback_fps_list:
                fallback_fps_list.remove(target_fps)
            attempt_order = [target_fps] + fallback_fps_list

            for fps in attempt_order:
                print(f"[ZED SDK] Attempting to open at {fps} FPS...")
                self.init_params.camera_fps = fps
                err = self.zed.open(self.init_params)
                if err == sl.ERROR_CODE.SUCCESS:
                    print(f"[ZED SDK] Success! Opened at {fps} FPS.")
                    self.is_opened = True
                    break
                print(f"[ZED SDK] Failed to open at {fps} FPS: {err}")

            if not self.is_opened:
                print("[ZED SDK] Critical Error: Unable to open camera with any settings.")
                return

            info = self.zed.get_camera_information()
            print(f"[ZED SDK] Camera Initialized. Model: {info.camera_model}, SN: {info.serial_number}")

        def grab(self):
            if not self.is_opened:
                self.last_grab_status = "NOT_OPENED"
                return False, None

            err = self.zed.grab(self.runtime_parameters)
            self.last_grab_status = str(err)
            if err != sl.ERROR_CODE.SUCCESS:
                return False, None

            self.zed.retrieve_image(self.image_left, self.view_mode)
            frame = self.image_left.get_data()[:, :, :3]
            if self.width > 0 and self.height > 0:
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    if HAS_OPENCV:
                        interp = cv2.INTER_AREA if frame.shape[1] > self.width else cv2.INTER_CUBIC
                        frame = cv2.resize(frame, (self.width, self.height), interpolation=interp)

            if getattr(config, "ENABLE_SOFTWARE_SHARPENING", False) and HAS_OPENCV:
                kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
                frame = cv2.filter2D(frame, -1, kernel)

            return True, frame

        def get_imu_orientation(self):
            snapshot = self.get_sensor_snapshot()
            return snapshot["imu"]["rpy_rad"]

        def get_device_info(self):
            if not self.is_opened:
                return _default_device_info(
                    backend="zed_sdk",
                    connected=False,
                    sdk_available=True,
                    model="ZED",
                    serial_number="N/A",
                    firmware_version="N/A",
                    sensors_firmware_version="N/A",
                    resolution=_resolution_text(self.width, self.height),
                    fps=int(self.init_params.camera_fps),
                    capabilities=_camera_capabilities(
                        supports_manual_focus=self.supports_manual_focus,
                        supports_auto_focus=self.supports_auto_focus,
                        supports_depth_controls=True,
                        supports_sensor_snapshot=True,
                        supports_health_status=hasattr(self.zed, "getHealthStatus"),
                        supports_streaming=True,
                    ),
                )

            info = self.zed.get_camera_information()
            resolution = info.camera_configuration.resolution
            return _default_device_info(
                backend="zed_sdk",
                connected=True,
                sdk_available=True,
                model=str(info.camera_model),
                serial_number=info.serial_number,
                firmware_version=info.camera_configuration.firmware_version,
                sensors_firmware_version=info.sensors_configuration.firmware_version,
                resolution=_resolution_text(resolution.width, resolution.height),
                fps=int(info.camera_configuration.fps),
                capabilities=_camera_capabilities(
                    supports_manual_focus=self.supports_manual_focus,
                    supports_auto_focus=self.supports_auto_focus,
                    supports_depth_controls=True,
                    supports_sensor_snapshot=True,
                    supports_health_status=hasattr(self.zed, "getHealthStatus"),
                    supports_streaming=True,
                ),
            )

        def get_sensor_snapshot(self):
            snapshot = _default_sensor_snapshot("zed_sdk", True)
            snapshot["imu"].update(self.last_sensor_snapshot["imu"])
            snapshot["magnetometer"].update(self.last_sensor_snapshot["magnetometer"])
            snapshot["barometer"].update(self.last_sensor_snapshot["barometer"])

            if not self.is_opened:
                self.last_sensor_snapshot = snapshot
                return snapshot

            if self.zed.get_sensors_data(self.sensors_data, sl.TIME_REFERENCE.CURRENT) != sl.ERROR_CODE.SUCCESS:
                self.last_sensor_snapshot = snapshot
                return snapshot

            imu_data = self.sensors_data.get_imu_data()
            imu_fresh = self.ts_handler.is_new(imu_data)
            if imu_fresh or not snapshot["imu"]["available"]:
                q = imu_data.get_pose().get_orientation().get()
                yaw, pitch, roll = quaternion_to_euler_yxz([q[0], q[1], q[2], q[3]])
                snapshot["imu"] = {
                    "available": True,
                    "fresh": bool(imu_fresh),
                    "rpy_rad": [float(yaw), float(pitch), float(roll)],
                    "angular_velocity_dps": _vector_to_list(imu_data.get_angular_velocity()),
                    "linear_acceleration_mps2": _vector_to_list(imu_data.get_linear_acceleration()),
                }

            magnetometer_data = self.sensors_data.get_magnetometer_data()
            mag_fresh = self.ts_handler.is_new(magnetometer_data)
            if mag_fresh or not snapshot["magnetometer"]["available"]:
                snapshot["magnetometer"] = {
                    "available": True,
                    "fresh": bool(mag_fresh),
                    "field_ut": _vector_to_list(magnetometer_data.get_magnetic_field_calibrated()),
                }

            barometer_data = self.sensors_data.get_barometer_data()
            baro_fresh = self.ts_handler.is_new(barometer_data)
            if baro_fresh or not snapshot["barometer"]["available"]:
                snapshot["barometer"] = {
                    "available": True,
                    "fresh": bool(baro_fresh),
                    "pressure_hpa": float(barometer_data.pressure),
                }

            self.last_sensor_snapshot = snapshot
            return snapshot

        def get_health_status(self):
            status = _default_health_status("zed_sdk", hasattr(self.zed, "getHealthStatus"))
            status["last_grab_status"] = self.last_grab_status
            if not self.is_opened or not hasattr(self.zed, "getHealthStatus"):
                self.last_health_status = status
                return status

            try:
                health = self.zed.getHealthStatus()
                status.update(
                    {
                        "supported": True,
                        "enabled": bool(getattr(health, "enabled", False)),
                        "low_image_quality": bool(getattr(health, "low_image_quality", False)),
                        "low_lighting": bool(getattr(health, "low_lighting", False)),
                        "low_depth_reliability": bool(getattr(health, "low_depth_reliability", False)),
                        "low_motion_sensors_reliability": bool(
                            getattr(health, "low_motion_sensors_reliability", False)
                        ),
                    }
                )
            except Exception as exc:
                status["last_grab_status"] = f"{self.last_grab_status} / HEALTH_ERROR: {exc}"

            self.last_health_status = status
            return status

        def get_camera_settings(self, setting_name):
            settings_map = {
                "BRIGHTNESS": sl.VIDEO_SETTINGS.BRIGHTNESS,
                "CONTRAST": sl.VIDEO_SETTINGS.CONTRAST,
                "HUE": sl.VIDEO_SETTINGS.HUE,
                "SATURATION": sl.VIDEO_SETTINGS.SATURATION,
                "SHARPNESS": sl.VIDEO_SETTINGS.SHARPNESS,
                "GAIN": sl.VIDEO_SETTINGS.GAIN,
                "EXPOSURE": sl.VIDEO_SETTINGS.EXPOSURE,
                "WHITEBALANCE": sl.VIDEO_SETTINGS.WHITEBALANCE_TEMPERATURE,
                "AEC_AGC": sl.VIDEO_SETTINGS.AEC_AGC,
                "WHITEBALANCE_AUTO": sl.VIDEO_SETTINGS.WHITEBALANCE_AUTO,
            }
            if self.supports_manual_focus:
                settings_map["FOCUS"] = sl.VIDEO_SETTINGS.FOCUS
            if self.supports_auto_focus:
                settings_map["FOCUS_AUTO"] = sl.VIDEO_SETTINGS.FOCUS_AUTO

            setting = settings_map.get(setting_name.upper())
            if setting is None:
                return -1
            return self.zed.get_camera_settings(setting)

        def set_camera_settings(self, setting_name, value):
            settings_map = {
                "BRIGHTNESS": sl.VIDEO_SETTINGS.BRIGHTNESS,
                "CONTRAST": sl.VIDEO_SETTINGS.CONTRAST,
                "HUE": sl.VIDEO_SETTINGS.HUE,
                "SATURATION": sl.VIDEO_SETTINGS.SATURATION,
                "SHARPNESS": sl.VIDEO_SETTINGS.SHARPNESS,
                "GAIN": sl.VIDEO_SETTINGS.GAIN,
                "EXPOSURE": sl.VIDEO_SETTINGS.EXPOSURE,
                "WHITEBALANCE": sl.VIDEO_SETTINGS.WHITEBALANCE_TEMPERATURE,
                "AEC_AGC": sl.VIDEO_SETTINGS.AEC_AGC,
                "WHITEBALANCE_AUTO": sl.VIDEO_SETTINGS.WHITEBALANCE_AUTO,
            }
            if self.supports_manual_focus:
                settings_map["FOCUS"] = sl.VIDEO_SETTINGS.FOCUS
            if self.supports_auto_focus:
                settings_map["FOCUS_AUTO"] = sl.VIDEO_SETTINGS.FOCUS_AUTO

            setting = settings_map.get(setting_name.upper())
            if setting is None:
                print(f"[ZED SDK] Unknown setting: {setting_name}")
                return False

            self.zed.set_camera_settings(setting, int(value))
            if self.init_params.sdk_verbose:
                print(f"[ZED SDK] Set {setting_name} to {value}")
            return True

        def set_confidence_threshold(self, value):
            self.runtime_parameters.confidence_threshold = int(value)
            print(f"[ZED SDK] Set Confidence Threshold: {value}")

        def set_disparity_range(self, value):
            self.runtime_parameters.texture_confidence_threshold = int(value)
            print(f"[ZED SDK] Set Texture Confidence Threshold: {value}")

        def set_view_mode(self, mode_str):
            if "Stereo" in mode_str:
                self.view_mode = sl.VIEW.SIDE_BY_SIDE
            elif "Right" in mode_str:
                self.view_mode = sl.VIEW.RIGHT
            else:
                self.view_mode = sl.VIEW.LEFT
            print(f"[ZED SDK] Set View Mode: {self.view_mode}")

        def set_focus(self, value):
            if not self.supports_manual_focus:
                return False
            return self.set_camera_settings("FOCUS", value)

        def set_auto_focus(self, enabled):
            if not self.supports_auto_focus:
                return False
            return self.set_camera_settings("FOCUS_AUTO", 1 if enabled else 0)

        def enable_streaming(self, codec="H264", bitrate=8000, port=30000):
            if not self.is_opened:
                self.streaming_status["last_error"] = "Camera not opened."
                return False

            stream_params = sl.StreamingParameters()
            stream_params.codec = (
                sl.STREAMING_CODEC.H265 if codec == "H265" else sl.STREAMING_CODEC.H264
            )
            stream_params.bitrate = int(bitrate)
            stream_params.port = int(port)

            err = self.zed.enable_streaming(stream_params)
            if err == sl.ERROR_CODE.SUCCESS:
                self.streaming_status.update(
                    {
                        "enabled": True,
                        "codec": codec,
                        "bitrate_kbps": int(bitrate),
                        "port": int(port),
                        "last_error": "",
                    }
                )
                print(f"[ZED SDK] Streaming Enabled on port {port} ({codec}, {bitrate}Kbps)")
                return True

            self.streaming_status["last_error"] = str(err)
            print(f"[ZED SDK] Failed to enable streaming: {err}")
            return False

        def disable_streaming(self):
            if not self.is_opened:
                self.streaming_status["enabled"] = False
                return False
            self.zed.disable_streaming()
            self.streaming_status["enabled"] = False
            self.streaming_status["last_error"] = ""
            print("[ZED SDK] Streaming Disabled.")
            return True

        def get_streaming_status(self):
            return dict(self.streaming_status)

        def close(self):
            self.zed.close()


class CameraInterface:
    """
    Unified Camera Interface for ZED.
    Supports native ZED SDK if available, gracefully falls back to OpenCV.
    """

    def __init__(self, camera_id=config.ZED_CAMERA_ID, resolution=getattr(config, "STREAM_RESOLUTION", "1280x720"), fps=config.STREAM_FPS):
        self.camera_id = camera_id
        self.width, self.height = map(int, resolution.split("x"))
        self.fps = fps
        self.is_opened = False
        self.view_mode = "Stereo (SBS)"
        self.zed = None
        self.runtime_params = None
        self.mat = None
        self.cap = None
        self.streaming_status = _default_streaming_status("unavailable", False)

        if HAS_ZED_SDK and config.USE_ZED_SDK:
            print("ZED SDK detected. Attempting to initialize...")
            zed_res_str = "HD720"
            if self.width >= 4400:
                zed_res_str = "HD2K"
            elif self.width >= 3840:
                zed_res_str = "HD1080"
            elif self.width >= 2200:
                zed_res_str = "HD720"

            self.zed_wrapper = ZEDCameraWrapper(
                fps=fps,
                resolution_str=zed_res_str,
                camera_id=self.camera_id,
                target_width=self.width,
                target_height=self.height,
            )
            if self.zed_wrapper.is_opened:
                self.zed = self.zed_wrapper
                self.is_opened = True
                self.streaming_status = self.zed.get_streaming_status()
                print("[CameraInterface] Using ZED SDK for capture and IMU.")
                return

        self._init_opencv()

    def _init_opencv(self):
        if not HAS_OPENCV:
            print("OpenCV not available. Camera fallback disabled.")
            return

        print(f"Initializing Camera {self.camera_id} via OpenCV...")
        self.cap = cv2.VideoCapture(self.camera_id)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.is_opened = True
            actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"Camera Initialized: {actual_w}x{actual_h} @ {self.fps}FPS")
        else:
            print(f"Failed to open Camera {self.camera_id}")

    def _normalize_view_mode(self, mode):
        mode_text = str(mode or "Stereo (SBS)")
        if "Right" in mode_text:
            return "Right Eye"
        if "Left" in mode_text:
            return "Left Eye"
        return "Stereo (SBS)"

    def _apply_view_mode_to_frame(self, frame):
        mode = self._normalize_view_mode(self.view_mode)
        if mode == "Stereo (SBS)" or frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
            return frame

        width = int(frame.shape[1])
        if width < 2 or width % 2 != 0:
            return frame

        midpoint = width // 2
        if mode == "Right Eye":
            return frame[:, midpoint:, ...].copy()
        return frame[:, :midpoint, ...].copy()

    def read(self):
        if self.zed:
            return self.zed.grab()
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return ret, frame
            return ret, self._apply_view_mode_to_frame(frame)
        return False, None

    def get_imu_data(self):
        if self.zed:
            return self.zed.get_imu_orientation()
        return None

    def get_device_info(self):
        if self.zed:
            return self.zed.get_device_info()
        if self.cap:
            return _default_device_info(
                backend="opencv",
                connected=bool(self.is_opened),
                sdk_available=bool(HAS_ZED_SDK and config.USE_ZED_SDK),
                model="OpenCV / UVC Generic",
                serial_number="N/A",
                firmware_version="N/A",
                sensors_firmware_version="N/A",
                resolution=_resolution_text(self.width, self.height),
                fps=self.fps,
                capabilities=_camera_capabilities(),
            )
        return _default_device_info(
            backend="unavailable",
            connected=False,
            sdk_available=bool(HAS_ZED_SDK and config.USE_ZED_SDK),
            model="Camera unavailable",
            serial_number="N/A",
            firmware_version="N/A",
            sensors_firmware_version="N/A",
            resolution=_resolution_text(self.width, self.height),
            fps=self.fps,
            capabilities=_camera_capabilities(),
        )

    def get_sensor_snapshot(self):
        if self.zed:
            return self.zed.get_sensor_snapshot()
        return _default_sensor_snapshot(
            backend="opencv" if self.cap else "unavailable",
            supported=False,
        )

    def get_health_status(self):
        if self.zed:
            return self.zed.get_health_status()
        return _default_health_status(
            backend="opencv" if self.cap else "unavailable",
            supported=False,
        )

    def get_streaming_status(self):
        if self.zed:
            return self.zed.get_streaming_status()
        return _default_streaming_status(
            backend="opencv" if self.cap else "unavailable",
            supported=False,
        )

    def close(self):
        if self.zed:
            self.zed.close()
        if self.cap:
            self.cap.release()

    def set_brightness(self, value):
        if self.zed:
            return self.zed.set_camera_settings("BRIGHTNESS", value)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_BRIGHTNESS, value)
            print(f"Set Brightness: {value}")
            return True
        return False

    def set_contrast(self, value):
        if self.zed:
            return self.zed.set_camera_settings("CONTRAST", value)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_CONTRAST, value)
            print(f"Set Contrast: {value}")
            return True
        return False

    def set_exposure(self, value):
        if self.zed:
            return self.zed.set_camera_settings("EXPOSURE", value)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_EXPOSURE, value)
            print(f"Set Exposure: {value}")
            return True
        return False

    def set_gain(self, value):
        if self.zed:
            return self.zed.set_camera_settings("GAIN", value)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_GAIN, value)
            print(f"Set Gain: {value}")
            return True
        return False

    def set_whitebalance(self, value):
        if self.zed:
            return self.zed.set_camera_settings("WHITEBALANCE", value)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_WHITE_BALANCE_BLUE_U, value)
            print(f"Set White Balance: {value}")
            return True
        return False

    def set_auto_exposure(self, enabled):
        val = 1 if enabled else 0
        if self.zed:
            return self.zed.set_camera_settings("AEC_AGC", val)
        if self.cap:
            v4l2_auto = 3 if enabled else 1
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, v4l2_auto)
            print(f"Set Auto Exposure: {enabled} (V4L2 val: {v4l2_auto})")
            return True
        return False

    def set_auto_whitebalance(self, enabled):
        val = 1 if enabled else 0
        if self.zed:
            return self.zed.set_camera_settings("WHITEBALANCE_AUTO", val)
        if self.cap:
            self.cap.set(cv2.CAP_PROP_AUTO_WB, val)
            print(f"Set Auto White Balance: {enabled}")
            return True
        return False

    def set_confidence_threshold(self, value):
        if self.zed:
            self.zed.set_confidence_threshold(value)
            return True
        return False

    def set_disparity_range(self, value):
        if self.zed:
            self.zed.set_disparity_range(value)
            return True
        return False

    def set_view_mode(self, mode):
        self.view_mode = self._normalize_view_mode(mode)
        if self.zed:
            self.zed.set_view_mode(self.view_mode)
            return True
        if self.cap:
            print(f"[CameraInterface] Using OpenCV fallback preview mode: {self.view_mode}")
            return True
        return True

    def set_focus(self, value):
        if self.zed:
            return self.zed.set_focus(value)
        print("[CameraInterface] Manual focus is not supported in the current fallback backend.")
        return False

    def set_auto_focus(self, enabled):
        if self.zed:
            return self.zed.set_auto_focus(enabled)
        print("[CameraInterface] Auto focus is not supported in the current fallback backend.")
        return False

    def set_camera_settings(self, setting, value):
        if setting == "FOCUS":
            return self.set_focus(value)
        if self.zed:
            return self.zed.set_camera_settings(setting, value)
        print(f"[CameraInterface] Generic set_camera_settings({setting}, {value}) is unsupported.")
        return False

    def enable_streaming(self, codec="H264", bitrate=8000, port=30000):
        if self.zed:
            return self.zed.enable_streaming(codec, bitrate, port)
        return False

    def disable_streaming(self):
        if self.zed:
            return self.zed.disable_streaming()
        return False
