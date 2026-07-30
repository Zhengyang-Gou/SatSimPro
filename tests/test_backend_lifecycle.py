import unittest

from gui.backend_lifecycle_worker import (
    RemoteBackendLifecycleWorker,
    _cleanup_command,
)
from gui.config import backend_configs_from_env


class BackendLifecycleTests(unittest.TestCase):
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

        self.assertEqual(command[-2], "gzy0")
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
