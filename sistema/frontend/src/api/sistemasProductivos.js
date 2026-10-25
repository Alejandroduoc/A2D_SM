// Centraliza las operaciones administrativas de sistemas productivos.
import client from "./client";

export async function listarSistemasProductivos(activo = null) {
  const params = typeof activo === "boolean" ? { activo } : {};
  const respuesta = await client.get("/sistemas-productivos", { params });
  return respuesta.data;
}

export async function crearSistemaProductivo(nombre) {
  const respuesta = await client.post("/sistemas-productivos", { nombre });
  return respuesta.data;
}

export async function actualizarSistemaProductivo(id, cambios) {
  const respuesta = await client.put(`/sistemas-productivos/${id}`, cambios);
  return respuesta.data;
}
