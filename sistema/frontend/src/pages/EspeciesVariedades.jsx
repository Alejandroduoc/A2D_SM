// Coordina los dos listados y descarta respuestas que dejaron de estar vigentes.
import { useEffect, useRef, useState } from "react";
// Presenta los errores HTTP con el formato compartido por la aplicación.
import { extraerMensajeError } from "../api/client";
import { actualizarEspecie, crearEspecie, listarEspecies } from "../api/especies";
import { actualizarVariedad, crearVariedad, listarVariedades } from "../api/variedades";

// Traduce los valores visibles del selector al contrato booleano de la API.
function activoDesdeFiltro(filtro) {
  return filtro === "todos" ? null : filtro === "activos";
}

// Muestra un estado comprensible por texto, además del color de la etiqueta.
function EtiquetaEstado({ activo, femenino = false }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${activo ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-slate-100 text-slate-600 ring-slate-500/20"}`}>
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
    const accion = especie.activo ? "desactivar" : "activar";
    if (!window.confirm(`¿Deseas ${accion} la especie «${especie.nombre}»?`)) return;
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
    const accion = variedad.activo ? "desactivar" : "activar";
    if (!window.confirm(`¿Deseas ${accion} la variedad «${variedad.nombre}»?`)) return;
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
      <h1 id="titulo-especies-variedades" className="text-3xl font-semibold text-frigorifico-950">Especies y variedades</h1>
      <p className="mt-2 text-slate-500">Consulta los catálogos y las variedades asociadas a cada especie.</p>

      <div className="mt-8 grid min-w-0 gap-8 lg:grid-cols-2 lg:items-start">
        <section aria-labelledby="titulo-especies" className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <h2 id="titulo-especies" className="text-xl font-semibold text-frigorifico-950">Especies</h2>
          {mensajeEspecies && <p role="status" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{mensajeEspecies}</p>}
          {errorOperacionEspecies && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorOperacionEspecies}</p>}
          <form onSubmit={guardarEspecie} className="mt-5 rounded-xl bg-slate-50 p-4">
            <label htmlFor="nombre-especie" className="block text-sm font-semibold text-slate-700">{formEspecie.id === null ? "Nueva especie" : "Editar especie"}</label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input id="nombre-especie" type="text" required maxLength={50} value={formEspecie.nombre} onChange={(event) => setFormEspecie((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardandoEspecie} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-100" />
              <button type="submit" disabled={guardandoEspecie} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{guardandoEspecie ? "Guardando…" : "Guardar"}</button>
              {formEspecie.id !== null && <button type="button" onClick={() => setFormEspecie({ id: null, nombre: "" })} disabled={guardandoEspecie} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">Cancelar</button>}
            </div>
          </form>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <div className="w-full sm:w-auto">
              <label htmlFor="filtro-especies" className="mb-2 block text-sm font-semibold text-slate-700">Mostrar especies</label>
              <select id="filtro-especies" value={filtroEspecies} onChange={cambiarFiltroEspecies} className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 sm:min-w-48">
                <option value="todos">Todos</option>
                <option value="activos">Activos</option>
                <option value="inactivos">Inactivos</option>
              </select>
            </div>
            <button type="button" onClick={() => setRecargaEspecies((valor) => valor + 1)} disabled={cargandoEspecies} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">Recargar especies</button>
          </div>

          <div className="mt-6 min-w-0" aria-busy={cargandoEspecies}>
            {cargandoEspecies ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Cargando especies…</p>
            ) : errorEspecies ? (
              <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700">{errorEspecies}</p>
            ) : especies.length === 0 ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">No hay especies con este filtro</p>
            ) : (
              <div role="region" aria-label="Listado de especies" tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <caption className="sr-only">Especies según el filtro seleccionado</caption>
                  <thead className="border-b border-slate-200 bg-frigorifico-50 text-frigorifico-950">
                    <tr><th scope="col" className="px-4 py-3 font-semibold">Nombre</th><th scope="col" className="px-4 py-3 font-semibold">Estado</th><th scope="col" className="px-4 py-3 font-semibold">Acciones</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {especies.map((especie) => {
                      const seleccionada = especie.id === especieId;
                      return (
                        <tr key={especie.id} className={seleccionada ? "bg-frigorifico-50" : "hover:bg-slate-50"}>
                          <td className="px-4 py-4 font-medium text-frigorifico-900">{especie.nombre}</td>
                          <td className="px-4 py-4"><EtiquetaEstado activo={especie.activo} femenino /></td>
                          <td className="px-4 py-4">
                            <div className="flex flex-wrap gap-2">
                              <button type="button" onClick={() => seleccionarEspecie(especie.id)} aria-pressed={seleccionada} className={`rounded-lg border px-3 py-2 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700 ${seleccionada ? "border-frigorifico-800 bg-frigorifico-900 text-white" : "border-slate-300 text-frigorifico-900 hover:bg-frigorifico-50"}`}>{seleccionada ? "Seleccionada" : "Ver variedades"}</button>
                              <button type="button" onClick={() => { setMensajeEspecies(""); setErrorOperacionEspecies(""); setFormEspecie({ id: especie.id, nombre: especie.nombre }); }} disabled={cambiandoEspecieId === especie.id || guardandoEspecie} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-frigorifico-900 disabled:opacity-50">Editar</button>
                              <button type="button" onClick={() => cambiarEstadoEspecie(especie)} disabled={cambiandoEspecieId === especie.id || guardandoEspecie} className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-900 disabled:opacity-50">{cambiandoEspecieId === especie.id ? "Actualizando…" : especie.activo ? "Desactivar" : "Activar"}</button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <section aria-labelledby="titulo-variedades" className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="flex min-h-14 flex-wrap items-center justify-between gap-3">
            <h2 id="titulo-variedades" className="text-xl font-semibold text-frigorifico-950">{especieSeleccionada ? `Variedades de ${especieSeleccionada.nombre}` : "Variedades"}</h2>
            {especieSeleccionada && <EtiquetaEstado activo={especieSeleccionada.activo} femenino />}
          </div>
          {mensajeVariedades && <p role="status" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{mensajeVariedades}</p>}
          {errorOperacionVariedades && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorOperacionVariedades}</p>}
          <form onSubmit={guardarVariedad} className="mt-5 rounded-xl bg-slate-50 p-4">
            <label htmlFor="nombre-variedad" className="block text-sm font-semibold text-slate-700">{formVariedad.id === null ? "Nueva variedad" : "Editar variedad"}</label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input id="nombre-variedad" type="text" required maxLength={50} value={formVariedad.nombre} onChange={(event) => setFormVariedad((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardandoVariedad || !especieSeleccionada || (formVariedad.id === null && !especieSeleccionada.activo)} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-100" />
              <button type="submit" disabled={guardandoVariedad || !especieSeleccionada || (formVariedad.id === null && !especieSeleccionada.activo)} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{guardandoVariedad ? "Guardando…" : "Guardar"}</button>
              {formVariedad.id !== null && <button type="button" onClick={() => setFormVariedad({ id: null, nombre: "" })} disabled={guardandoVariedad} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">Cancelar</button>}
            </div>
            {!especieSeleccionada && <p className="mt-2 text-xs text-slate-500">Selecciona una especie para crear variedades.</p>}
            {especieSeleccionada && !especieSeleccionada.activo && formVariedad.id === null && <p className="mt-2 text-xs text-amber-800">Activa la especie para crear una variedad.</p>}
          </form>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <div className="w-full sm:w-auto">
              <label htmlFor="filtro-variedades" className="mb-2 block text-sm font-semibold text-slate-700">Mostrar variedades</label>
              <select id="filtro-variedades" value={filtroVariedades} disabled={!puedeConsultarVariedades} onChange={(event) => setFiltroVariedades(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:cursor-not-allowed disabled:bg-slate-100 sm:min-w-48">
                <option value="todos">Todos</option>
                <option value="activos">Activos</option>
                <option value="inactivos">Inactivos</option>
              </select>
            </div>
            <button type="button" onClick={() => setRecargaVariedades((valor) => valor + 1)} disabled={!puedeConsultarVariedades || cargandoVariedades} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">Recargar variedades</button>
          </div>

          <div className="mt-6 min-w-0" aria-busy={cargandoVariedades}>
            {cargandoEspecies ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Actualizando especies antes de consultar sus variedades…</p>
            ) : errorEspecies ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Corrige la consulta de especies para recuperar este listado.</p>
            ) : !especieSeleccionada ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Selecciona una especie para consultar sus variedades</p>
            ) : cargandoVariedades ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Cargando variedades…</p>
            ) : errorVariedades ? (
              <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700">{errorVariedades}</p>
            ) : variedades.length === 0 ? (
              <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">No hay variedades de esta especie con este filtro</p>
            ) : (
              <div role="region" aria-label={`Variedades de ${especieSeleccionada.nombre}`} tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <caption className="sr-only">Variedades de la especie seleccionada</caption>
                  <thead className="border-b border-slate-200 bg-frigorifico-50 text-frigorifico-950"><tr><th scope="col" className="px-4 py-3 font-semibold">Nombre</th><th scope="col" className="px-4 py-3 font-semibold">Estado</th><th scope="col" className="px-4 py-3 font-semibold">Acciones</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {variedades.map((variedad) => (
                      <tr key={variedad.id} className="hover:bg-slate-50">
                        <td className="px-4 py-4 font-medium text-frigorifico-900">{variedad.nombre}</td>
                        <td className="px-4 py-4"><EtiquetaEstado activo={variedad.activo} femenino /></td>
                        <td className="px-4 py-4"><div className="flex flex-wrap gap-2">
                          <button type="button" onClick={() => { setMensajeVariedades(""); setErrorOperacionVariedades(""); setFormVariedad({ id: variedad.id, nombre: variedad.nombre }); }} disabled={cambiandoVariedadId === variedad.id || guardandoVariedad} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-frigorifico-900 disabled:opacity-50">Editar</button>
                          <button type="button" onClick={() => cambiarEstadoVariedad(variedad)} disabled={cambiandoVariedadId === variedad.id || guardandoVariedad || (!variedad.activo && !especieSeleccionada.activo)} title={!variedad.activo && !especieSeleccionada.activo ? "Activa primero la especie" : undefined} className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-900 disabled:opacity-50">{cambiandoVariedadId === variedad.id ? "Actualizando…" : variedad.activo ? "Desactivar" : "Activar"}</button>
                        </div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
