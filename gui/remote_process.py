"""Bounded subprocess I/O; cancellation never waits on the caller's thread."""

import os
import signal
import subprocess
import threading
import time


class RemoteCommandCancelled(RuntimeError):
    pass


class RemoteProcessRunner:
    def __init__(self):
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    def run(self, command, *, input, timeout):
        if self.cancelled.is_set():
            raise RemoteCommandCancelled("已取消")
        kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                  if os.name == "nt" else {"start_new_session": True})
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, **kwargs,
        )
        deadline = time.monotonic() + timeout
        pending_input = input
        completed = False
        try:
            while True:
                if self.cancelled.is_set():
                    raise RemoteCommandCancelled("已取消")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"远程命令超过 {timeout:g}s")
                try:
                    output, _ = process.communicate(
                        input=pending_input, timeout=min(0.1, remaining),
                    )
                    completed = True
                    return subprocess.CompletedProcess(command, process.returncode, output)
                except subprocess.TimeoutExpired:
                    pending_input = None
        finally:
            # This code runs on the worker, including cancellation escalation
            # and reaping. A killed SSH client is also bounded remotely by timeout.
            if not completed:
                self._signal(process, kill=False)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self._signal(process, kill=True)
                    process.wait()
            process.stdin.close()
            process.stdout.close()

    @staticmethod
    def _signal(process, *, kill):
        try:
            if os.name == "nt":
                process.kill() if kill else process.terminate()
            else:
                os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
        except ProcessLookupError:
            pass
