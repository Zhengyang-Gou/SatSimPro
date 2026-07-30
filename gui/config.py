"""Runtime configuration helpers for the GUI layer."""

import os
from dataclasses import asdict, dataclass
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
DEFAULT_REDIS_SOCKET_TIMEOUT = env_float("SATNET_REDIS_SOCKET_TIMEOUT", 1.0, minimum=0.001)
DEFAULT_REMOTE_DEPLOY_SCRIPT = env_str(
    "SATNET_REMOTE_DEPLOY_SCRIPT",
    "/home/s223/satnet-backend/scripts/deploy.sh",
)
DEFAULT_REMOTE_MEASURE_SCRIPT = env_str(
    "SATNET_REMOTE_MEASURE_SCRIPT",
    "/home/s223/satnet-backend/scripts/measure_slice.sh",
)
DEFAULT_REMOTE_PROBE_COUNT = env_int("SATNET_REMOTE_PROBE_COUNT", 5, minimum=1)
DEFAULT_REMOTE_PROBE_PPS = env_float("SATNET_REMOTE_PROBE_PPS", 10.0, minimum=0.1)
DEFAULT_REMOTE_PROBE_LEAD_SEC = env_float("SATNET_REMOTE_PROBE_LEAD_SEC", 3.0, minimum=0.0)
DEFAULT_REMOTE_SLICE_DURATION_SEC = env_float("SATNET_REMOTE_SLICE_DURATION_SEC", 10.0, minimum=0.1)
DEFAULT_REMOTE_TIME_SLICES = env_int("SATNET_REMOTE_TIME_SLICES", 60, minimum=1)
DEFAULT_REMOTE_NODES_PER_ORBIT = env_int("SATNET_REMOTE_NODES_PER_ORBIT", 20, minimum=1, maximum=99)
DEFAULT_REMOTE_COMMAND_TIMEOUT_SEC = env_float("SATNET_REMOTE_COMMAND_TIMEOUT_SEC", 20.0, minimum=0.1)
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

@dataclass(frozen=True)
class RemoteBackend:
    """One Linux host responsible for a contiguous range of orbital planes."""

    name: str
    orbit_start: int
    orbit_end: int
    ssh_host_alias: str
    ssh_host: str
    ssh_port: int
    ssh_username: str
    ssh_private_key: str
    deploy_script: str
    health_script: str
    cleanup_script: str
    measure_script: str
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379

    def contains_orbit(self, orbit_number: int) -> bool:
        return self.orbit_start <= int(orbit_number) <= self.orbit_end

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _backend_from_env(
    name: str,
    *,
    orbit_start: int,
    orbit_end: int,
    ssh_host_alias: str,
    ssh_host: str,
    ssh_username: str,
    home: str,
) -> RemoteBackend:
    prefix = f"SATNET_{name.upper()}_"
    return RemoteBackend(
        name=name,
        orbit_start=env_int(f"{prefix}ORBIT_START", orbit_start, minimum=1, maximum=99),
        orbit_end=env_int(f"{prefix}ORBIT_END", orbit_end, minimum=1, maximum=99),
        ssh_host_alias=env_str(f"{prefix}SSH_HOST_ALIAS", ssh_host_alias),
        ssh_host=env_str(f"{prefix}SSH_HOST", ssh_host),
        ssh_port=env_int(f"{prefix}SSH_PORT", 22, minimum=1, maximum=65535),
        ssh_username=env_str(f"{prefix}SSH_USERNAME", ssh_username),
        ssh_private_key=env_str(
            f"{prefix}SSH_PRIVATE_KEY",
            "~/.ssh/id_ed25519_satellite_simulation",
        ),
        deploy_script=env_str(
            f"{prefix}REMOTE_DEPLOY_SCRIPT",
            f"{home}/satnet-backend/scripts/deploy.sh",
        ),
        health_script=env_str(
            f"{prefix}REMOTE_HEALTH_SCRIPT",
            f"{home}/satnet-backend/scripts/health.sh",
        ),
        cleanup_script=env_str(
            f"{prefix}REMOTE_CLEANUP_SCRIPT",
            f"{home}/satnet-backend/scripts/cleanup.sh",
        ),
        measure_script=env_str(
            f"{prefix}REMOTE_MEASURE_SCRIPT",
            f"{home}/satnet-backend/scripts/measure_slice.sh",
        ),
        redis_host=env_str(f"{prefix}REDIS_HOST", "127.0.0.1"),
        redis_port=env_int(f"{prefix}REDIS_PORT", 6379, minimum=1, maximum=65535),
    )


def backend_configs_from_env() -> List[RemoteBackend]:
    """Return the two default 600-node backends in deterministic orbit order."""
    backends = [
        _backend_from_env(
            "gzy0",
            orbit_start=1,
            orbit_end=30,
            ssh_host_alias="gzy0",
            ssh_host="121.48.163.223",
            ssh_username="s223",
            home="/home/s223",
        ),
        _backend_from_env(
            "gzy1",
            orbit_start=31,
            orbit_end=60,
            ssh_host_alias="gzy1",
            ssh_host="121.48.163.234",
            ssh_username="test",
            home="/home/test",
        ),
    ]
    backends.sort(key=lambda backend: (backend.orbit_start, backend.name))
    if backends and backends[0].orbit_start != 1:
        raise ValueError(
            f"后端轨道范围必须从 1 开始，当前从 {backends[0].orbit_start} 开始"
        )
    for backend in backends:
        if backend.orbit_start > backend.orbit_end:
            raise ValueError(
                f"后端轨道范围无效：{backend.name}="
                f"{backend.orbit_start}-{backend.orbit_end}"
            )
    for previous, current in zip(backends, backends[1:]):
        if previous.orbit_end >= current.orbit_start:
            raise ValueError(
                f"后端轨道范围重叠：{previous.name}={previous.orbit_start}-{previous.orbit_end}, "
                f"{current.name}={current.orbit_start}-{current.orbit_end}"
            )
        if previous.orbit_end + 1 != current.orbit_start:
            raise ValueError(
                f"后端轨道范围不连续：{previous.name} 结束于 {previous.orbit_end}，"
                f"{current.name} 开始于 {current.orbit_start}"
            )
    return backends


