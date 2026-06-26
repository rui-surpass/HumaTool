import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACKING_START_PATH = PROJECT_ROOT / "config" / "tracking_start_pose.json"
TRACKING_START_PATH_ENV = "ROBO_NECK_TRACKING_START_PATH"
DEFAULT_AVP_CONNECTION_PATH = PROJECT_ROOT / "config" / "avp_connection.json"
AVP_CONNECTION_PATH_ENV = "ROBO_NECK_AVP_CONNECTION_PATH"


def get_project_root():
    return str(PROJECT_ROOT)


def get_tracking_start_path():
    return os.getenv(TRACKING_START_PATH_ENV, str(DEFAULT_TRACKING_START_PATH))


def get_avp_connection_path():
    return os.getenv(AVP_CONNECTION_PATH_ENV, str(DEFAULT_AVP_CONNECTION_PATH))
