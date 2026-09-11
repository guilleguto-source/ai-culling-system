import { HardwareInfo, Settings, JobStatus, JobResults } from './api';

declare global {
  interface Window {
    api: {
      getBackendStatus: () => Promise<{ running: boolean; status: string; url: string }>;
      getHardwareInfo: () => Promise<HardwareInfo>;
      sendSettings: (settings: Settings) => Promise<{ success: boolean; settings: Settings }>;
      getSettings: () => Promise<Settings>;
      ingestMedia: (directory: string, mode?: string) => Promise<{ job_id: string; status: string }>;
      getJobStatus: () => Promise<JobStatus>;
      getJobResults: () => Promise<JobResults>;

      selectFolder: (defaultPath?: string) => Promise<string | null>;
      preventSleep: () => Promise<number>;
      allowSleep: () => Promise<boolean>;
      suspendPC: () => Promise<boolean>;
      onBackendLog: (callback: (log: string) => void) => () => void;
      onBackendStatusChange: (callback: (status: string) => void) => () => void;
    };
  }
}

export {};
