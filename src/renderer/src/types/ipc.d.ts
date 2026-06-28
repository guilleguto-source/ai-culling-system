declare global {
  interface Window {
    api: {
      getBackendStatus: () => Promise<{ running: boolean; status: string; url: string }>;
      getHardwareInfo: () => Promise<any>;
      sendSettings: (settings: any) => Promise<any>;
      getSettings: () => Promise<any>;
      ingestMedia: (directory: string) => Promise<{ job_id: string; status: string }>;
      getJobStatus: () => Promise<any>;
      getJobResults: () => Promise<any>;
      onBackendLog: (callback: (log: string) => void) => () => void;
      onBackendStatusChange: (callback: (status: string) => void) => () => void;
    };
  }
}

export {};
