# Windows desktop launcher

To open Personal Workspace by double-clicking an icon rather than typing
PowerShell commands, run **Create Desktop Shortcut.bat** once. It creates
`Personal Workspace.lnk` on the current Windows user's desktop, including
OneDrive-redirected desktops. It points to `Launch Personal Workspace.bat`
inside this repository, so keep the project folder in its current location.

After that, double-click the shortcut to start the local Streamlit server and
open the app in the browser. The server terminal is minimized, **not hidden**.
You must keep it running while using the app. To shut down the server, open
that terminal window and press `Ctrl+C` (confirm if prompted). Closing the
server or turning off the computer makes the local web address unavailable.

This shortcut is not a hosted app, background service, mobile app, or Windows
installer. It does not change the database or require administrator rights.
The separate `Launch Calendar V3 Demo.bat` continues to use a demo database;
the desktop shortcut launches your normal personal workspace.
