// Reutiliza el cliente autenticado y su manejo central de sesión.
import client from "./client";

export async function listarCalidades(activo = null) {
  const params = typeof activo === "boolean" ? { activo } : {};
  const respuesta = await client.get("/calidades", { params });
  return respuesta.data;
}

export async function crearCalidad(nombre) {
  const respuesta = await client.post("/calidades", { nombre });
  return respuesta.data;
}

export async function actualizarCalidad(id, cambios) {
  const respuesta = await client.put(`/calidades/${id}`, cambios);
  return respuesta.data;
}
