// Reutiliza el cliente que adjunta el token y renueva la sesión.
import client from "./client";

// Especies activas para el selector (HU11; recepción y administrador).
export async function listarEspecies() {
  // GET /opciones/especies; la API filtra los inactivos.
  const respuesta = await client.get("/opciones/especies");
  // Devuelve la lista de { id, nombre }.
  return respuesta.data;
}

// Variedades activas de la especie elegida.
export async function listarVariedades(especieId) {
  // GET /opciones/variedades?especie_id=N; una especie inactiva devuelve [].
  const respuesta = await client.get("/opciones/variedades", { params: { especie_id: especieId } });
  // Devuelve la lista de { id, nombre }.
  return respuesta.data;
}

// Calidades activas para el selector.
export async function listarCalidades() {
  // GET /opciones/calidades.
  const respuesta = await client.get("/opciones/calidades");
  // Devuelve la lista de { id, nombre }.
  return respuesta.data;
}

// Sistemas productivos activos para el selector.
export async function listarSistemasProductivos() {
  // GET /opciones/sistemas-productivos.
  const respuesta = await client.get("/opciones/sistemas-productivos");
  // Devuelve la lista de { id, nombre }.
  return respuesta.data;
}

// Productores activos cuyo RUT empieza con el texto o cuya razón social lo contiene.
export async function buscarProductores(texto) {
  // GET /opciones/productores?buscar=texto; la API devuelve como máximo 20.
  const respuesta = await client.get("/opciones/productores", { params: { buscar: texto } });
  // Devuelve la lista de { id, rut, razon_social }.
  return respuesta.data;
}
