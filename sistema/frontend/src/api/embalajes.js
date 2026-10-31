// Centraliza las operaciones administrativas de embalajes.
import client from "./client";

// Lista embalajes; null pide todos y true/false filtra por estado.
export async function listarEmbalajes(activo = null) {
  // Sólo envía el parámetro cuando el filtro es booleano.
  const params = typeof activo === "boolean" ? { activo } : {};
  // Consulta el mantenimiento protegido para administradores.
  const respuesta = await client.get("/embalajes", { params });
  // Devuelve las filas recibidas desde la API.
  return respuesta.data;
}

// Crea un embalaje de peso fijo o a granel.
export async function crearEmbalaje(datos) {
  // kg_por_caja=null representa explícitamente la modalidad a granel.
  const respuesta = await client.post("/embalajes", datos);
  // Devuelve el objeto público del embalaje.
  return respuesta.data;
}

// Modifica nombre, kilos por caja o estado de un embalaje.
export async function actualizarEmbalaje(id, cambios) {
  // Conserva null dentro del cuerpo cuando se convierte a granel.
  const respuesta = await client.put(`/embalajes/${id}`, cambios);
  // Devuelve el estado confirmado por el backend.
  return respuesta.data;
}
