import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useToast } from './Toast';
import { MetadataPanel } from './MetadataPanel';

interface ClientToolsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentDirectory: string;
}

interface MetadataProfile {
  id: string;
  name: string;
  creator: string;
  copyright_notice: string;
  credit?: string;
  usage_terms?: string;
  web_statement?: string;
  is_default?: boolean;
}

export const ClientToolsModal: React.FC<ClientToolsModalProps> = ({ isOpen, onClose, currentDirectory }) => {
  const [activeTab, setActiveTab] = useState<'export' | 'import' | 'metadata'>('export');
  
  // Export State
  const [exportFilter, setExportFilter] = useState<'all' | 'selected'>('all');
  const [exporting, setExporting] = useState(false);
  
  // Import State
  const [pasteText, setPasteText] = useState('');
  const [importing, setImporting] = useState(false);

  // Metadata State
  const [profiles, setProfiles] = useState<MetadataProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [taxonomy, setTaxonomy] = useState<Record<string, { label: string; has_age: boolean; default_age?: string; base_tags: string[] }>>({});
  const [cities, setCities] = useState<string[]>([]);
  
  // Metadata Form Fields
  const [eventType, setEventType] = useState<string>('boda_religiosa');
  const [age, setAge] = useState<string>('');
  const [protagonist, setProtagonist] = useState<string>('');
  const [selectedCity, setSelectedCity] = useState<string>('Guayaquil');
  const [customCity, setCustomCity] = useState<string>('');
  const [customTags, setCustomTags] = useState<string>('');
  const [metadataScope, setMetadataScope] = useState<'all' | 'selected'>('all');
  const [keywordsMode, setKeywordsMode] = useState<'append' | 'replace'>('append');
  
  // GPS Detection State
  const [gpsStatus, setGpsStatus] = useState<{ checked: boolean; hasGps: boolean; city: string | null; coords: string | null }>({
    checked: false,
    hasGps: false,
    city: null,
    coords: null
  });
  const [detectingGps, setDetectingGps] = useState(false);
  const [applyingMetadata, setApplyingMetadata] = useState(false);

  // Profile Editor Modal/Drawer State
  const [editingProfile, setEditingProfile] = useState<boolean>(false);
  const [profileForm, setProfileForm] = useState<Partial<MetadataProfile>>({
    name: '',
    creator: '',
    copyright_notice: '© {year} {creator}. Todos los derechos reservados.',
    credit: '',
    usage_terms: '',
    web_statement: '',
    is_default: false
  });

  const { showToast } = useToast();

  useEffect(() => {
    if (isOpen) {
      loadMetadataConfig();
      if (currentDirectory) {
        checkGps(currentDirectory);
      }
    }
  }, [isOpen, currentDirectory]);

  const loadMetadataConfig = async () => {
    try {
      const res = await apiClient.getMetadataConfig();
      setProfiles(res.profiles || []);
      setTaxonomy(res.taxonomy || {});
      setCities(res.cities || []);

      const def = res.profiles?.find((p) => p.is_default) || res.profiles?.[0];
      if (def) {
        setSelectedProfileId(def.id);
      }
    } catch (e) {
      console.error('Error cargando configuración de metadatos:', e);
    }
  };

  const checkGps = async (dir: string) => {
    setDetectingGps(true);
    try {
      const res = await apiClient.detectGPS(dir);
      if (res.has_gps) {
        setGpsStatus({
          checked: true,
          hasGps: true,
          city: res.suggested_city,
          coords: `${res.latitude}, ${res.longitude}`
        });
        if (res.suggested_city) {
          setSelectedCity(res.suggested_city);
        }
      } else {
        setGpsStatus({ checked: true, hasGps: false, city: null, coords: null });
      }
    } catch (e) {
      setGpsStatus({ checked: true, hasGps: false, city: null, coords: null });
    } finally {
      setDetectingGps(false);
    }
  };

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

  // Metadata Profile Actions
  const handleOpenNewProfile = () => {
    setProfileForm({
      id: undefined,
      name: '',
      creator: '',
      copyright_notice: '© {year} {creator}. Todos los derechos reservados.',
      credit: '',
      usage_terms: 'Uso personal y privado acordado bajo contrato.',
      web_statement: '',
      is_default: profiles.length === 0
    });
    setEditingProfile(true);
  };

  const handleOpenEditProfile = () => {
    const p = profiles.find((item) => item.id === selectedProfileId);
    if (!p) return;
    setProfileForm({ ...p });
    setEditingProfile(true);
  };

  const handleSaveProfile = async () => {
    if (!profileForm.name?.trim()) {
      showToast('Ingresa un nombre para el perfil.', 'warning');
      return;
    }
    try {
      const res = await apiClient.saveMetadataProfile(profileForm as any);
      showToast('Perfil de copyright guardado.', 'success');
      setEditingProfile(false);
      await loadMetadataConfig();
      if (res.profile?.id) {
        setSelectedProfileId(res.profile.id);
      }
    } catch (e: any) {
      showToast(`Error guardando perfil: ${e.message || e}`, 'error');
    }
  };

  const handleDeleteProfile = async () => {
    if (!selectedProfileId) return;
    if (profiles.length <= 1) {
      showToast('Debe existir al menos un perfil de copyright.', 'warning');
      return;
    }
    try {
      await apiClient.deleteMetadataProfile(selectedProfileId);
      showToast('Perfil eliminado.', 'info');
      await loadMetadataConfig();
    } catch (e: any) {
      showToast(`Error eliminando perfil: ${e.message || e}`, 'error');
    }
  };

  const handleSetDefaultProfile = async () => {
    if (!selectedProfileId) return;
    try {
      await apiClient.setDefaultMetadataProfile(selectedProfileId);
      showToast('Perfil establecido como predeterminado.', 'success');
      await loadMetadataConfig();
    } catch (e: any) {
      showToast(`Error al marcar predeterminado: ${e.message || e}`, 'error');
    }
  };

  const handleApplyMetadata = async () => {
    if (!currentDirectory) {
      showToast('No hay una carpeta de proyecto abierta.', 'warning');
      return;
    }

    const finalCity = selectedCity === 'Otro' ? customCity.trim() : selectedCity;

    setApplyingMetadata(true);
    try {
      const res = await apiClient.applyBatchMetadata({
        directory: currentDirectory,
        filter_mode: metadataScope,
        profile_id: selectedProfileId,
        event_type: eventType,
        age: age.trim() || undefined,
        protagonist: protagonist.trim() || undefined,
        city: finalCity || undefined,
        custom_tags: customTags.trim() || undefined,
        keywords_mode: keywordsMode
      });

      if (res.errors > 0) {
        showToast(
          `Metadatos aplicados: ${res.updated_shots} disparos actualizados, ${res.errors} fallos.`,
          'warning'
        );
      } else {
        showToast(
          `¡Éxito! Se actualizaron los metadatos de ${res.updated_shots} disparos fotográficos.`,
          'success'
        );
      }
    } catch (e: any) {
      showToast(`Error aplicando metadatos: ${e.message || e}`, 'error');
    } finally {
      setApplyingMetadata(false);
    }
  };

  const activeProfile = profiles.find((p) => p.id === selectedProfileId);
  const currentEventTaxonomy = taxonomy[eventType];

  // Cálculo de previsualización de tags automáticos
  const previewTags: string[] = [];
  if (currentEventTaxonomy?.base_tags) {
    previewTags.push(...currentEventTaxonomy.base_tags);
  }
  if (currentEventTaxonomy?.has_age && age.trim()) {
    previewTags.push(age.trim().toLowerCase().includes('año') ? age.trim() : `${age.trim()} Años`);
  }
  if (protagonist.trim()) {
    previewTags.push(protagonist.trim());
  }
  const cityTag = selectedCity === 'Otro' ? customCity.trim() : selectedCity;
  if (cityTag) {
    previewTags.push(cityTag);
  }
  if (customTags.trim()) {
    customTags.split(',').map((t) => t.trim()).filter(Boolean).forEach((t) => previewTags.push(t));
  }

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={headerStyle}>
          <h2 style={{ margin: 0, fontSize: 'var(--text-lg)' }}>Herramientas de Cliente & Metadatos</h2>
          <button onClick={onClose} style={closeBtnStyle}>×</button>
        </div>
        
        <div style={tabsStyle}>
          <button 
            style={activeTab === 'metadata' ? activeTabStyle : inactiveTabStyle}
            onClick={() => setActiveTab('metadata')}
          >
            Metadatos & Copyright
          </button>
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
          {activeTab === 'metadata' && (
            <MetadataPanel
              directory={currentDirectory}
              showApplyButton={true}
              showScopeSelector={true}
            />
          )}

          {activeTab === 'export' && (
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
          )}

          {activeTab === 'import' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                Aplica 4 Estrellas y Etiqueta Roja a las fotos seleccionadas por el cliente. Las extensiones se ignoran (un JPG marcará su RAW original).
              </p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-medium)' }}>Opción 1: Pegar lista de nombres</span>
                <textarea 
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  placeholder={'IMG_001.CR3\nIMG_005.CR3\n...'}
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
  maxWidth: '600px',
  maxHeight: '90vh',
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
  padding: '12px 8px',
  background: 'none',
  border: 'none',
  borderBottom: '2px solid transparent',
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--fw-medium)',
  cursor: 'pointer',
  color: 'var(--text-secondary)',
  textAlign: 'center'
};

