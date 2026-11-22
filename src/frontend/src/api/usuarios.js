// Operaciones de administración de usuarios y cambio de la propia contraseña.
import client from "./client";

// Lista todas las cuentas (solo administrador; la API valida el rol).
export async function listarUsuarios() {
  const respuesta = await client.get("/auth/usuarios");
  return respuesta.data;
}

// Crea una cuenta con nombre de login, nombre completo, contraseña y roles.
export async function crearUsuario(datos) {
  const respuesta = await client.post("/auth/usuarios", datos);
  return respuesta.data;
}

// Edita nombre, roles, estado o restablece la contraseña; solo envía lo que cambia.
export async function actualizarUsuario(id, cambios) {
  const respuesta = await client.put(`/auth/usuarios/${id}`, cambios);
  return respuesta.data;
}

// Cambia la contraseña de la sesión actual; la API exige la contraseña vigente.
export async function cambiarMiPassword(password_actual, password_nueva) {
  await client.put("/auth/me/password", { password_actual, password_nueva });
}