def build_ssh_command(
    remote_command: str,
    ssh_host_alias: Optional[str] = None,
    *,
    backend: Optional[RemoteBackend] = None,
) -> List[str]:
    """Build an ssh command that works without requiring a user ssh config alias."""
    alias = (
        backend.ssh_host_alias
        if backend is not None and ssh_host_alias is None
        else DEFAULT_SSH_HOST_ALIAS if ssh_host_alias is None else ssh_host_alias
    )
    command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
    ]

    if alias:
        return command + [alias, remote_command]

    ssh_port = backend.ssh_port if backend is not None else DEFAULT_SSH_PORT
    private_key = backend.ssh_private_key if backend is not None else DEFAULT_SSH_PRIVATE_KEY
    ssh_host = backend.ssh_host if backend is not None else DEFAULT_SSH_HOST
    ssh_username = backend.ssh_username if backend is not None else DEFAULT_SSH_USERNAME
    command.extend(["-p", str(ssh_port)])
    backend_key_env = (
        os.getenv(f"SATNET_{backend.name.upper()}_SSH_PRIVATE_KEY")
        if backend is not None
        else os.getenv("SATNET_SSH_PRIVATE_KEY")
    )
    if private_key and (backend_key_env or os.path.exists(private_key)):
        command.extend(["-i", private_key])

    target = ssh_host
    if ssh_username:
        target = f"{ssh_username}@{ssh_host}"

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


def redis_password_for_backend(backend: RemoteBackend) -> Optional[str]:
    """Return a backend-specific Redis password, falling back to the shared one."""
    prefix = f"SATNET_{backend.name.upper()}_"
    password = os.getenv(f"{prefix}REDIS_PASSWORD")
    if password:
        return password

    password_path = os.path.expanduser(
        os.getenv(
            f"{prefix}REDIS_PASSWORD_FILE",
            f"~/.config/satellite-simulation/{backend.name}_redis_password",
        )
    )
    try:
        with open(password_path, encoding="utf-8-sig") as password_file:
            password = password_file.read().strip()
            if password:
                return password
    except OSError:
        pass

    return redis_password_from_env_or_file()


def sudo_password_from_env_or_file() -> Optional[str]:
    password = os.getenv("SATNET_SUDO_PASSWORD")
    if password:
        return password

    try:
        with open(DEFAULT_SUDO_PASSWORD_FILE, encoding="utf-8-sig") as password_file:
            return password_file.read().strip() or None
    except OSError:
        return None


def sudo_password_for_backend(backend: RemoteBackend) -> Optional[str]:
    env_name = f"SATNET_{backend.name.upper()}_SUDO_PASSWORD"
    password = os.getenv(env_name)
    if password:
        return password

    password_path = os.path.expanduser(
        os.getenv(
            f"SATNET_{backend.name.upper()}_SUDO_PASSWORD_FILE",
            f"~/.config/satellite-simulation/{backend.name}_sudo_password",
        )
    )
    try:
        with open(password_path, encoding="utf-8-sig") as password_file:
            password = password_file.read().strip()
            if password:
                return password
    except OSError:
        pass

    return sudo_password_from_env_or_file()


def redis_config_from_env() -> Dict[str, Any]:
    """
    Redis/SSH connection settings for this project.

    Redis is disabled by default. Enable it in the GUI, or set
    SATNET_REDIS_ENABLED=1 before launching.
    """
    backend_configs = []
    for backend in backend_configs_from_env():
        prefix = f"SATNET_{backend.name.upper()}_"
        redis_ssh_private_key = (
            backend.ssh_private_key
            if os.getenv(f"{prefix}SSH_PRIVATE_KEY")
            or os.path.exists(backend.ssh_private_key)
            else None
        )
        backend_configs.append(
            {
                "name": backend.name,
                "orbit_start": backend.orbit_start,
                "orbit_end": backend.orbit_end,
                "host": backend.redis_host,
                "port": backend.redis_port,
                "password": redis_password_for_backend(backend),
                "db": env_int(f"{prefix}REDIS_DB", DEFAULT_REDIS_DB, minimum=0),
                "key_prefix": env_str(f"{prefix}REDIS_KEY_PREFIX", DEFAULT_REDIS_KEY_PREFIX),
                "loss_scale": DEFAULT_REDIS_LOSS_SCALE,
                "loss_enabled": DEFAULT_REDIS_LOSS_ENABLED,
                "socket_timeout": DEFAULT_REDIS_SOCKET_TIMEOUT,
                "enabled": True,
                "raise_on_error": True,
                "use_ssh": env_bool(f"{prefix}REDIS_USE_SSH", True),
                "ssh_host": backend.ssh_host,
                "ssh_port": backend.ssh_port,
                "ssh_username": backend.ssh_username,
                "ssh_password": os.getenv(f"{prefix}SSH_PASSWORD") or None,
                "ssh_private_key": redis_ssh_private_key,
                "ssh_private_key_passphrase": os.getenv(f"{prefix}SSH_PRIVATE_KEY_PASSPHRASE") or None,
            }
        )

    return {
        "enabled": env_bool("SATNET_REDIS_ENABLED", False),
        "loss_enabled": DEFAULT_REDIS_LOSS_ENABLED,
        "strict": True,
        "backends": backend_configs,
    }
