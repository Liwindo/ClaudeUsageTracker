"""Config loading, validation, and auto-migration."""

import tomllib

from claude_usage_monitor.config import Config

ALL_KEYS = {
    "poll_interval_seconds", "notification_thresholds", "firefox_profile_path",
    "log_level", "user_agent", "update_check", "skip_update_version", "autostart",
}


def test_first_run_writes_all_options(tmp_path):
    path = tmp_path / "config.toml"
    Config.load(path)
    written = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(written) == ALL_KEYS


def test_migration_appends_missing_keys_and_preserves_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(
        b'poll_interval_seconds = 60\n'
        b'notification_thresholds = [70]\n'
        b'log_level = "INFO"\n'
    )
    cfg = Config.load(path)
    migrated = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(migrated) == ALL_KEYS
    assert migrated["poll_interval_seconds"] == 60
    assert migrated["notification_thresholds"] == [70]
    assert migrated["log_level"] == "INFO"
    assert migrated["update_check"] is True
    assert cfg.update_check is True


def test_complete_file_is_not_rewritten(tmp_path):
    path = tmp_path / "config.toml"
    Config.load(path)  # creates a complete file
    mtime = path.stat().st_mtime_ns
    Config.load(path)
    assert path.stat().st_mtime_ns == mtime


def test_poll_interval_is_floored_at_10(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"poll_interval_seconds = 0\n")
    assert Config.load(path).poll_interval_seconds == 10


def test_scalar_thresholds_fall_back_to_defaults(tmp_path):
    # "80" would iterate character-wise into [8, 0] (threshold 0 fires on
    # every poll) and a bare 80 would raise TypeError and block startup.
    for raw in (b'notification_thresholds = "80"\n',
                b'notification_thresholds = 80\n'):
        path = tmp_path / "config.toml"
        path.write_bytes(raw)
        assert Config.load(path).notification_thresholds == [80, 95]


def test_string_thresholds_are_coerced_to_int(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b'notification_thresholds = ["80", "95"]\n')
    assert Config.load(path).notification_thresholds == [80, 95]


def test_new_options_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = Config(
        user_agent="UA", update_check=False,
        skip_update_version="2.0.0", autostart=True, _path=path,
    )
    cfg.save()
    loaded = Config.load(path)
    assert loaded.user_agent == "UA"
    assert loaded.update_check is False
    assert loaded.skip_update_version == "2.0.0"
    assert loaded.autostart is True
