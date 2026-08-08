/**
 * src/renderer/src/api/client.ts
 * Cliente API tipado y centralizado para la comunicación con el backend FastAPI.
 */

import {
  HardwareInfo,
  Settings,
  JobStatus,
  JobResults,
  BurstFaceCropsResponse,
  CalibrationCandidate,
  CalibrationStatsResponse,
  LearningSummary,
  CachedProject,
  StorylineChapter
} from '../types/api';

export const BACKEND_URL = 'http://127.0.0.1:8000';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options?.headers || {})
  };

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      // Ignorar fallback a statusText
    }
    throw new Error(`API Error [${response.status}]: ${errorDetail}`);
  }

  return response.json();
}

export const apiClient = {
  // --- Sistema & Configuración ---
  getHealth: () => request<{ status: string; version: string; stale_code: boolean }>('/health'),

  getHardware: () => request<HardwareInfo>('/hardware'),

  getSettings: () => request<Settings>('/settings'),

  saveSettings: (settings: Settings) =>
    request<{ success: boolean; settings: Settings }>('/settings', {
      method: 'POST',
      body: JSON.stringify(settings)
    }),

  getProfiles: () => request<{ perfiles: string[] }>('/profiles'),

  saveProfile: (nombre: string) =>
    request<{ success: boolean; guardado: string }>('/profiles/save', {
      method: 'POST',
      body: JSON.stringify({ nombre })
    }),

  applyProfile: (nombre: string) =>
    request<{ success: boolean; aplicado: string }>('/profiles/apply', {
      method: 'POST',
      body: JSON.stringify({ nombre })
    }),

  deleteProfile: (nombre: string) =>
    request<{ success: boolean; eliminado: string }>('/profiles/delete', {
      method: 'POST',
      body: JSON.stringify({ nombre })
    }),

  getWorkflowProfiles: () => request<Record<string, any>>('/workflow_profiles'),

  applyWorkflowProfile: (profileId: string) =>
    request<{ success: boolean; applied: string }>('/workflow_profiles/apply', {
      method: 'POST',
      body: JSON.stringify({ profile_id: profileId })
    }),

  // --- Culling & Pipeline ---
  startIngest: (directory: string, mode: 'cull' | 'cull_edit' = 'cull_edit') =>
    request<{ job_id: string; status: string; mode: string }>('/ingest', {
      method: 'POST',
      body: JSON.stringify({ directory, mode })
    }),

  getStatus: () => request<JobStatus>('/status'),

  getResults: () => request<JobResults>('/results'),

  // --- Ráfagas, Duelos & Rostros ---
  learnPreference: (winnerPath: string, loserPath: string) =>
    request<{ success: boolean; learned: boolean; xmp: Record<string, any> }>('/learn_preference', {
      method: 'POST',
      body: JSON.stringify({ winner_path: winnerPath, loser_path: loserPath })
    }),

  getBurstFaceCrops: (clusterId: number, directory?: string) => {
    const q = directory ? `?directory=${encodeURIComponent(directory)}` : '';
    return request<BurstFaceCropsResponse>(`/bursts/${clusterId}/face_crops${q}`);
  },

  // --- Calibración Facial ---
  getCalibrationCandidates: (directory: string, limit: number = 30) =>
    request<{
      atributos: Record<string, string[]>;
      etiquetadas: number;
      candidatas: CalibrationCandidate[];
    }>(`/calibration/candidates?directory=${encodeURIComponent(directory)}&limit=${limit}`),

  labelCalibration: (data: {
    photo_path: string;
    face_index: number;
    face_bbox: number[];
    labels: Record<string, string>;
    predictions?: Record<string, string>;
  }) =>
    request<{ success: boolean; guardadas: number; total: number }>('/calibration/label', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  getCalibrationStats: () => request<CalibrationStatsResponse>('/calibration/stats'),

  // --- Exportación, Pre-Edición & Lightroom ---
  applyEdits: (directory: string) =>
    request<{ success: boolean; edited: number; preset: string | null; xmp: Record<string, any> }>(
      '/apply_edits',
      {
        method: 'POST',
        body: JSON.stringify({ directory })
      }
    ),

  reimportXmp: (directory: string) =>
    request<{
      success: boolean;
      corrections: number;
      upgraded: number;
      downgraded: number;
      learned: number;
      total_examples: number;
      hint?: string;
    }>('/reimport_xmp', {
      method: 'POST',
      body: JSON.stringify({ directory })
    }),

  checkUndo: (directory: string) =>
    request<{ disponible: boolean }>(`/undo_export/available?directory=${encodeURIComponent(directory)}`),

  undoExport: (directory: string) =>
    request<{ success: boolean; restauradas: number; limpiadas?: number; fallidas?: number; detail?: string }>(
      '/undo_export',
      {
        method: 'POST',
        body: JSON.stringify({ directory })
      }
    ),

  getSyncPending: () => request<{ events: string[] }>('/sync/pending'),

  snoozeSync: (directory: string, hours: number = 8.0) =>
    request<{ success: boolean }>('/sync/snooze', {
      method: 'POST',
      body: JSON.stringify({ directory, hours })
    }),

  dismissSync: (directory: string) =>
    request<{ success: boolean }>('/sync/dismiss', {
      method: 'POST',
      body: JSON.stringify({ directory })
    }),

  getLearningSummary: () => request<LearningSummary>('/learning/summary'),

  // --- Media, Búsqueda & Caché ---
  semanticSearch: (q: string, directory: string, limit: number = 50) =>
    request<{ results: { path: string; filename: string; score: number; thumb: string }[] }>(
      `/search/semantic?q=${encodeURIComponent(q)}&directory=${encodeURIComponent(directory)}&limit=${limit}`
    ),

  getStoryline: (directory: string, gap: number = 30) =>
    request<{ storyline: StorylineChapter[] }>(
      `/storyline?directory=${encodeURIComponent(directory)}&gap=${gap}`
    ),

  getCachedProjects: () => request<CachedProject[]>('/cache/projects'),

  clearCache: (directory: string) =>
    request<{ success: boolean }>('/cache/clear', {
      method: 'POST',
      body: JSON.stringify({ directory })
    }),

  openCacheFolder: () =>
    request<{ success: boolean }>('/cache/open', {
      method: 'POST'
    }),

  getPresets: () =>
    request<{ active: string; recent: string[]; exposure_bias: number; enabled: boolean }>('/presets'),

  usePreset: (path: string) =>
    request<{ success: boolean; active: string; recent: string[] }>('/presets/use', {
      method: 'POST',
      body: JSON.stringify({ path })
    }),

  getExif: (path: string) =>
    request<Record<string, any>>(`/exif?path=${encodeURIComponent(path)}`),

  getLightroomPendingChanges: (directory: string, catalog_path: string) =>
    request<{ pendientes: number; total: number }>('/lightroom/pending_changes', {
      method: 'POST',
      body: JSON.stringify({ directory, catalog_path })
    }),

  getThumbnailUrl: (path: string, size: 'ui' | 'duel' = 'ui') =>
    `${BACKEND_URL}/thumbnail?path=${encodeURIComponent(path)}&size=${size}`,

  getPreviewUrl: (path: string, conEdicion: boolean = true) =>
    `${BACKEND_URL}/preview?path=${encodeURIComponent(path)}&con_edicion=${conEdicion}`,

  getStorylineUrl: (medoidThumb: string) =>
    medoidThumb.startsWith('http') ? medoidThumb : `${BACKEND_URL}${medoidThumb.startsWith('/') ? '' : '/'}${medoidThumb}`,

  getFaceCropUrl: (path: string, bbox: number[], size: number = 256) => {
    const [x, y, w, h] = bbox;
    return `${BACKEND_URL}/bursts/face_crop_img?path=${encodeURIComponent(path)}&x=${x}&y=${y}&w=${w}&h=${h}&size=${size}`;
  },

  getDebugOverlayUrl: (path: string) =>
    `${BACKEND_URL}/debug/overlay?path=${encodeURIComponent(path)}`,

  // --- Revelado Avanzado & 3D-LUT (Fase 3) ---
  getLutStatus: () => request<import('../types/api').LutStatusResponse>('/advanced/lut_status'),

  getLuts: () => request<{ luts: import('../types/api').LutProfile[] }>('/advanced/luts'),

  applyLut: (params: { lut_id?: string; strength?: number; image_paths?: string[] }) =>
    request<{ status: string; applied_count: number }>('/advanced/apply_lut', {
      method: 'POST',
      body: JSON.stringify(params)
    }),

  relightFaces: (params: { intensity?: number; image_paths?: string[] }) =>
    request<{ status: string; applied_count: number }>('/advanced/relight_faces', {
      method: 'POST',
      body: JSON.stringify(params)
    }),

  skinRetouch: (params: { smoothness?: number; image_paths?: string[] }) =>
    request<{ status: string; applied_count: number }>('/advanced/skin_retouch', {
      method: 'POST',
      body: JSON.stringify(params)
    })
};
