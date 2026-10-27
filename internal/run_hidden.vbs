Option Explicit

Dim fso, folder, modePath, modeFile, mode, pythonExe, pyScript, shell, pathEntries, pathEntry, pythonCandidate
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
modePath = fso.BuildPath(folder, "auto_login_mode.txt")

' The scheduled task stays installed, but does no network work while off.
If Not fso.FileExists(modePath) Then WScript.Quit 0
Set modeFile = fso.OpenTextFile(modePath, 1, False)
mode = ""
If Not modeFile.AtEndOfStream Then mode = LCase(Trim(modeFile.ReadLine))
modeFile.Close
If mode <> "on" Then WScript.Quit 0

Set shell = CreateObject("WScript.Shell")
pythonExe = ""
pathEntries = Split(shell.ExpandEnvironmentStrings("%PATH%"), ";")
For Each pathEntry In pathEntries
    pythonCandidate = fso.BuildPath(Trim(pathEntry), "pythonw.exe")
    If fso.FileExists(pythonCandidate) Then
        pythonExe = pythonCandidate
        Exit For
    End If
Next

pyScript = fso.BuildPath(folder, "campus_wifi_auto_login_once.py")
If pythonExe = "" Or Not fso.FileExists(pyScript) Then WScript.Quit 1

shell.Run Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & pyScript & Chr(34), 0, False
