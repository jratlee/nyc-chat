// Central API base URL.
// Override at build/deploy time with VITE_API_BASE_URL (e.g. a Codespaces
// forwarded URL or a production backend). Falls back to the local FastAPI port.
export const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8005'
