import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useToast } from './Toast';

export interface MetadataProfile {
  id: string;
  name: string;
  creator: string;
  copyright_notice: string;
  credit?: string;
  usage_terms?: string;
  web_statement?: string;
  is_default?: boolean;
}

export interface MetadataPayload {
  profile_id?: string;
  event_type: string;
  age?: string;
  protagonist?: string;
  city?: string;
  custom_tags?: string;
  keywords_mode: 'append' | 'replace';
  filter_mode?: 'all' | 'selected';
}

interface MetadataPanelProps {
  directory: string;
  showApplyButton?: boolean;
  showScopeSelector?: boolean;
  disabled?: boolean;
  onChange?: (payload: MetadataPayload) => void;
  onApplied?: () => void;
}

export const MetadataPanel: React.FC<MetadataPanelProps> = ({
  directory,
  showApplyButton = false,
  showScopeSelector = false,
  disabled = false,
  onChange,
  onApplied
}) => {
  // Profiles & taxonomy
  const [profiles, setProfiles] = useState<MetadataProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [taxonomy, setTaxonomy] = useState<Record<string, { label: string; has_age: boolean; default_age?: string; base_tags: string[] }>>({});
  const [cities, setCities] = useState<string[]>([]);

  // Metadata form fields
  const [eventType, setEventType] = useState<string>('boda_religiosa');
  const [age, setAge] = useState<string>('');
  const [protagonist, setProtagonist] = useState<string>('');
  const [selectedCity, setSelectedCity] = useState<string>('Guayaquil');
  const [customCity, setCustomCity] = useState<string>('');
  const [customTags, setCustomTags] = useState<string>('');
  const [metadataScope, setMetadataScope] = useState<'all' | 'selected'>('all');
  const [keywordsMode, setKeywordsMode] = useState<'append' | 'replace'>('append');

  // Existing metadata & GPS from sample photo
  const [gpsStatus, setGpsStatus] = useState<{
    checked: boolean;
    hasGps: boolean;
    city: string | null;
    coords: string | null;
    existingCreator: string | null;
    existingCopyright: string | null;
    sampleFile: string | null;
  }>({
    checked: false,
    hasGps: false,
    city: null,
    coords: null,
    existingCreator: null,
    existingCopyright: null,
    sampleFile: null
  });
  const [detectingGps, setDetectingGps] = useState(false);
  const [applyingMetadata, setApplyingMetadata] = useState(false);

  // Profile Editor Modal
  const [editingProfile, setEditingProfile] = useState<boolean>(false);
  const [profileForm, setProfileForm] = useState<Partial<MetadataProfile>>({
    name: '',
    creator: '',
    copyright_notice: '© {year} {creator}. Todos los derechos reservados.',
    credit: '',
    usage_terms: 'Uso personal y privado acordado bajo contrato.',
    web_statement: '',
    is_default: false
  });

  const { showToast } = useToast();

  useEffect(() => {
    loadMetadataConfig();
  }, []);

  useEffect(() => {
    if (directory) {
      checkDirectoryMetadata(directory);
    }
  }, [directory]);

  // Propagate state to parent whenever changes occur
  useEffect(() => {
    if (onChange) {
      const finalCity = selectedCity === 'Otro' ? customCity.trim() : selectedCity;
      onChange({
        profile_id: selectedProfileId || undefined,
        event_type: eventType,
        age: age.trim() || undefined,
        protagonist: protagonist.trim() || undefined,
        city: finalCity || undefined,
        custom_tags: customTags.trim() || undefined,
        keywords_mode: keywordsMode,
        filter_mode: metadataScope
      });
    }
  }, [selectedProfileId, eventType, age, protagonist, selectedCity, customCity, customTags, keywordsMode, metadataScope]);

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

  const checkDirectoryMetadata = async (dir: string) => {
    setDetectingGps(true);
    try {
      const res = await apiClient.detectGPS(dir);
      const coords = res.has_gps && res.latitude && res.longitude
        ? `${res.latitude}, ${res.longitude}`
        : null;

      setGpsStatus({
        checked: true,
        hasGps: res.has_gps,
        city: res.suggested_city || null,
        coords,
        existingCreator: res.existing_creator || null,
        existingCopyright: res.existing_copyright || null,
        sampleFile: res.sample_file || null
      });

      if (res.suggested_city) {
        setSelectedCity(res.suggested_city);
      }
    } catch {
      setGpsStatus({
        checked: true,
        hasGps: false,
        city: null,
        coords: null,
        existingCreator: null,
        existingCopyright: null,
        sampleFile: null
      });
    } finally {
      setDetectingGps(false);
    }
  };

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

  const handleApplyBatchNow = async () => {
    if (!directory) {
      showToast('No hay una carpeta de proyecto asignada.', 'warning');
      return;
    }

    const finalCity = selectedCity === 'Otro' ? customCity.trim() : selectedCity;
    setApplyingMetadata(true);
    try {
      const res = await apiClient.applyBatchMetadata({
        directory,
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
          `Metadatos aplicados: ${res.updated_shots} fotos actualizadas, ${res.errors} fallos.`,
          'warning'
        );
      } else {
        showToast(
          `¡Éxito! Se actualizaron los metadatos de ${res.updated_shots} fotos.`,
          'success'
        );
      }
      if (onApplied) onApplied();
    } catch (e: any) {
      showToast(`Error aplicando metadatos: ${e.message || e}`, 'error');
    } finally {
      setApplyingMetadata(false);
    }
  };

  const activeProfile = profiles.find((p) => p.id === selectedProfileId);
  const currentEventTaxonomy = taxonomy[eventType];

  // Cálculo de tags automáticos en tiempo real
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
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      opacity: disabled ? 0.45 : 1,
      pointerEvents: disabled ? 'none' : 'auto',
      transition: 'opacity 0.2s ease'
    }}>
      {/* Banner de Metadatos Detectados en las Fotos Actuales */}
      {gpsStatus.checked && (
        <div style={{
          padding: '12px 14px',
          borderRadius: 'var(--radius-md)',
          backgroundColor: 'rgba(231, 161, 58, 0.08)',
          border: '1px solid rgba(231, 161, 58, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              🔍 Metadatos Actuales Detectados en la Carpeta
            </span>
            {gpsStatus.sampleFile && (
              <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                Muestra: {gpsStatus.sampleFile}
              </span>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            <div>
              <strong>Autor actual:</strong> {gpsStatus.existingCreator || <span style={{ color: 'var(--text-tertiary)' }}>No asignado en cámara</span>}
            </div>
            <div>
              <strong>Copyright actual:</strong> {gpsStatus.existingCopyright || <span style={{ color: 'var(--text-tertiary)' }}>No asignado en cámara</span>}
            </div>
            <div>
              <strong>Ubicación GPS:</strong>{' '}
              {gpsStatus.hasGps ? (
                <span style={{ color: '#10B981', fontWeight: 'var(--fw-medium)' }}>
                  📍 {gpsStatus.city ? `${gpsStatus.city} (${gpsStatus.coords})` : gpsStatus.coords}
                </span>
              ) : (
                <span style={{ color: 'var(--text-tertiary)' }}>Sin GPS en EXIF</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sección 1: Perfiles de Copyright */}
      <div style={cardSectionStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={sectionTitleStyle}>1. Perfil de Copyright a Inyectar</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button onClick={handleOpenNewProfile} style={miniBtnStyle}>+ Nuevo</button>
            <button onClick={handleOpenEditProfile} style={miniBtnStyle} disabled={!selectedProfileId}>Editar</button>
            <button onClick={handleSetDefaultProfile} style={miniBtnStyle} title="Fijar como predeterminado" disabled={!selectedProfileId}>
              ★ Predeterminado
            </button>
            {profiles.length > 1 && (
              <button onClick={handleDeleteProfile} style={{ ...miniBtnStyle, color: '#EF4444' }} title="Eliminar perfil">
                🗑
              </button>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            style={{ ...selectStyle, flex: 1 }}
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.is_default ? '★ (Predeterminado)' : ''} — {p.creator || 'Sin autor'}
              </option>
            ))}
          </select>
        </div>

        {activeProfile && (
          <div style={profilePreviewStyle}>
            <div>
              <strong>Aviso a escribir:</strong>{' '}
              {(activeProfile.copyright_notice || '')
                .replace('{year}', String(new Date().getFullYear()))
                .replace('{creator}', activeProfile.creator || '')
                .replace('{client}', protagonist || '')}
            </div>
            <div>
              <strong>Crédito / Agencia:</strong> {activeProfile.credit || activeProfile.creator || '—'}
            </div>
          </div>
        )}
      </div>

      {/* Sub-formulario Modal para editar perfil */}
      {editingProfile && (
        <div style={profileEditorOverlayStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h4 style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
              {profileForm.id ? 'Editar Perfil de Copyright' : 'Nuevo Perfil de Copyright'}
            </h4>
            <button onClick={() => setEditingProfile(false)} style={miniBtnStyle}>✕</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <label style={fieldLabelStyle}>
              Nombre del Perfil:
              <input
                type="text"
                value={profileForm.name || ''}
                onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                placeholder="Ej. Estudio Principal, Boda VIP, etc."
                style={inputStyle}
              />
            </label>
            <label style={fieldLabelStyle}>
              Autor / Fotógrafo:
              <input
                type="text"
                value={profileForm.creator || ''}
                onChange={(e) => setProfileForm({ ...profileForm, creator: e.target.value })}
                placeholder="Ej. Guille Guto"
                style={inputStyle}
              />
            </label>
            <label style={fieldLabelStyle}>
              Aviso de Copyright (usa {'{year}'}, {'{creator}'} y {'{client}'}):
              <input
                type="text"
                value={profileForm.copyright_notice || ''}
                onChange={(e) => setProfileForm({ ...profileForm, copyright_notice: e.target.value })}
                placeholder="© {year} {creator}. Todos los derechos reservados."
                style={inputStyle}
              />
            </label>
            <label style={fieldLabelStyle}>
              Línea de Crédito / Agencia:
              <input
                type="text"
                value={profileForm.credit || ''}
                onChange={(e) => setProfileForm({ ...profileForm, credit: e.target.value })}
                placeholder="Ej. Guille Guto Photography"
                style={inputStyle}
              />
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
              <button onClick={() => setEditingProfile(false)} style={secondaryBtnStyle}>Cancelar</button>
              <button onClick={handleSaveProfile} style={actionBtnStyle}>Guardar Perfil</button>
            </div>
          </div>
        </div>
      )}

      {/* Sección 2: Evento y Protagonistas */}
      <div style={cardSectionStyle}>
        <span style={sectionTitleStyle}>2. Clasificación de Evento & Protagonista</span>
        
        <div style={{ display: 'grid', gridTemplateColumns: currentEventTaxonomy?.has_age ? '1fr 1fr' : '1fr', gap: '12px' }}>
          <label style={fieldLabelStyle}>
            Categoría de Evento:
            <select
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value);
                if (!taxonomy[e.target.value]?.has_age) {
                  setAge('');
                }
              }}
              style={selectStyle}
            >
              {Object.entries(taxonomy).map(([key, item]) => (
                <option key={key} value={key}>{item.label}</option>
              ))}
            </select>
          </label>

          {currentEventTaxonomy?.has_age && (
            <label style={fieldLabelStyle}>
              Edad / Años Cumplidos:
              <input
                type="text"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="Ej. 1 Año, 5 Años, 33 Años"
                style={inputStyle}
              />
            </label>
          )}
        </div>

        <label style={fieldLabelStyle}>
          Nombre de Protagonista(s) / Cliente:
          <input
            type="text"
            value={protagonist}
            onChange={(e) => setProtagonist(e.target.value)}
            placeholder="Ej. Carlos & Andrea / Valentina / Familia Pérez"
            style={inputStyle}
          />
        </label>
      </div>

      {/* Sección 3: Ubicación y Ciudad */}
      <div style={cardSectionStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={sectionTitleStyle}>3. Ubicación Geográfica</span>
          {gpsStatus.hasGps && (
            <span style={{ fontSize: 'var(--text-xs)', color: '#10B981' }}>
              📍 Coordenadas detectadas automáticamente
            </span>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: selectedCity === 'Otro' ? '1fr 1fr' : '1fr', gap: '12px' }}>
          <label style={fieldLabelStyle}>
            Ciudad / Localidad:
            <select
              value={selectedCity}
              onChange={(e) => setSelectedCity(e.target.value)}
              style={selectStyle}
            >
              {cities.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
              <option value="Otro">Otro / Personalizado...</option>
            </select>
          </label>

          {selectedCity === 'Otro' && (
            <label style={fieldLabelStyle}>
              Especificar Ciudad:
              <input
                type="text"
                value={customCity}
                onChange={(e) => setCustomCity(e.target.value)}
                placeholder="Ej. Galápagos, Baños..."
                style={inputStyle}
              />
            </label>
          )}
        </div>
      </div>

      {/* Sección 4: Palabras Clave Libres y Previsualización */}
      <div style={cardSectionStyle}>
        <span style={sectionTitleStyle}>4. Palabras Clave Generadas (Keywords XMP)</span>
        
        <label style={fieldLabelStyle}>
          Tags adicionales (separados por coma):
          <input
            type="text"
            value={customTags}
            onChange={(e) => setCustomTags(e.target.value)}
            placeholder="Ej. Hacienda, Aire Libre, Novios, Noche"
            style={inputStyle}
          />
        </label>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            Keywords que se inyectarán en lote (dc:subject):
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {previewTags.map((tag, idx) => (
              <span key={idx} style={tagChipStyle}>{tag}</span>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: showScopeSelector ? '1fr 1fr' : '1fr', gap: '12px', marginTop: '6px' }}>
          <label style={fieldLabelStyle}>
            Modo de Etiquetas:
            <select
              value={keywordsMode}
              onChange={(e) => setKeywordsMode(e.target.value as any)}
              style={selectStyle}
            >
              <option value="append">Añadir a existentes (Append)</option>
              <option value="replace">Reemplazar existentes</option>
            </select>
          </label>

          {showScopeSelector && (
            <label style={fieldLabelStyle}>
              ¿A qué fotos aplicar?:
              <select
                value={metadataScope}
                onChange={(e) => setMetadataScope(e.target.value as any)}
                style={selectStyle}
              >
                <option value="all">Todas las fotos del proyecto</option>
                <option value="selected">Solo fotos seleccionadas</option>
              </select>
            </label>
          )}
        </div>
      </div>

      {/* Botón de Ejecución inmediata opcional (para ClientToolsModal) */}
      {showApplyButton && (
        <button
          onClick={handleApplyBatchNow}
          disabled={applyingMetadata || !directory}
          style={{ ...actionBtnStyle, marginTop: '4px' }}
        >
          {applyingMetadata ? 'Inyectando Metadatos a XMP...' : 'Aplicar Metadatos & Copyright en Lote'}
        </button>
      )}
    </div>
  );
};

// Styles
const cardSectionStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '10px',
  padding: '14px',
  backgroundColor: 'var(--color-surface-elevated)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)'
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)',
  fontWeight: 'var(--fw-bold)',
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em'
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
  backgroundColor: 'var(--color-bg)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  outline: 'none'
};

const selectStyle: React.CSSProperties = {
  padding: '8px 10px',
  backgroundColor: 'var(--color-bg)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--text-sm)',
  outline: 'none'
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
  backgroundColor: 'var(--color-bg)',
  color: 'var(--text-secondary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer'
};

const profilePreviewStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  backgroundColor: 'var(--color-bg)',
  padding: '8px 10px',
  borderRadius: 'var(--radius-sm)',
  border: '1px dashed var(--border-default)',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px'
};

const profileEditorOverlayStyle: React.CSSProperties = {
  padding: '14px',
  backgroundColor: 'var(--color-bg)',
  border: '1px solid var(--accent-primary)',
  borderRadius: 'var(--radius-md)',
  display: 'flex',
  flexDirection: 'column',
  gap: '10px'
};

const tagChipStyle: React.CSSProperties = {
  fontSize: 'var(--text-xs)',
  padding: '3px 8px',
  backgroundColor: 'rgba(231, 161, 58, 0.08)',
  border: '1px solid rgba(231, 161, 58, 0.3)',
  borderRadius: '12px',
  color: 'var(--accent-primary)',
  fontWeight: 'var(--fw-medium)'
};

export default MetadataPanel;
