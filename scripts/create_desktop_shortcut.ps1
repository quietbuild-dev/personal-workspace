# Creates an ordinary Windows desktop shortcut. No installation, admin rights,
# background service, scheduled task, or permanent execution-policy change.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $project 'Launch Personal Workspace.bat'
$icon = Join-Path $project 'assets\personal-workspace.ico'
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Could not find the launcher at $launcher"
}
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutFile = Join-Path $desktop 'Personal Workspace.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutFile)
$link.TargetPath = $launcher
$link.WorkingDirectory = $project
$link.Description = 'Open Personal Workspace in your browser (local Streamlit app)'
$link.WindowStyle = 7  # Minimize the server terminal, do not hide it.
if (Test-Path -LiteralPath $icon) {
    $link.IconLocation = "$icon,0"
}
$link.Save()
Write-Host "Created: $shortcutFile"
Write-Host 'Double-click the shortcut to open Personal Workspace.'
Write-Host 'The minimized server window must keep running while you use the app.'
