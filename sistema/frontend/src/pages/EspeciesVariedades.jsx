// Coordina los dos listados y descarta respuestas que dejaron de estar vigentes.
import { useEffect, useRef, useState } from "react";
// Presenta los errores HTTP con el formato compartido por la aplicación.
import { extraerMensajeError } from "../api/client";
import { actualizarEspecie, crearEspecie, listarEspecies } from "../api/especies";
import { actualizarVariedad, crearVariedad, listarVariedades } from "../api/variedades";
// Estilos y reglas compartidas con las demás pantallas de catálogos.
import {
  AYUDA,
  BOTON_EDITAR,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  botonEstado,
  CAMPO,
  CELDA,
  CELDA_AVISO,
  claseEstado,
  claseFila,
  confirmarCambioEstado,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  enfocar,
  ETIQUETA,
  MENSAJE_ERROR,
  MENSAJE_EXITO,
  SELECTOR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";

// Traduce los valores visibles del selector al contrato booleano de la API.
function activoDesdeFiltro(filtro) {
  return filtro === "todos" ? null : filtro === "activos";
}

// Muestra un estado comprensible por texto, además del color de la etiqueta.
function EtiquetaEstado({ activo, femenino = false }) {
  return (
    <span className={claseEstado(activo)}>
      {activo ? (femenino ? "Activa" : "Activo") : (femenino ? "Inactiva" : "Inactivo")}
    </span>
  );
}

// Presenta y administra los catálogos relacionados de especies y variedades.
export default function EspeciesVariedades() {
  const [especies, setEspecies] = useState([]);
  const [filtroEspecies, setFiltroEspecies] = useState("todos");
  const [cargandoEspecies, setCargandoEspecies] = useState(true);
  const [errorEspecies, setErrorEspecies] = useState("");
  const [recargaEspecies, setRecargaEspecies] = useState(0);
  const [especieId, setEspecieId] = useState(null);
  const [formEspecie, setFormEspecie] = useState({ id: null, nombre: "" });
  const [guardandoEspecie, setGuardandoEspecie] = useState(false);
  const [cambiandoEspecieId, setCambiandoEspecieId] = useState(null);
  const [mensajeEspecies, setMensajeEspecies] = useState("");
  const [errorOperacionEspecies, setErrorOperacionEspecies] = useState("");
  const escrituraEspecie = useRef(false);

  const [variedades, setVariedades] = useState([]);
  const [filtroVariedades, setFiltroVariedades] = useState("todos");
  const [cargandoVariedades, setCargandoVariedades] = useState(false);
  const [errorVariedades, setErrorVariedades] = useState("");
  const [recargaVariedades, setRecargaVariedades] = useState(0);
  const [formVariedad, setFormVariedad] = useState({ id: null, nombre: "" });
  const [guardandoVariedad, setGuardandoVariedad] = useState(false);
  const [cambiandoVariedadId, setCambiandoVariedadId] = useState(null);
  const [mensajeVariedades, setMensajeVariedades] = useState("");
  const [errorOperacionVariedades, setErrorOperacionVariedades] = useState("");
  const escrituraVariedad = useRef(false);
  // Campos de nombre, para llevar el foco ahí al pulsar "Editar".
  const campoEspecie = useRef(null);
  const campoVariedad = useRef(null);
  // Título de la sección Variedades: recibe el foco al elegir una especie para que la vista baje hasta él.
  const tituloVariedades = useRef(null);

  // Carga la especie en el formulario y enfoca el campo.
  function editarEspecie(especie) {
    setMensajeEspecies("");
    setErrorOperacionEspecies("");
    setFormEspecie({ id: especie.id, nombre: especie.nombre });
    enfocar(campoEspecie);
  }

  // Carga la variedad en el formulario y enfoca el campo.
  function editarVariedad(variedad) {
    setMensajeVariedades("");
    setErrorOperacionVariedades("");
    setFormVariedad({ id: variedad.id, nombre: variedad.nombre });
    enfocar(campoVariedad);
  }

  // La fila vigente es la única fuente para el nombre y estado del encabezado hijo.
  const especieSeleccionada = especies.find((especie) => especie.id === especieId) ?? null;
  const puedeConsultarVariedades = Boolean(
    especieSeleccionada && !cargandoEspecies && !errorEspecies,
  );

  // Cambiar o perder el padre cierra cualquier edición de una variedad anterior.
  useEffect(() => {
    setFormVariedad({ id: null, nombre: "" });
    setMensajeVariedades("");
    setErrorOperacionVariedades("");
  }, [especieId]);

  // Carga el catálogo padre al entrar, cambiar su filtro o solicitar una recarga.
  useEffect(() => {
    let vigente = true;

    async function cargarEspecies() {
      setCargandoEspecies(true);
      setErrorEspecies("");
      setEspecies([]);
      try {
        const filas = await listarEspecies(activoDesdeFiltro(filtroEspecies));
        if (!vigente) return;
        setEspecies(filas);
        // La recarga conserva el contexto únicamente si la especie aún está visible.
        setEspecieId((idActual) => (
          filas.some((especie) => especie.id === idActual) ? idActual : null
        ));
      } catch (errorRecibido) {
        if (vigente) {
          setErrorEspecies(extraerMensajeError(errorRecibido, "No se pudo cargar la lista de especies"));
        }
      } finally {
        if (vigente) setCargandoEspecies(false);
      }
    }

    cargarEspecies();
    return () => { vigente = false; };
  }, [filtroEspecies, recargaEspecies]);

  // Carga las hijas solo cuando existe una especie vigente dentro del catálogo padre.
  useEffect(() => {
    let vigente = true;

    if (!puedeConsultarVariedades) {
      setVariedades([]);
      setErrorVariedades("");
      setCargandoVariedades(false);
      return () => { vigente = false; };
    }

    async function cargarVariedades() {
      setCargandoVariedades(true);
      setErrorVariedades("");
      setVariedades([]);
      try {
        const filas = await listarVariedades(
          especieId,
          activoDesdeFiltro(filtroVariedades),
        );
        if (vigente) setVariedades(filas);
      } catch (errorRecibido) {
        if (vigente) {
          setErrorVariedades(extraerMensajeError(errorRecibido, "No se pudo cargar la lista de variedades"));
        }
      } finally {
        if (vigente) setCargandoVariedades(false);
      }
    }

    cargarVariedades();
    return () => { vigente = false; };
  }, [especieId, filtroVariedades, recargaVariedades, puedeConsultarVariedades]);

  // Un cambio explícito del padre retira inmediatamente todo el contexto anterior.
  function cambiarFiltroEspecies(event) {
    setEspecieId(null);
    setVariedades([]);
    setErrorVariedades("");
    setCargandoVariedades(false);
    setFiltroVariedades("todos");
    setFiltroEspecies(event.target.value);
  }

  // Inicia el contexto hijo desde Todos y evita presentar filas de otra especie.
  function seleccionarEspecie(id) {
    setVariedades([]);
    setErrorVariedades("");
    setCargandoVariedades(false);
    setFiltroVariedades("todos");
    setEspecieId(id);
    // Con las secciones apiladas, Variedades queda más abajo: espera a que React pinte
    // "Variedades de …" y le da el foco; el navegador hace scroll hasta ese título.
    requestAnimationFrame(() => tituloVariedades.current?.focus());
  }

  // Crea o renombra una especie y deja que la recarga determine su estado final.
  async function guardarEspecie(event) {
    event.preventDefault();
    if (escrituraEspecie.current) return;
    const nombre = formEspecie.nombre.trim();
    setMensajeEspecies("");
    setErrorOperacionEspecies("");
    if (!nombre || nombre.length > 50) {
      setErrorOperacionEspecies("El nombre es obligatorio y admite hasta 50 caracteres.");
      return;
    }
    escrituraEspecie.current = true;
    setGuardandoEspecie(true);
    try {
      const resultado = formEspecie.id === null
        ? await crearEspecie(nombre)
        : await actualizarEspecie(formEspecie.id, { nombre });
      setMensajeEspecies(formEspecie.id === null
        ? `Especie «${resultado.nombre}» creada.`
        : `Especie «${resultado.nombre}» actualizada.`);
      setFormEspecie({ id: null, nombre: "" });
      setRecargaEspecies((valor) => valor + 1);
    } catch (errorRecibido) {
      setErrorOperacionEspecies(extraerMensajeError(errorRecibido, "No se pudo guardar la especie"));
    } finally {
      escrituraEspecie.current = false;
      setGuardandoEspecie(false);
    }
  }

  // Envía solo el nuevo booleano y conserva los conflictos explicados por la API.
  async function cambiarEstadoEspecie(especie) {
    if (escrituraEspecie.current) return;
    // Solo desactivar pide confirmación, igual que en Productores.
    if (!confirmarCambioEstado(especie.activo, `la especie «${especie.nombre}»`)) return;
    escrituraEspecie.current = true;
    setCambiandoEspecieId(especie.id);
    setMensajeEspecies("");
    setErrorOperacionEspecies("");
    try {
      const resultado = await actualizarEspecie(especie.id, { activo: !especie.activo });
      setMensajeEspecies(`Especie «${resultado.nombre}» ${resultado.activo ? "activada" : "desactivada"}.`);
      setRecargaEspecies((valor) => valor + 1);
    } catch (errorRecibido) {
      setErrorOperacionEspecies(extraerMensajeError(errorRecibido, "No se pudo cambiar el estado de la especie"));
    } finally {
      escrituraEspecie.current = false;
      setCambiandoEspecieId(null);
    }
  }

  // Crea o renombra dentro de la especie seleccionada sin enviar especie_id al editar.
  async function guardarVariedad(event) {
    event.preventDefault();
    if (escrituraVariedad.current || !especieSeleccionada) return;
    const nombre = formVariedad.nombre.trim();
    setMensajeVariedades("");
    setErrorOperacionVariedades("");
    if (!nombre || nombre.length > 50) {
      setErrorOperacionVariedades("El nombre es obligatorio y admite hasta 50 caracteres.");
      return;
    }
    if (formVariedad.id === null && !especieSeleccionada.activo) {
      setErrorOperacionVariedades("La especie debe estar activa para crear una variedad.");
      return;
    }
    escrituraVariedad.current = true;
    setGuardandoVariedad(true);
    try {
      const resultado = formVariedad.id === null
        ? await crearVariedad(especieSeleccionada.id, nombre)
        : await actualizarVariedad(formVariedad.id, { nombre });
      setMensajeVariedades(formVariedad.id === null
        ? `Variedad «${resultado.nombre}» creada.`
        : `Variedad «${resultado.nombre}» actualizada.`);
      setFormVariedad({ id: null, nombre: "" });
      setRecargaVariedades((valor) => valor + 1);
    } catch (errorRecibido) {
      setErrorOperacionVariedades(extraerMensajeError(errorRecibido, "No se pudo guardar la variedad"));
    } finally {
      escrituraVariedad.current = false;
      setGuardandoVariedad(false);
    }
  }

  // Reactivar exige un padre activo; las demás reglas permanecen en el backend.
  async function cambiarEstadoVariedad(variedad) {
    if (escrituraVariedad.current || !especieSeleccionada) return;
    if (!variedad.activo && !especieSeleccionada.activo) {
      setErrorOperacionVariedades("La especie debe estar activa para habilitar una variedad");
      return;
    }
    // Solo desactivar pide confirmación.
    if (!confirmarCambioEstado(variedad.activo, `la variedad «${variedad.nombre}»`)) return;
    escrituraVariedad.current = true;
    setCambiandoVariedadId(variedad.id);
    setMensajeVariedades("");
    setErrorOperacionVariedades("");
    try {
      const resultado = await actualizarVariedad(variedad.id, { activo: !variedad.activo });
      setMensajeVariedades(`Variedad «${resultado.nombre}» ${resultado.activo ? "activada" : "desactivada"}.`);
      setRecargaVariedades((valor) => valor + 1);
    } catch (errorRecibido) {
      setErrorOperacionVariedades(extraerMensajeError(errorRecibido, "No se pudo cambiar el estado de la variedad"));
    } finally {
      escrituraVariedad.current = false;
      setCambiandoVariedadId(null);
    }
  }

  return (
    <section aria-labelledby="titulo-especies-variedades" className="min-w-0">
      {/* Se muestra dentro de la pestaña de Mantenedores: el título visible es el de la pestaña. */}
      <h2 id="titulo-especies-variedades" className="sr-only">Especies y variedades</h2>
      <p className="text-sm text-slate-500">Especie de fruta (ej. Cereza, Uva). Elige una especie para ver y mantener sus variedades.</p>

      {/* Especies y Variedades apiladas en una columna, como los mantenedores del proyecto de referencia. */}
      <div className="mt-6 min-w-0 space-y-10">
        <section aria-labelledby="titulo-especies" className="min-w-0 space-y-4">
          <h2 id="titulo-especies" className="text-lg font-bold text-frigorifico-900">Especies</h2>
          {mensajeEspecies && <p role="status" className={MENSAJE_EXITO}>{mensajeEspecies}</p>}
          {errorOperacionEspecies && <p role="alert" className={MENSAJE_ERROR}>{errorOperacionEspecies}</p>}
          {/* Tarjeta del formulario: campo en grilla y botones debajo. */}
          <form onSubmit={guardarEspecie} className={TARJETA}>
            <h3 className={`mb-3 ${SUBTITULO}`}>{formEspecie.id === null ? "Nueva especie" : "Editar especie"}</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label htmlFor="nombre-especie" className={ETIQUETA}>Nombre</label>
                <input ref={campoEspecie} id="nombre-especie" type="text" required maxLength={50} value={formEspecie.nombre} onChange={(event) => setFormEspecie((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardandoEspecie} className={CAMPO} />
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="submit" disabled={guardandoEspecie} className={BOTON_PRINCIPAL}>{guardandoEspecie ? "Guardando…" : "Guardar"}</button>
              {formEspecie.id !== null && <button type="button" onClick={() => setFormEspecie({ id: null, nombre: "" })} disabled={guardandoEspecie} className={BOTON_SECUNDARIO}>Cancelar</button>}
            </div>
          </form>

          {/* Encabezado del listado: subtítulo a la izquierda; filtro y recarga a la derecha. */}
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h3 className={SUBTITULO}>Registradas</h3>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-full sm:w-48">
                <label htmlFor="filtro-especies" className={ETIQUETA}>Mostrar</label>
                <select id="filtro-especies" value={filtroEspecies} onChange={cambiarFiltroEspecies} className={SELECTOR}>
                  <option value="todos">Todos</option>
                  <option value="activos">Activos</option>
                  <option value="inactivos">Inactivos</option>
                </select>
              </div>
              {/* Usa el botón principal compartido de catalogo.js, igual que "Guardar". */}
              <button type="button" onClick={() => setRecargaEspecies((valor) => valor + 1)} disabled={cargandoEspecies} className={BOTON_PRINCIPAL}>Recargar especies</button>
            </div>
          </div>

          {/* El error de consulta se muestra como mensaje; la tabla queda con su aviso. */}
          {errorEspecies && <p role="alert" className={MENSAJE_ERROR}>{errorEspecies}</p>}
          <div role="region" aria-label="Listado de especies" aria-busy={cargandoEspecies} tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Especies según el filtro seleccionado</caption>
              <thead className={ENCABEZADO_TABLA}>
                <tr><th scope="col" className={CELDA}>Nombre</th><th scope="col" className={CELDA}>Estado</th><th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {/* Cargando, error y vacío son una fila dentro de la tabla, como en la referencia. */}
                {cargandoEspecies ? <tr><td colSpan={3} className={CELDA_AVISO}>Cargando…</td></tr>
                  : errorEspecies ? <tr><td colSpan={3} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                    : especies.length === 0 ? <tr><td colSpan={3} className={CELDA_AVISO}>Sin especies con este filtro.</td></tr>
                      : especies.map((especie) => {
                        const seleccionada = especie.id === especieId;
                        return (
                          <tr key={especie.id} className={formEspecie.id === especie.id ? claseFila(true) : seleccionada ? "bg-frigorifico-50" : claseFila(false)} aria-current={formEspecie.id === especie.id ? "true" : undefined}>
                            <td className={`${CELDA} text-slate-600`}>{especie.nombre}</td>
                            <td className={CELDA}><EtiquetaEstado activo={especie.activo} femenino /></td>
                            <td className={`${CELDA} text-right`}>
                              <div className="flex flex-wrap items-center justify-end gap-3">
                                {/* Elegir la especie es la acción principal de la fila: botón con contorno; las otras son enlaces. */}
                                <button type="button" onClick={() => seleccionarEspecie(especie.id)} aria-pressed={seleccionada} className={seleccionada ? BOTON_PRINCIPAL : BOTON_SECUNDARIO}>{seleccionada ? "Seleccionada" : "Ver variedades"}</button>
                                <button type="button" onClick={() => editarEspecie(especie)} disabled={cambiandoEspecieId === especie.id || guardandoEspecie} aria-label={`Editar ${especie.nombre}`} className={BOTON_EDITAR}>Editar</button>
                                <button type="button" onClick={() => cambiarEstadoEspecie(especie)} disabled={cambiandoEspecieId === especie.id || guardandoEspecie} aria-label={`${especie.activo ? "Desactivar" : "Activar"} ${especie.nombre}`} className={botonEstado(especie.activo)}>{cambiandoEspecieId === especie.id ? "Actualizando…" : especie.activo ? "Desactivar" : "Activar"}</button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-labelledby="titulo-variedades" className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* ref y tabIndex={-1}: se puede enfocar por código sin sumarse al recorrido con Tab; sin contorno porque no es un control. */}
            <h2 ref={tituloVariedades} tabIndex={-1} id="titulo-variedades" className="text-lg font-bold text-frigorifico-900 focus:outline-none">{especieSeleccionada ? `Variedades de ${especieSeleccionada.nombre}` : "Variedades"}</h2>
            {especieSeleccionada && <EtiquetaEstado activo={especieSeleccionada.activo} femenino />}
          </div>
          {mensajeVariedades && <p role="status" className={MENSAJE_EXITO}>{mensajeVariedades}</p>}
          {errorOperacionVariedades && <p role="alert" className={MENSAJE_ERROR}>{errorOperacionVariedades}</p>}
          {/* Tarjeta del formulario: campo en grilla, ayuda bajo el campo y botones debajo. */}
          <form onSubmit={guardarVariedad} className={TARJETA}>
            <h3 className={`mb-3 ${SUBTITULO}`}>{formVariedad.id === null ? "Nueva variedad" : "Editar variedad"}</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label htmlFor="nombre-variedad" className={ETIQUETA}>Nombre</label>
                <input ref={campoVariedad} id="nombre-variedad" type="text" required maxLength={50} value={formVariedad.nombre} onChange={(event) => setFormVariedad((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardandoVariedad || !especieSeleccionada || (formVariedad.id === null && !especieSeleccionada.activo)} className={CAMPO} />
                {!especieSeleccionada && <p className={AYUDA}>Selecciona una especie para crear variedades.</p>}
                {especieSeleccionada && !especieSeleccionada.activo && formVariedad.id === null && <p className="mt-1 text-xs text-amber-800">Activa la especie para crear una variedad.</p>}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="submit" disabled={guardandoVariedad || !especieSeleccionada || (formVariedad.id === null && !especieSeleccionada.activo)} className={BOTON_PRINCIPAL}>{guardandoVariedad ? "Guardando…" : "Guardar"}</button>
              {formVariedad.id !== null && <button type="button" onClick={() => setFormVariedad({ id: null, nombre: "" })} disabled={guardandoVariedad} className={BOTON_SECUNDARIO}>Cancelar</button>}
            </div>
          </form>

          {/* Encabezado del listado: subtítulo a la izquierda; filtro y recarga a la derecha. */}
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h3 className={SUBTITULO}>Registradas</h3>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-full sm:w-48">
                <label htmlFor="filtro-variedades" className={ETIQUETA}>Mostrar</label>
                <select id="filtro-variedades" value={filtroVariedades} disabled={!puedeConsultarVariedades} onChange={(event) => setFiltroVariedades(event.target.value)} className={SELECTOR}>
                  <option value="todos">Todos</option>
                  <option value="activos">Activos</option>
                  <option value="inactivos">Inactivos</option>
                </select>
              </div>
              {/* Usa el botón principal compartido de catalogo.js, igual que "Guardar". */}
              <button type="button" onClick={() => setRecargaVariedades((valor) => valor + 1)} disabled={!puedeConsultarVariedades || cargandoVariedades} className={BOTON_PRINCIPAL}>Recargar variedades</button>
            </div>
          </div>

          {/* El error de consulta se muestra como mensaje; la tabla queda con su aviso. */}
          {errorVariedades && especieSeleccionada && !cargandoEspecies && !errorEspecies && <p role="alert" className={MENSAJE_ERROR}>{errorVariedades}</p>}
          <div role="region" aria-label={especieSeleccionada ? `Variedades de ${especieSeleccionada.nombre}` : "Listado de variedades"} aria-busy={cargandoVariedades} tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Variedades de la especie seleccionada</caption>
              <thead className={ENCABEZADO_TABLA}><tr><th scope="col" className={CELDA}>Nombre</th><th scope="col" className={CELDA}>Estado</th><th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {/* Cada situación sin datos es una fila de aviso dentro de la tabla. */}
                {cargandoEspecies ? <tr><td colSpan={3} className={CELDA_AVISO}>Actualizando especies antes de consultar sus variedades…</td></tr>
                  : errorEspecies ? <tr><td colSpan={3} className={CELDA_AVISO}>Corrige la consulta de especies para recuperar este listado.</td></tr>
                    : !especieSeleccionada ? <tr><td colSpan={3} className={CELDA_AVISO}>Selecciona una especie para consultar sus variedades.</td></tr>
                      : cargandoVariedades ? <tr><td colSpan={3} className={CELDA_AVISO}>Cargando…</td></tr>
                        : errorVariedades ? <tr><td colSpan={3} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                          : variedades.length === 0 ? <tr><td colSpan={3} className={CELDA_AVISO}>Sin variedades de esta especie con este filtro.</td></tr>
                            : variedades.map((variedad) => (
                              <tr key={variedad.id} className={claseFila(formVariedad.id === variedad.id)} aria-current={formVariedad.id === variedad.id ? "true" : undefined}>
                                <td className={`${CELDA} text-slate-600`}>{variedad.nombre}</td>
                                <td className={CELDA}><EtiquetaEstado activo={variedad.activo} femenino /></td>
                                <td className={`${CELDA} text-right`}><div className="flex flex-wrap justify-end gap-3">
                                  <button type="button" onClick={() => editarVariedad(variedad)} disabled={cambiandoVariedadId === variedad.id || guardandoVariedad} aria-label={`Editar ${variedad.nombre}`} className={BOTON_EDITAR}>Editar</button>
                                  <button type="button" onClick={() => cambiarEstadoVariedad(variedad)} disabled={cambiandoVariedadId === variedad.id || guardandoVariedad || (!variedad.activo && !especieSeleccionada.activo)} title={!variedad.activo && !especieSeleccionada.activo ? "Activa primero la especie" : undefined} aria-label={`${variedad.activo ? "Desactivar" : "Activar"} ${variedad.nombre}`} className={botonEstado(variedad.activo)}>{cambiandoVariedadId === variedad.id ? "Actualizando…" : variedad.activo ? "Desactivar" : "Activar"}</button>
                                </div></td>
                              </tr>
                            ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  );
}
