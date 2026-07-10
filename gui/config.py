"""Runtime configuration helpers for the GUI layer."""

import os
from typing import Any, Dict, List, Optional


def env_int(
    name: str,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return os.path.expanduser(default)
    return os.path.expanduser(value.strip())


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


DEFAULT_REDIS_HOST = env_str("SATNET_REDIS_HOST", "127.0.0.1")
DEFAULT_REDIS_PORT = env_int("SATNET_REDIS_PORT", 6379, minimum=1, maximum=65535)
DEFAULT_REDIS_DB = env_int("SATNET_REDIS_DB", 0, minimum=0)
DEFAULT_REDIS_KEY_PREFIX = env_str("SATNET_REDIS_KEY_PREFIX", "data")
DEFAULT_REDIS_LOSS_ENABLED = env_bool("SATNET_REDIS_LOSS_ENABLED", True)
DEFAULT_REDIS_LOSS_SCALE = env_float("SATNET_REDIS_LOSS_SCALE", 1.0, minimum=0.0)
DEFAULT_REDIS_SOCKET_TIMEOUT = env_float("SATNET_REDIS_SOCKET_TIMEOUT", 0.05, minimum=0.001)
DEFAULT_REMOTE_DEPLOY_SCRIPT = env_str("SATNET_REMOTE_DEPLOY_SCRIPT", "/home/s223/yzy/scripts/deploy.sh")
DEFAULT_REMOTE_MEASURE_SCRIPT = env_str("SATNET_REMOTE_MEASURE_SCRIPT", "/home/s223/yzy/scripts/measure_slice.sh")
DEFAULT_REMOTE_PROBE_COUNT = env_int("SATNET_REMOTE_PROBE_COUNT", 5, minimum=1)
DEFAULT_REMOTE_PROBE_PPS = env_float("SATNET_REMOTE_PROBE_PPS", 10.0, minimum=0.1)
DEFAULT_REMOTE_SLICE_DURATION_SEC = env_float("SATNET_REMOTE_SLICE_DURATION_SEC", 10.0, minimum=0.1)
DEFAULT_REMOTE_TIME_SLICES = env_int("SATNET_REMOTE_TIME_SLICES", 60, minimum=1)
DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC = env_float("SATNET_REMOTE_COMMAND_TIMEOUT_SEC", 10.0, minimum=0.1)
DEFAULT_SSH_HOST_ALIAS = env_str("SATNET_SSH_HOST_ALIAS", "")
DEFAULT_SSH_HOST = env_str("SATNET_SSH_HOST", "121.48.163.223")
DEFAULT_SSH_PORT = env_int("SATNET_SSH_PORT", 22, minimum=1, maximum=65535)
DEFAULT_SSH_USERNAME = env_str("SATNET_SSH_USERNAME", "s223")
DEFAULT_SSH_PRIVATE_KEY = env_str("SATNET_SSH_PRIVATE_KEY", "~/.ssh/id_ed25519_satellite_simulation")
DEFAULT_REDIS_PASSWORD_FILE = env_str(
    "SATNET_REDIS_PASSWORD_FILE",
    "~/.config/satellite-simulation/redis_password",
)
DEFAULT_SUDO_PASSWORD_FILE = env_str(
    "SATNET_SUDO_PASSWORD_FILE",
    "~/.config/satellite-simulation/sudo_password",
)


def build_ssh_command(remote_command: str, ssh_host_alias: Optional[str] = None) -> List[str]:
    """Build an ssh command that works without requiring a user ssh config alias."""
    alias = DEFAULT_SSH_HOST_ALIAS if ssh_host_alias is None else ssh_host_alias
    command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
    ]

    if alias:
        return command + [alias, remote_command]

    command.extend(["-p", str(DEFAULT_SSH_PORT)])
    if os.getenv("SATNET_SSH_PRIVATE_KEY") or os.path.exists(DEFAULT_SSH_PRIVATE_KEY):
        command.extend(["-i", DEFAULT_SSH_PRIVATE_KEY])

    target = DEFAULT_SSH_HOST
    if DEFAULT_SSH_USERNAME:
        target = f"{DEFAULT_SSH_USERNAME}@{DEFAULT_SSH_HOST}"

    return command + [target, remote_command]


def redis_password_from_env_or_file() -> Optional[str]:
    password = os.getenv("SATNET_REDIS_PASSWORD") or os.getenv("REDIS_PASSWORD")
    if password:
        return password

    try:
        with open(DEFAULT_REDIS_PASSWORD_FILE, encoding="utf-8") as password_file:
            return password_file.read().strip() or None
    except OSError:
        return None

def sudo_password_from_env_or_file() -> Optional[str]:
    password = os.getenv("SATNET_SUDO_PASSWORD")
    if password:
        return password

    try:
        with open(DEFAULT_SUDO_PASSWORD_FILE, encoding="utf-8-sig") as password_file:
            return password_file.read().strip() or None
    except OSError:
        return None


def redis_config_from_env() -> Dict[str, Any]:
    """
    Redis/SSH connection settings for this project.

    Redis is disabled by default. Enable it in the GUI, or set
    SATNET_REDIS_ENABLED=1 before launching.
    """
    return {
        "enabled": env_bool("SATNET_REDIS_ENABLED", False),
        "host": DEFAULT_REDIS_HOST,
        "port": DEFAULT_REDIS_PORT,
        "password": redis_password_from_env_or_file(),
        "db": DEFAULT_REDIS_DB,
        "key_prefix": DEFAULT_REDIS_KEY_PREFIX,
        "loss_enabled": DEFAULT_REDIS_LOSS_ENABLED,
        "loss_scale": DEFAULT_REDIS_LOSS_SCALE,
        "socket_timeout": DEFAULT_REDIS_SOCKET_TIMEOUT,
        "use_ssh": env_bool("SATNET_REDIS_USE_SSH", True),
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_port": DEFAULT_SSH_PORT,
        "ssh_username": DEFAULT_SSH_USERNAME,
        "ssh_password": os.getenv("SATNET_SSH_PASSWORD") or None,
        "ssh_private_key": DEFAULT_SSH_PRIVATE_KEY,
        "ssh_private_key_passphrase": os.getenv("SATNET_SSH_PRIVATE_KEY_PASSPHRASE") or None,
    }
