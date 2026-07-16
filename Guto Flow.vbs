' Photo Culler — lanzador de escritorio sin terminal.
' Arranca Electron en modo local (CULLING_LOCAL=1): frontend compilado
' (dist/renderer) + backend Python del sistema, sin ventanas de consola.
' Si cambias el codigo, regenera con: npm run build:frontend && npm run build:electron
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = projectDir
sh.Environment("PROCESS")("CULLING_LOCAL") = "1"

electronCmd = projectDir & "\node_modules\.bin\electron.cmd"
If Not fso.FileExists(electronCmd) Then
  MsgBox "No se encontro Electron. Ejecuta 'npm install' en " & projectDir, 48, "Guto Flow"
  WScript.Quit 1
End If

' 0 = ventana oculta (la consola de electron.cmd); la ventana de la app aparece igual.
sh.Run """" & electronCmd & """ .", 0, False
