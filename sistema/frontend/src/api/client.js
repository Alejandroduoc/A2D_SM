// Importa Axios para realizar peticiones HTTP.
import axios from "axios";

// Usa la URL entregada por Docker o la URL estándar de desarrollo.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// Centraliza la configuración de todas las llamadas a la API.
const client = axios.create({ baseURL: API_URL });

// Agrega el access token a cada petición autenticada.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = ["Bearer", token].join(" ");
  return config;
});

// Expira la sesión local cuando la API rechaza un token existente.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const esLogin = error.config?.url?.endsWith("/auth/login");
    if (error.response?.status === 401 && !esLogin && window.location.pathname !== "/login") {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// Convierte los formatos de error de FastAPI en un mensaje visible.
export function extraerMensajeError(err, mensajePorDefecto = "Ocurrió un error inesperado") {
  if (!err?.response) return "No se pudo conectar con el servidor";
  const detail = err.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" · ");
  return mensajePorDefecto;
}

// Exporta el cliente configurado.
export default client;
