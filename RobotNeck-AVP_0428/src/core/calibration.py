import json
import os


class TrackingStartPoseCalibration:
    def __init__(self, path, default_yaw_step, default_pitch_step):
        self.path = str(path)
        self.default = {
            "yaw_start_step": int(default_yaw_step),
            "pitch_start_step": int(default_pitch_step),
        }

    def load(self):
        if not os.path.exists(self.path):
            return dict(self.default)

        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return dict(data.get("current", self.default))

    def save(self, yaw_start_step, pitch_start_step):
        current = self.load()
        payload = {
            "current": {
                "yaw_start_step": int(yaw_start_step),
                "pitch_start_step": int(pitch_start_step),
            },
            "previous": current,
        }
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return dict(payload["current"])

    def rollback(self):
        if not os.path.exists(self.path):
            return dict(self.default)

        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        previous = dict(data.get("previous", self.default))
        payload = {
            "current": previous,
            "previous": dict(data.get("current", self.default)),
        }
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return previous


class AVPConnectionCalibration:
    def __init__(self, path, default_ip, default_auto_reconnect=False):
        self.path = str(path)
        self.default = {
            "ip": str(default_ip),
            "auto_reconnect": bool(default_auto_reconnect),
        }

    def load(self):
        if not os.path.exists(self.path):
            return dict(self.default)

        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return dict(data.get("current", self.default))

    def save(self, ip, auto_reconnect):
        current = self.load()
        payload = {
            "current": {
                "ip": str(ip),
                "auto_reconnect": bool(auto_reconnect),
            },
            "previous": current,
        }
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return dict(payload["current"])

    def rollback(self):
        if not os.path.exists(self.path):
            return dict(self.default)

        with open(self.path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        previous = dict(data.get("previous", self.default))
        payload = {
            "current": previous,
            "previous": dict(data.get("current", self.default)),
        }
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return previous
