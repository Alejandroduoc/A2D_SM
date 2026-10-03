// Importa las herramientas de estado y contexto de React.
import { createContext, useContext, useEffect, useState } from "react";
// Usa el cliente que agrega automáticamente el token.
import client from "./client";

// Mantiene la sesión disponible para todas las pantallas.
const AuthContext = createContext(null);

// Provee el usuario, el estado de carga y las operaciones de sesión.
export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null);
  const [cargando, setCargando] = useState(true);

  // Valida el token guardado cada vez que se abre o recarga la aplicación.
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setCargando(false);
      return;
    }
    client
      .get("/auth/me")
      .then((res) => setUsuario(res.data))
      .catch(() => {
        localStorage.removeItem("access_token");
        setUsuario(null);
      })
      .finally(() => setCargando(false));
  }, []);

  // Inicia sesión, guarda el token y carga los datos públicos del usuario.
  async function login(nombre_usuario, password) {
    const res = await client.post("/auth/login", { nombre_usuario, password });
    localStorage.setItem("access_token", res.data.access_token);
    const me = await client.get("/auth/me");
    setUsuario(me.data);
  }

  // Elimina la sesión del navegador.
  function logout() {
    localStorage.removeItem("access_token");
    setUsuario(null);
  }

  // Entrega el estado y las operaciones a los componentes descendientes.
  return <AuthContext.Provider value={{ usuario, cargando, login, logout }}>{children}</AuthContext.Provider>;
}

// Expone un atajo tipado por convención para consumir el contexto.
export function useAuth() {
  return useContext(AuthContext);
}
