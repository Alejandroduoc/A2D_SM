// Cada sección conserva un ciclo de consulta y escritura completamente independiente.
import { useEffect, useRef, useState } from "react";
import { extraerMensajeError } from "../api/client";
import { actualizarCalidad, crearCalidad, listarCalidades } from "../api/calidades";
import {
  actualizarSistemaProductivo,
  crearSistemaProductivo,
  listarSistemasProductivos,
} from "../api/sistemasProductivos";

function activoDesdeFiltro(filtro) {
  return filtro === "todos" ? null : filtro === "activos";
}

// Reutiliza la presentación sin compartir estado entre los dos catálogos.
function PanelCatalogo({ clave, titulo, singular, femenino, listar, crear, actualizar }) {
  const [filas, setFilas] = useState([]);
  const [filtro, setFiltro] = useState("todos");
  const [cargando, setCargando] = useState(true);
  const [errorListado, setErrorListado] = useState("");
  const [recarga, setRecarga] = useState(0);
  const [form, setForm] = useState({ id: null, nombre: "" });
  const [guardando, setGuardando] = useState(false);
  const [cambiandoId, setCambiandoId] = useState(null);
  const [mensaje, setMensaje] = useState("");
  const [errorOperacion, setErrorOperacion] = useState("");
  const escrituraEnCurso = useRef(false);

  useEffect(() => {
    let vigente = true;
    async function cargar() {
      setCargando(true);
      setErrorListado("");
      setFilas([]);
      try {
        const resultado = await listar(activoDesdeFiltro(filtro));
        if (vigente) setFilas(resultado);
      } catch (error) {
        if (vigente) setErrorListado(extraerMensajeError(error, `No se pudo cargar ${titulo.toLowerCase()}`));
      } finally {
        if (vigente) setCargando(false);
      }
    }
    cargar();
    return () => { vigente = false; };
  }, [filtro, recarga, listar, titulo]);

  async function guardar(event) {
    event.preventDefault();
    if (escrituraEnCurso.current) return;
    const nombre = form.nombre.trim();
    setMensaje("");
    setErrorOperacion("");
    if (!nombre || nombre.length > 50) {
      setErrorOperacion("El nombre es obligatorio y admite hasta 50 caracteres.");
      return;
    }
    escrituraEnCurso.current = true;
    setGuardando(true);
    try {
      const resultado = form.id === null
        ? await crear(nombre)
        : await actualizar(form.id, { nombre });
      setMensaje(`${singular} «${resultado.nombre}» ${form.id === null ? (femenino ? "creada" : "creado") : (femenino ? "actualizada" : "actualizado")}.`);
      setForm({ id: null, nombre: "" });
      setRecarga((valor) => valor + 1);
    } catch (error) {
      setErrorOperacion(extraerMensajeError(error, `No se pudo guardar ${singular.toLowerCase()}`));
    } finally {
      escrituraEnCurso.current = false;
      setGuardando(false);
    }
  }

  async function cambiarEstado(fila) {
    if (escrituraEnCurso.current) return;
    const accion = fila.activo ? "desactivar" : "activar";
    if (!window.confirm(`¿Deseas ${accion} ${singular.toLowerCase()} «${fila.nombre}»?`)) return;
    escrituraEnCurso.current = true;
    setCambiandoId(fila.id);
    setMensaje("");
    setErrorOperacion("");
    try {
      const resultado = await actualizar(fila.id, { activo: !fila.activo });
      setMensaje(`${singular} «${resultado.nombre}» ${resultado.activo ? (femenino ? "activada" : "activado") : (femenino ? "desactivada" : "desactivado")}.`);
      setRecarga((valor) => valor + 1);
    } catch (error) {
      setErrorOperacion(extraerMensajeError(error, `No se pudo cambiar el estado de ${singular.toLowerCase()}`));
    } finally {
      escrituraEnCurso.current = false;
      setCambiandoId(null);
    }
  }

  return (
    <section aria-labelledby={`titulo-${clave}`} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <h2 id={`titulo-${clave}`} className="text-xl font-semibold text-frigorifico-950">{titulo}</h2>
      {mensaje && <p role="status" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{mensaje}</p>}
      {errorOperacion && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorOperacion}</p>}

      <form onSubmit={guardar} className="mt-5 rounded-xl bg-slate-50 p-4">
        <label htmlFor={`nombre-${clave}`} className="block text-sm font-semibold text-slate-700">{form.id === null ? `${femenino ? "Nueva" : "Nuevo"} ${singular.toLowerCase()}` : `Editar ${singular.toLowerCase()}`}</label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input id={`nombre-${clave}`} type="text" required maxLength={50} value={form.nombre} onChange={(event) => setForm((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardando} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-100" />
          <button type="submit" disabled={guardando} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:opacity-50">{guardando ? "Guardando…" : "Guardar"}</button>
          {form.id !== null && <button type="button" onClick={() => setForm({ id: null, nombre: "" })} disabled={guardando} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">Cancelar</button>}
        </div>
      </form>

      <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
        <div className="w-full sm:w-auto">
          <label htmlFor={`filtro-${clave}`} className="mb-2 block text-sm font-semibold text-slate-700">Mostrar {titulo.toLowerCase()}</label>
          <select id={`filtro-${clave}`} value={filtro} onChange={(event) => setFiltro(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 sm:min-w-48">
            <option value="todos">Todos</option><option value="activos">Activos</option><option value="inactivos">Inactivos</option>
          </select>
        </div>
        <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando} className="rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Recargar</button>
      </div>

      <div className="mt-6 min-w-0" aria-busy={cargando}>
        {cargando ? <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Cargando {titulo.toLowerCase()}…</p>
          : errorListado ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700">{errorListado}</p>
            : filas.length === 0 ? <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">No hay registros con este filtro</p>
              : <div role="region" aria-label={`Listado de ${titulo.toLowerCase()}`} tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <caption className="sr-only">{titulo} según el filtro seleccionado</caption>
                  <thead className="border-b border-slate-200 bg-frigorifico-50 text-frigorifico-950"><tr><th scope="col" className="px-4 py-3">Nombre</th><th scope="col" className="px-4 py-3">Estado</th><th scope="col" className="px-4 py-3">Acciones</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">{filas.map((fila) => <tr key={fila.id} className="hover:bg-slate-50">
                    <td className="px-4 py-4 font-medium text-frigorifico-900">{fila.nombre}</td>
                    <td className="px-4 py-4"><span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${fila.activo ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-slate-100 text-slate-600 ring-slate-500/20"}`}>{fila.activo ? (femenino ? "Activa" : "Activo") : (femenino ? "Inactiva" : "Inactivo")}</span></td>
                    <td className="px-4 py-4"><div className="flex flex-wrap gap-2">
                      <button type="button" onClick={() => { setMensaje(""); setErrorOperacion(""); setForm({ id: fila.id, nombre: fila.nombre }); }} disabled={guardando || cambiandoId === fila.id} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-frigorifico-900 disabled:opacity-50">Editar</button>
                      <button type="button" onClick={() => cambiarEstado(fila)} disabled={guardando || cambiandoId === fila.id} className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-900 disabled:opacity-50">{cambiandoId === fila.id ? "Actualizando…" : fila.activo ? "Desactivar" : "Activar"}</button>
                    </div></td>
                  </tr>)}</tbody>
                </table>
              </div>}
      </div>
    </section>
  );
}

export default function CalidadesSistemasProductivos() {
  return (
    <section aria-labelledby="titulo-calidades-sistemas" className="min-w-0">
      <h1 id="titulo-calidades-sistemas" className="text-3xl font-semibold text-frigorifico-950">Calidades y sistemas productivos</h1>
      <p className="mt-2 text-slate-500">Gestiona los catálogos de clasificación y forma de producción.</p>
      <div className="mt-8 grid min-w-0 gap-8 lg:grid-cols-2 lg:items-start">
        <PanelCatalogo clave="calidades" titulo="Calidades" singular="Calidad" femenino listar={listarCalidades} crear={crearCalidad} actualizar={actualizarCalidad} />
        <PanelCatalogo clave="sistemas-productivos" titulo="Sistemas productivos" singular="Sistema productivo" femenino={false} listar={listarSistemasProductivos} crear={crearSistemaProductivo} actualizar={actualizarSistemaProductivo} />
      </div>
    </section>
  );
}
