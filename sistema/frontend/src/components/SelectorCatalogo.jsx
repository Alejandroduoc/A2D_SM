// Clases compartidas de etiqueta, lista desplegable y ayuda.
import { AYUDA, ETIQUETA, SELECTOR } from "./catalogo";

// Lista desplegable genérica para un catálogo de { id, nombre } (HU11).
export default function SelectorCatalogo({
  id, // Id del <select>, enlazado con su etiqueta.
  etiqueta, // Texto visible de la etiqueta.
  opciones, // Registros activos que entrega la API.
  valor, // Id elegido como texto; "" significa sin elegir.
  onChange, // Recibe el nuevo id como texto.
  deshabilitado = false, // Bloquea la lista mientras carga o mientras falta un dato previo.
  textoVacio = "Seleccione…", // Primera opción, sin valor.
  ayuda = "", // Texto opcional bajo la lista.
}) {
  // Id del texto de ayuda, para leerlo junto con la lista.
  const idAyuda = ayuda ? `${id}-ayuda` : undefined;

  return (
    <div>
      {/* La etiqueta apunta al <select> para los lectores de pantalla. */}
      <label htmlFor={id} className={ETIQUETA}>{etiqueta}</label>
      {/* El valor siempre es texto; el padre lo convierte a número si lo necesita. */}
      <select
        id={id}
        className={SELECTOR}
        value={valor}
        onChange={(evento) => onChange(evento.target.value)}
        disabled={deshabilitado}
        aria-describedby={idAyuda}
      >
        {/* Opción inicial sin valor. */}
        <option value="">{textoVacio}</option>
        {/* Una opción por registro activo. */}
        {opciones.map((opcion) => (
          <option key={opcion.id} value={String(opcion.id)}>{opcion.nombre}</option>
        ))}
      </select>
      {/* Ayuda opcional bajo la lista. */}
      {ayuda && <p id={idAyuda} className={AYUDA}>{ayuda}</p>}
    </div>
  );
}
