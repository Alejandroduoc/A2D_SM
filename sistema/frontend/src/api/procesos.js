// Reutiliza el cliente autenticado y su renovación automática de sesión.
import client from "./client";

// Lista los embalajes activos para el formulario de proceso.
export async function listarEmbalajesProceso() {
  // El operador de proceso no accede a los mantenedores: la API le entrega esta lista.
  const respuesta = await client.get("/procesos/embalajes");
  // Devuelve id, nombre, kilos por caja y si es a granel.
  return respuesta.data;
}

// Lista las tarjas que todavía se pueden procesar; el número es opcional.
export async function listarTarjasDisponibles(numeroTarja) {
  // Axios omite los parámetros undefined.
  const respuesta = await client.get("/procesos/tarjas-disponibles", {
    params: { numero_tarja: numeroTarja },
  });
  // Devuelve cada tarja con sus kilos pendientes.
  return respuesta.data;
}

// Registra un proceso con sus tarjas (HU18).
export async function registrarProceso(datos) {
  // El backend asigna el folio y calcula los kilos, los totales y los estados.
  const respuesta = await client.post("/procesos", datos);
  // Devuelve el proceso confirmado, con sus tarjas.
  return respuesta.data;
}

// Corrige un proceso registrado; lo que sale vuelve a sus tarjas de recepción.
export async function editarProceso(id, datos) {
  // El cuerpo indica cómo debe quedar el proceso.
  const respuesta = await client.put(`/procesos/${id}`, datos);
  // Devuelve el proceso actualizado.
  return respuesta.data;
}

// Anula un proceso, solo el administrador (HU25); devuelve el proceso actualizado.
export async function anularProceso(id) {
  // Sin cuerpo: no se exige motivo y el servidor audita.
  const respuesta = await client.post(`/procesos/${id}/anular`);
  // Devuelve el proceso anulado.
  return respuesta.data;
}

// Lista los procesos, los más recientes primero.
export async function listarProcesos() {
  // Sin filtros: la API limita la cantidad de filas.
  const respuesta = await client.get("/procesos");
  // Devuelve las cabeceras.
  return respuesta.data;
}

// Obtiene un proceso con sus tarjas.
export async function obtenerProceso(id) {
  // El id viaja en la ruta.
  const respuesta = await client.get(`/procesos/${id}`);
  // Devuelve la cabecera y el detalle.
  return respuesta.data;
}

// Lista las tarjas con merma rebajada, para poder reabrirlas.
export async function listarTarjasRebajadas() {
  // Sin filtros: la API limita la cantidad de filas.
  const respuesta = await client.get("/procesos/tarjas-rebajadas");
  // Devuelve cada tarja con su merma.
  return respuesta.data;
}

// Deshace una rebaja hecha por error.
export async function reabrirTarja(tarjaId) {
  // Sin cuerpo: el servidor recalcula el estado y audita.
  const respuesta = await client.post(`/procesos/tarjas/${tarjaId}/reabrir`);
  // Devuelve cómo quedó la tarja.
  return respuesta.data;
}

// Rebaja como merma los kilos que le quedan a una tarja.
export async function terminarTarja(tarjaId) {
  // Sin cuerpo: los kilos los calcula el servidor, que además audita.
  const respuesta = await client.post(`/procesos/tarjas/${tarjaId}/terminar`);
  // Devuelve cómo quedó la tarja.
  return respuesta.data;
}
