// Estado y efectos de React.
import { useEffect, useState } from "react";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Búsqueda de productores activos (HU11).
import { buscarProductores } from "../api/opciones";
// Muestra el RUT con puntos y guion.
import { formatearRut } from "../utils/rut";
// Clases compartidas.
import { AYUDA, BOTON_EDITAR, CAMPO, ETIQUETA, MENSAJE_ERROR } from "./catalogo";

// Caracteres mínimos para buscar; la API devuelve [] con menos.
const MINIMO = 2;
// Espera tras la última tecla antes de llamar a la API.
const ESPERA_MS = 300;

// Buscador de productores por RUT o razón social; entrega el elegido al padre.
export default function SelectorProductor({
  id, // Id del campo de búsqueda.
  valor, // Productor elegido ({ id, rut, razon_social }) o null.
  onChange, // Recibe el productor elegido, o null al cambiarlo.
}) {
  // Texto que escribe el operador.
  const [texto, setTexto] = useState("");
  // Productores encontrados para ese texto.
  const [resultados, setResultados] = useState([]);
  // Indica que hay una búsqueda pendiente o en curso.
  const [buscando, setBuscando] = useState(false);
  // Mensaje de error de la última búsqueda.
  const [error, setError] = useState("");

  // Busca 300 ms después de la última tecla, y no en cada letra.
  useEffect(() => {
    // Quita espacios al inicio y al final, igual que la API.
    const consulta = texto.trim();
    // Con menos de 2 caracteres no se consulta la API.
    if (consulta.length < MINIMO) {
      setResultados([]);
      setBuscando(false);
      setError("");
      return undefined;
    }
    // Ignora la respuesta si el texto cambió mientras llegaba.
    let vigente = true;
    // Muestra "Buscando…" mientras corre la espera.
    setBuscando(true);
    // Programa la búsqueda.
    const temporizador = setTimeout(async () => {
      try {
        // Llama a GET /opciones/productores?buscar=texto.
        const encontrados = await buscarProductores(consulta);
        // Guarda los resultados si el texto no cambió.
        if (vigente) {
          setResultados(encontrados);
          setError("");
        }
      } catch (errorRecibido) {
        // Muestra el error y deja la lista vacía.
        if (vigente) {
          setResultados([]);
          setError(extraerMensajeError(errorRecibido, "No se pudo buscar productores"));
        }
      } finally {
        // Termina el estado de búsqueda.
        if (vigente) setBuscando(false);
      }
    }, ESPERA_MS);
    // Si el texto cambia antes de los 300 ms, se cancela la búsqueda anterior.
    return () => {
      vigente = false;
      clearTimeout(temporizador);
    };
  }, [texto]);

  // Entrega el productor al padre y limpia la búsqueda.
  function elegir(productor) {
    onChange(productor);
    setTexto("");
    setResultados([]);
  }

  // Con un productor elegido se muestra su ficha y la acción para cambiarlo.
  if (valor) {
    return (
      <div>
        {/* Etiqueta del dato elegido. */}
        <p className={ETIQUETA}>Productor</p>
        {/* Ficha con RUT y razón social. */}
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded border border-slate-300 bg-slate-50 px-2.5 py-2 text-sm">
          <span className="break-words text-slate-700">
            <span className="font-semibold text-frigorifico-900">{formatearRut(valor.rut)}</span> · {valor.razon_social}
          </span>
          {/* Vuelve al buscador. */}
          <button type="button" className={BOTON_EDITAR} onClick={() => onChange(null)}>Cambiar</button>
        </div>
      </div>
    );
  }

  // Texto de estado bajo el campo.
  const consulta = texto.trim();
  const estado = consulta.length < MINIMO
    ? "Escriba al menos 2 caracteres del RUT o de la razón social."
    : buscando
      ? "Buscando…"
      : resultados.length === 0
        ? "Sin productores activos que coincidan."
        : `${resultados.length} resultado(s)${resultados.length === 20 ? " (máximo 20; afine la búsqueda)" : ""}.`;

  return (
    <div>
      {/* Etiqueta enlazada con el campo de búsqueda. */}
      <label htmlFor={id} className={ETIQUETA}>Productor</label>
      {/* Campo de búsqueda; 50 caracteres como en la API. */}
      <input
        id={id}
        type="search"
        className={CAMPO}
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
        maxLength={50}
        autoComplete="off"
        placeholder="RUT o razón social"
        aria-describedby={`${id}-estado`}
      />
      {/* Estado de la búsqueda, anunciado por los lectores de pantalla. */}
      <p id={`${id}-estado`} className={AYUDA} role="status" aria-live="polite">{estado}</p>
      {/* Error de la API, si lo hubo. */}
      {error && <p className={`mt-2 ${MENSAJE_ERROR}`} role="alert">{error}</p>}
      {/* Resultados como botones; al pulsar uno, se elige. */}
      {!buscando && resultados.length > 0 && (
        <ul className="mt-2 max-h-60 divide-y divide-slate-100 overflow-y-auto rounded border border-slate-200 bg-white" aria-label="Productores encontrados">
          {resultados.map((productor) => (
            <li key={productor.id}>
              <button
                type="button"
                className="block w-full px-2.5 py-2 text-left text-sm text-slate-600 transition hover:bg-frigorifico-50 focus-visible:bg-frigorifico-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar"
                onClick={() => elegir(productor)}
              >
                <span className="font-semibold text-frigorifico-900">{formatearRut(productor.rut)}</span> · {productor.razon_social}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
