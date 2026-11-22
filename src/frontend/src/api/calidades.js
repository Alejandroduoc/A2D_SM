// Reutiliza el cliente autenticado y su manejo central de sesión.
import client from "./client";

// Lista calidades; null pide todas y true/false filtra por estado.
export async function listarCalidades(activo = null) {
  // Solo envía el parámetro cuando el filtro es booleano.
  const params = typeof activo === "boolean" ? { activo } : {};
  // GET /calidades (solo administrador; la API valida el rol).
  const respuesta = await client.get("/calidades", { params });
  // Devuelve la lista recibida.
  return respuesta.data;
}

// Crea una calidad con el nombre indicado.
export async function crearCalidad(nombre) {
  // POST /calidades; la API normaliza el nombre y responde 201.
  const respuesta = await client.post("/calidades", { nombre });
  // Devuelve la calidad creada.
  return respuesta.data;
}

// Renombra o cambia el estado de una calidad.
export async function actualizarCalidad(id, cambios) {
  // PUT /calidades/{id} con solo los campos que cambian.
  const respuesta = await client.put(`/calidades/${id}`, cambios);
  // Devuelve la calidad actualizada.
  return respuesta.data;
}
