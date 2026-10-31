// Estado y efectos de React.
import { useEffect, useState } from "react";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Listas de solo lectura para formularios (HU11).
import { listarCalidades, listarEspecies, listarSistemasProductivos, listarVariedades } from "../api/opciones";
// Lista desplegable genérica y buscador de productores.
import SelectorCatalogo from "../components/SelectorCatalogo";
import SelectorProductor from "../components/SelectorProductor";
// Clases compartidas.
import { AYUDA, MENSAJE_ERROR, SUBTITULO } from "../components/catalogo";
// Muestra el RUT con puntos y guion en el resumen.
import { formatearRut } from "../utils/rut";

// Nombre de la opción elegida, o "—" si no hay.
function nombreDe(opciones, id) {
  return opciones.find((opcion) => String(opcion.id) === id)?.nombre ?? "—";
}

// Vista previa de los selectores que usará el registro de tarjas (HU12, E3).
export default function RecepcionVistaPrevia() {
  // Catálogos que no dependen de otro dato.
  const [especies, setEspecies] = useState([]);
  const [calidades, setCalidades] = useState([]);
  const [sistemas, setSistemas] = useState([]);
  // Carga y error de esos catálogos.
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  // Variedades de la especie elegida, con su propia carga y error.
  const [variedades, setVariedades] = useState([]);
  const [cargandoVariedades, setCargandoVariedades] = useState(false);
  const [errorVariedades, setErrorVariedades] = useState("");
  // Selección actual; los ids van como texto ("" = sin elegir).
  const [productor, setProductor] = useState(null);
  const [sistemaId, setSistemaId] = useState("");
  const [especieId, setEspecieId] = useState("");
  const [variedadId, setVariedadId] = useState("");
  const [calidadId, setCalidadId] = useState("");

  // Carga especies, calidades y sistemas productivos al abrir la página.
  useEffect(() => {
    // Ignora la respuesta si el usuario salió de la página.
    let vigente = true;
    async function cargar() {
      try {
        // Las tres consultas van en paralelo.
        const [listaEspecies, listaCalidades, listaSistemas] = await Promise.all([
          listarEspecies(),
          listarCalidades(),
          listarSistemasProductivos(),
        ]);
        // Guarda las listas.
        if (vigente) {
          setEspecies(listaEspecies);
          setCalidades(listaCalidades);
          setSistemas(listaSistemas);
        }
      } catch (errorRecibido) {
        // Muestra el error de carga.
        if (vigente) setError(extraerMensajeError(errorRecibido, "No se pudieron cargar las listas"));
      } finally {
        // Habilita las listas.
        if (vigente) setCargando(false);
      }
    }
    // Lanza la carga y la marca como obsoleta al salir.
    cargar();
    return () => { vigente = false; };
  }, []);

  // Recarga las variedades cada vez que cambia la especie (criterio 2 de HU11).
  useEffect(() => {
    // Sin especie no hay variedades que ofrecer.
    if (!especieId) {
      setVariedades([]);
      setErrorVariedades("");
      return undefined;
    }
    // Ignora la respuesta de una especie anterior.
    let vigente = true;
    async function cargar() {
      // Vacía la lista mientras llegan las nuevas variedades.
      setCargandoVariedades(true);
      setErrorVariedades("");
      setVariedades([]);
      try {
        // GET /opciones/variedades?especie_id=N.
        const lista = await listarVariedades(Number(especieId));
        // Guarda las variedades de esta especie.
        if (vigente) setVariedades(lista);
      } catch (errorRecibido) {
        // Muestra el error bajo la lista de variedades.
        if (vigente) setErrorVariedades(extraerMensajeError(errorRecibido, "No se pudieron cargar las variedades"));
      } finally {
        // Termina la carga.
        if (vigente) setCargandoVariedades(false);
      }
    }
    // Lanza la carga y la marca como obsoleta si la especie vuelve a cambiar.
    cargar();
    return () => { vigente = false; };
  }, [especieId]);

  // Al cambiar la especie se limpia la variedad elegida, que era de la especie anterior.
  function cambiarEspecie(id) {
    setEspecieId(id);
    setVariedadId("");
  }

  // Texto de la primera opción de variedades según el estado.
  const textoVariedad = !especieId
    ? "Elija primero una especie"
    : cargandoVariedades
      ? "Cargando…"
      : variedades.length === 0
        ? "Sin variedades activas"
        : "Seleccione…";
  // Primera opción de las demás listas mientras cargan.
  const textoVacio = cargando ? "Cargando…" : "Seleccione…";

  // Filas del resumen de lo elegido.
  const resumen = [
    ["Productor", productor ? `${formatearRut(productor.rut)} · ${productor.razon_social}` : "—"],
    ["Sistema productivo", nombreDe(sistemas, sistemaId)],
    ["Especie", nombreDe(especies, especieId)],
    ["Variedad", nombreDe(variedades, variedadId)],
    ["Calidad", nombreDe(calidades, calidadId)],
  ];

  return (
    <div className="space-y-6">
      {/* Encabezado con rótulo dorado, título y descripción. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E2 · Recepción</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Recepción (vista previa)</h1>
        <p className="mt-2 text-sm text-slate-500">Listas que usará el registro de tarjas: solo muestran registros activos.</p>
      </div>

      {/* Error al cargar los catálogos. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {/* Formulario grande, patrón de Procesamiento de socradex. */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-busy={cargando}>
        {/* Cabecera de la tarjeta. */}
        <div className="mb-5">
          <h2 className="font-semibold text-frigorifico-900">Datos de la recepción</h2>
          <p className="mt-1 text-xs text-slate-500">Al cambiar la especie, la variedad elegida se limpia.</p>
        </div>

        {/* Productor, buscado por RUT o razón social. */}
        <SelectorProductor id="recepcion-productor" valor={productor} onChange={setProductor} />

        {/* Catálogos de la fruta recibida. */}
        <div className="mt-6 grid grid-cols-1 gap-3 border-t border-slate-200 pt-5 sm:grid-cols-2">
          <SelectorCatalogo
            id="recepcion-sistema"
            etiqueta="Sistema productivo"
            opciones={sistemas}
            valor={sistemaId}
            onChange={setSistemaId}
            deshabilitado={cargando}
            textoVacio={textoVacio}
          />
          <SelectorCatalogo
            id="recepcion-calidad"
            etiqueta="Calidad"
            opciones={calidades}
            valor={calidadId}
            onChange={setCalidadId}
            deshabilitado={cargando}
            textoVacio={textoVacio}
          />
          <SelectorCatalogo
            id="recepcion-especie"
            etiqueta="Especie"
            opciones={especies}
            valor={especieId}
            onChange={cambiarEspecie}
            deshabilitado={cargando}
            textoVacio={textoVacio}
          />
          <SelectorCatalogo
            id="recepcion-variedad"
            etiqueta="Variedad"
            opciones={variedades}
            valor={variedadId}
            onChange={setVariedadId}
            deshabilitado={!especieId || cargandoVariedades}
            textoVacio={textoVariedad}
          />
        </div>
        {/* Error al cargar las variedades de la especie elegida. */}
        {errorVariedades && <p className={`mt-3 ${MENSAJE_ERROR}`} role="alert">{errorVariedades}</p>}

        {/* Resumen de lo elegido. */}
        <div className="mt-6 border-t border-slate-200 pt-5">
          <h3 className={SUBTITULO}>Resumen</h3>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {resumen.map(([etiqueta, valor]) => (
              <div key={etiqueta} className="flex flex-wrap gap-x-2">
                <dt className="font-semibold text-slate-600">{etiqueta}:</dt>
                <dd className="break-words text-slate-700">{valor}</dd>
              </div>
            ))}
          </dl>
          {/* Sin botón de guardar: el registro llega con HU12. */}
          <p className={`${AYUDA} mt-4`}>Vista previa: el registro de tarjas llega con HU12 (E3).</p>
        </div>
      </section>
    </div>
  );
}
