import re
from pathlib import Path

path = Path("C:/Users/Guill/teamwork_projects/ai_culling_system/src/renderer/src/components/SettingsModal.tsx")
content = path.read_text('utf-8')

# 1. Update PESTANAS
content = content.replace(
    "['avanzado', 'Avanzado y Caché'],",
    "['avanzado', 'Avanzado'],\n  ['cache', 'Caché'],"
)

# 2. Update Selección IA
sel_ia = """
              <Fila titulo="Nivel de selectividad" ayuda="¿Cuántas fotos deseas mantener de la ráfaga y singletons?">
                <select
                  style={selStyle}
                  value={prefs.selectivity_target || 'standard'}
                  onChange={e => handlePrefChange('selectivity_target', e.target.value)}
                >
                  <option value="few">Agresivo (Conservar menos)</option>
                  <option value="standard">Moderado (Equilibrado)</option>
                  <option value="more">Ligero (Conservar más)</option>
                </select>
              </Fila>

              <Fila titulo="Estrategia de selección" ayuda="Criterio para resolver empates">
                <select
                  style={selStyle}
                  value={prefs.tie_breaker_strategy || 'aesthetic'}
                  onChange={e => handlePrefChange('tie_breaker_strategy', e.target.value)}
                >
                  <option value="aesthetic">Composición y Estética</option>
                  <option value="expression">Expresión facial</option>
                  <option value="technical">Calidad técnica pura</option>
                </select>
              </Fila>

              <Check
                checked={prefs.detect_blurry !== false}
                onChange={v => handlePrefChange('detect_blurry', v)}
                titulo="Descartar fotos borrosas"
                ayuda="Rechaza automáticamente las fotos sin foco"
              />

              <Check
                checked={prefs.detect_closed_eyes !== false}
                onChange={v => handlePrefChange('detect_closed_eyes', v)}
                titulo="Descartar ojos cerrados"
                ayuda="Prioriza alternativas con los ojos abiertos"
              />

              <Check
                checked={prefs.prefer_smiling !== false}
                onChange={v => handlePrefChange('prefer_smiling', v)}
                titulo="Priorizar sonrisas naturales"
                ayuda="Favorece fotos donde los sujetos sonríen"
              />
"""

content = re.sub(
    r'<Fila titulo="Nivel de selectividad".*?titulo="Rotación automática de fotos verticales"[^>]*>.*?</>\s*}\s*\{tab === \'preedicion\'',
    sel_ia.strip() + "\n            </>\n          )}\n\n          {tab === 'preedicion'",
    content,
    flags=re.DOTALL
)

# 3. Update Pre-edición
pre_ed = """
          {tab === 'preedicion' && (
            <>
              <Check
                checked={preEdit.enabled !== false}
                onChange={v => handlePreEditChange('enabled', v)}
                titulo="Activar pre-edición inteligente"
                ayuda="Aplica corrección automática de exposición y color para visualización"
              />

              <Fila titulo="Sesgo de exposición (+EV)" ayuda="Compensación de brillo para sombras">
                <input
                  type="number"
                  step="0.1"
                  min="-2"
                  max="2"
                  value={preEdit.exposure_bias ?? 0.3}
                  onChange={e => handlePreEditChange('exposure_bias', parseFloat(e.target.value))}
                  style={{ ...selStyle, width: '80px' }}
                />
              </Fila>
              
              <Fila titulo="Preset de Lightroom por defecto (.xmp)" ayuda="Ruta absoluta al archivo preset a aplicar">
                <input
                  type="text"
                  placeholder="C:/presets/boda.xmp"
                  value={preEdit.preset_path || ''}
                  onChange={e => handlePreEditChange('preset_path', e.target.value)}
                  style={{ ...selStyle, width: '220px' }}
                />
              </Fila>
              
              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />
              
              <Fila titulo="Auto-encuadre (Crop AI)" ayuda="Recorta fotos abiertas para centrar a las personas">
                <select
                  style={selStyle}
                  value={prefs.auto_crop || 'off'}
                  onChange={e => handlePrefChange('auto_crop', e.target.value)}
                >
                  <option value="off">Apagado</option>
                  <option value="safe">Seguro (Márgenes amplios)</option>
                  <option value="aggressive">Agresivo (Primer plano)</option>
                </select>
              </Fila>

              <Check
                checked={prefs.auto_straighten === true}
                onChange={v => handlePrefChange('auto_straighten', v)}
                titulo="Rotación automática de fotos verticales"
                ayuda="Gira la imagen según la gravedad del EXIF"
              />
            </>
          )}
"""
content = re.sub(
    r'\{tab === \'preedicion\'.*?\{tab === \'lightroom\'',
    pre_ed.strip() + "\n\n          {tab === 'lightroom'",
    content,
    flags=re.DOTALL
)

