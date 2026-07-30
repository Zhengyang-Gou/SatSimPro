"""Background worker for one distributed remote measurement time slice."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from .config import (
    DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC,
    DEFAULT_REMOTE_PROBE_COUNT,
    DEFAULT_REMOTE_PROBE_LEAD_SEC,
    DEFAULT_REMOTE_PROBE_PPS,
    RemoteBackend,
    backend_configs_from_env,
    build_ssh_command,
    sudo_password_for_backend,
)
from .output_text import decode_external_output


class RemoteMeasureSliceWorker(QObject):
    """Execute one measure_slice transaction concurrently on every backend."""

    finished = Signal(int, bool, str, float)

    def __init__(
        self,
        *,
        time_slice: int,
        backends: Optional[Sequence[RemoteBackend]] = None,
        probe_count: int = DEFAULT_REMOTE_PROBE_COUNT,
        probe_pps: float = DEFAULT_REMOTE_PROBE_PPS,
        timeout_sec: float = DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC,
        probe_lead_sec: float = DEFAULT_REMOTE_PROBE_LEAD_SEC,
        sudo_passwords: Optional[Dict[str, str]] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.time_slice = int(time_slice)
        self.backends = tuple(backends or backend_configs_from_env())
        self.probe_count = int(probe_count)
        self.probe_pps = float(probe_pps)
        self.timeout_sec = float(timeout_sec)
        self.probe_lead_sec = float(probe_lead_sec)
        self.sudo_passwords = dict(sudo_passwords or {})
        self._processes: Dict[str, subprocess.Popen[bytes]] = {}
        self._process_lock = threading.Lock()
        self._cancelled = threading.Event()
        self.probe_start_epoch_ms = 0

    @Slot()
    def run(self) -> None:
        started_at = time.monotonic()
        self.probe_start_epoch_ms = int(
            (time.time() + self.probe_lead_sec) * 1000
        )
        results: List[Tuple[str, bool, str]] = []
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, len(self.backends)),
                thread_name_prefix="measure",
            ) as executor:
                futures = {
                    executor.submit(self._run_backend, backend): backend.name
                    for backend in self.backends
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        results.append((name, False, str(exc)))
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            self.finished.emit(self.time_slice, False, f"并行测量启动失败：{exc}", elapsed)
            return

        elapsed = time.monotonic() - started_at
        results.sort(key=lambda item: item[0])
        message = "\n".join(
            f"[{name}] {'完成' if ok else '失败'}{f'：{output}' if output else ''}"
            for name, ok, output in results
        )
        ok = bool(results) and all(result[1] for result in results) and not self._cancelled.is_set()
        if self._cancelled.is_set():
            message = message or f"时间片 {self.time_slice} 已取消"
        self.finished.emit(self.time_slice, ok, message, elapsed)

    def _run_backend(self, backend: RemoteBackend) -> Tuple[str, bool, str]:
        if self._cancelled.is_set():
            return backend.name, False, "已取消"

        password = self.sudo_passwords.get(backend.name)
        if password is None:
            password = sudo_password_for_backend(backend) or ""

        remote_command = (
            f"sudo -S -p '' env "
            f"SATNET_BACKEND={backend.name} "
            f"SATNET_ORBIT_START={backend.orbit_start} "
            f"SATNET_ORBIT_END={backend.orbit_end} "
            f"SATNET_PROBE_START_EPOCH_MS={self.probe_start_epoch_ms} "
            f"timeout {self.timeout_sec:g}s "
            f"bash {backend.measure_script} "
            f"{self.time_slice} {self.probe_count} {self.probe_pps:g} "
            f"{self.probe_start_epoch_ms}"
        )
        command = build_ssh_command(remote_command, backend=backend)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **self._popen_process_group_kwargs(),
        )
        with self._process_lock:
            self._processes[backend.name] = process

        try:
            password_input = f"{password}\n".encode("utf-8") if password else b"\n"
            output_bytes, _ = process.communicate(
                input=password_input,
                timeout=self.timeout_sec + 1.0,
            )
            returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            self._terminate_process(process)
            output = decode_external_output(exc.stdout)
            return backend.name, False, (output or f"超过 {self.timeout_sec:g}s").strip()
        finally:
            with self._process_lock:
                self._processes.pop(backend.name, None)

        output = decode_external_output(output_bytes)
        if self._cancelled.is_set():
            return backend.name, False, "已取消"
        if returncode == 0:
            return backend.name, True, self._tail(output)
        return backend.name, False, self._tail(output) or f"退出码 {returncode}"

    @Slot()
    def cancel(self) -> None:
        self._cancelled.set()
        with self._process_lock:
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                self._terminate_process(process)

    def _tail(self, output: str, limit: int = 4) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return " | ".join(lines[-limit:])

    def _popen_process_group_kwargs(self) -> dict:
        if sys.platform.startswith("win"):
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def _terminate_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if sys.platform.startswith("win"):
            process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            if sys.platform.startswith("win"):
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    process.kill()
