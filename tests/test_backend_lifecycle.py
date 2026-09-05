import unittest
import json
import os
from pathlib import Path
import subprocess
import tempfile

from gui.backend_lifecycle_worker import (
    RemoteBackendLifecycleWorker,
    _cleanup_command,
)
from gui.config import backend_configs_from_env


class BackendLifecycleTests(unittest.TestCase):
    def test_health_script_reports_active_dataset_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            state = root / "state"
            commands = root / "commands"
            for folder in (data, state, commands):
                folder.mkdir()
            manifest = {"run_id": "active-run", "experiment": {"altitude_km": 550}}
            (data / "manifest.json").write_text(json.dumps(manifest))
            (state / "current_timeslice").write_text("0\n")
            (state / "deployment.env").write_text("session_id=owned\n")
            for name, body in {"docker": "echo S10101", "ovs-vsctl": "exit 0"}.items():
                executable = commands / name
                executable.write_text("#!/bin/sh\n" + body + "\n")
                executable.chmod(0o755)
            config = root / "host.env"
            config.write_text("\n".join([
                "SATNET_BACKEND=gzy0", "SATNET_ORBIT_START=1", "SATNET_ORBIT_END=1",
                "SATNET_NODES_PER_ORBIT=1", "SATNET_BRIDGE=test",
                f'SATNET_DATA_ROOT="{data}"', f'SATNET_STATE_DIR="{state}"',
                f'SATNET_PLATFORM_ROOT="{root}"',
            ]))
            environment = {**os.environ, "SATNET_HOST_CONFIG": str(config),
                           "PATH": str(commands) + os.pathsep + os.environ["PATH"]}
            result = subprocess.run(["bash", "backend/scripts/health.sh"],
                env=environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = RemoteBackendLifecycleWorker._parse_health_output(result.stdout)
            self.assertEqual(parsed["manifest"], manifest)
            self.assertEqual(parsed["session_id"], "owned")

    def test_health_output_is_parsed_for_session_and_counts(self):
        result = RemoteBackendLifecycleWorker._parse_health_output(
            "\n".join(
                [
                    "SATNET_BACKEND=gzy0",
                    "SATNET_SESSION_ID=session-123",
                    "SATNET_CONTAINER_COUNT=600",
                    "SATNET_EXPECTED_CONTAINERS=600",
                    "SATNET_HEALTH=deployed",
                ]
            )
        )

        self.assertEqual(result["health"], "deployed")
        self.assertEqual(result["session_id"], "session-123")
        self.assertEqual(result["container_count"], "600")
        self.assertEqual(result["expected_containers"], "600")

    def test_owned_cleanup_passes_session_without_force(self):
        backend = backend_configs_from_env()[0]

        command = _cleanup_command(
            backend,
            session_id="session-123",
            force=False,
        )

        self.assertEqual(command[-2], "s223@121.48.163.223")
        self.assertIn("SATNET_EXPECT_SESSION_ID=session-123", command[-1])
        self.assertIn("SATNET_FORCE_CLEANUP=0", command[-1])
        self.assertIn(backend.cleanup_script, command[-1])

    def test_manual_cleanup_is_explicitly_forced(self):
        backend = backend_configs_from_env()[1]

        command = _cleanup_command(
            backend,
            session_id="session-123",
            force=True,
        )

        self.assertIn("SATNET_FORCE_CLEANUP=1", command[-1])


if __name__ == "__main__":
    unittest.main()
