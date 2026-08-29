import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export const api = axios.create({ baseURL: API_URL });

const TOKEN_KEY = "tally333_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message = err?.response?.data?.error || err.message || "Request failed";
    return Promise.reject(new Error(message));
  }
);

/** Fetches a submission's original photo as a Blob — the endpoint is
 * JWT-protected, so a plain <img src>/<a href> can't carry the bearer token
 * and this has to go through fetch(). GCS-backed submissions come back as
 * `{url}` JSON rather than a redirect (a redirect would forward this same
 * Authorization header cross-origin to GCS, which then rejects it trying to
 * use it as GCS's own auth instead of the URL's query-string signature) — in
 * that case, fetch the bytes from that URL with no headers at all. */
export async function fetchSubmissionImageBlob(id: string): Promise<Blob> {
  const res = await fetch(`${API_URL}/api/submissions/${id}/image`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error("Could not load the document");

  if ((res.headers.get("content-type") || "").includes("application/json")) {
    const { url } = await res.json();
    const fileRes = await fetch(url);
    if (!fileRes.ok) throw new Error("Could not load the document");
    return fileRes.blob();
  }
  return res.blob();
}
