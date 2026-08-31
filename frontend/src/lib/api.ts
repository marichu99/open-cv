import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";
export const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || API_URL;

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
