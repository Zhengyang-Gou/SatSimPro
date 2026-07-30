# Satellite backend integration

This directory contains the integration-owned boundary between the GUI and the
remotely maintained control/data-plane projects.

The GUI calls only the stable commands under `scripts/`.  Host-specific source
locations live in `config/host.env`; scripts must not embed `/home/*/dky`,
`/home/*/lyh`, or `/home/*/yzy` paths.

## Remote layout

Install the directory as:

- gzy0: `/home/s223/satnet-backend`
- gzy1: `/home/test/satnet-backend`

The initial migration uses `SATNET_CONTROL_MODE=legacy`: stable entry points
delegate to the imported platform snapshot. This changes the source path
without silently changing the active controller. A later LYH adapter can
replace the implementation behind the same entry points.

`upstream/` contains read-only integration snapshots of maintainer-owned
source. Refresh them only with the explicit import command; normal deploy and
measurement commands never read code outside this tree.

`runtime/` is for generated data, logs, PIDs, caches, and results; it is not
source code and must not be committed.

`patches/` contains deterministic compatibility patches applied to the copied
platform snapshot before deployment. Maintainer-owned source directories
outside `satnet-backend` remain untouched.

From the Windows project root, install or refresh both remote entry points with:

```powershell
powershell -ExecutionPolicy Bypass -File backend/install.ps1
```

## Deployment lifecycle

The GUI uses three stable lifecycle commands on each backend:

- `scripts/deploy.sh` deploys the backend and records the GUI session in
  `runtime/state/<backend>/deployment.env`.
- `scripts/health.sh` verifies the expected running containers, OVS bridge,
  receiver process, and time-slice state.
- `scripts/cleanup.sh` stops the receiver and removes only the containers,
  bridge, and runtime state belonging to that backend's orbit range.

Manual cleanup is forced after confirmation in the GUI. Automatic cleanup on
application exit includes the session ID and is refused by the backend if the
active deployment belongs to a different session.
