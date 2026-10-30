' Guto Flow 3.0 Beta — Lanzador silencioso de escritorio
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = projectDir
sh.Environment("PROCESS")("CULLING_LOCAL") = "1"

electronCmd = projectDir & "\node_modules\.bin\electron.cmd"
If Not fso.FileExists(electronCmd) Then
  MsgBox "No se encontro Electron. Ejecuta 'npm install' en " & projectDir, 48, "Guto Flow 3.0 Beta"
  WScript.Quit 1
End If

' 0 = ventana oculta (la consola de electron.cmd); la ventana de la app aparece de inmediato.
sh.Run """" & electronCmd & """ .", 0, False
