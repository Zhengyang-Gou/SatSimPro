"""Exercise Qt lifecycle behavior without a display, VTK rendering, or SSH."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication, QWidget

from gui import main_window
from gui.config import backend_configs_from_env
from gui.deploy_worker import RemoteDeployWorker
from gui.backend_lifecycle_worker import RemoteBackendLifecycleWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def spin(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(main_window, "Visualizer", QWidget)
    monkeypatch.setattr(main_window.MainWindow, "check_remote_deployment", lambda self: None)
    monkeypatch.setattr(main_window, "redis_config_from_env", lambda: {"enabled": False})
    instance = main_window.MainWindow()
    instance._show_result_dialog = Mock()
    yield instance
    if not instance._closing:
        instance.owned_backend_names.clear()
        instance._deployment_cleanup_candidates.clear()
        instance.close()
    spin(app, lambda: instance._close_ready)


def test_partial_deployment_preserves_successful_backend(window, monkeypatch):
    worker = RemoteDeployWorker(backends=backend_configs_from_env(), session_id=window.remote_session_id)
    monkeypatch.setattr(worker, "_run_backend", lambda b: (b.name, b.name == "gzy0", "result"))
    worker.finished.connect(window._handle_deploy_finished)
    worker.run()
    assert window.owned_backend_names == {"gzy0"}
    assert not window.deploy_completed


def test_load_saved_dataset_restores_epoch_and_slice_settings(window):
    from datetime import datetime, timedelta
    from core.experiment import config_digest, experiment_config
    from core.strategies import GridDeltaStrategy

    epoch = datetime(2026, 1, 1)
    config = experiment_config(orbit_num=3, sat_per_orbit=3, phase_factor=1,
        altitude_km=550, inclination_deg=53, epoch_time=epoch,
        start_time=epoch + timedelta(seconds=30), step_duration_sec=5,
        time_slices=12, strategy=GridDeltaStrategy(True, 65))
    window.loop = Mock()
    window._load_dataset_config({"experiment": config, "config_digest": config_digest(config)})
    assert window.calculator.epoch_time == epoch
    assert window.current_time == epoch + timedelta(seconds=30)
    assert window.remote_total_slices == 12
    assert window.remote_slice_timer.interval() == 5000
    assert window.strategy.latitude_fuse_enabled
    assert window.strategy.latitude_threshold == 65
    assert window.current_walker_config["phase_factor"] == 1


def test_close_waits_for_workers_and_cleans_owned_backend_asynchronously(window, app, monkeypatch):
    class SlowWorker(QObject):
        finished = Signal()

        def cancel(self):
            self.cancelled = True

        @Slot()
        def run(self):
            time.sleep(.25)
            self.finished.emit()

    worker = SlowWorker()
    thread = QThread(window)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit, Qt.DirectConnection)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(window._cleanup_export_worker)
    window.export_worker = worker
    window.export_worker_thread = thread
    window.owned_backend_names.add("gzy0")
    cleanup_calls = []

    def cleanup(self, backend):
        cleanup_calls.append((backend.name, self.force, self.session_id))
        time.sleep(.2)
        return backend.name, True, {}, "cleaned"

    monkeypatch.setattr(RemoteBackendLifecycleWorker, "_run_backend", cleanup)
    ticks = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: ticks.append(1))
    heartbeat.start(10)
    thread.start()
    started = time.monotonic()
    window.close()
    assert time.monotonic() - started < .1
    assert window._closing and not window._close_ready
    assert window.export_worker_thread is thread
    assert not cleanup_calls
    spin(app, lambda: window._close_ready)
    heartbeat.stop()
    assert len(ticks) >= 10
    assert cleanup_calls == [("gzy0", False, window.remote_session_id)]
    assert not window.owned_backend_names


def test_late_redis_result_after_stop_is_ignored(window):
    window.redis_query_seq = 10
    window.registry.apply_redis_delay = Mock()
    window.stop_remote_play()
    window._apply_redis_result(10, 0, {"delay": {(0, 1): 5}})
    window.registry.apply_redis_delay.assert_not_called()


def test_close_retains_busy_redis_thread_until_provider_is_closed(window, app, monkeypatch):
    from gui.redis_worker import RedisQueryWorker
    from threading import Event

    entered = Event()
    closed = Event()

    class Provider:
        def get_latest_link_metrics_many(self, *args):
            entered.set()
            time.sleep(.25)
            return {"delay": {}}

        def close(self):
            closed.set()

    provider = Provider()

    def get_provider(worker):
        worker.provider = provider
        return provider

    monkeypatch.setattr(RedisQueryWorker, "_provider", get_provider)
    window.start_redis_worker({"enabled": True})
    window.redis_query_requested.emit(1, 0, [], [])
    spin(app, entered.is_set)
    window.close()
    assert window._retiring_redis_threads
    assert not closed.is_set()
    spin(app, lambda: window._close_ready)
    assert closed.is_set()
    assert not window._retiring_redis_threads
