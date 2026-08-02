' SceneCut Pro+ — silent desktop launch (no console window)
Option Explicit

Dim sh, fso, root, pythonw, script, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
script = root & "\desktop_app.py"
pythonw = root & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
  ' Fallback: show console launcher so user can see errors
  sh.Run """" & root & "\desktop\Launch.bat""", 1, False
  WScript.Quit 0
End If

If Not fso.FileExists(script) Then
  MsgBox "desktop_app.py missing in:" & vbCrLf & root, vbCritical, "SceneCut Pro+"
  WScript.Quit 1
End If

sh.CurrentDirectory = root
cmd = """" & pythonw & """ """ & script & """"
sh.Run cmd, 0, False
