// Cada sección conserva un ciclo de consulta y escritura completamente independiente.
// Estado, efectos y referencia mutable de React.
import { useEffect, useRef, useState } from "react";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Operaciones del catálogo de calidades.
import { actualizarCalidad, crearCalidad, listarCalidades } from "../api/calidades";
// Operaciones del catálogo de sistemas productivos.
import {
  actualizarSistemaProductivo,
  crearSistemaProductivo,
  listarSistemasProductivos,
} from "../api/sistemasProductivos";
// Estilos y reglas compartidas con las demás pantallas de catálogos.
import {
  BOTON_EDITAR,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  botonEstado,
  claseFila,
  confirmarCambioEstado,
  enfocar,
} from "../components/catalogo";

// Traduce el filtro visible a null (todos), true (activos) o false (inactivos).
function activoDesdeFiltro(filtro) {
  return filtro === "todos" ? null : filtro === "activos";
}

// Reutiliza la presentación sin compartir estado entre los dos catálogos.
function PanelCatalogo({ clave, titulo, singular, femenino, listar, crear, actualizar }) {
  // Filas mostradas y filtro elegido.
  const [filas, setFilas] = useState([]);
  const [filtro, setFiltro] = useState("todos");
  // Estados de carga y error del listado; recarga fuerza una nueva consulta.
  const [cargando, setCargando] = useState(true);
  const [errorListado, setErrorListado] = useState("");
  const [recarga, setRecarga] = useState(0);
  // Formulario: id null = alta; un id = edición.
  const [form, setForm] = useState({ id: null, nombre: "" });
  // Indicadores de escritura en curso y mensajes al usuario.
  const [guardando, setGuardando] = useState(false);
  const [cambiandoId, setCambiandoId] = useState(null);
  const [mensaje, setMensaje] = useState("");
  const [errorOperacion, setErrorOperacion] = useState("");
  // Evita dobles envíos mientras una escritura no termina.
  const escrituraEnCurso = useRef(false);
  // Campo del nombre, para llevar el foco ahí al pulsar "Editar".
  const campoNombre = useRef(null);

  // Carga el nombre de la fila en el formulario y lleva el foco al campo.
  function editar(fila) {
    setMensaje("");
    setErrorOperacion("");
    setForm({ id: fila.id, nombre: fila.nombre });
    enfocar(campoNombre);
  }

  // Carga el listado cada vez que cambia el filtro o se pide recargar.
  useEffect(() => {
    // Ignora respuestas de una carga anterior si el componente cambió.
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
    // Lanza la carga y marca la respuesta como obsoleta al limpiar el efecto.
    cargar();
    return () => { vigente = false; };
  }, [filtro, recarga, listar, titulo]);

  // Crea o renombra según el estado del formulario.
  async function guardar(event) {
    event.preventDefault();
    // No permite un segundo envío simultáneo.
    if (escrituraEnCurso.current) return;
    // Valida en pantalla lo mismo que exige la API (1 a 50 caracteres).
    const nombre = form.nombre.trim();
    setMensaje("");
    setErrorOperacion("");
    if (!nombre || nombre.length > 50) {
      setErrorOperacion("El nombre es obligatorio y admite hasta 50 caracteres.");
      return;
    }
    // Marca la escritura en curso y deshabilita el botón.
    escrituraEnCurso.current = true;
    setGuardando(true);
    // Llama a crear o actualizar y muestra el resultado.
    try {
      const resultado = form.id === null
        ? await crear(nombre)
        : await actualizar(form.id, { nombre });
      setMensaje(`${singular} «${resultado.nombre}» ${form.id === null ? (femenino ? "creada" : "creado") : (femenino ? "actualizada" : "actualizado")}.`);
      // Limpia el formulario y recarga la tabla.
      setForm({ id: null, nombre: "" });
      setRecarga((valor) => valor + 1);
    // Muestra 409 (nombre repetido) o 422 tal como los envía la API.
    } catch (error) {
      setErrorOperacion(extraerMensajeError(error, `No se pudo guardar ${singular.toLowerCase()}`));
    // Libera el formulario aunque haya error.
    } finally {
      escrituraEnCurso.current = false;
      setGuardando(false);
    }
  }

  // Activa o desactiva; no existe borrado.
  async function cambiarEstado(fila) {
    if (escrituraEnCurso.current) return;
    // Solo desactivar pide confirmación, igual que en Productores.
    if (!confirmarCambioEstado(fila.activo, `${singular.toLowerCase()} «${fila.nombre}»`)) return;
    escrituraEnCurso.current = true;
    setCambiandoId(fila.id);
    setMensaje("");
    setErrorOperacion("");
    // Envía solo el estado contrario al actual.
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

  // Panel: mensajes, formulario, filtro y tabla del catálogo.
  return (
    <section aria-labelledby={`titulo-${clave}`} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <h2 id={`titulo-${clave}`} className="text-xl font-semibold text-frigorifico-950">{titulo}</h2>
      {mensaje && <p role="status" className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{mensaje}</p>}
      {errorOperacion && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorOperacion}</p>}

      {/* Formulario de alta o edición. */}
      <form onSubmit={guardar} className="mt-5 rounded-xl bg-slate-50 p-4">
        <label htmlFor={`nombre-${clave}`} className="block text-sm font-semibold text-slate-700">{form.id === null ? `${femenino ? "Nueva" : "Nuevo"} ${singular.toLowerCase()}` : `Editar ${singular.toLowerCase()}`}</label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input ref={campoNombre} id={`nombre-${clave}`} type="text" required maxLength={50} value={form.nombre} onChange={(event) => setForm((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardando} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-100" />
          <button type="submit" disabled={guardando} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
          {form.id !== null && <button type="button" onClick={() => setForm({ id: null, nombre: "" })} disabled={guardando} className={BOTON_SECUNDARIO}>Cancelar</button>}
        </div>
      </form>

      {/* Filtro por estado y botón para recargar. */}
      <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
        <div className="w-full sm:w-auto">
          <label htmlFor={`filtro-${clave}`} className="mb-2 block text-sm font-semibold text-slate-700">Mostrar {titulo.toLowerCase()}</label>
          <select id={`filtro-${clave}`} value={filtro} onChange={(event) => setFiltro(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 sm:min-w-48">
            <option value="todos">Todos</option><option value="activos">Activos</option><option value="inactivos">Inactivos</option>
          </select>
        </div>
        <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando} className={BOTON_PRINCIPAL}>Recargar</button>
      </div>

      {/* Tabla con estados de carga, error y vacío. */}
      <div className="mt-6 min-w-0" aria-busy={cargando}>
        {cargando ? <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">Cargando {titulo.toLowerCase()}…</p>
          : errorListado ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700">{errorListado}</p>
            : filas.length === 0 ? <p role="status" className="rounded-xl bg-slate-50 p-5 text-slate-500">No hay registros con este filtro</p>
              : <div role="region" aria-label={`Listado de ${titulo.toLowerCase()}`} tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <caption className="sr-only">{titulo} según el filtro seleccionado</caption>
                  <thead className="border-b border-slate-200 bg-frigorifico-50 text-frigorifico-950"><tr><th scope="col" className="px-4 py-3">Nombre</th><th scope="col" className="px-4 py-3">Estado</th><th scope="col" className="px-4 py-3">Acciones</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">{filas.map((fila) => <tr key={fila.id} className={claseFila(form.id === fila.id)} aria-current={form.id === fila.id ? "true" : undefined}>
                    <td className="px-4 py-4 font-medium text-frigorifico-900">{fila.nombre}</td>
                    <td className="px-4 py-4"><span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${fila.activo ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-slate-100 text-slate-600 ring-slate-500/20"}`}>{fila.activo ? (femenino ? "Activa" : "Activo") : (femenino ? "Inactiva" : "Inactivo")}</span></td>
                    <td className="px-4 py-4"><div className="flex flex-wrap gap-2">
                      {/* aria-label nombra el registro: el lector de pantalla no dice solo "Editar". */}
                      <button type="button" onClick={() => editar(fila)} disabled={guardando || cambiandoId === fila.id} aria-label={`Editar ${fila.nombre}`} className={BOTON_EDITAR}>Editar</button>
                      <button type="button" onClick={() => cambiarEstado(fila)} disabled={guardando || cambiandoId === fila.id} aria-label={`${fila.activo ? "Desactivar" : "Activar"} ${fila.nombre}`} className={botonEstado(fila.activo)}>{cambiandoId === fila.id ? "Actualizando…" : fila.activo ? "Desactivar" : "Activar"}</button>
                    </div></td>
                  </tr>)}</tbody>
                </table>
              </div>}
      </div>
    </section>
  );
}

// Página: muestra los dos catálogos con estados independientes.
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
