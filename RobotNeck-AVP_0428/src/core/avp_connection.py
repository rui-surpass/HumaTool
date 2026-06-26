from config import config
from src.core.calibration import AVPConnectionCalibration
from src.core.paths import get_avp_connection_path


def get_avp_connection_store(path=None):
    return AVPConnectionCalibration(
        path or get_avp_connection_path(),
        default_ip=getattr(config, "AVP_IP", ""),
        default_auto_reconnect=False,
    )


def load_avp_connection_settings(path=None):
    return get_avp_connection_store(path).load()


def save_avp_connection_settings(ip, auto_reconnect, path=None):
    return get_avp_connection_store(path).save(ip=ip, auto_reconnect=auto_reconnect)


def rollback_avp_connection_settings(path=None):
    return get_avp_connection_store(path).rollback()
