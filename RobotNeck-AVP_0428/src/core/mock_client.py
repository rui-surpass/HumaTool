import numpy as np


class MockAVPClient:
    """
    Mock AVP Client for testing without Vision Pro.
    """
    def __init__(self, ip=""):
        print("[Mock] AVP Client Initialized")
        self.ip = ip
        self.session_mode = "tracking_only"
        self.t = 0
        self.stream_resolution = "1280x720"
        self.stream_fps = 30
        self.stream_bitrate = 8192
        self.using_dummy_video = False
        self.frame_source = None
        self.connected = False

    def connect(self, ip=None, auto_reconnect=False, session_mode="tracking_only"):
        if ip:
            self.ip = ip
        self.session_mode = session_mode or "tracking_only"
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def retry_now(self):
        self.connected = True
        return True

    def get_connection_status(self):
        return {
            "state": "ready" if self.connected else "idle",
            "ip": self.ip,
            "auto_reconnect": False,
            "session_mode": self.session_mode,
            "last_error": None,
            "state_age_sec": 0.0,
            "last_sample_timestamp": None,
            "has_ever_received_pose": self.connected,
        }

    def get_pose_status(self):
        return {
            "valid": self.connected,
            "reason": "" if self.connected else "idle",
            "fresh": self.connected,
            "state_age_sec": 0.0,
        }

    def get_latest_head_pose(self):
        """Standard Mock Pose"""
        self.t += 0.1
        yaw = 0.5 * np.sin(self.t)
        pitch = 0.2 * np.cos(self.t)
        return yaw, pitch, 0.0

    def get_latest_head_pose_matrix(self):
        """Mock 4x4 Matrix"""
        self.t += 0.05
        yaw = 0.5 * np.sin(self.t)
        # pitch = 0.2 * np.cos(self.t) 
        
        cy, sy = np.cos(yaw), np.sin(yaw)
        rot = np.eye(4)
        rot[0,0] = cy;  rot[0,2] = sy
        rot[1,1] = 1
        rot[2,0] = -sy; rot[2,2] = cy
        return rot

    def start_video_stream(self, frame_source=None, resolution=None, fps=None, bitrate=None, stereo=True, latency="Balanced"):
        self.frame_source = frame_source
        self.session_mode = "streaming"
        print("[Mock] Video Stream Started")
        
    def stop_video_stream(self, close_camera=False):
        self.frame_source = None
        self.session_mode = "tracking_only"
        print("[Mock] Video Stream Stopped")

    def restart_video_stream(self, frame_source=None, resolution=None, fps=None, bitrate=None, stereo=True, latency="Balanced"):
        self.frame_source = frame_source
        print(f"[Mock] Restart Stream: {resolution} {fps} {bitrate}")

    def get_camera_imu(self):
        if self.frame_source and hasattr(self.frame_source, "get_imu_data"):
            return self.frame_source.get_imu_data()
        return 0.0, 0.0, 0.0

    def close(self):
        self.disconnect()
        self.stop_video_stream()
