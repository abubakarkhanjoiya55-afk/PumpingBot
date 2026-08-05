' SceneCut Pro+ — CapCut-style installer entry (NO black CMD window)
Option Explicit

Dim sh, fso, root, ps1, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = root & "\desktop\setup_gui.ps1"

If Not fso.FileExists(ps1) Then
  MsgBox "setup_gui.ps1 missing. ZIP incomplete — dubara download karo.", vbCritical, "SceneCut Pro+"
  WScript.Quit 1
End If

sh.CurrentDirectory = root
' 0 = hidden PowerShell console; WinForms UI still shows
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """ -SourceDir """ & root & """"
sh.Run cmd, 0, True
