# Desktop launcher (Windows)

Prefer a dedicated window instead of another browser tab? Personal Workspace can open in its own Windows window using **pywebview** and **Microsoft Edge WebView2**. It's the same Streamlit app, with the same tasks, calendar, database, and planner — just without the browser tabs.

## Set it up

First, follow the [Windows installation steps](../README.md#windows). Then run this in PowerShell from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& ".\Create Desktop Shortcut.bat"
```

Double-click **Personal Workspace** on your desktop. You don't need to recreate the shortcut for normal Python source updates.

## What's running behind the window?

The launcher runs a local Streamlit server on `127.0.0.1` using an available port, then displays it in a WebView2 window. It only runs while the desktop app is open. No Microsoft account or internet connection is required to use your local workspace.

**This isn't a standalone `.exe`.** The project folder, Python environment, and dependencies must remain installed. Windows also needs WebView2 and a compatible .NET runtime; WebView2 doesn't use your normal Edge browser profile or extensions.

## If something goes wrong

- **Window won't open:** Check `%LOCALAPPDATA%\PersonalWorkspace\desktop-server.log`.
- **WebView2 or .NET error:** Install the missing Microsoft runtime.
- **`No module named 'webview'`:** Reinstall the development requirements.
- **Prefer a browser?** Run `.\.venv\Scripts\python.exe -m streamlit run app.py`.

**Data safety:** The normal desktop shortcut opens your personal database, not the demo. For exploring or testing edits, use [the sample workspace](PLAYGROUND_DESKTOP_DEMO.md).

This launcher is Windows-only. On macOS, use the [browser instructions](../README.md#macos).
