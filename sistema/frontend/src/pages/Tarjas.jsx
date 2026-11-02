// Estado, efectos y referencias de la consulta.
import { useCallback, useEffect, useRef, useState } from "react";
// Enlace a la hoja de impresión.
import { Link } from "react-router-dom";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Usuario de la sesión: solo el administrador ve Anular.
import { useAuth } from "../api/AuthContext";
// Listado con filtros y detalle de una tarja.
import { anularTarja, listarTarjas, obtenerTarja } from "../api/tarjas";
// Buscador compartido de productores (HU11).
import SelectorProductor from "../components/SelectorProductor";
// Clases comunes de formularios, tablas y mensajes.
import {
  AYUDA,
  BOTON_EDITAR,
  BOTON_PELIGRO,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  CAMPO,
  CELDA,
  CELDA_AVISO,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  ETIQUETA,
  MENSAJE_ERROR,
  MENSAJE_EXITO,
  SELECTOR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";
// Presentación del RUT con puntos y guion.
import { formatearRut } from "../utils/rut";

// Estados de una tarja con su texto visible.
const ESTADOS = [
  { valor: "RECEPCIONADA", texto: "Recepcionada" },
  { valor: "PARCIAL", texto: "Parcial" },
  { valor: "PROCESADA", texto: "Procesada" },
  { valor: "ANULADA", texto: "Anulada" },
];
// Mismo tope de filas que el backend.
const MAXIMO_FILAS = 200;
// Filtros iniciales: sin filtros.
const FILTROS_VACIOS = { numero_tarja: "", desde: "", hasta: "", estado: "" };

// Clase del estado: cada uno con su color, sobre el patrón de claseEstado.
function claseEstadoTarja(estado) {
  // Base común de la etiqueta.
  const base = "rounded-full border px-2 py-0.5 text-xs";
  // La anulada se destaca en rojo.
  if (estado === "ANULADA") return `${base} border-red-200 bg-red-50 text-red-700`;
  // La parcial todavía tiene kilos en curso.
  if (estado === "PARCIAL") return `${base} border-amber-200 bg-amber-50 text-amber-700`;
  // La procesada ya terminó.
  if (estado === "PROCESADA") return `${base} border-slate-200 bg-slate-100 text-slate-500`;
  // La recepcionada está disponible.
  return `${base} border-emerald-200 bg-emerald-50 text-emerald-700`;
}

// Texto visible de un estado.
function textoEstado(estado) {
  // Si llegara un estado desconocido, muestra el valor recibido.
  return ESTADOS.find((opcion) => opcion.valor === estado)?.texto ?? estado;
}

// Muestra una fecha YYYY-MM-DD como DD-MM-YYYY, sin pasar por zonas horarias.
function formatearFecha(valor) {
  // Separa las partes del texto.
  const [anio, mes, dia] = String(valor).split("-");
  // Las ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Muestra la fecha y hora de registro, guardada en UTC, en la hora de la planta.
function formatearFechaHora(valor) {
  // La API la entrega sin zona: se indica que es UTC.
  return new Date(`${valor}Z`).toLocaleString("es-CL", { timeZone: "America/Santiago" });
}

// Muestra un peso decimal con coma, sin pasar por float.
function formatearKilos(valor) {
  // La API entrega los decimales como texto.
  return String(valor).replace(".", ",");
}

// Consulta de tarjas por número, productor, fechas y estado (HU17).
export default function Tarjas() {
  // La API sigue siendo la autoridad; esto solo evita mostrar una acción que respondería 403.
  const { usuario } = useAuth();
  const esAdministrador = usuario.roles.includes("administrador");
  // Filtros que escribe el operador.
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  // Productor elegido en el filtro.
  const [productor, setProductor] = useState(null);
  // Filas de la tabla.
  const [tarjas, setTarjas] = useState([]);
  // Estado de carga y error del listado.
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  // Detalle abierto, su carga y su error.
  const [detalle, setDetalle] = useState(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(null);
  const [errorDetalle, setErrorDetalle] = useState("");
  // Tarja que se está anulando y resultado de la anulación.
  const [anulandoId, setAnulandoId] = useState(null);
  const [mensaje, setMensaje] = useState("");
  // Número de la última búsqueda: una respuesta antigua se descarta.
  const ultimaBusqueda = useRef(0);
  // Título del detalle, para llevar el foco al abrirlo.
  const tituloDetalle = useRef(null);

  // Pide el listado con los filtros indicados.
  const buscar = useCallback(async (criterios, productorElegido) => {
    // Marca esta búsqueda como la vigente.
    const busqueda = ++ultimaBusqueda.current;
    // Muestra la fila de carga.
    setCargando(true);
    setError("");
    try {
      // Envía solo los filtros con valor.
      const lista = await listarTarjas({
        numero_tarja: criterios.numero_tarja.trim() || undefined,
        productor_id: productorElegido?.id,
        desde: criterios.desde || undefined,
        hasta: criterios.hasta || undefined,
        estado: criterios.estado || undefined,
      });
      // Guarda el resultado si sigue vigente.
      if (busqueda === ultimaBusqueda.current) setTarjas(lista);
    } catch (errorRecibido) {
      // Muestra el error y deja la tabla vacía.
      if (busqueda === ultimaBusqueda.current) {
        setTarjas([]);
        setError(extraerMensajeError(errorRecibido, "No se pudieron consultar las tarjas"));
      }
    } finally {
      // Termina la carga de la búsqueda vigente.
      if (busqueda === ultimaBusqueda.current) setCargando(false);
    }
  }, []);

  // Al abrir la pantalla muestra las tarjas más recientes.
  useEffect(() => {
    buscar(FILTROS_VACIOS, null);
  }, [buscar]);

  // Lleva el foco al detalle apenas se abre.
  useEffect(() => {
    if (detalle) tituloDetalle.current?.focus();
  }, [detalle]);

  // Actualiza un filtro.
  function cambiarFiltro(evento) {
    // El nombre del campo coincide con la clave del filtro.
    const { name, value } = evento.target;
    setFiltros((anteriores) => ({ ...anteriores, [name]: value }));
  }

  // Aplica los filtros del formulario.
  function aplicarFiltros(evento) {
    // Evita la navegación nativa del formulario.
    evento.preventDefault();
    // Cierra el detalle de la búsqueda anterior.
    setDetalle(null);
    setErrorDetalle("");
    // Busca con lo escrito.
    buscar(filtros, productor);
  }

  // Quita los filtros y vuelve a las tarjas más recientes.
  function limpiarFiltros() {
    setFiltros(FILTROS_VACIOS);
    setProductor(null);
    setDetalle(null);
    setErrorDetalle("");
    buscar(FILTROS_VACIOS, null);
  }

  // Pide el detalle de una tarja.
  async function verDetalle(id) {
    // Marca la fila que se está cargando.
    setCargandoDetalle(id);
    setErrorDetalle("");
    try {
      // Muestra los datos completos.
      setDetalle(await obtenerTarja(id));
    } catch (errorRecibido) {
      // Muestra el error sobre la tabla.
      setDetalle(null);
      setErrorDetalle(extraerMensajeError(errorRecibido, "No se pudo consultar la tarja"));
    } finally {
      // Libera la fila.
      setCargandoDetalle(null);
    }
  }

  // Anula una tarja, previa confirmación (HU24).
  async function anular(tarja) {
    // Es irreversible: se pide confirmar. No se exige motivo.
    if (!window.confirm(`¿Anular la tarja N° ${tarja.numero_tarja}? Sus bandejas dejarán de sumar al saldo del productor. Esta acción no se puede deshacer.`)) return;
    // Bloquea la fila y limpia los mensajes anteriores.
    setAnulandoId(tarja.id);
    setMensaje("");
    setErrorDetalle("");
    try {
      // La API anula la tarja y su entrada de bandejas en una sola transacción.
      const anulada = await anularTarja(tarja.id);
      // Informa el resultado.
      setMensaje(`Tarja N° ${anulada.numero_tarja} anulada.`);
      // Si su detalle estaba abierto, lo actualiza.
      setDetalle((actual) => (actual?.id === anulada.id ? anulada : actual));
      // Recarga el listado con los filtros que están escritos.
      await buscar(filtros, productor);
    } catch (errorRecibido) {
      // Muestra el error sobre la tabla, por ejemplo si tiene kilos en procesos.
      setErrorDetalle(extraerMensajeError(errorRecibido, "No se pudo anular la tarja"));
    } finally {
      // Libera la fila.
      setAnulandoId(null);
    }
  }

  // Datos del detalle como pares de etiqueta y valor.
  const filasDetalle = detalle
    ? [
      ["Productor", `${detalle.productor_codigo} · ${formatearRut(detalle.productor_rut)} · ${detalle.productor_razon_social}`],
      ["Sistema productivo", detalle.sistema_productivo],
      ["Especie", detalle.especie],
      ["Variedad", detalle.variedad],
      ["Calidad", detalle.calidad],
      ["Calidad visual", `${detalle.porcentaje_calidad} %`],
      ["Tipo de bandeja", detalle.tipo_bandeja],
      ["Cantidad de bandejas", detalle.cantidad_bandejas],
      ["Tara por bandeja", `${formatearKilos(detalle.tara_kg)} kg`],
      ["Peso del pallet", `${formatearKilos(detalle.peso_pallet_kg)} kg`],
      ["Kilos de balanza", `${formatearKilos(detalle.kilos_brutos)} kg`],
      ["Kilos netos", `${detalle.kilos_netos} kg`],
      ["Promedio por bandeja", `${formatearKilos(detalle.kg_promedio_bandeja)} kg`],
      ["Kilos procesados", `${formatearKilos(detalle.kilos_procesados)} kg`],
      ["Kilos pendientes", `${formatearKilos(detalle.kilos_pendientes)} kg`],
      ["Fecha de recepción", formatearFecha(detalle.fecha_recepcion)],
      ["Registrada", formatearFechaHora(detalle.fecha_hora)],
      ["Registrada por", detalle.registrada_por],
    ]
    : [];

  // Renderiza el encabezado, los filtros, el detalle y la tabla.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 3. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E3 · Recepción</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Tarjas</h1>
        <p className="mt-2 text-sm text-slate-500">Busque las tarjas recibidas y revise sus datos y sus kilos.</p>
      </div>

      {/* Filtros: se combinan entre sí. */}
      <form onSubmit={aplicarFiltros} className={TARJETA}>
        <h2 className={`mb-3 ${SUBTITULO}`}>Filtros</h2>
        {/* Productor, por código, RUT o razón social; Enter elige el primero. */}
        <SelectorProductor id="filtro-productor" valor={productor} onChange={setProductor} elegirPrimeroConEnter />
        {/* Los demás filtros en grilla. */}
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* Número exacto de la tarja. */}
          <div>
            <label htmlFor="filtro-numero" className={ETIQUETA}>Número de tarja</label>
            <input
              id="filtro-numero"
              name="numero_tarja"
              type="number"
              min="1"
              step="1"
              value={filtros.numero_tarja}
              onChange={cambiarFiltro}
              className={CAMPO}
            />
          </div>
          {/* Primer día de recepción. */}
          <div>
            <label htmlFor="filtro-desde" className={ETIQUETA}>Recepción desde</label>
            <input id="filtro-desde" name="desde" type="date" value={filtros.desde} onChange={cambiarFiltro} className={CAMPO} />
          </div>
          {/* Último día de recepción. */}
          <div>
            <label htmlFor="filtro-hasta" className={ETIQUETA}>Recepción hasta</label>
            <input id="filtro-hasta" name="hasta" type="date" value={filtros.hasta} onChange={cambiarFiltro} className={CAMPO} />
          </div>
          {/* Estado de la tarja. */}
          <div>
            <label htmlFor="filtro-estado" className={ETIQUETA}>Estado</label>
            <select id="filtro-estado" name="estado" value={filtros.estado} onChange={cambiarFiltro} className={SELECTOR}>
              <option value="">Todos</option>
              {ESTADOS.map((opcion) => <option key={opcion.valor} value={opcion.valor}>{opcion.texto}</option>)}
            </select>
          </div>
        </div>
        {/* Acciones de los filtros. */}
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="submit" disabled={cargando} className={BOTON_PRINCIPAL}>Buscar</button>
          <button type="button" onClick={limpiarFiltros} className={BOTON_SECUNDARIO}>Limpiar</button>
        </div>
      </form>

      {/* Errores del listado y del detalle. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}
      {errorDetalle && <p className={MENSAJE_ERROR} role="alert">{errorDetalle}</p>}
      {/* Resultado de la anulación. */}
      {mensaje && <p className={MENSAJE_EXITO} role="status">{mensaje}</p>}

      {/* Detalle completo de la tarja elegida (HU17 criterio 2). */}
      {detalle && (
        <section aria-labelledby="titulo-detalle-tarja" className={TARJETA}>
          {/* Título, estado y acción para cerrar. */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="titulo-detalle-tarja" ref={tituloDetalle} tabIndex={-1} className="font-semibold text-frigorifico-900 outline-none">Tarja N° {detalle.numero_tarja}</h2>
              <span className={claseEstadoTarja(detalle.estado)}>{textoEstado(detalle.estado)}</span>
            </div>
            <button type="button" onClick={() => setDetalle(null)} className={BOTON_EDITAR}>Cerrar</button>
          </div>
          {/* Datos en dos columnas desde pantallas medianas. */}
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {filasDetalle.map(([etiqueta, valor]) => (
              <div key={etiqueta} className="flex flex-wrap gap-x-2">
                <dt className="font-semibold text-slate-600">{etiqueta}:</dt>
                <dd className="break-words text-slate-700">{valor}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* Resultados. */}
      <div>
        <h2 className={`mb-3 ${SUBTITULO}`}>Resultados</h2>
        {/* Tabla accesible; si no cabe, hace scroll dentro de su contenedor. */}
        <div role="region" aria-label="Listado de tarjas" aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
          <table className="w-full text-sm">
            <caption className="sr-only">Tarjas según los filtros aplicados</caption>
            {/* Encabezados; la columna de acciones solo tiene texto para lectores de pantalla. */}
            <thead className={ENCABEZADO_TABLA}>
              <tr>
                <th scope="col" className={`${CELDA} text-right`}>N°</th>
                <th scope="col" className={CELDA}>Recepción</th>
                <th scope="col" className={CELDA}>Productor</th>
                <th scope="col" className={CELDA}>Fruta</th>
                <th scope="col" className={`${CELDA} text-right`}>Bandejas</th>
                <th scope="col" className={`${CELDA} text-right`}>Kilos netos</th>
                <th scope="col" className={CELDA}>Estado</th>
                <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            {/* Cargando y vacío ocupan una fila dentro de la tabla. */}
            <tbody className="divide-y divide-slate-100">
              {cargando ? (
                <tr><td colSpan={8} className={CELDA_AVISO}>Cargando…</td></tr>
              ) : tarjas.length === 0 ? (
                <tr><td colSpan={8} className={CELDA_AVISO}>Sin tarjas con estos filtros.</td></tr>
              ) : (
                tarjas.map((tarja) => (
                  <tr key={tarja.id} className="hover:bg-slate-50">
                    <td className={`${CELDA} text-right font-medium text-slate-700`}>{tarja.numero_tarja}</td>
                    <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{formatearFecha(tarja.fecha_recepcion)}</td>
                    <td className={`${CELDA} text-slate-600`}>{tarja.productor_codigo} · {tarja.productor_razon_social}</td>
                    <td className={`${CELDA} text-slate-600`}>{tarja.especie} / {tarja.variedad}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{tarja.cantidad_bandejas}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{tarja.kilos_netos}</td>
                    <td className={CELDA}><span className={claseEstadoTarja(tarja.estado)}>{textoEstado(tarja.estado)}</span></td>
                    <td className={`${CELDA} text-right`}>
                      <div className="flex flex-wrap justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => verDetalle(tarja.id)}
                          disabled={cargandoDetalle === tarja.id}
                          aria-label={`Ver detalle de la tarja ${tarja.numero_tarja}`}
                          className={`whitespace-nowrap ${BOTON_EDITAR}`}
                        >
                          {cargandoDetalle === tarja.id ? "Cargando…" : "Ver detalle"}
                        </button>
                        {/* Una tarja anulada no se imprime (HU16). */}
                        {tarja.estado !== "ANULADA" && (
                          <Link to={`/tarjas/${tarja.id}/imprimir`} aria-label={`${tarja.veces_impresa > 0 ? "Reimprimir" : "Imprimir"} la tarja ${tarja.numero_tarja}`} className={`whitespace-nowrap ${BOTON_EDITAR}`}>
                            {tarja.veces_impresa > 0 ? "Reimprimir" : "Imprimir"}
                          </Link>
                        )}
                        {/* Solo el administrador, y solo sin kilos en procesos (HU24 criterios 1 y 2). */}
                        {esAdministrador && tarja.estado === "RECEPCIONADA" && (
                          <button
                            type="button"
                            onClick={() => anular(tarja)}
                            disabled={anulandoId === tarja.id}
                            aria-label={`Anular la tarja ${tarja.numero_tarja}`}
                            className={`whitespace-nowrap ${BOTON_PELIGRO}`}
                          >
                            {anulandoId === tarja.id ? "Anulando…" : "Anular"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {/* Avisa cuando el tope deja filas fuera. */}
        {!cargando && tarjas.length === MAXIMO_FILAS && (
          <p className={AYUDA}>Se muestran las {MAXIMO_FILAS} más recientes; use los filtros para acotar la búsqueda.</p>
        )}
      </div>
    </div>
  );
}
