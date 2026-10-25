// Importa Axios para realizar peticiones HTTP.
import axios from "axios";

// Usa la URL entregada por Docker o la URL estándar de desarrollo.
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// Nombres de las llaves del navegador donde se guardan los tokens.
export const LLAVE_ACCESS = "access_token";
export const LLAVE_REFRESH = "refresh_token";

// Centraliza la configuración de todas las llamadas a la API.
const client = axios.create({ baseURL: API_URL });

// Cliente aparte, sin interceptores, solo para renovar: evita un ciclo infinito de reintentos.
const clienteRenovacion = axios.create({ baseURL: API_URL });

// Guarda el par de tokens que entregan el login y la renovación.
export function guardarTokens({ access_token, refresh_token }) {
  localStorage.setItem(LLAVE_ACCESS, access_token);
  localStorage.setItem(LLAVE_REFRESH, refresh_token);
}

// Borra la sesión del navegador.
export function borrarTokens() {
  localStorage.removeItem(LLAVE_ACCESS);
  localStorage.removeItem(LLAVE_REFRESH);
}

// Agrega el access token a cada petición autenticada.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem(LLAVE_ACCESS);
  if (token) config.headers.Authorization = ["Bearer", token].join(" ");
  return config;
});

// Una sola renovación a la vez: si varias peticiones vencen juntas, todas esperan la misma.
let renovacionEnCurso = null;

// Pide tokens nuevos con el refresh token guardado; devuelve el access nuevo.
async function renovarSesion() {
  const refresh = localStorage.getItem(LLAVE_REFRESH);
  // Sin refresh token no hay nada que renovar.
  if (!refresh) throw new Error("Sin refresh token");
  const respuesta = await clienteRenovacion.post("/auth/refresh", { refresh_token: refresh });
  guardarTokens(respuesta.data);
  return respuesta.data.access_token;
}

// Cuando el access token vence (401), renueva la sesión una vez y repite la petición.
// Así la persona no pierde lo que estaba escribiendo cada 30 minutos.
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const esLogin = original?.url?.endsWith("/auth/login");
    // Solo se intenta una vez por petición y nunca para el propio login.
    if (error.response?.status === 401 && original && !esLogin && !original._reintentada) {
      original._reintentada = true;
      try {
        renovacionEnCurso ??= renovarSesion().finally(() => { renovacionEnCurso = null; });
        const nuevoToken = await renovacionEnCurso;
        original.headers.Authorization = ["Bearer", nuevoToken].join(" ");
        return client(original);
      } catch {
        // La renovación falló (refresh vencido o usuario desactivado): vuelve al login avisando.
        borrarTokens();
        if (window.location.pathname !== "/login") window.location.href = "/login?expirada=1";
      }
    }
    return Promise.reject(error);
  },
);

// Convierte los formatos de error de FastAPI en un mensaje visible.
export function extraerMensajeError(err, mensajePorDefecto = "Ocurrió un error inesperado") {
  if (!err?.response) return "No se pudo conectar con el servidor";
  const detail = err.response.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg.replace(/^Value error, /, "")).join(" · ");
  return mensajePorDefecto;
}

// Exporta el cliente configurado.
export default client;
