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

  // Panel apilado como en la referencia: mensajes, formulario, encabezado del listado y tabla.
  return (
    <section aria-labelledby={`titulo-${clave}`} className="min-w-0 space-y-4">
      <h2 id={`titulo-${clave}`} className="text-lg font-bold text-frigorifico-900">{titulo}</h2>
      {mensaje && <p role="status" className={MENSAJE_EXITO}>{mensaje}</p>}
      {errorOperacion && <p role="alert" className={MENSAJE_ERROR}>{errorOperacion}</p>}

      {/* Tarjeta del formulario: campos en grilla y botones debajo. */}
      <form onSubmit={guardar} className={TARJETA}>
        <h3 className={`mb-3 ${SUBTITULO}`}>{form.id === null ? `${femenino ? "Nueva" : "Nuevo"} ${singular.toLowerCase()}` : `Editar ${singular.toLowerCase()}`}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor={`nombre-${clave}`} className={ETIQUETA}>Nombre</label>
            <input ref={campoNombre} id={`nombre-${clave}`} type="text" required maxLength={50} value={form.nombre} onChange={(event) => setForm((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardando} className={CAMPO} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="submit" disabled={guardando} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
          {form.id !== null && <button type="button" onClick={() => setForm({ id: null, nombre: "" })} disabled={guardando} className={BOTON_SECUNDARIO}>Cancelar</button>}
        </div>
      </form>

      {/* Encabezado del listado: subtítulo a la izquierda; filtro y recarga a la derecha. */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h3 className={SUBTITULO}>{femenino ? "Registradas" : "Registrados"}</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full sm:w-48">
            <label htmlFor={`filtro-${clave}`} className={ETIQUETA}>Mostrar</label>
            <select id={`filtro-${clave}`} value={filtro} onChange={(event) => setFiltro(event.target.value)} className={SELECTOR}>
              <option value="todos">Todos</option><option value="activos">Activos</option><option value="inactivos">Inactivos</option>
            </select>
          </div>
          <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando} className={BOTON_PRINCIPAL}>Recargar</button>
        </div>
      </div>

      {/* El error de consulta se muestra como mensaje; la tabla queda con su aviso. */}
      {errorListado && <p role="alert" className={MENSAJE_ERROR}>{errorListado}</p>}
      <div role="region" aria-label={`Listado de ${titulo.toLowerCase()}`} aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
        <table className="w-full text-sm">
          <caption className="sr-only">{titulo} según el filtro seleccionado</caption>
          <thead className={ENCABEZADO_TABLA}><tr><th scope="col" className={CELDA}>Nombre</th><th scope="col" className={CELDA}>Estado</th><th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {/* Cargando, error y vacío son una fila dentro de la tabla, como en la referencia. */}
            {cargando ? <tr><td colSpan={3} className={CELDA_AVISO}>Cargando…</td></tr>
              : errorListado ? <tr><td colSpan={3} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                : filas.length === 0 ? <tr><td colSpan={3} className={CELDA_AVISO}>Sin registros con este filtro.</td></tr>
                  : filas.map((fila) => <tr key={fila.id} className={claseFila(form.id === fila.id)} aria-current={form.id === fila.id ? "true" : undefined}>
                    <td className={`${CELDA} text-slate-600`}>{fila.nombre}</td>
                    <td className={CELDA}><span className={claseEstado(fila.activo)}>{fila.activo ? (femenino ? "Activa" : "Activo") : (femenino ? "Inactiva" : "Inactivo")}</span></td>
                    <td className={`${CELDA} text-right`}><div className="flex flex-wrap justify-end gap-3">
                      {/* aria-label nombra el registro: el lector de pantalla no dice solo "Editar". */}
                      <button type="button" onClick={() => editar(fila)} disabled={guardando || cambiandoId === fila.id} aria-label={`Editar ${fila.nombre}`} className={BOTON_EDITAR}>Editar</button>
                      <button type="button" onClick={() => cambiarEstado(fila)} disabled={guardando || cambiandoId === fila.id} aria-label={`${fila.activo ? "Desactivar" : "Activar"} ${fila.nombre}`} className={botonEstado(fila.activo)}>{cambiandoId === fila.id ? "Actualizando…" : fila.activo ? "Desactivar" : "Activar"}</button>
                    </div></td>
                  </tr>)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// Página: muestra los dos catálogos con estados independientes.
export default function CalidadesSistemasProductivos() {
  return (
    <section aria-labelledby="titulo-calidades-sistemas" className="min-w-0">
      {/* Se muestra dentro de la pestaña de Mantenedores: el título visible es el de la pestaña. */}
      <h2 id="titulo-calidades-sistemas" className="sr-only">Calidades y sistemas productivos</h2>
      <p className="text-sm text-slate-500">Catálogos de clasificación de la fruta y de forma de producción.</p>
      {/* Calidades y Sistemas productivos apilados en una columna, como los mantenedores del proyecto de referencia. */}
      <div className="mt-6 min-w-0 space-y-10">
        <PanelCatalogo clave="calidades" titulo="Calidades" singular="Calidad" femenino listar={listarCalidades} crear={crearCalidad} actualizar={actualizarCalidad} />
        <PanelCatalogo clave="sistemas-productivos" titulo="Sistemas productivos" singular="Sistema productivo" femenino={false} listar={listarSistemasProductivos} crear={crearSistemaProductivo} actualizar={actualizarSistemaProductivo} />
      </div>
    </section>
  );
}
