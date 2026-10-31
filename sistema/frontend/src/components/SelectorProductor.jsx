// Estado, efectos y referencias de React.
import { useEffect, useRef, useState } from "react";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Búsqueda de productores activos (HU11).
import { buscarProductores } from "../api/opciones";
// Muestra el RUT con puntos y guion.
import { formatearRut } from "../utils/rut";
// Clases compartidas.
import { AYUDA, BOTON_EDITAR, CAMPO, ETIQUETA, MENSAJE_ERROR, OPCION_LISTA } from "./catalogo";

// Caracteres mínimos para buscar; la API devuelve [] con menos.
const MINIMO = 2;
// Tope de resultados de la API (MAXIMO_RESULTADOS en services/opciones.py).
const MAXIMO = 20;
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
  // Campo de búsqueda y botón "Cambiar", para no perder el foco del teclado.
  const campoRef = useRef(null);
  const cambiarRef = useRef(null);
  // Dónde poner el foco cuando cambie el productor elegido: "cambiar", "campo" o null.
  const focoPendiente = useRef(null);

  // Tras elegir, el foco va a "Cambiar"; tras "Cambiar", vuelve al campo de búsqueda.
  useEffect(() => {
    // Elige el elemento según la acción que cambió el productor.
    const destino = focoPendiente.current === "cambiar" ? cambiarRef : focoPendiente.current === "campo" ? campoRef : null;
    // Ese elemento ya existe porque React pintó la vista nueva.
    destino?.current?.focus();
    // El foco se mueve una sola vez por acción.
    focoPendiente.current = null;
  }, [valor]);

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
    // El botón pulsado desaparece; el foco pasará a "Cambiar".
    focoPendiente.current = "cambiar";
    onChange(productor);
    setTexto("");
    setResultados([]);
  }

  // Quita el productor elegido; el foco volverá al campo de búsqueda.
  function cambiar() {
    focoPendiente.current = "campo";
    onChange(null);
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
          <button ref={cambiarRef} type="button" className={BOTON_EDITAR} onClick={cambiar}>Cambiar</button>
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
      : error
        ? "" // Si la búsqueda falló, solo se muestra el error; "sin coincidencias" sería falso.
        : resultados.length === 0
          ? "Sin productores activos que coincidan."
          : `${resultados.length} resultado(s)${resultados.length === MAXIMO ? ` (máximo ${MAXIMO}; afine la búsqueda)` : ""}.`;

  return (
    <div>
      {/* Etiqueta enlazada con el campo de búsqueda. */}
      <label htmlFor={id} className={ETIQUETA}>Productor</label>
      {/* Campo de búsqueda; 50 caracteres como en la API. */}
      <input
        ref={campoRef}
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
                className={OPCION_LISTA}
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
