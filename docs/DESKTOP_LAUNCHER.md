# Personal Workspace: Windows desktop window

The Windows launcher displays Personal Workspace inside an embedded WebView2
window instead of opening Microsoft Edge or Google Chrome. There are no browser
tabs, extension setup pages, browser sign-ins, or visible PowerShell window.
The Python/Streamlit code, SQLite storage, scheduling and Undo logic are unchanged.

## Installation

On Windows, from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& ".\Create Desktop Shortcut.bat"
```

Double-click **Personal Workspace** on your desktop. It uses the existing
Windows shortcut and `.vbs` launcher; you do not need to recreate a shortcut
when only `scripts/launch_desktop.py` has changed.

## How it works

The launcher starts a private Streamlit server bound only to `127.0.0.1` on a
random free port; it waits for the server, then opens a native `pywebview`
window using Windows WebView2 (Chromium). No Microsoft account or internet
connection is required to use the local project. The app still needs its
server **while the window is open**, but it is a background process and stops
when the window closes. It does not run 24/7.

This is a local desktop wrapper, **not** a bundled `.exe` installer: the
project folder, Python `.venv`, and dependencies must still be present.
The Windows machine must have the Microsoft Edge **WebView2 Runtime** and a
compatible .NET runtime installed. These components do **not** use the normal
Edge browser profile or its extensions. Windows 11 often includes WebView2;
if missing, install the official Microsoft WebView2 Runtime.

## Troubleshooting

- If the window fails to open, read
  `%LOCALAPPDATA%\PersonalWorkspace\desktop-server.log`.
- If you see a WebView2/.NET error, install the relevant runtime from Microsoft.
- If `No module named 'webview'` appears, install the project's requirements.
- You can always run the same application in an ordinary browser using
  `.\.venv\Scripts\python.exe -m streamlit run app.py`.
- The launcher clears `WORKSPACE_DB_PATH` so it opens your **personal** database,
  never the temporary demo database. Do not test destructive actions using
  this shortcut; use a separate demo process for exploratory tests.
- Neither the Windows desktop shortcut nor this launcher should be run on macOS.
