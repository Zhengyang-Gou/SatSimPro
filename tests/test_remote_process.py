from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time

import pytest

from gui.remote_process import RemoteCommandCancelled, RemoteProcessRunner


def test_command_input_survives_communicate_polling():
    result = RemoteProcessRunner().run(
        [sys.executable, "-c", "import sys,time; x=sys.stdin.read(); time.sleep(.25); print(x)"],
        input=b"test input", timeout=2,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b"test input"


def test_hung_process_times_out_and_is_reaped(monkeypatch):
    processes = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    with pytest.raises(TimeoutError):
        RemoteProcessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"], input=b"", timeout=.15,
        )
    assert processes[0].poll() is not None


def test_cancel_is_nonblocking_and_handles_inflight_process():
    runner = RemoteProcessRunner()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(runner.run,
            [sys.executable, "-c", "import time; time.sleep(30)"], input=b"", timeout=20)
        time.sleep(.15)
        started = time.monotonic()
        runner.cancel()
        assert time.monotonic() - started < .1
        with pytest.raises(RemoteCommandCancelled):
            future.result(timeout=2)
