# Removes the pc-energy-optimizer scheduled task.
$ErrorActionPreference = "Stop"
$TaskName = "PcEnergyOptimizer"

try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch {}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Task '$TaskName' removed. (The agent process may keep running until logoff; end pythonw.exe in Task Manager if needed.)"
