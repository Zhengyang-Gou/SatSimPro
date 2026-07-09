"""Background worker for remote one-click deployment."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from .config import (
    DEFAULT_REMOTE_DEPLOY_SCRIPT,
    build_ssh_command,
    sudo_password_from_env_or_file,
)


class RemoteDeployWorker(QObject):
    """Run the remote deployment script without blocking the GUI thread."""

    finished = Signal(bool, str)

    def __init__(
        self,
        *,
        ssh_host_alias: Optional[str] = None,
        remote_script: str = DEFAULT_REMOTE_DEPLOY_SCRIPT,
        sudo_password: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.ssh_host_alias = ssh_host_alias
        self.remote_script = remote_script
        self.sudo_password = sudo_password
        self._process: Optional[subprocess.Popen[str]] = None
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        password = self._read_sudo_password()
        command = build_ssh_command(
            f"sudo -S -p '' bash {self.remote_script}",
            self.ssh_host_alias,
        )

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
            )
        except Exception as exc:
            if self._cancelled:
                self.finished.emit(False, "Deploy 已取消")
            else:
                self.finished.emit(False, f"Deploy 启动失败：{exc}")
            return
        finally:
            process = self._process
            self._process = None

        returncode = process.returncode if process is not None else 1
        output = (output or "").strip()
        if self._cancelled:
            self.finished.emit(False, "Deploy 已取消")
        elif returncode == 0:
            self.finished.emit(True, output or "部署完成")
        else:
            self.finished.emit(False, output or f"Deploy 失败，退出码 {returncode}")

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