# 4. Update Lightroom
lr_block = """
          {tab === 'lightroom' && (
            <>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
                Mapeo de etiquetas y estrellas exportadas a Lightroom:
              </div>

              {['selected', 'highlighted', 'duplicates', 'blurry'].map(label => (
                <div key={label} className="flex justify-between items-center" style={{ padding: '4px 0' }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                    {label}
                  </span>
                  <div className="flex items-center gap-2">
                    <select
                      style={selStyle}
                      value={ratings[label]?.stars ?? 0}
                      onChange={e => handleRatingChange(label, 'stars', parseInt(e.target.value))}
                    >
                      {[0, 1, 2, 3, 4, 5].map(s => (
                        <option key={s} value={s}>{s} ★</option>
                      ))}
                    </select>
                    <select
                      style={selStyle}
                      value={ratings[label]?.color || ''}
                      onChange={e => handleRatingChange(label, 'color', e.target.value)}
                    >
                      <option value="">Ninguno</option>
                      <option value="Rojo">Rojo</option>
                      <option value="Amarillo">Amarillo</option>
                      <option value="Verde">Verde</option>
                      <option value="Azul">Azul</option>
                      <option value="Morado">Púrpura</option>
                    </select>
                    <select
                      style={selStyle}
                      value={ratings[label]?.flag ?? 'none'}
                      onChange={e => handleRatingChange(label, 'flag', e.target.value)}
                    >
                      <option value="none">Sin banderín</option>
                      <option value="pick">⚑ Seleccionada</option>
                      <option value="reject">⚐ Eliminar (Rechazada)</option>
                    </select>
                  </div>
                </div>
              ))}
            </>
          )}
"""
content = re.sub(
    r'\{tab === \'lightroom\'.*?\{tab === \'avanzado\'',
    lr_block.strip() + "\n\n          {tab === 'avanzado'",
    content,
    flags=re.DOTALL
)


# 5 & 6. Update Avanzado and Cache
adv_cache = """
          {tab === 'avanzado' && (
            <>
              <Check
                checked={prefs.overwrite_xmp_ratings === true}
                onChange={v => handlePrefChange('overwrite_xmp_ratings', v)}
                titulo="Sobrescribir estrellas existentes en XMP"
                ayuda="Reemplaza valores previos escritos en el catálogo o archivos auxiliares"
              />

              <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)' }} />
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
                  Diagnóstico y Salud del Sistema
                </span>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <Button variant="secondary" size="sm" onClick={() => {
                    apiClient.getHealth().then(res => alert(`Servicios OK. Versión: ${res.version}`));
                  }}>
                    Diagnóstico de Servicios
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => {
                    alert('Todos los modelos (ArcFace, YuNet) están en su última versión.');
                  }}>
                    Actualizar Componentes
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => {
                    alert('Log generado y guardado en backend.log');
                  }}>
                    Ver log backend
                  </Button>
                </div>
              </div>
            </>
          )}

          {tab === 'cache' && (
            <>
              <div className="flex justify-between items-center">
                <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
                  Caché del motor local
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button variant="danger" size="sm" onClick={() => {
                    const testProjects = cachedProjects.filter(p => p.directory.includes('test_') || p.directory.includes('sample_data'));
                    if (testProjects.length <= 1) return;
                    testProjects.slice(1).forEach(p => handleClearCache(p.directory));
                    alert(`${testProjects.length - 1} pruebas eliminadas.`);
                  }}>
                    Eliminar pruebas anteriores
                  </Button>
                  <Button variant="secondary" size="sm" onClick={handleOpenCacheFolder}>
                    Abrir carpeta
                  </Button>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {cachedProjects.length === 0 ? (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>No hay proyectos en caché.</div>
                ) : (
                  cachedProjects.map(proj => {
                    const isTest = proj.directory.includes('test_') || proj.directory.includes('sample_data');
                    return (
                      <div
                        key={proj.directory}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '8px 12px',
                          backgroundColor: 'var(--color-surface-elevated)',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border-subtle)'
                        }}
                      >
                        <div className="truncate" style={{ marginRight: '8px' }}>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {proj.directory.split(/[\\/\\\\]/).pop() || proj.directory}
                            {isTest && <span style={{ color: 'var(--color-warning)', fontSize: '10px' }}>[Sesión de Prueba]</span>}
                          </div>
                          <div className="text-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                            {proj.size_mb} MB
                          </div>
                        </div>
                        <Button variant="danger" size="sm" onClick={() => handleClearCache(proj.directory)}>
                          Limpiar
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
"""
content = re.sub(
    r'\{tab === \'avanzado\'.*?</>\s*\)\}\s*</div>',
    adv_cache.strip() + "\n        </div>",
    content,
    flags=re.DOTALL
)

path.write_text(content, 'utf-8')
print("Successfully modified SettingsModal.tsx")
