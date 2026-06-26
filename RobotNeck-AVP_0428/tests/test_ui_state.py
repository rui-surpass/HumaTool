from src.gui.ui_state import SystemSnapshot, derive_dashboard_state


def test_dashboard_state_keeps_camera_connect_independent_from_avp():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=False,
            camera_connected=False,
            motor_connected=False,
            streaming=False,
            tracking=False,
            pose_sample_valid=False,
            pose_sample_reason="idle",
        )
    )

    assert state.motor_action_label == "Connect Motor"
    assert state.motor_action_enabled is True
    assert state.avp_action_label == "Connect AVP"
    assert state.avp_action_enabled is True
    assert state.connect_camera_enabled is True
    assert state.stream_action_label == "Start Stream"
    assert state.stream_action_enabled is False
    assert "Connect AVP" in state.stream_action_reason
    assert state.tracking_action_label == "Start Tracking"
    assert state.tracking_action_enabled is False
    assert "Connect AVP" in state.tracking_action_reason
    assert state.recovery_title == "AVP not connected"
    assert state.recovery_detail == "Use Quick Actions > Device Actions to connect AVP."
    assert state.recovery_action_label == "Connect AVP"
    assert state.recovery_action == "connect_avp"
    assert state.recovery_action_enabled is False
    assert state.recovery_button_visible is False
    assert state.severity == "blocked"
    assert state.severity_label == "Blocked"


def test_dashboard_state_enables_tracking_before_stream_when_pose_and_motors_ready():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=False,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=True,
            pose_sample_reason="ready",
        )
    )

    assert state.hero_label == "Waiting for Camera"
    assert state.motor_action_label == "Disconnect Motor"
    assert state.motor_action_enabled is True
    assert state.avp_action_label == "Disconnect AVP"
    assert state.avp_action_enabled is True
    assert state.connect_camera_enabled is True
    assert state.stream_action_enabled is False
    assert "Connect the ZED camera" in state.stream_action_reason
    assert state.tracking_action_label == "Start Tracking"
    assert state.tracking_action_enabled is True
    assert state.tracking_action_reason == "Start neck tracking using the current Pose Control workflow."
    assert state.calibrate_action_label == "Move To Home And Calibrate"
    assert state.calibrate_action_enabled is True
    assert state.recovery_title == "Camera required for stream"
    assert state.recovery_action_label == "Connect Camera"
    assert state.recovery_action == "connect_camera"
    assert state.recovery_action_enabled is False
    assert state.recovery_button_visible is False
    assert state.severity == "blocked"


def test_dashboard_state_allows_stream_before_first_pose_when_camera_ready():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=False,
            streaming=False,
            tracking=False,
            pose_sample_valid=False,
            pose_sample_reason="waiting_first_sample",
        )
    )

    assert state.hero_label == "Ready to Stream"
    assert state.stream_action_label == "Start Stream"
    assert state.stream_action_enabled is True
    assert state.stream_action_reason == "Start the VisionPro stream using the connected camera."
    assert state.tracking_action_label == "Start Tracking"
    assert state.tracking_action_enabled is False
    assert "Connect the neck motors first." in state.tracking_action_reason
    assert state.recovery_title == "Waiting for first pose sample"
    assert "Video streaming can start now" in state.recovery_detail
    assert state.recovery_action_label == "Check AVP"
    assert state.recovery_button_visible is True
    assert state.severity == "warning"
    assert state.severity_label == "Warning"


def test_dashboard_state_allows_tracking_before_first_pose_when_avp_and_motors_ready():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=False,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=False,
            pose_sample_reason="waiting_first_sample",
        )
    )

    assert state.tracking_action_label == "Start Tracking"
    assert state.tracking_action_enabled is True
    assert state.tracking_action_reason == "Start neck tracking using the current Pose Control workflow."


def test_dashboard_state_disables_tracking_when_pose_control_blocks_it():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=True,
            pose_sample_reason="ready",
            tracking_blocked=True,
            tracking_block_reason="Finish manual adjust before starting tracking.",
        )
    )

    assert state.hero_label == "Tracking Blocked"
    assert state.tracking_action_enabled is False
    assert state.tracking_action_reason == "Finish manual adjust before starting tracking."
    assert state.recovery_title == "Tracking is temporarily blocked"
    assert state.severity == "warning"


def test_dashboard_state_switches_stream_and_tracking_actions_to_stop_modes():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=True,
            tracking=True,
            avp_session_mode="streaming",
            pose_sample_valid=True,
            pose_sample_reason="ready",
        )
    )

    assert state.motor_action_label == "Disconnect Motor"
    assert state.motor_action_enabled is False
    assert "Stop tracking" in state.motor_action_reason
    assert state.avp_action_label == "Disconnect AVP"
    assert state.avp_action_enabled is False
    assert "Stop tracking" in state.avp_action_reason
    assert state.stream_action_label == "Stop Stream"
    assert state.stream_action_enabled is True
    assert "Stop the active VisionPro stream" in state.stream_action_reason
    assert state.tracking_action_label == "Stop Tracking"
    assert state.tracking_action_enabled is True
    assert "Stop neck tracking" in state.tracking_action_reason
    assert state.calibrate_action_enabled is False
    assert state.recovery_title == "System online"
    assert state.recovery_action_label == "Check AVP"
    assert state.recovery_action == "check_avp"
    assert state.recovery_action_enabled is True
    assert state.recovery_button_visible is True
    assert state.severity == "ready"
    assert state.severity_label == "Ready"


def test_dashboard_state_recommends_retry_for_yaw_issue():
    state = derive_dashboard_state(
        SystemSnapshot(
            avp_connected=True,
            camera_connected=True,
            motor_connected=True,
            streaming=False,
            tracking=False,
            pose_sample_valid=True,
            pose_sample_reason="ready",
            yaw_inactive=True,
        )
    )

    assert state.hero_label == "Yaw Check"
    assert state.recovery_title == "Yaw input looks inactive"
    assert "switching to AVP + Stream" in state.recovery_detail
    assert state.recovery_action_label == "Check AVP"
    assert state.recovery_action == "check_avp"
    assert state.recovery_button_visible is True
    assert state.severity == "warning"
    assert state.severity_label == "Warning"
