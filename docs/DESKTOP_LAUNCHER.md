# Personal Workspace: standalone desktop window (Windows)

This launcher keeps the existing Streamlit application and SQLite data intact.
Instead of opening a normal browser tab, it starts the local server with no
visible terminal and launches Microsoft Edge (or Chrome) in application mode.
The browser window has no normal address bar or tabs.

## Set up

From the project folder, run `Create Desktop Shortcut.bat` once. It updates
`Personal Workspace.lnk` on your Windows desktop to use the new launcher.
No administrator permissions or new Python packages are required.

Double-click **Personal Workspace** on the desktop. The launcher starts a
private loopback Streamlit server, waits until it is healthy, and then opens
an independent Edge/Chrome application window. Close that window to request
shutdown of the corresponding local server process. A fresh browser profile
is used for that window so the user's other browser windows do not interfere.

The server is still required under the hood; it is simply hidden from the UI.
This is not a packaged installer or a cloud-hosted application. It works only
while your Windows PC is running. The `.venv` and installed browser must still
be available, and the project directory must remain in its current location.

## Troubleshooting

* If there is no desktop icon, run `Create Desktop Shortcut.bat` again.
* If the app does not open, check `%LOCALAPPDATA%\PersonalWorkspace\desktop-server.log`.
* The launcher deliberately removes `WORKSPACE_DB_PATH` from its child process
  environment, so it always uses the normal personal DB, not the demo DB.
* The separate `Launch Calendar V3 Demo.bat` remains unchanged and continues
  to use the demo database and an ordinary browser tab.
* If the app window closes unexpectedly, the local server is terminated.
* If Windows Edge/Chrome processes do not close with the standalone window,
  Windows may keep the server open. Check Task Manager if necessary.

All original app code, databases, and tests remain unchanged by this patch.
