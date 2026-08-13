# Registers pc-energy-optimizer as a hidden at-logon Scheduled Task for the current user.
# Run from anywhere: powershell -ExecutionPolicy Bypass -File install\install-task.ps1

$ErrorActionPreference = "Stop"
$Project = Split-Path $PSScriptRoot -Parent
$TaskName = "PcEnergyOptimizer"

$ConfigPath = Join-Path $Project "config.toml"
if (-not (Test-Path $ConfigPath)) {
    Write-Error "config.toml not found. Copy config.example.toml to config.toml, set bind_host to this PC's Tailscale IP and generate a token:  python -c `"import secrets; print(secrets.token_urlsafe(32))`""
}

Write-Host "Syncing environment with uv..."
uv sync --project $Project
$Pythonw = Join-Path $Project ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) { Write-Error "$Pythonw not found after uv sync" }

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-m pc_energy_optimizer" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -Hidden
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' registered and started."

# Smoke test /health
$config = Get-Content $ConfigPath -Raw
$BindHost = if ($config -match 'bind_host\s*=\s*"([^"]+)"') { $Matches[1] } else { "127.0.0.1" }
$Port = if ($config -match 'port\s*=\s*(\d+)') { $Matches[1] } else { "8787" }
$HealthUrl = "http://${BindHost}:${Port}/health"

Write-Host "Polling $HealthUrl (up to 30s; may take longer at logon while Tailscale comes up)..."
$ok = $false
foreach ($i in 1..15) {
    try {
        $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        if ($resp.status -eq "ok") { $ok = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if ($ok) {
    Write-Host "Health check OK (version $($resp.version))."
} else {
    Write-Warning "No response yet - check logs\agent.log (bind retries are normal right after logon)."
}
Write-Host ""
Write-Host "Reminders:"
Write-Host " - Add an Uptime Kuma HTTP monitor for $HealthUrl (keyword 'ok', 60s)."
Write-Host " - For strict suspend (never hibernate), consider: powercfg /h off"
