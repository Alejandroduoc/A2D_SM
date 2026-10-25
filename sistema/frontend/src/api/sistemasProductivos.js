// Centraliza las operaciones administrativas de sistemas productivos.
import client from "./client";

// Lista sistemas productivos; null pide todos y true/false filtra por estado.
export async function listarSistemasProductivos(activo = null) {
  // Solo envía el parámetro cuando el filtro es booleano.
  const params = typeof activo === "boolean" ? { activo } : {};
  // GET /sistemas-productivos (solo administrador; la API valida el rol).
  const respuesta = await client.get("/sistemas-productivos", { params });
  // Devuelve la lista recibida.
  return respuesta.data;
}

// Crea un sistema productivo con el nombre indicado.
export async function crearSistemaProductivo(nombre) {
  // POST /sistemas-productivos; la API normaliza el nombre y responde 201.
  const respuesta = await client.post("/sistemas-productivos", { nombre });
  // Devuelve el sistema creado.
  return respuesta.data;
}

// Renombra o cambia el estado de un sistema productivo.
export async function actualizarSistemaProductivo(id, cambios) {
  // PUT /sistemas-productivos/{id} con solo los campos que cambian.
  const respuesta = await client.put(`/sistemas-productivos/${id}`, cambios);
  // Devuelve el sistema actualizado.
  return respuesta.data;
}
