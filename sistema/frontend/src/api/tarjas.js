// Reutiliza el cliente autenticado y su renovación automática de sesión.
import client from "./client";

// Registra una tarja con los datos que el operador ingresó en recepción.
export async function registrarTarja(datos) {
  // El backend asigna número, tara, kilos netos, estado, usuario y fecha UTC.
  const respuesta = await client.post("/tarjas", datos);
  // Devuelve la tarja completa para mostrar su número y kilos confirmados.
  return respuesta.data;
}

// Lista las tarjas según los filtros (HU17); los filtros sin valor no se envían.
export async function listarTarjas(filtros) {
  // Axios omite los parámetros undefined.
  const respuesta = await client.get("/tarjas", { params: filtros });
  // Devuelve las filas del listado.
  return respuesta.data;
}

// Obtiene el detalle completo de una tarja (HU17).
export async function obtenerTarja(id) {
  // El id viaja en la ruta.
  const respuesta = await client.get(`/tarjas/${id}`);
  // Devuelve los datos, los nombres de los catálogos y los kilos.
  return respuesta.data;
}

// Consulta los acumulados sin procesar del productor seleccionado.
export async function pendientesProductor(productorId) {
  // El identificador viaja como query param validado por FastAPI.
  const respuesta = await client.get("/tarjas/pendientes", {
    params: { productor_id: productorId },
  });
  // Devuelve productor_id, cantidad de tarjas y suma de kilos.
  return respuesta.data;
}
