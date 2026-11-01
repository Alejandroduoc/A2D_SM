// Reutiliza el cliente autenticado y su renovación automática de sesión.
import client from "./client";

// Registra una tarja con los datos que el operador ingresó en recepción.
export async function registrarTarja(datos) {
  // El backend asigna número, tara, kilos netos, estado, usuario y fecha UTC.
  const respuesta = await client.post("/tarjas", datos);
  // Devuelve la tarja completa para mostrar su número y kilos confirmados.
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
