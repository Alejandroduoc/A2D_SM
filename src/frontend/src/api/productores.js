// Reutiliza el cliente que adjunta el token y trata la expiración de sesión.
import client from "./client";

// Consulta el catálogo completo o un estado explícito, incluidos los inactivos.
export async function listarProductores(activo = null) {
  // Conserva false como filtro; null significa consultar ambos estados.
  const params = typeof activo === "boolean" ? { activo } : {};
  // Deja que los errores se propaguen para distinguirlos de una lista vacía válida.
  const respuesta = await client.get("/productores", { params });
  // Entrega las filas al componente sin exponer la estructura interna de Axios.
  return respuesta.data;
}

// Crea un productor con los datos de negocio; el servidor identifica al actor.
export async function crearProductor(datos) {
  // No reintenta ni oculta un fallo de escritura como si hubiera sido un éxito.
  const respuesta = await client.post("/productores", datos);
  // Devuelve el registro normalizado y generado por el backend.
  return respuesta.data;
}

// Edita datos o estado usando el id estable del productor en la URL.
export async function actualizarProductor(id, cambios) {
  // El cuerpo contiene solo cambios de negocio, sin instrucciones de auditoría.
  const respuesta = await client.put(`/productores/${id}`, cambios);
  // Conserva los errores para que la pantalla permita corregir o comprobar el resultado.
  return respuesta.data;
}
