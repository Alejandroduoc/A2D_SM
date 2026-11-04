// Reutiliza el cliente autenticado y su renovación automática de sesión.
import client from "./client";

// Obtiene el recorrido completo de una tarja por su número (HU23).
export async function consultarTrazabilidad(numeroTarja) {
  // El número viaja en la ruta.
  const respuesta = await client.get(`/trazabilidad/tarjas/${numeroTarja}`);
  // Devuelve la recepción, sus procesos, sus kilos y su historial.
  return respuesta.data;
}
