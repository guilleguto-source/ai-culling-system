import React, { useState, useEffect, useCallback } from 'react';

const API = 'http://127.0.0.1:8000';

// Etiquetas legibles por atributo. `teclas` son los atajos de la fila, en el
// mismo orden que `valores` (1ª tecla = 1er valor).
const OPCIONES: Record<string, { titulo: string; teclas: string; valores: [string, string][] }> = {
  eyes: {
    titulo: 'Ojos', teclas: 'qwe',
    valores: [['abiertos', 'Abiertos'], ['cerrados', 'Cerrados'], ['entrecerrados', 'Entrecerrados']]
  },
  gaze: {
    titulo: 'Mirada', teclas: 'asd',
    valores: [['camara', 'A cámara'], ['fuera', 'A otro lado']]
  },
  mouth: {
    titulo: 'Boca', teclas: 'zxc',
    valores: [['sonrisa', 'Sonrisa'], ['neutra', 'Neutra'], ['hablando', 'Hablando / mueca']]
  },
  glasses: {
    titulo: 'Lentes', teclas: 'fgh',
    valores: [['sin', 'Sin lentes'], ['lentes', 'Lentes'], ['oscuros', 'Lentes oscuros']]
  },
};

// Lo que se pre-marca cuando el detector no opina (no tiene señal geométrica).
// Lentes → "sin": es el caso normal; el usuario solo toca la fila si hay lentes.
const DEFAULTS: Record<string, string> = { glasses: 'sin' };

// Descartes: la cara no se juzga, se etiqueta como lo que es.
// [tecla, valor, texto, ayuda] — la tecla es también la que muestra el botón.
const DESCARTES: [string, string, string, string][] = [
  ['1', 'no_cara', 'No es una cara', 'Un estampado, un muñeco, un dibujo: el detector se equivocó'],
  ['2', 'ilegible', 'Indistinguible', 'Cara real pero lejana, movida o tapada: ni el ojo humano la juzga'],
];

interface Candidata {
  photo_path: string;
  face_index: number;
  face_bbox: number[];
  uncertainty: number;
  predictions: Record<string, string>;
}

