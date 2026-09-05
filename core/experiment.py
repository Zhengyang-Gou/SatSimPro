"""Versioned experiment metadata shared by export and remote playback."""

from datetime import datetime, timezone
import hashlib
import json
import math


def utc_text(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def experiment_config(*, orbit_num, sat_per_orbit, phase_factor, altitude_km,
                      inclination_deg, epoch_time, start_time, step_duration_sec,
                      time_slices, strategy, random_failure_enabled=False,
                      failure_probability=0.0, random_seed=42):
    return {
        "schema_version": 1,
        "orbit_num": int(orbit_num), "sat_per_orbit": int(sat_per_orbit),
        "phase_factor": int(phase_factor), "altitude_km": float(altitude_km),
        "inclination_deg": float(inclination_deg),
        "epoch_time": utc_text(epoch_time), "start_time": utc_text(start_time),
        "step_duration_sec": float(step_duration_sec), "time_slices": int(time_slices),
        "strategy": type(strategy).__name__,
        "latitude_fuse_enabled": bool(getattr(strategy, "latitude_fuse_enabled", False)),
        "latitude_threshold": float(getattr(strategy, "latitude_threshold", 70.0)),
        "random_failure_enabled": bool(random_failure_enabled),
        "failure_probability": float(failure_probability), "random_seed": int(random_seed),
    }


def config_digest(config):
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def read_experiment_config(manifest):
    """Validate a saved configuration before using it to create a constellation."""
    config = manifest.get("experiment") if isinstance(manifest, dict) else None
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("数据集缺少受支持的实验元信息，请重新导出。")
    if manifest.get("config_digest") != config_digest(config):
        raise ValueError("数据集配置摘要不匹配。")
    for key, low, high in (("orbit_num", 3, 99), ("sat_per_orbit", 3, 99),
                           ("phase_factor", 0, 1000), ("time_slices", 1, 1000000)):
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"数据集 {key} 无效。")
    for key, low, high in (("altitude_km", 100, 20000), ("inclination_deg", 0, 180),
                           ("step_duration_sec", .1, 3600), ("latitude_threshold", 0, 90)):
        value = config.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"数据集 {key} 无效。")
    if config.get("strategy") != "GridDeltaStrategy" or type(config.get("latitude_fuse_enabled")) is not bool:
        raise ValueError("数据集拓扑策略无效。")
    try:
        utc_text(config["epoch_time"])
        utc_text(config["start_time"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("数据集历元或起始时间无效。") from exc
    return dict(config)


def validate_remote_experiments(details, *, backends, walker, strategy,
                                step_duration_sec, time_slices, expected_identity=None):
    """Return the agreed dataset start, or reject missing/mismatched metadata."""
    expected = experiment_config(
        **{key: walker[key] for key in ("orbit_num", "sat_per_orbit", "phase_factor",
                                       "altitude_km", "inclination_deg", "epoch_time")},
        start_time=walker["epoch_time"], step_duration_sec=step_duration_sec,
        time_slices=time_slices, strategy=strategy,
    )
    agreed = None
    for backend in backends:
        manifest = details.get(backend.name, {}).get("manifest")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("experiment"), dict):
            raise ValueError(f"{backend.name} 缺少实验元信息，请更新后端脚本并部署重新导出的数据集。")
        actual = read_experiment_config(manifest)
        if any(key not in actual for key in expected):
            raise ValueError(f"{backend.name} 实验元信息不完整，请重新导出数据集。")
        digest = config_digest(actual)
        if manifest.get("config_digest") != digest:
            raise ValueError(f"{backend.name} 数据集配置摘要不匹配。")
        if (manifest.get("host") != backend.name
                or manifest.get("orbit_start") != backend.orbit_start
                or manifest.get("orbit_end") != backend.orbit_end):
            raise ValueError(f"{backend.name} 数据集主机归属或轨道范围不匹配。")
        identity = (manifest.get("run_id"), digest)
        if expected_identity is not None and identity != expected_identity:
            raise ValueError(f"{backend.name} 与本地载入的数据集运行编号或配置不同。")
        if not identity[0] or (agreed is not None and identity != agreed):
            raise ValueError("两台后端的数据集运行编号或配置不同。")
        agreed = identity
        for key in ("schema_version", "orbit_num", "sat_per_orbit", "phase_factor",
                    "altitude_km", "inclination_deg", "epoch_time", "step_duration_sec",
                    "strategy", "latitude_fuse_enabled", "latitude_threshold"):
            if actual[key] != expected[key]:
                raise ValueError(f"{backend.name} 的 {key} 不一致：远端={actual[key]}，本地={expected[key]}")
        count = actual["time_slices"]
        if not isinstance(count, int) or count < time_slices:
            raise ValueError(f"{backend.name} 数据集时间片不足：需要 {time_slices}，实际 {count}")
        if not isinstance(actual["step_duration_sec"], (int, float)) or not math.isfinite(actual["step_duration_sec"]):
            raise ValueError(f"{backend.name} 时间片周期无效。")
        start = datetime.fromisoformat(utc_text(actual["start_time"]))
    if agreed is None:
        raise ValueError("没有可用的远程后端。")
    return start.replace(tzinfo=None)
