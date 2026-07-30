# Windows Frontend + Linux Backend

This project can run the PySide6/PyVista GUI on Windows while keeping deployment,
measurement scripts, Redis, containers, and OVS on two Linux backend hosts.

The default 60x20 constellation is split by complete orbital planes:

```text
gzy0: s223@121.48.163.223:22, orbits 01-30, 600 satellites
gzy1: test@121.48.163.234:22, orbits 31-60, 600 satellites
Redis: each backend's 127.0.0.1:6379 through independent SSH tunnels
```

So the normal Windows launch path is simply:

```powershell
conda env create -f environment.yml
conda activate satsim
python main.py
```

Windows needs a local OpenSSH client. Check it with:

```powershell
ssh -V
```

## SSH Requirements

The defaults use the OpenSSH aliases `gzy0` and `gzy1`. Both aliases must use
public-key authentication because background commands run with `BatchMode=yes`.

Verify both connections from PowerShell:

```powershell
ssh gzy0 "echo ok"
ssh gzy1 "echo ok"
```

If the key is managed by `ssh-agent` or another default OpenSSH identity, the
explicit `-i` file is not required.

## Optional Overrides

Each backend can be overridden independently:

```powershell
$env:SATNET_GZY0_SSH_HOST_ALIAS = "gzy0"
$env:SATNET_GZY0_ORBIT_START = "1"
$env:SATNET_GZY0_ORBIT_END = "30"
$env:SATNET_GZY0_REMOTE_HEALTH_SCRIPT = "/home/s223/satnet-backend/scripts/health.sh"
$env:SATNET_GZY0_REMOTE_CLEANUP_SCRIPT = "/home/s223/satnet-backend/scripts/cleanup.sh"
$env:SATNET_GZY0_REMOTE_MEASURE_SCRIPT = "/home/s223/satnet-backend/scripts/measure_slice.sh"

$env:SATNET_GZY1_SSH_HOST_ALIAS = "gzy1"
$env:SATNET_GZY1_ORBIT_START = "31"
$env:SATNET_GZY1_ORBIT_END = "60"
$env:SATNET_GZY1_REMOTE_HEALTH_SCRIPT = "/home/test/satnet-backend/scripts/health.sh"
$env:SATNET_GZY1_REMOTE_CLEANUP_SCRIPT = "/home/test/satnet-backend/scripts/cleanup.sh"
$env:SATNET_GZY1_REMOTE_MEASURE_SCRIPT = "/home/test/satnet-backend/scripts/measure_slice.sh"
python main.py
```

Direct host/user/key overrides are also available using the corresponding
`SATNET_GZY0_*` or `SATNET_GZY1_*` prefix.

Both Redis instances are queried in parallel and results are routed by the source
satellite's orbit. To enable Redis query on launch:

```powershell
$env:SATNET_REDIS_ENABLED = "1"
```

Per-host sudo passwords can be placed in user-only files:

```text
%USERPROFILE%\.config\satellite-simulation\gzy0_sudo_password
%USERPROFILE%\.config\satellite-simulation\gzy1_sudo_password
```

The shared Redis password file remains:

```text
%USERPROFILE%\.config\satellite-simulation\gzy0_redis_password
%USERPROFILE%\.config\satellite-simulation\gzy1_redis_password
```

Environment overrides are `SATNET_GZY0_SUDO_PASSWORD`,
`SATNET_GZY1_SUDO_PASSWORD`, `SATNET_GZY0_REDIS_PASSWORD`, and
`SATNET_GZY1_REDIS_PASSWORD`.

Remote measurement uses a 10-second slice, a 20-second command deadline, and a
shared probe start timestamp. The remote scripts must treat their fourth
argument (or `SATNET_PROBE_START_EPOCH_MS`) as the barrier time.
