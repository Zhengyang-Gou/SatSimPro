from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from core.experiment import config_digest, experiment_config, validate_remote_experiments
from core.strategies import GridDeltaStrategy
from gui.config import backend_configs_from_env
from gui.backend_lifecycle_worker import RemoteBackendLifecycleWorker


@pytest.fixture
def experiment():
    walker = dict(orbit_num=60, sat_per_orbit=20, phase_factor=0, altitude_km=550,
                  inclination_deg=53, epoch_time=datetime(2026, 1, 1))
    strategy = GridDeltaStrategy()
    config = experiment_config(**walker, start_time=walker["epoch_time"] + timedelta(seconds=30),
                               step_duration_sec=10, time_slices=60, strategy=strategy)
    backends = backend_configs_from_env()
    details = {b.name: {"manifest": dict(
        host=b.name, orbit_start=b.orbit_start, orbit_end=b.orbit_end,
        run_id="test-run", config_digest=config_digest(config), experiment=deepcopy(config),
    )} for b in backends}
    return details, dict(backends=backends, walker=walker, strategy=strategy,
                         step_duration_sec=10, time_slices=60)


def test_agreed_dataset_start_drives_playback(experiment):
    details, kwargs = experiment
    assert validate_remote_experiments(details, **kwargs) == datetime(2026, 1, 1, 0, 0, 30)


@pytest.mark.parametrize("key,value", [
    ("altitude_km", 508.0), ("inclination_deg", 55.0), ("phase_factor", 1),
    ("epoch_time", "2026-01-02T00:00:00.000000+00:00"),
    ("step_duration_sec", 20.0), ("latitude_fuse_enabled", True),
    ("strategy", "other"), ("time_slices", 20),
])
def test_rejects_matching_shape_with_different_experiment(experiment, key, value):
    details, kwargs = experiment
    for item in details.values():
        manifest = item["manifest"]
        manifest["experiment"][key] = value
        manifest["config_digest"] = config_digest(manifest["experiment"])
    with pytest.raises(ValueError):
        validate_remote_experiments(details, **kwargs)


@pytest.mark.parametrize("mutation", ["missing", "legacy", "digest", "run", "host"])
def test_rejects_incomplete_or_mixed_backend_packages(experiment, mutation):
    details, kwargs = experiment
    manifest = details["gzy1"]["manifest"]
    if mutation == "missing":
        del details["gzy1"]
    elif mutation == "legacy":
        del manifest["experiment"]
    elif mutation == "digest":
        manifest["config_digest"] = "wrong"
    elif mutation == "run":
        manifest["run_id"] = "another-run"
    else:
        manifest["host"] = "gzy0"
    with pytest.raises(ValueError):
        validate_remote_experiments(details, **kwargs)


def test_health_parser_handles_invalid_manifest():
    parsed = RemoteBackendLifecycleWorker._parse_health_output("SATNET_MANIFEST={bad json")
    assert parsed["manifest"] is None


def test_remote_run_must_match_explicitly_loaded_dataset(experiment):
    details, kwargs = experiment
    kwargs["expected_identity"] = ("different-run", details["gzy0"]["manifest"]["config_digest"])
    with pytest.raises(ValueError, match="本地载入"):
        validate_remote_experiments(details, **kwargs)
