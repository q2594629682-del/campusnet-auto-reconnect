# install_startup_task_hidden.ps1
# Run as Administrator PowerShell

$ErrorActionPreference = "Stop"

$TaskName = "CampusWiFiAutoLoginEvery5Min"
$ScriptDir = $PSScriptRoot
$VbsFile = Join-Path $ScriptDir "run_hidden.vbs"

if (!(Test-Path $VbsFile)) {
    Write-Host "Missing file:"
    Write-Host $VbsFile
    exit 1
}

# Remove old tasks
$OldTasks = @(
    "CampusWiFiKeeper",
    "CampusWiFiKeeper",
    "CampusWiFiAutoLogin",
    "CampusWiFiAutoLoginEvery5Min"
)

foreach ($t in $OldTasks) {
    $old = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if ($null -ne $old) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
    }
}

$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$VbsFile`"" `
    -WorkingDirectory $ScriptDir

$Trigger1 = New-ScheduledTaskTrigger -AtLogOn

$Trigger2 = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($Trigger1,$Trigger2) `
    -Settings $Settings `
    -Principal $Principal `
    -Force

Write-Host "Hidden campus Wi-Fi task installed."
