; installer.nsh — Personalización del instalador NSIS de Guto Flow
; Este archivo es incluido por electron-builder automáticamente.

; Página de bienvenida personalizada
!define MUI_WELCOMEPAGE_TITLE "Bienvenido a Guto Flow"
!define MUI_WELCOMEPAGE_TEXT "Este asistente te guiará por la instalación de Guto Flow.$\r$\n$\r$\nGuto Flow es tu sistema de culling y pre-edición de fotos con inteligencia artificial.$\r$\n$\r$\nLos modelos de IA se descargarán la primera vez que abras la app (requiere internet, ~720 MB total).$\r$\n$\r$\nHaz clic en Siguiente para continuar."

; Mostrar nota sobre modelos al finalizar
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Ver notas sobre los modelos de IA"
