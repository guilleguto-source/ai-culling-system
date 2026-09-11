# Limpieza de Proyectos de Prueba y Huérfanos

Crear un modo de limpieza para eliminar proyectos basura ("test", "prueba", "evento") o aquellos cuyos directorios ya no existen en el disco, para mantener la Biblioteca ordenada.

## Proposed Changes

### Backend
#### [MODIFY] [media.py](file:///C:/Users/Guill/teamwork_projects/ai_culling_system/backend/routers/media.py)
- Añadir un nuevo endpoint `DELETE /library/cleanup`.
- El endpoint iterará sobre los archivos `.db` en el directorio de análisis.
- Criterios para eliminar la base de datos y la caché de miniaturas:
  - El directorio original (`directory`) ya no existe en el disco.
  - El nombre de la carpeta (en minúsculas) incluye palabras clave: `"test_"`, `"prueba"`, `"debug"`, o es exactamente `"evento"`.
- Retornará la cantidad de proyectos eliminados.

### Frontend
#### [MODIFY] [LibraryView.tsx](file:///C:/Users/Guill/teamwork_projects/ai_culling_system/src/renderer/src/components/LibraryView.tsx)
- Añadir un botón secundario (ej. "Limpiar Pruebas") en la cabecera junto al título de "Biblioteca" o un botón general de purga.
- Al hacer clic, consumirá el endpoint `DELETE /library/cleanup`.
- Recargará la lista de proyectos automáticamente tras la limpieza.

## Verification Plan
1. Hacer clic en el nuevo botón "Limpiar Pruebas" en la Biblioteca.
2. Verificar que los proyectos "evento", "Evento De Prueba", "test_debug..." desaparecen de la UI.
3. Verificar que los archivos `.db` correspondientes fueron eliminados del directorio de análisis.
