Option Explicit
Dim fs, shell, project, python, launcher, command
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
project = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(project, ".venv\Scripts\pythonw.exe")
If Not fs.FileExists(python) Then
    python = fs.BuildPath(project, ".venv\Scripts\python.exe")
End If
If Not fs.FileExists(python) Then
    MsgBox "Python environment is missing. Please follow the setup steps in README.md.", 16, "Personal Workspace"
    WScript.Quit 1
End If
launcher = fs.BuildPath(project, "scripts\launch_desktop.py")
If Not fs.FileExists(launcher) Then
    MsgBox "The desktop launcher is missing: " & launcher, 16, "Personal Workspace"
    WScript.Quit 1
End If
shell.CurrentDirectory = project
command = Chr(34) & python & Chr(34) & " " & Chr(34) & launcher & Chr(34)
shell.Run command, 0, False
