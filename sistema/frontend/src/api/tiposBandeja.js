// Centraliza las operaciones administrativas de tipos de bandeja.
import client from "./client";

// Lista tipos de bandeja; null pide todos y true/false filtra por estado.
export async function listarTiposBandeja(activo = null) {
  // Sólo envía el parámetro cuando el filtro es booleano.
  const params = typeof activo === "boolean" ? { activo } : {};
  // Consulta el mantenimiento protegido para administradores.
  const respuesta = await client.get("/tipos-bandeja", { params });
  // Devuelve las filas recibidas desde la API.
  return respuesta.data;
}

// Crea un tipo de bandeja con nombre y tara.
export async function crearTipoBandeja(datos) {
  // La API valida, normaliza y responde con el registro creado.
  const respuesta = await client.post("/tipos-bandeja", datos);
  // Devuelve el objeto público de la bandeja.
  return respuesta.data;
}

// Modifica nombre, tara o estado de un tipo de bandeja.
export async function actualizarTipoBandeja(id, cambios) {
  // Envía únicamente los campos que cambian.
  const respuesta = await client.put(`/tipos-bandeja/${id}`, cambios);
  // Devuelve el estado confirmado por el backend.
  return respuesta.data;
}
