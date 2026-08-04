' SceneCut Pro+ — silent desktop launch (NO CMD, NO pywebview/.NET)
Option Explicit

Dim sh, fso, root, pythonw, script, exe, cmd, ffmpegBin
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

exe = root & "\SceneCutProPlus.exe"
If fso.FileExists(exe) Then
  sh.CurrentDirectory = root
  sh.Environment("Process")("SCENECUT_DESKTOP") = "1"
  sh.Run """" & exe & """", 1, False
  WScript.Quit 0
End If

script = root & "\desktop_app.py"
pythonw = root & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
  MsgBox "SceneCut Pro+ install incomplete." & vbCrLf & _
         "Download Setup.exe again from the website.", _
         vbCritical, "SceneCut Pro+"
  WScript.Quit 1
End If

If Not fso.FileExists(script) Then
  MsgBox "desktop_app.py missing in:" & vbCrLf & root, vbCritical, "SceneCut Pro+"
  WScript.Quit 1
End If

ffmpegBin = root & "\tools\ffmpeg\bin"
If fso.FolderExists(ffmpegBin) Then
  sh.Environment("Process")("PATH") = ffmpegBin & ";" & sh.Environment("Process")("PATH")
End If

sh.CurrentDirectory = root
sh.Environment("Process")("SCENECUT_DESKTOP") = "1"
cmd = """" & pythonw & """ """ & script & """"
sh.Run cmd, 0, False
