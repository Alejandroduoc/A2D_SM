// Importa las herramientas de estado y contexto de React.
import { createContext, useContext, useEffect, useState } from "react";
// Usa el cliente que agrega automáticamente el token y lo renueva al vencer.
import client, { borrarTokens, guardarTokens, LLAVE_ACCESS } from "./client";

// Mantiene la sesión disponible para todas las pantallas.
const AuthContext = createContext(null);

// Provee el usuario, el estado de carga y las operaciones de sesión.
export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null);
  const [cargando, setCargando] = useState(true);

  // Valida el token guardado cada vez que se abre o recarga la aplicación.
  useEffect(() => {
    const token = localStorage.getItem(LLAVE_ACCESS);
    if (!token) {
      setCargando(false);
      return;
    }
    // Si el access venció, el cliente lo renueva solo antes de responder.
    client
      .get("/auth/me")
      .then((res) => setUsuario(res.data))
      .catch(() => {
        borrarTokens();
        setUsuario(null);
      })
      .finally(() => setCargando(false));
  }, []);

  // Inicia sesión, guarda ambos tokens y carga los datos públicos del usuario.
  async function login(nombre_usuario, password) {
    const res = await client.post("/auth/login", { nombre_usuario, password });
    guardarTokens(res.data);
    const me = await client.get("/auth/me");
    setUsuario(me.data);
  }

  // Elimina la sesión del navegador (access y refresh).
  function logout() {
    borrarTokens();
    setUsuario(null);
  }

  // Entrega el estado y las operaciones a los componentes descendientes.
  return <AuthContext.Provider value={{ usuario, cargando, login, logout }}>{children}</AuthContext.Provider>;
}

// Expone un atajo tipado por convención para consumir el contexto.
export function useAuth() {
  return useContext(AuthContext);
}
