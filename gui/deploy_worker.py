"""Background worker for distributed one-click deployment."""

from __future__ import annotations

import shlex
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from .config import (
    RemoteBackend,
    backend_configs_from_env,
    build_ssh_command,
    sudo_password_for_backend,
    env_float,
)
from .output_text import decode_external_output
from .remote_process import RemoteProcessRunner


class RemoteDeployWorker(QObject):
    """Run every backend deployment concurrently without blocking the GUI."""

    finished = Signal(bool, object, str)

    def __init__(
        self,
        *,
        backends: Optional[Sequence[RemoteBackend]] = None,
        sudo_passwords: Optional[Dict[str, str]] = None,
        session_id: str = "",
        timeout_sec: Optional[float] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.backends = tuple(backends or backend_configs_from_env())
        self.sudo_passwords = dict(sudo_passwords or {})
        self.session_id = session_id
        self.timeout_sec = timeout_sec if timeout_sec is not None else env_float("SATNET_DEPLOY_TIMEOUT_SEC", 600.0, minimum=0.1)
        self._runner = RemoteProcessRunner()
        self._cancelled = self._runner.cancelled

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
            self.finished.emit(False, {}, f"并行部署启动失败：{exc}")
            return

        results.sort(key=lambda item: item[0])
        message = "\n".join(
            f"[{name}] {'完成' if ok else '失败'}{f'：{output}' if output else ''}"
            for name, ok, output in results
        )
        ok = bool(results) and all(result[1] for result in results) and not self._cancelled.is_set()
        details = {name: {"ok": success, "output": output, "session_id": self.session_id if success else ""}
                   for name, success, output in results}
        self.finished.emit(ok, details, message or "部署已取消")

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
                f"timeout --kill-after=2s {self.timeout_sec:g}s bash {shlex.quote(backend.deploy_script)}"
            ),
            backend=backend,
        )
        password_input = f"{password}\n".encode("utf-8") if password else b"\n"
        completed = self._runner.run(
            command, input=password_input, timeout=self.timeout_sec + 3.0,
        )
        output_bytes = completed.stdout
        returncode = completed.returncode

        output = decode_external_output(output_bytes)
        if self._cancelled.is_set():
            return backend.name, False, "已取消"
        if returncode == 0:
            return backend.name, True, self._tail(output)
        return backend.name, False, self._tail(output) or f"退出码 {returncode}"

    @Slot()
    def cancel(self) -> None:
        self._runner.cancel()

    def _tail(self, output: str, limit: int = 6) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return " | ".join(lines[-limit:])
