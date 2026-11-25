# Update the current user's Personal Workspace desktop shortcut (no admin needed).
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $project 'Launch Personal Workspace Desktop.vbs'
$icon = Join-Path $project 'assets\personal-workspace.ico'
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Could not find the desktop launcher at $launcher"
}
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutFile = Join-Path $desktop 'Personal Workspace.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutFile)
$link.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$link.Arguments = '"' + $launcher + '"'
$link.WorkingDirectory = $project
$link.Description = 'Personal Workspace - local standalone desktop window'
$link.WindowStyle = 1
if (Test-Path -LiteralPath $icon) {
    $link.IconLocation = "$icon,0"
}
$link.Save()
Write-Host "Desktop shortcut updated: $shortcutFile"
Write-Host 'Double-click Personal Workspace. No terminal window is needed.'
