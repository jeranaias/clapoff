<#
    Registers clapoff to start, hidden, every time you log in.
    Run:    powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
    Undo:   Unregister-ScheduledTask -TaskName clapoff -Confirm:$false

    Heads up: hidden means no console window, which means no keyboard abort.
    Clap-to-abort still works. That is the only abort you get.
#>
$ErrorActionPreference = 'Stop'

$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { throw "pythonw not found on PATH. Install Python, then try again." }

$module = 'clapoff.cli'
try { & python -c "import clapoff" 2>$null } catch { throw "clapoff isn't installed. Run: pip install git+https://github.com/jeranaias/clapoff" }

$action  = New-ScheduledTaskAction -Execute $pythonw -Argument "-m $module"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0

Register-ScheduledTask -TaskName 'clapoff' -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
Write-Host "clapoff will now start when you log in. It is listening. Be nice to it."
