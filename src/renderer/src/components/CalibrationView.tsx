import React, { useState, useEffect, useCallback } from 'react';
import Loupe from './Loupe';
import { apiClient } from '../api/client';

// Etiquetas legibles por atributo
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

const DEFAULTS: Record<string, string> = { glasses: 'sin' };

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
      const data = await apiClient.getCalibrationStats();
      setStats(data);
    } catch { /* backend caído */ }
  }, []);

  const cargar = useCallback(async () => {
    if (!directory) return;
    setCargando(true);
    setMsg('');
    try {
      const d = await apiClient.getCalibrationCandidates(directory, 40);
      setCands(d.candidatas || []);
      setI(0);
      if (!d.candidatas?.length) setMsg('No hay caras pendientes. Corre un culling primero.');
    } catch (e: any) {
      setMsg(e.message || 'Error cargando caras');
    } finally {
      setCargando(false);
    }
  }, [directory]);

  useEffect(() => { cargar(); cargarStats(); }, [cargar, cargarStats]);

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
      await apiClient.labelCalibrationFace({
        photo_path: actual.photo_path,
        face_index: actual.face_index,
        face_bbox: actual.face_bbox,
        labels,
        predictions: actual.predictions,
      });
      cargarStats();
    } catch { }
    siguiente();
  };

  const guardar = () => enviar({ ...sel, subject: 'persona' });
  const descartar = (valor: string) => enviar({ subject: valor });

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
    ? apiClient.getCalibrationFaceUrl(
        actual.photo_path,
        actual.face_bbox[0],
        actual.face_bbox[1],
        actual.face_bbox[2],
        actual.face_bbox[3]
      )
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
            flexDirection: 'column', padding: '12px' }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              <Loupe src={url} alt="cara"
                style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: '6px' }} />
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '8px', textAlign: 'center' }}>
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

            {/* Descartes */}
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
