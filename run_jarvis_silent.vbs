' JARVIS Silent Background Launcher
' Starts JARVIS as a background daemon with no visible command prompt window.
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir
WshShell.Run "pythonw -m jarvis run", 0, False
