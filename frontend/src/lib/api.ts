import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
export const api = axios.create({ baseURL: API_BASE });

export const WS_URL = import.meta.env.VITE_WS_URL
  ? `${import.meta.env.VITE_WS_URL}/ws/live`
  : `ws://${window.location.host}/ws/live`;

export const WS_ALERTS_URL = import.meta.env.VITE_WS_URL
  ? `${import.meta.env.VITE_WS_URL}/ws/alerts`
  : `ws://${window.location.host}/ws/alerts`;
