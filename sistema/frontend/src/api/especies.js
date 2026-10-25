// Reutiliza el cliente que adjunta el token y administra la sesión expirada.
import client from "./client";

// Consulta todas las especies o limita el resultado a un estado explícito.
export async function listarEspecies(activo = null) {
  // Conserva false como filtro; null significa incluir ambos estados.
  const params = typeof activo === "boolean" ? { activo } : {};
  const respuesta = await client.get("/especies", { params });
  // Propaga los errores para distinguirlos de un catálogo vacío válido.
  return respuesta.data;
}

// Crea una especie; el backend normaliza el nombre y valida su unicidad.
export async function crearEspecie(nombre) {
  const respuesta = await client.post("/especies", { nombre });
  return respuesta.data;
}

// Modifica únicamente los campos enviados para la especie indicada.
export async function actualizarEspecie(id, cambios) {
  const respuesta = await client.put(`/especies/${id}`, cambios);
  return respuesta.data;
}
