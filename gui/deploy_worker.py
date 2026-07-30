"""Background worker for distributed one-click deployment."""

from __future__ import annotations

import os
import signal
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from .config import (
    RemoteBackend,
    backend_configs_from_env,
    build_ssh_command,
    sudo_password_for_backend,
)
from .output_text import decode_external_output


class RemoteDeployWorker(QObject):
    """Run every backend deployment concurrently without blocking the GUI."""

    finished = Signal(bool, str)

    def __init__(
        self,
        *,
        backends: Optional[Sequence[RemoteBackend]] = None,
        sudo_passwords: Optional[Dict[str, str]] = None,
        session_id: str = "",
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.backends = tuple(backends or backend_configs_from_env())
        self.sudo_passwords = dict(sudo_passwords or {})
        self.session_id = session_id
        self._processes: Dict[str, subprocess.Popen[bytes]] = {}
        self._process_lock = threading.Lock()
        self._cancelled = threading.Event()

    @Slot()
    def run(self) -> None:
        results = []
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, len(self.backends)),
                thread_name_prefix="deploy",
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
            self.finished.emit(False, f"并行部署启动失败：{exc}")
            return

        results.sort(key=lambda item: item[0])
        message = "\n".join(
            f"[{name}] {'完成' if ok else '失败'}{f'：{output}' if output else ''}"
            for name, ok, output in results
        )
        ok = bool(results) and all(result[1] for result in results) and not self._cancelled.is_set()
        self.finished.emit(ok, message or "部署已取消")

    def _run_backend(self, backend: RemoteBackend) -> Tuple[str, bool, str]:
        if self._cancelled.is_set():
            return backend.name, False, "已取消"

        password = self.sudo_passwords.get(backend.name)
        if password is None:
            password = sudo_password_for_backend(backend) or ""
        command = build_ssh_command(
            (
                "sudo -S -p '' env "
                f"SATNET_BACKEND={backend.name} "
                f"SATNET_ORBIT_START={backend.orbit_start} "
                f"SATNET_ORBIT_END={backend.orbit_end} "
                f"SATNET_SESSION_ID={shlex.quote(self.session_id)} "
                f"bash {shlex.quote(backend.deploy_script)}"
            ),
            backend=backend,
        )
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
            output_bytes, _ = process.communicate(input=password_input)
            returncode = process.returncode
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

    def _tail(self, output: str, limit: int = 6) -> str:
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
