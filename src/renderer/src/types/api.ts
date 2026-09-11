/**
 * src/renderer/src/types/api.ts
 * Definiciones de tipos e interfaces TypeScript para la comunicación con la API de FastAPI y el backend de Electron.
 */

export interface HardwareInfo {
  using_gpu: boolean;
  gpu_provider: string | null;
  physical_cores: number;
  logical_cores: number;
}

export interface HardwareProfile {
  tier: 'ultra' | 'balanced' | 'cpu_light' | 'low_spec';
  tier_label: string;
  description: string;
  specs: {
    has_gpu: boolean;
    gpu_name: string;
    vram_gb: number;
    cpu_physical_cores: number;
    cpu_logical_threads: number;
    ram_gb: number;
  };
  recommended_config: {
    use_cascade: boolean;
    heavy_detector: string;
    safety_cap: number;
    max_workers: number;
  };
  last_scan: string;
}

export interface CullingEstimate {
  total_photos: number;
  min_photos: number;
  max_photos: number;
  estimated_percentage: number;
  is_calibrated: boolean;
  samples_count: number;
}

export interface PresetItem {
  name: string;
  path: string;
}

export interface BackendStatus {
  running: boolean;
  status: 'starting' | 'running' | 'stopped' | 'error' | 'unknown';
  url: string;
}

export interface RatingMapItem {
  stars: number;
  color: string;
}

export interface RatingsMapping {
  selected: RatingMapItem;
  highlighted: RatingMapItem;
  duplicates: RatingMapItem;
  closed_eyes: RatingMapItem;
  blurry: RatingMapItem;
  [key: string]: RatingMapItem;
}

export interface PreEditPreferences {
  enabled: boolean;
  preset_path: string;
  recent_presets: string[];
  exposure_bias: number;
  exposure_deadband: number;
  auto_wb: boolean;
  neural_lut?: {
    enabled: boolean;
    strength: number;
    fallback_lut: string;
  };
  tonal_rescue?: {
    enabled: boolean;
    highlights_threshold: number;
    shadows_threshold: number;
  };
  [key: string]: any;
}

export interface LutProfile {
  id: string;
  name: string;
  display_name: string;
  description: string;
  settings: Record<string, number>;
}

export interface LutStatusResponse {
  total_learned_scenes: number;
  total_learned_samples: number;
  recipes_summary: Record<string, { samples: number; fields: string[] }>;
  available_luts: LutProfile[];
  current_config: {
    enabled: boolean;
    strength: number;
    fallback_lut: string;
  };
}

export interface SelectionPreferences {
  detect_duplicates: boolean;
  detect_closed_eyes: boolean;
  prefer_open_eyes: boolean;
  prefer_smiles: boolean;
  strictness: 'relaxed' | 'balanced' | 'strict';
  selectivity_target: 'standard' | 'aggressive' | 'conservative';
  ensure_person_coverage: boolean;
  use_vlm_refinement: boolean;
  overwrite_xmp_ratings: boolean;
  pre_edit: PreEditPreferences;
  [key: string]: any;
}

export interface ModelSettings {
  device: 'auto' | 'cpu' | 'cuda' | 'directml';
  blur_threshold: number;
  dbscan_epsilon: number;
  [key: string]: any;
}

export interface Settings {
  selection_preferences: SelectionPreferences;
  ratings_mapping: RatingsMapping;
  model_settings: ModelSettings;
  workflow_profiles?: Record<string, any>;
  [key: string]: any;
}

export interface JobStatus {
  job_id: string | null;
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  phase_text: string;
  total: number;
  processed: number;
  stats: Record<string, any>;
  error: string | null;
  mode: 'cull' | 'cull_edit' | string;
}

export interface CropData {
  top: number;
  left: number;
  bottom: number;
  right: number;
  angle: number;
}

export interface DevelopData {
  Exposure2012?: number;
  IncrementalTemperature?: number;
  IncrementalTint?: number;
  [key: string]: any;
}

export interface PhotoResult {
  path: string;
  filename: string;
  cluster_id: number;
  is_cluster_representative: boolean;
  label: 'selected' | 'highlighted' | 'duplicates' | 'closed_eyes' | 'blurry' | string;
  stars: number;
  color: string;
  score: number;
  blur_score: number;
  reasons: string[];
  faces_count?: number;
  closed_eyes_count?: number;
  smiling_count?: number;
  margin?: number;
  decided_by?: string;
  crop?: CropData | null;
  develop?: DevelopData | null;
  thumb_url?: string;
  error?: string;
}

export interface JobResults {
  results: PhotoResult[];
  stats: {
    total_images?: number;
    total_clusters?: number;
    ingest?: Record<string, any>;
    selectivity?: Record<string, any>;
    xmp?: Record<string, any>;
    [key: string]: any;
  };
}

export interface FaceCropItem {
  person_id: string;
  photo_path: string;
  face_index: number;
  face_bbox: number[];
  is_representative: boolean;
  score: number;
  is_eyes_open: boolean;
  is_smiling: boolean;
  is_looking_at_camera: boolean;
  blur_score: number;
}

export interface BurstPersonCrops {
  person_id: string;
  crops: FaceCropItem[];
}

export interface BurstFaceCropsResponse {
  cluster_id: number;
  people: BurstPersonCrops[];
}

export interface CalibrationCandidate {
  photo_path: string;
  face_index: number;
  face_bbox: number[];
  uncertainty: number;
  predictions: Record<string, string>;
}

export interface CalibrationStatsResponse {
  total: number;
  por_atributo: Record<
    string,
    {
      precision: number;
      geometria: number;
      aprendido: number | null;
      faltan: number;
      total: number;
      aciertos: number;
    }
  >;
}

export interface LearningSummary {
  gusto?: Record<string, any>;
  calibracion?: Record<string, any>;
  estilo_revelado?: Record<string, any>;
  estilo_recorte?: Record<string, any>;
  [key: string]: any;
}

export interface CachedProject {
  directory: string;
  last_accessed: number;
  size_mb: number;
  db_hash: string;
}

export interface LibraryProject {
  directory: string;
  folder_name: string;
  last_accessed: number;
  exported_at?: string;
  size_mb: number;
  total_photos: number;
  bursts_count: number;
  selected_count: number;
  highlighted_count: number;
  discarded_count: number;
  duplicates_count: number;
  blurry_count: number;
  closed_eyes_count: number;
  last_synced_at?: string | null;
  synced_count?: number;
  sample_photo?: string;
  status: 'completed' | 'in_progress' | 'cached';
  progress?: number;
}

export interface StorylinePhoto {
  path: string;
  thumb_url: string;
  time: string;
  score: number;
}

export interface StorylineChapter {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  photo_count: number;
  medoid_thumb: string;
  medoid_path: string;
  paths: string[];
}

export interface VIPSubject {
  id: number;
  count: number;
  name: string;
  representative_thumb: string;
  representative_path?: string;
}


