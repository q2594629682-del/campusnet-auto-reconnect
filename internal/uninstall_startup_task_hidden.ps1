# uninstall_startup_task_hidden.ps1

$Tasks = @(
    "CampusWiFiKeeper",
    "CampusWiFiKeeper",
    "CampusWiFiAutoLogin",
    "CampusWiFiAutoLoginEvery5Min"
)

foreach ($t in $Tasks) {
    $task = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Write-Host "Removed $t"
    }
}

Write-Host "Done."
