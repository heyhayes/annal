<#
.SYNOPSIS
    Install or uninstall Annal as a Windows scheduled task that runs at logon.

.DESCRIPTION
    Registers a scheduled task that starts the Annal MCP server in HTTP daemon
    mode when the current user logs in. The task auto-restarts on failure.

.PARAMETER Action
    "install" to create the task, "uninstall" to remove it, "status" to check.

.PARAMETER AnnalPath
    Path to the annal executable (e.g. C:\path\to\annal\.venv\Scripts\annal.exe).
    Required for install.

.EXAMPLE
    .\annal-service.ps1 -Action install -AnnalPath "C:\dev\annal\.venv\Scripts\annal.exe"
    .\annal-service.ps1 -Action status
    .\annal-service.ps1 -Action uninstall
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "uninstall", "status")]
    [string]$Action,

    [string]$AnnalPath
)

$TaskName = "Annal MCP Server"

switch ($Action) {
    "install" {
        if (-not $AnnalPath) {
            Write-Error "AnnalPath is required for install. Provide the path to annal.exe."
            exit 1
        }

        if (-not (Test-Path $AnnalPath)) {
            Write-Error "annal executable not found at: $AnnalPath"
            exit 1
        }

        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existingTask) {
            Write-Host "Task '$TaskName' already exists. Uninstall first to reinstall."
            exit 1
        }

        $taskAction = New-ScheduledTaskAction `
            -Execute $AnnalPath `
            -Argument "--transport streamable-http"

        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -RestartCount 3 `
            -RestartInterval (New-TimeSpan -Seconds 10) `
            -ExecutionTimeLimit (New-TimeSpan -Duration 0)

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $taskAction `
            -Trigger $trigger `
            -Settings $settings `
            -Description "Annal semantic memory MCP server (HTTP daemon)" `
            -RunLevel Limited

        Write-Host "Installed '$TaskName' scheduled task. It will start at next logon."
        Write-Host "To start it now: Start-ScheduledTask -TaskName '$TaskName'"
    }

    "uninstall" {
        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $existingTask) {
            Write-Host "Task '$TaskName' not found."
            exit 0
        }

        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Uninstalled '$TaskName' scheduled task."
    }

    "status" {
        $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (-not $existingTask) {
            Write-Host "Task '$TaskName' is not installed."
        } else {
            $info = Get-ScheduledTaskInfo -TaskName $TaskName
            Write-Host "Task '$TaskName' is installed."
            Write-Host "  State: $($existingTask.State)"
            Write-Host "  Last run: $($info.LastRunTime)"
            Write-Host "  Last result: $($info.LastTaskResult)"
        }
    }
}
