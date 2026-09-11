import React, { useState } from 'react';
import { apiClient } from '../api/client';
import { useToast } from './Toast';

interface ClientToolsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentDirectory: string;
}

export const ClientToolsModal: React.FC<ClientToolsModalProps> = ({ isOpen, onClose, currentDirectory }) => {
  const [activeTab, setActiveTab] = useState<'export' | 'import'>('export');
  
  // Export State
  const [exportFilter, setExportFilter] = useState<'all' | 'selected'>('all');
  const [exporting, setExporting] = useState(false);
  
  // Import State
  const [pasteText, setPasteText] = useState('');
  const [importing, setImporting] = useState(false);
  
  const { showToast } = useToast();

  if (!isOpen) return null;

  const handleExport = async () => {
    if (!currentDirectory) return;
    
    try {
      const outputDir = await window.api.selectFolder();
      if (!outputDir) return;
      
      setExporting(true);
      const res = await apiClient.exportPreviews(currentDirectory, outputDir, exportFilter);
      
      if (res.errors > 0) {
        showToast(`Exportación finalizada: ${res.exported} exitosas, ${res.errors} errores.`, 'warning');
      } else {
        showToast(`Exportadas ${res.exported} previews exitosamente.`, 'success');
      }
    } catch (e: any) {
      showToast(`Error al exportar: ${e.message || e}`, 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleImportText = async () => {
    if (!currentDirectory || !pasteText.trim()) return;
    
    const lines = pasteText.split(/\n|,|;/).map(s => s.trim()).filter(Boolean);
    if (lines.length === 0) return;
    
    setImporting(true);
    try {
      const res = await apiClient.importSelection(currentDirectory, lines);
      showToast(`Se aplicaron 4 estrellas y etiqueta roja a ${res.updated} fotos.`, 'success');
      setPasteText('');
    } catch (e: any) {
      showToast(`Error al importar: ${e.message || e}`, 'error');
    } finally {
      setImporting(false);
    }
  };

  const handleImportFolder = async () => {
    if (!currentDirectory) return;
    
    try {
      const clientFolder = await window.api.selectFolder();
      if (!clientFolder) return;
      
      setImporting(true);
      const res = await apiClient.importSelection(currentDirectory, [], clientFolder);
      showToast(`Se aplicaron 4 estrellas y etiqueta roja a ${res.updated} fotos.`, 'success');
    } catch (e: any) {
      showToast(`Error al importar carpeta: ${e.message || e}`, 'error');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={headerStyle}>
          <h2 style={{ margin: 0, fontSize: 'var(--text-lg)' }}>Herramientas de Cliente</h2>
          <button onClick={onClose} style={closeBtnStyle}>×</button>
        </div>
        
        <div style={tabsStyle}>
          <button 
            style={activeTab === 'export' ? activeTabStyle : inactiveTabStyle}
            onClick={() => setActiveTab('export')}
          >
            Exportar Previews
          </button>
          <button 
            style={activeTab === 'import' ? activeTabStyle : inactiveTabStyle}
            onClick={() => setActiveTab('import')}
          >
            Importar Selección
          </button>
        </div>
        
        <div style={contentStyle}>
          {activeTab === 'export' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                Exporta las miniaturas de caché como imágenes JPG a una carpeta externa para entregas rápidas al cliente.
              </p>
              
              <label style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-medium)' }}>¿Qué fotos exportar?</span>
                <select 
                  value={exportFilter} 
                  onChange={(e) => setExportFilter(e.target.value as any)}
                  style={selectStyle}
                >
                  <option value="all">Todas las procesadas (Recomendado)</option>
                  <option value="selected">Solo las seleccionadas/highlights por IA</option>
                </select>
              </label>
              
              <button onClick={handleExport} disabled={exporting} style={actionBtnStyle}>
                {exporting ? 'Exportando...' : 'Elegir Carpeta Destino y Exportar'}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                Aplica 4 Estrellas y Etiqueta Roja a las fotos seleccionadas por el cliente. Las extensiones se ignoran (un JPG marcará su RAW original).
              </p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-medium)' }}>Opción 1: Pegar lista de nombres</span>
                <textarea 
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  placeholder="IMG_001.CR3\nIMG_005.CR3\n..."
                  style={textAreaStyle}
                  rows={5}
                />
                <button 
                  onClick={handleImportText} 
                  disabled={importing || !pasteText.trim()} 
                  style={actionBtnStyle}
                >
                  {importing ? 'Aplicando...' : 'Aplicar desde Texto'}
                </button>
              </div>
              
              <div style={{ textAlign: 'center', margin: '8px 0', color: 'var(--text-muted)' }}>— O —</div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-medium)' }}>Opción 2: Usar carpeta de selecciones</span>
                <button 
                  onClick={handleImportFolder} 
                  disabled={importing} 
                  style={{ ...actionBtnStyle, backgroundColor: 'var(--color-surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }}
                >
                  {importing ? 'Aplicando...' : 'Seleccionar Carpeta con Fotos'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Styles
const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0, left: 0, right: 0, bottom: 0,
  backgroundColor: 'rgba(5, 7, 10, 0.75)',
  backdropFilter: 'blur(4px)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-lg)',
  width: '100%',
  maxWidth: '480px',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden'
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '16px 20px',
  borderBottom: '1px solid var(--border-default)',
  backgroundColor: 'var(--color-surface-elevated)'
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  fontSize: '24px',
  cursor: 'pointer',
  padding: '0 4px',
  lineHeight: 1
};

const tabsStyle: React.CSSProperties = {
  display: 'flex',
  borderBottom: '1px solid var(--border-default)',
  backgroundColor: 'var(--color-surface-elevated)'
};

const tabBaseStyle: React.CSSProperties = {
  flex: 1,
  padding: '12px',
  background: 'none',
  border: 'none',
  borderBottom: '2px solid transparent',
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--fw-medium)',
  cursor: 'pointer',
  color: 'var(--text-secondary)'
};

const activeTabStyle: React.CSSProperties = {
  ...tabBaseStyle,
  color: 'var(--accent-primary)',
  borderBottomColor: 'var(--accent-primary)',
};

const inactiveTabStyle: React.CSSProperties = {
  ...tabBaseStyle,
};

const contentStyle: React.CSSProperties = {
  padding: '20px',
  display: 'flex',
  flexDirection: 'column',
  gap: '16px'
};

const selectStyle: React.CSSProperties = {
  padding: '10px',
  backgroundColor: 'var(--color-bg)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)'
};

const textAreaStyle: React.CSSProperties = {
  padding: '10px',
  backgroundColor: 'var(--color-bg)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  resize: 'vertical',
  fontFamily: 'var(--font-mono)'
};

const actionBtnStyle: React.CSSProperties = {
  padding: '12px',
  backgroundColor: 'var(--accent-primary)',
  color: 'var(--color-bg)',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--fw-bold)',
  cursor: 'pointer',
  transition: 'opacity 0.2s',
  opacity: 1
};
