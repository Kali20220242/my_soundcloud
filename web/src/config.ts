const fallbackApiBaseUrl = typeof window !== "undefined" ? `${window.location.origin}/api` : "/api";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || fallbackApiBaseUrl;
export const MINIO_PUBLIC_ENDPOINT = import.meta.env.VITE_MINIO_PUBLIC_ENDPOINT || "http://localhost:9000";
export const MINIO_BUCKET = import.meta.env.VITE_MINIO_BUCKET || "tracks";

export const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || ""
};

export const FIREBASE_ENABLED = Object.values(FIREBASE_CONFIG).every(Boolean);