const activeTabStyle: React.CSSProperties = {
  ...tabBaseStyle,
  color: 'var(--accent-primary)',
  borderBottomColor: 'var(--accent-primary)',
  fontWeight: 'var(--fw-bold)'
};

const inactiveTabStyle: React.CSSProperties = {
  ...tabBaseStyle,
};

const contentStyle: React.CSSProperties = {
  padding: '18px 20px',
  display: 'flex',
  flexDirection: 'column',
  gap: '16px',
  overflowY: 'auto'
};

const cardSectionStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '10px',
  padding: '14px',
  backgroundColor: 'var(--color-bg)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)'
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 'var(--text-sm)',
  fontWeight: 'var(--fw-bold)',
  color: 'var(--text-primary)'
};

const fieldLabelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '6px',
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontWeight: 'var(--fw-medium)'
};

const inputStyle: React.CSSProperties = {
  padding: '8px 10px',
  backgroundColor: 'var(--color-surface)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  outline: 'none'
};

const selectStyle: React.CSSProperties = {
  padding: '8px 10px',
  backgroundColor: 'var(--color-surface)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  outline: 'none'
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

const secondaryBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: 'var(--color-surface)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  cursor: 'pointer'
};

const miniBtnStyle: React.CSSProperties = {
  padding: '4px 8px',
  fontSize: 'var(--text-xs)',
  backgroundColor: 'var(--color-surface)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer'
};

const profilePreviewStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  backgroundColor: 'var(--color-surface)',
  padding: '8px 10px',
  borderRadius: 'var(--radius-sm)',
  border: '1px dashed var(--border-default)',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px'
};

const profileEditorOverlayStyle: React.CSSProperties = {
  padding: '12px',
  backgroundColor: 'var(--color-surface-elevated)',
  border: '1px solid var(--accent-primary)',
  borderRadius: 'var(--radius-md)',
  display: 'flex',
  flexDirection: 'column',
  gap: '8px'
};

const tagChipStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)',
  padding: '3px 8px',
  backgroundColor: 'var(--color-surface)',
  border: '1px solid var(--border-default)',
  borderRadius: '12px',
  color: 'var(--accent-primary)',
  fontWeight: 'var(--fw-medium)'
};
