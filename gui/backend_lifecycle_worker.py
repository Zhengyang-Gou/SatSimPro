"""Background health checks and cleanup for distributed remote backends."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from .config import RemoteBackend, build_ssh_command
from .output_text import decode_external_output


def _remote_environment(backend: RemoteBackend) -> str:
    return (
        f"SATNET_BACKEND={shlex.quote(backend.name)} "
        f"SATNET_ORBIT_START={backend.orbit_start} "
        f"SATNET_ORBIT_END={backend.orbit_end} "
    )


def _cleanup_command(
    backend: RemoteBackend,
    *,
    session_id: str,
    force: bool,
) -> list[str]:
    remote_command = (
        "sudo -S -p '' env "
        + _remote_environment(backend)
        + f"SATNET_EXPECT_SESSION_ID={shlex.quote(session_id)} "
        + f"SATNET_FORCE_CLEANUP={'1' if force else '0'} "
        + f"bash {shlex.quote(backend.cleanup_script)}"
    )
    return build_ssh_command(remote_command, backend=backend)


def cleanup_backends_sync(
    backends: Sequence[RemoteBackend],
    *,
    sudo_passwords: Dict[str, str],
    session_id: str,
    timeout_sec: float = 120.0,
) -> Tuple[bool, str]:
    """Best-effort owned cleanup used while the application is closing."""

    def cleanup_one(backend: RemoteBackend) -> Tuple[str, bool, str]:
        password = sudo_passwords.get(backend.name, "")
        try:
            completed = subprocess.run(
                _cleanup_command(backend, session_id=session_id, force=False),
                input=(f"{password}\n" if password else "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_sec,
                check=False,
            )
        except Exception as exc:
            return backend.name, False, str(exc)
        output = decode_external_output(completed.stdout)
        return backend.name, completed.returncode == 0, output.strip()

    results = []
    with ThreadPoolExecutor(
        max_workers=max(1, len(backends)),
        thread_name_prefix="shutdown-cleanup",
    ) as executor:
        futures = [executor.submit(cleanup_one, backend) for backend in backends]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item[0])
    message = "\n".join(
        f"[{name}] {'完成' if ok else '失败'}{f'：{output}' if output else ''}"
        for name, ok, output in results
    )
    return bool(results) and all(item[1] for item in results), message


class RemoteBackendLifecycleWorker(QObject):
    """Check or clean every configured backend without blocking the GUI."""

    finished = Signal(str, bool, object, str)

    def __init__(
        self,
        operation: str,
        *,
        backends: Sequence[RemoteBackend],
        sudo_passwords: Optional[Dict[str, str]] = None,
        session_id: str = "",
        force: bool = False,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        if operation not in {"health", "cleanup"}:
            raise ValueError(f"unsupported backend lifecycle operation: {operation}")
        self.operation = operation
        self.backends = tuple(backends)
        self.sudo_passwords = dict(sudo_passwords or {})
        self.session_id = session_id
        self.force = force
        self._processes: Dict[str, subprocess.Popen[bytes]] = {}
        self._process_lock = threading.Lock()
        self._cancelled = threading.Event()

    @Slot()
    def run(self) -> None:
        results = []
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, len(self.backends)),
                thread_name_prefix=f"backend-{self.operation}",
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
                        results.append((name, False, {}, str(exc)))
        except Exception as exc:
            self.finished.emit(self.operation, False, {}, str(exc))
            return

        results.sort(key=lambda item: item[0])
        details = {
            name: {"ok": ok, **metadata, "output": output}
            for name, ok, metadata, output in results
        }
        message = "\n".join(
            f"[{name}] {'正常' if ok else '异常'}{f'：{output}' if output else ''}"
            for name, ok, _metadata, output in results
        )
        ok = bool(results) and all(item[1] for item in results)
        ok = ok and not self._cancelled.is_set()
        self.finished.emit(self.operation, ok, details, message)

    def _run_backend(
        self,
        backend: RemoteBackend,
    ) -> Tuple[str, bool, Dict[str, Any], str]:
        if self._cancelled.is_set():
            return backend.name, False, {}, "已取消"

        if self.operation == "health":
            remote_command = (
                "sudo -S -p '' env "
                + _remote_environment(backend)
                + f"bash {shlex.quote(backend.health_script)}"
            )
            command = build_ssh_command(remote_command, backend=backend)
            password = self.sudo_passwords.get(backend.name, "")
            password_input = (f"{password}\n" if password else "\n").encode("utf-8")
        else:
            command = _cleanup_command(
                backend,
                session_id=self.session_id,
                force=self.force,
            )
            password = self.sudo_passwords.get(backend.name, "")
            password_input = (f"{password}\n" if password else "\n").encode("utf-8")

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if password_input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **self._popen_process_group_kwargs(),
        )
        with self._process_lock:
            self._processes[backend.name] = process
        try:
            output_bytes, _ = process.communicate(input=password_input)
            returncode = process.returncode
        finally:
            with self._process_lock:
                self._processes.pop(backend.name, None)

        output = decode_external_output(output_bytes).strip()
        metadata = self._parse_health_output(output) if self.operation == "health" else {}
        if self._cancelled.is_set():
            return backend.name, False, metadata, "已取消"
        return backend.name, returncode == 0, metadata, self._tail(output)

    @staticmethod
    def _parse_health_output(output: str) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("SATNET_") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        return {
            "health": values.get("SATNET_HEALTH", "unknown"),
            "session_id": values.get("SATNET_SESSION_ID", ""),
            "container_count": values.get("SATNET_CONTAINER_COUNT", ""),
            "expected_containers": values.get("SATNET_EXPECTED_CONTAINERS", ""),
            "reasons": values.get("SATNET_REASONS", ""),
        }

    @Slot()
    def cancel(self) -> None:
        self._cancelled.set()
        with self._process_lock:
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                self._terminate_process(process)

    @staticmethod
    def _tail(output: str, limit: int = 8) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return " | ".join(lines[-limit:])

    @staticmethod
    def _popen_process_group_kwargs() -> dict:
        if sys.platform.startswith("win"):
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
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
