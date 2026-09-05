"""Background health checks and cleanup for distributed remote backends."""

from __future__ import annotations

import json
import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from .config import RemoteBackend, build_ssh_command, env_float
from .output_text import decode_external_output
from .remote_process import RemoteProcessRunner


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
    timeout_sec: float = 120.0,
) -> list[str]:
    remote_command = (
        "sudo -S -p '' env "
        + _remote_environment(backend)
        + f"SATNET_EXPECT_SESSION_ID={shlex.quote(session_id)} "
        + f"SATNET_FORCE_CLEANUP={'1' if force else '0'} "
        + f"timeout --kill-after=2s {timeout_sec:g}s bash {shlex.quote(backend.cleanup_script)}"
    )
    return build_ssh_command(remote_command, backend=backend)


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
        timeout_sec: Optional[float] = None,
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
        default_timeout = 20.0 if operation == "health" else 120.0
        self.timeout_sec = timeout_sec if timeout_sec is not None else env_float(
            f"SATNET_{operation.upper()}_TIMEOUT_SEC", default_timeout, minimum=0.1)
        self._runner = RemoteProcessRunner()
        self._cancelled = self._runner.cancelled

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
                + f"timeout --kill-after=2s {self.timeout_sec:g}s bash {shlex.quote(backend.health_script)}"
            )
            command = build_ssh_command(remote_command, backend=backend)
            password = self.sudo_passwords.get(backend.name, "")
        else:
            command = _cleanup_command(
                backend,
                session_id=self.session_id,
                force=self.force,
                timeout_sec=self.timeout_sec,
            )
            password = self.sudo_passwords.get(backend.name, "")

        password_input = f"{password}\n".encode("utf-8") if password else b"\n"
        completed = self._runner.run(
            command, input=password_input, timeout=self.timeout_sec + 3.0,
        )
        output_bytes = completed.stdout
        returncode = completed.returncode

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
        try:
            manifest = json.loads(values.get("SATNET_MANIFEST", "null"))
        except ValueError:
            manifest = None
        return {
            "manifest": manifest,
            "health": values.get("SATNET_HEALTH", "unknown"),
            "session_id": values.get("SATNET_SESSION_ID", ""),
            "container_count": values.get("SATNET_CONTAINER_COUNT", ""),
            "expected_containers": values.get("SATNET_EXPECTED_CONTAINERS", ""),
            "reasons": values.get("SATNET_REASONS", ""),
        }

    @Slot()
    def cancel(self) -> None:
        self._runner.cancel()

    @staticmethod
    def _tail(output: str, limit: int = 8) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return " | ".join(lines[-limit:])
