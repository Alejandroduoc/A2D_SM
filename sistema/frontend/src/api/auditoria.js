// Reutiliza el cliente autenticado y su renovación automática.
import client from "./client";

// Obtiene los actores que tienen eventos de auditoría.
export async function consultarUsuariosAuditoria() {
  // La ruta entrega solo id y nombre completo.
  const respuesta = await client.get("/auditoria/usuarios");
  // Devuelve la lista para el selector.
  return respuesta.data;
}

// Obtiene las tablas que tienen eventos de auditoría.
export async function consultarTablasAuditoria() {
  // La ruta entrega los nombres técnicos.
  const respuesta = await client.get("/auditoria/tablas");
  // Devuelve la lista para el selector.
  return respuesta.data;
}

// Consulta una página de la bitácora con sus filtros.
export async function consultarBitacora(filtros) {
  // Axios omite los valores undefined del query string.
  const respuesta = await client.get("/auditoria", { params: filtros });
  // Devuelve eventos y metadatos de paginación.
  return respuesta.data;
}
