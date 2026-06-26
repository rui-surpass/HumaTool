import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)


from src.core.avp_connection import (
    get_avp_connection_store,
    load_avp_connection_settings,
    rollback_avp_connection_settings,
    save_avp_connection_settings,
)


def test_avp_connection_settings_default_to_config_ip_and_auto_reconnect_off(tmpdir):
    path = tmpdir.join("avp_connection.json")

    loaded = load_avp_connection_settings(path)

    assert loaded["ip"]
    assert loaded["auto_reconnect"] is False


def test_avp_connection_settings_save_keeps_current_and_previous(tmpdir):
    path = tmpdir.join("avp_connection.json")

    save_avp_connection_settings("172.20.10.2", False, path)
    saved = save_avp_connection_settings("192.168.0.12", True, path)
    record = get_avp_connection_store(path)

    assert saved == {"ip": "192.168.0.12", "auto_reconnect": True}
    assert record.load() == saved


def test_avp_connection_settings_rollback_restores_previous_record(tmpdir):
    path = tmpdir.join("avp_connection.json")

    save_avp_connection_settings("172.20.10.2", False, path)
    save_avp_connection_settings("192.168.0.12", True, path)
    rolled_back = rollback_avp_connection_settings(path)

    assert rolled_back == {"ip": "172.20.10.2", "auto_reconnect": False}