export default function CalibrationView({ directory }: { directory?: string }) {
  const [cands, setCands] = useState<Candidata[]>([]);
  const [i, setI] = useState(0);
  const [sel, setSel] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<any>(null);
  const [cargando, setCargando] = useState(false);
  const [msg, setMsg] = useState('');

  const actual = cands[i];

  const cargarStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/calibration/stats`);
      if (r.ok) setStats(await r.json());
    } catch { /* backend caído: no bloquea la vista */ }
  }, []);

  const cargar = useCallback(async () => {
    if (!directory) return;
    setCargando(true);
    setMsg('');
    try {
      const r = await fetch(`${API}/calibration/candidates?directory=${encodeURIComponent(directory)}&limit=40`);
      const d = await r.json();
      if (!r.ok) { setMsg(d.detail || 'Error cargando caras'); return; }
      setCands(d.candidatas || []);
      setI(0);
      if (!d.candidatas?.length) setMsg('No hay caras pendientes. Corre un culling primero.');
    } catch {
      setMsg('Error de conexión con el backend');
    } finally {
      setCargando(false);
    }
  }, [directory]);

  useEffect(() => { cargar(); cargarStats(); }, [cargar, cargarStats]);

  // Al cambiar de cara, pre-marcar lo que propone el detector. Una predicción
  // vacía = el detector no opina sobre ese atributo: ahí manda el default.
  useEffect(() => {
    if (!actual) return;
    const opina = Object.entries(actual.predictions).filter(([, v]) => v);
    setSel({ ...DEFAULTS, ...Object.fromEntries(opina) });
  }, [actual]);

  const siguiente = () => {
    if (i + 1 >= cands.length) { cargar(); cargarStats(); }
    else setI(i + 1);
  };

  const enviar = async (labels: Record<string, string>) => {
    if (!actual) return;
    try {
      await fetch(`${API}/calibration/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          photo_path: actual.photo_path,
          face_index: actual.face_index,
          face_bbox: actual.face_bbox,
          labels,
          predictions: actual.predictions,
        })
      });
      cargarStats();
    } catch { /* se pierde una etiqueta, no vale bloquear el flujo */ }
    siguiente();
  };

  // Cara buena: atributos + subject=persona (el ejemplo positivo que el
  // clasificador necesita para aprender a distinguir la basura).
  const guardar = () => enviar({ ...sel, subject: 'persona' });

  // Descarte: solo subject. Los ojos o la boca de un estampado no significan
  // nada y ensuciarían el entrenamiento.
  const descartar = (valor: string) => enviar({ subject: valor });

  // Atajos: las teclas de cada fila (ver OPCIONES y DESCARTES),
  // Enter = confirmar, Espacio = saltar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') { e.preventDefault(); guardar(); return; }
      if (e.key === ' ') { e.preventDefault(); siguiente(); return; }
      const desc = DESCARTES.find(([tecla]) => tecla === e.key);
      if (desc) { e.preventDefault(); descartar(desc[1]); return; }
      for (const [attr, o] of Object.entries(OPCIONES)) {
        const idx = o.teclas.indexOf(e.key.toLowerCase());
        if (idx >= 0 && o.valores[idx]) {
          setSel(s => ({ ...s, [attr]: o.valores[idx][0] }));
          return;
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (!directory) {
    return <div className="flex-center" style={{ height: '100%', color: 'var(--text-muted)' }}>
      Selecciona una carpeta y corre un culling para calibrar.
    </div>;
  }

  const url = actual
    ? `${API}/calibration/face?path=${encodeURIComponent(actual.photo_path)}` +
      `&x=${actual.face_bbox[0]}&y=${actual.face_bbox[1]}&w=${actual.face_bbox[2]}&h=${actual.face_bbox[3]}`
    : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '16px', gap: '12px' }}>
      {/* Cabecera: precisión REAL del detector sobre tus fotos */}
      <div className="flex-between glass-panel" style={{ padding: '10px 20px' }}>
        <div>
          <strong>Calibración</strong>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginLeft: '10px' }}>
            Enseña tu criterio: 1 cara a la vez. Ya marcamos lo que cree el detector — corrige solo lo que esté mal.
          </span>
        </div>
        <div style={{ display: 'flex', gap: '18px', fontSize: '0.75rem' }}>
          {stats && Object.entries(OPCIONES).map(([attr, o]) => {
            const a = stats.por_atributo?.[attr];
            const geo = a?.geometria != null ? `${Math.round(a.geometria * 100)}%` : '—';
            const apr = a?.aprendido != null ? `${Math.round(a.aprendido * 100)}%` : null;
            return (
              <span key={attr} style={{ color: 'var(--text-secondary)' }} title={
                'Geometría = precisión del detector actual contra tus etiquetas.\n' +
                'Aprendido = clasificador entrenado con tus etiquetas (validación cruzada).' +
                (a?.faltan ? `\nFaltan ${a.faltan} etiquetas para entrenar.` : '')
              }>
                {o.titulo}:{' '}
                <strong style={{ color: 'var(--accent-primary)' }}>{geo}</strong>
                {apr && <> · aprendido <strong style={{ color: 'var(--status-selected-text)' }}>{apr}</strong></>}
                <span style={{ color: 'var(--text-muted)' }}> ({a?.total || 0})</span>
              </span>
            );
          })}
        </div>
      </div>

      {msg && <div style={{ color: 'var(--text-muted)', textAlign: 'center' }}>{msg}</div>}

      {actual && (
        <div style={{ flex: 1, display: 'flex', gap: '16px', minHeight: 0 }}>
          {/* La cara */}
          <div className="glass-panel" style={{ flex: 1, minHeight: 0, display: 'flex',
            flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '12px' }}>
            <img src={url} alt="cara"
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: '6px' }} />
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '8px' }}>
              {actual.photo_path.split(/[\\/]/).pop()} · cara {actual.face_index + 1}
              {' · '}duda {Math.round(actual.uncertainty * 100)}%
            </div>
          </div>

          {/* Las preguntas */}
          <div style={{ width: '320px', display: 'flex', flexDirection: 'column', gap: '14px',
            overflowY: 'auto' }}>
            {Object.entries(OPCIONES).map(([attr, o]) => (
              <div key={attr} className="glass-panel" style={{ padding: '12px' }}>
                <div style={{ fontWeight: 600, marginBottom: '8px', fontSize: '0.85rem' }}>{o.titulo}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {o.valores.map(([valor, texto], j) => {
                    const activo = sel[attr] === valor;
                    const propuesto = actual.predictions[attr] === valor;
                    return (
                      <button key={valor}
                        onClick={() => setSel(s => ({ ...s, [attr]: valor }))}
                        className={activo ? 'btn btn-primary' : 'btn btn-secondary'}
                        style={{ justifyContent: 'space-between', fontSize: '0.8rem', padding: '6px 10px' }}>
                        <span>{texto}{propuesto && !activo ? ' ·' : ''}</span>
                        <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>
                          {o.teclas[j]?.toUpperCase()}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={guardar}>
                Guardar ⏎
              </button>
              <button className="btn btn-secondary" onClick={siguiente}
                title="Pasar sin decidir: no se guarda nada y volverá a preguntarse">
                Saltar ␣
              </button>
            </div>

            {/* Descartes: no es una cara juzgable. Se etiquetan (no se saltan)
                para que el clasificador aprenda a filtrarlas. */}
            <div style={{ display: 'flex', gap: '8px' }}>
              {DESCARTES.map(([tecla, valor, texto, ayuda]) => (
                <button key={valor} className="btn btn-secondary" title={ayuda}
                  onClick={() => descartar(valor)}
                  style={{ flex: 1, justifyContent: 'space-between', fontSize: '0.78rem',
                    padding: '6px 10px' }}>
                  <span>{texto}</span>
                  <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>{tecla}</span>
                </button>
              ))}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'center' }}>
              {i + 1} de {cands.length} en cola {cargando && '· cargando…'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
