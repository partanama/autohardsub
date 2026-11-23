Option Explicit

Dim fso, shell, appDir, portablePy, mainPy, pyCmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

portablePy = appDir & "\runtime_python\pythonw.exe"
mainPy = appDir & "\main.py"

If fso.FileExists(portablePy) Then
    pyCmd = """" & portablePy & """"
Else
    pyCmd = "pythonw.exe"
End If

shell.Run pyCmd & " """ & mainPy & """", 0, False
