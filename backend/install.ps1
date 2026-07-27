param(
    [string[]]$Targets = @("gzy0", "gzy1")
)

$ErrorActionPreference = "Stop"
$BackendSource = $PSScriptRoot

$Hosts = @{
    gzy0 = @{
        Home = "/home/s223"
        Config = "gzy0.env"
    }
    gzy1 = @{
        Home = "/home/test"
        Config = "gzy1.env"
    }
}

foreach ($Target in $Targets) {
    if (-not $Hosts.ContainsKey($Target)) {
        throw "Unknown backend target: $Target"
    }

    $RemoteHome = $Hosts[$Target].Home
    $RemoteRoot = "$RemoteHome/satnet-backend"
    $HostConfig = $Hosts[$Target].Config

    ssh $Target "mkdir -p '$RemoteRoot'"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create $RemoteRoot on $Target"
    }

    foreach ($Item in @("config", "scripts", "upstream", "runtime", "README.md")) {
        scp -r (Join-Path $BackendSource $Item) "${Target}:$RemoteRoot/"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to upload $Item to $Target"
        }
    }

    ssh $Target (
        "cp '$RemoteRoot/config/$HostConfig' '$RemoteRoot/config/host.env' " +
        "&& chmod 755 '$RemoteRoot'/scripts/*.sh " +
        "&& if [ -x '$RemoteRoot/upstream/dky-dataplane/scripts/deploy_all.sh' ]; then " +
        "bash '$RemoteRoot/scripts/verify.sh'; " +
        "else bash -n '$RemoteRoot'/scripts/*.sh && echo 'entrypoint_syntax=ok source_import=pending'; fi"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Backend verification failed on $Target"
    }
}
