// Reutiliza el cliente autenticado y su tratamiento central de errores.
import client from "./client";

// Consulta las variedades que pertenecen a una especie seleccionada.
export async function listarVariedades(especieId, activo = null) {
  // El id siempre delimita el catálogo hijo y false se conserva como filtro.
  const params = { especie_id: especieId };
  if (typeof activo === "boolean") params.activo = activo;
  const respuesta = await client.get("/variedades", { params });
  return respuesta.data;
}

// Crea una variedad asociada a la especie que sirve de contexto en pantalla.
export async function crearVariedad(especieId, nombre) {
  const respuesta = await client.post("/variedades", { especie_id: especieId, nombre });
  return respuesta.data;
}

// Modifica nombre o estado sin permitir reasignar la variedad a otra especie.
export async function actualizarVariedad(id, cambios) {
  const respuesta = await client.put(`/variedades/${id}`, cambios);
  return respuesta.data;
}
