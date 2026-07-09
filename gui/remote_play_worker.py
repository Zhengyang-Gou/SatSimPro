"""Background worker for one remote measurement time slice."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from .config import (
    DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC,
    DEFAULT_REMOTE_MEASURE_SCRIPT,
    DEFAULT_REMOTE_PROBE_COUNT,
    DEFAULT_REMOTE_PROBE_PPS,
    build_ssh_command,
    sudo_password_from_env_or_file,
)


class RemoteMeasureSliceWorker(QObject):
    """Execute one remote measure_slice.sh transaction."""

    finished = Signal(int, bool, str, float)

    def __init__(
        self,
        *,
        time_slice: int,
        ssh_host_alias: Optional[str] = None,
        remote_script: str = DEFAULT_REMOTE_MEASURE_SCRIPT,
        probe_count: int = DEFAULT_REMOTE_PROBE_COUNT,
        probe_pps: float = DEFAULT_REMOTE_PROBE_PPS,
        timeout_sec: float = DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC,
        sudo_password: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.time_slice = int(time_slice)
        self.ssh_host_alias = ssh_host_alias
        self.remote_script = remote_script
        self.probe_count = int(probe_count)
        self.probe_pps = float(probe_pps)
        self.timeout_sec = float(timeout_sec)
        self.sudo_password = sudo_password
        self._process: Optional[subprocess.Popen[str]] = None
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        password = self._read_sudo_password()
        command = build_ssh_command(
            (
                f"sudo -S -p '' timeout {self.timeout_sec:g}s bash {self.remote_script} "
                f"{self.time_slice} {self.probe_count} {self.probe_pps:g}"
            ),
            self.ssh_host_alias,
        )

        started_at = time.monotonic()
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **self._popen_process_group_kwargs(),
            )
            output, _ = self._process.communicate(
                input=f"{password}\n" if password else "\n",
                timeout=self.timeout_sec + 1.0,
            )
            returncode = self._process.returncode
        except subprocess.TimeoutExpired as exc:
            self.cancel()
            elapsed = time.monotonic() - started_at
            output = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
            message = output or f"时间片 {self.time_slice} 远端测量超过 {self.timeout_sec:g}s"
            self.finished.emit(self.time_slice, False, message, elapsed)
            return
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            if self._cancelled:
                self.finished.emit(self.time_slice, False, f"时间片 {self.time_slice} 已取消", elapsed)
            else:
                self.finished.emit(self.time_slice, False, f"时间片 {self.time_slice} 启动失败：{exc}", elapsed)
            return
        finally:
            self._process = None

        elapsed = time.monotonic() - started_at
        output = (output or "").strip()
        if self._cancelled:
            self.finished.emit(self.time_slice, False, f"时间片 {self.time_slice} 已取消", elapsed)
        elif returncode == 0:
            self.finished.emit(self.time_slice, True, output or f"时间片 {self.time_slice} 完成", elapsed)
        else:
            self.finished.emit(
                self.time_slice,
                False,
                output or f"时间片 {self.time_slice} 失败，退出码 {returncode}",
                elapsed,
            )

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._terminate_process(process)

    def _read_sudo_password(self) -> str:
        if self.sudo_password is not None:
            return self.sudo_password
        return sudo_password_from_env_or_file() or ""

    def _popen_process_group_kwargs(self) -> dict:
        if sys.platform.startswith("win"):
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
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
