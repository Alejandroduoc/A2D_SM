// Administra el estado de la consulta y su ciclo de vida dentro de la página.
import { useEffect, useRef, useState } from "react";
// Presenta los errores con los mismos mensajes usados por el resto del sistema.
import { extraerMensajeError } from "../api/client";
// Consulta la API administrativa mediante el cliente autenticado existente.
import { actualizarProductor, crearProductor, listarProductores } from "../api/productores";
// Presenta el RUT y anticipa errores sin sustituir los controles del servidor.
import { formatearRut, normalizarRut, validarRut } from "../utils/rut";

// Valores iniciales de los cuatro campos de negocio del formulario.
const FORM_VACIO = { rut: "", razon_social: "", direccion: "", telefono: "" };

// Distingue un rechazo conocido de una escritura cuyo resultado quedó incierto.
function mensajeDeEscritura(error, mensajePorDefecto) {
  // Mantiene los mensajes de validación y conflicto entregados por el servidor.
  const mensaje = extraerMensajeError(error, mensajePorDefecto);
  // Un fallo de red o del servidor puede ocurrir después de confirmar la escritura.
  if (!error.response || error.response.status >= 500) {
    return `${mensaje} No se pudo confirmar si la operación se guardó. Comprueba la lista antes de repetirla.`;
  }
  // Los rechazos controlados conservan su mensaje sin simular un éxito.
  return mensaje;
}

// Mantiene productores y su estado mediante las operaciones auditadas del backend.
export default function Productores() {
  // Conserva únicamente las filas de la última consulta vigente.
  const [productores, setProductores] = useState([]);
  // Distingue todos los registros de los filtros booleanos de la API.
  const [filtro, setFiltro] = useState("todos");
  // Evita mostrar un estado vacío mientras se obtiene la primera respuesta.
  const [cargando, setCargando] = useState(true);
  // Separa los fallos de consulta de un resultado válido sin filas.
  const [error, setError] = useState("");
  // Permite repetir la consulta aunque el filtro no haya cambiado.
  const [recarga, setRecarga] = useState(0);
  // null cierra el panel; un objeto vacío representa alta y un id representa edición.
  const [editando, setEditando] = useState(null);
  // Mantiene los textos escritos aunque la API rechace el formulario.
  const [form, setForm] = useState({ ...FORM_VACIO });
  // Separa los errores de escritura de los errores del listado.
  const [errorForm, setErrorForm] = useState("");
  // Muestra el aviso del RUT después de salir del campo, sin ventanas emergentes.
  const [rutRevisado, setRutRevisado] = useState(false);
  const rutValido = validarRut(form.rut);
  const errorRut = rutRevisado && !rutValido
    ? "El RUT ingresado es incorrecto. Revisa el número y su dígito verificador."
    : "";
  // Bloquea el formulario mientras se confirma su operación.
  const [guardando, setGuardando] = useState(false);
  // Identifica la acción de estado en curso para mostrar su progreso en la fila.
  const [cambiandoEstadoId, setCambiandoEstadoId] = useState(null);
  // Conserva el éxito de una escritura aunque falle la recarga posterior.
  const [mensajeExito, setMensajeExito] = useState("");
  // Presenta los errores de activación y desactivación fuera del formulario.
  const [errorOperacion, setErrorOperacion] = useState("");
  // Cierra la ventana entre dos eventos rápidos antes de que React actualice el estado.
  const escrituraEnCurso = useRef(false);
  // Comparte el bloqueo visual de todas las acciones de escritura.
  const ocupado = guardando || cambiandoEstadoId !== null;

  // Consulta al entrar, cambiar el estado seleccionado o pulsar Recargar.
  useEffect(() => {
    // Cada ejecución tiene su propia vigencia para descartar respuestas anteriores.
    let vigente = true;

    // Mantiene el efecto síncrono y concentra aquí la operación asíncrona.
    async function cargarProductores() {
      // Retira el resultado anterior antes de mostrar datos bajo otro filtro.
      setCargando(true);
      // Una consulta nueva permite recuperar la pantalla después de un error.
      setError("");
      // No conserva filas de la selección anterior mientras llega la respuesta.
      setProductores([]);
      // Traduce el selector a null, true o false sin perder el filtro de inactivos.
      const activo = filtro === "todos" ? null : filtro === "activos";

      try {
        // Obtiene los datos en el orden que entrega el servidor.
        const filas = await listarProductores(activo);
        // Una respuesta lenta anterior no puede reemplazar la selección vigente.
        if (vigente) setProductores(filas);
      } catch (errorRecibido) {
        // Ignora también los errores de consultas que ya no corresponden a la página.
        if (vigente) {
          setError(extraerMensajeError(errorRecibido, "No se pudo cargar la lista de productores"));
        }
      } finally {
        // Una consulta anterior no puede terminar la carga de otra más reciente.
        if (vigente) setCargando(false);
      }
    }

    // Inicia la lectura sin desactivar StrictMode ni agregar escrituras.
    cargarProductores();
    // Descarta actualizaciones tras cambiar de filtro o desmontar la página.
    return () => { vigente = false; };
  }, [filtro, recarga]);

  // Abre un formulario limpio o copia una fila sin modificar el objeto recibido.
  function abrirFormulario(productor = null) {
    // No cambia el contexto de una operación que sigue pendiente.
    if (escrituraEnCurso.current) return;
    setEditando(productor ? { ...productor } : {});
    // Los contactos nulos se representan como texto vacío únicamente en los inputs.
    setForm(productor ? {
      rut: formatearRut(productor.rut),
      razon_social: productor.razon_social,
      direccion: productor.direccion ?? "",
      telefono: productor.telefono ?? "",
    } : { ...FORM_VACIO });
    // Una apertura nueva no arrastra errores ni mensajes de otra operación.
    setErrorForm("");
    setRutRevisado(false);
    setErrorOperacion("");
    setMensajeExito("");
  }

  // Cancelar solo cierra el panel cuando no existe una escritura pendiente.
  function cerrarFormulario() {
    if (escrituraEnCurso.current) return;
    setEditando(null);
    setForm({ ...FORM_VACIO });
    setErrorForm("");
    setRutRevisado(false);
  }

  // Actualiza un campo sin mutar el formulario ni el productor original.
  function cambiarCampo(event) {
    const { name, value } = event.target;
    setForm((anterior) => ({ ...anterior, [name]: value }));
  }

  // Formatea al terminar de escribir para conservar el cursor durante la edición.
  function revisarRut() {
    setRutRevisado(true);
    setForm((anterior) => ({ ...anterior, rut: formatearRut(anterior.rut) }));
  }

  // Guarda solo los campos permitidos y mantiene separados escritura y recarga.
  async function guardar(event) {
    event.preventDefault();
    // La referencia impide dos solicitudes incluso dentro del mismo ciclo de eventos.
    if (escrituraEnCurso.current || editando === null) return;
    setErrorForm("");
    setRutRevisado(true);
    // Protege también envíos por teclado o disparados directamente sobre el formulario.
    if (!rutValido) return;
    // Prepara únicamente espacios exteriores; no altera símbolos ni capitalización.
    const datos = Object.fromEntries(Object.entries(form).map(([campo, valor]) => [campo, valor.trim()]));
    // Envía el formato canónico; los puntos pertenecen a la presentación.
    datos.rut = normalizarRut(datos.rut);
    // Complementa las restricciones HTML sin limitar el RUT presentado.
    if (!datos.rut || datos.razon_social.length < 3 || datos.razon_social.length > 150) {
      setErrorForm("Completa el RUT y una razón social de 3 a 150 caracteres.");
      return;
    }
    if (datos.direccion.length > 200 || datos.telefono.length > 20) {
      setErrorForm("La dirección admite hasta 200 caracteres y el teléfono hasta 20.");
      return;
    }
    const esEdicion = editando.id !== undefined;
    // El alta envía contactos vacíos como null, sin id ni estado.
    const cuerpo = esEdicion ? {} : { ...datos, direccion: datos.direccion || null, telefono: datos.telefono || null };
    if (esEdicion) {
      for (const campo of Object.keys(FORM_VACIO)) {
        // Compara la misma preparación textual aplicada al nuevo valor.
        const anterior = campo === "rut" ? normalizarRut(editando.rut) : (editando[campo] ?? "").trim();
        // Este formulario permite reemplazar contactos, pero aún no quitarlos.
        if ((campo === "direccion" || campo === "telefono") && anterior && !datos[campo]) {
          const etiqueta = campo === "direccion" ? "la dirección" : "el teléfono";
          const accion = campo === "direccion" ? "quitarla" : "quitarlo";
          setErrorForm(`Este formulario permite reemplazar ${etiqueta}, pero todavía no ${accion}.`);
          return;
        }
        // No envía campos idénticos, incluidos contactos originalmente nulos o vacíos.
        if (datos[campo] !== anterior) cuerpo[campo] = datos[campo];
      }
      // Una edición sin diferencias cierra sin PUT ni evento de auditoría.
      if (Object.keys(cuerpo).length === 0) {
        cerrarFormulario();
        setMensajeExito("No había cambios para guardar.");
        return;
      }
    }
    escrituraEnCurso.current = true;
    setGuardando(true);
    setMensajeExito("");
    setErrorOperacion("");
    try {
      // El servidor identifica al actor, normaliza el RUT y confirma su auditoría.
      const resultado = esEdicion
        ? await actualizarProductor(editando.id, cuerpo)
        : await crearProductor(cuerpo);
      // El éxito pertenece a la escritura, no al resultado de la consulta posterior.
      setMensajeExito(esEdicion
        ? `Datos de «${resultado.razon_social}» guardados.`
        : `Productor «${resultado.razon_social}» creado como activo.${filtro === "inactivos" ? " El filtro Inactivos se mantiene; puedes verlo en Activos o Todos." : ""}`);
      setEditando(null);
      setForm({ ...FORM_VACIO });
      // Conserva el filtro y delega cualquier error de recarga al efecto del listado.
      setRecarga((anterior) => anterior + 1);
    } catch (errorRecibido) {
      // Mantiene el panel y todos los valores escritos para corregir o comprobar el resultado.
      setErrorForm(mensajeDeEscritura(errorRecibido, "No se pudo guardar el productor"));
    } finally {
      escrituraEnCurso.current = false;
      setGuardando(false);
    }
  }

  // Cambia únicamente activo y deja que el backend genere el evento UPDATE.
  async function cambiarEstado(productor) {
    // No combina una acción de estado con un formulario abierto ni otra escritura.
    if (escrituraEnCurso.current || editando !== null) return;
    if (productor.activo && !window.confirm(`¿Desactivar a «${productor.razon_social}»? Se conservarán sus datos y su historial.`)) return;
    escrituraEnCurso.current = true;
    setCambiandoEstadoId(productor.id);
    setMensajeExito("");
    setErrorOperacion("");
    try {
      // Usa el id estable; no agrega auditoría, actor ni estados previos al cuerpo.
      const resultado = await actualizarProductor(productor.id, { activo: !productor.activo });
      setMensajeExito(`Productor «${resultado.razon_social}» ${resultado.activo ? "activado" : "desactivado"}.`);
      // La recarga hace desaparecer la fila si dejó de corresponder al filtro actual.
      setRecarga((anterior) => anterior + 1);
    } catch (errorRecibido) {
      // No modifica la etiqueta ni retira la fila antes de recibir éxito del servidor.
      setErrorOperacion(mensajeDeEscritura(errorRecibido, "No se pudo cambiar el estado del productor"));
    } finally {
      escrituraEnCurso.current = false;
      setCambiandoEstadoId(null);
    }
  }

  // Utiliza el espacio y la navegación del layout compartido.
  return (
    <section aria-labelledby="titulo-productores" className="min-w-0">
      {/* Conserva la presentación del mantenimiento y su identidad dentro del menú. */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 id="titulo-productores" className="text-3xl font-semibold text-frigorifico-950">Productores</h1>
          <p className="mt-2 text-slate-500">Gestión de los datos y el estado de los productores de la planta.</p>
        </div>
        <button type="button" onClick={() => abrirFormulario()} disabled={ocupado || editando !== null} className="rounded-lg bg-frigorifico-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">Nuevo productor</button>
      </div>

      {/* La confirmación de escritura permanece visible aunque falle el listado. */}
      {mensajeExito && <p id="mensaje-productores" role="status" className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{mensajeExito}</p>}
      {/* Los errores de estado no se confunden con los del formulario o la consulta. */}
      {errorOperacion && <p id="error-operacion-productor" role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{errorOperacion}</p>}

      {/* El panel de datos no repite el layout y conserva el registro original al editar. */}
      {editando !== null && (
        <form onSubmit={guardar} aria-labelledby="titulo-form-productor" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <h2 id="titulo-form-productor" className="text-xl font-semibold text-frigorifico-950">{editando.id !== undefined ? "Editar productor" : "Nuevo productor"}</h2>
          {errorForm && <p id="error-form-productor" role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{errorForm}</p>}
          {/* El bloqueo nativo incluye inputs, Guardar y Cancelar durante la escritura. */}
          <fieldset disabled={ocupado} className="mt-5 grid min-w-0 gap-5 sm:grid-cols-2">
            <div className="min-w-0">
              <label htmlFor="productor-rut" className="mb-2 block text-sm font-semibold text-slate-700">RUT</label>
              <input id="productor-rut" name="rut" type="text" value={form.rut} onChange={cambiarCampo} onBlur={revisarRut} onInvalid={(event) => { event.preventDefault(); setRutRevisado(true); }} required autoFocus aria-invalid={Boolean(errorRut)} aria-describedby={`ayuda-rut-productor${errorRut ? " error-rut-productor" : ""}`} className={`w-full rounded-lg border px-4 py-2 outline-none focus:ring-4 disabled:bg-slate-50 ${errorRut ? "border-red-500 focus:border-red-500 focus:ring-red-100" : "border-slate-300 focus:border-frigorifico-700 focus:ring-frigorifico-100"}`} />
              <p id="ayuda-rut-productor" className="mt-2 text-xs leading-5 text-slate-500">Puedes escribirlo con o sin puntos y guion. Al salir se mostrará como 12.345.678-5.</p>
              {errorRut && <p id="error-rut-productor" role="alert" className="mt-2 text-sm text-red-700">{errorRut}</p>}
            </div>
            <div className="min-w-0">
              <label htmlFor="productor-razon-social" className="mb-2 block text-sm font-semibold text-slate-700">Razón social</label>
              <input id="productor-razon-social" name="razon_social" type="text" value={form.razon_social} onChange={cambiarCampo} required minLength={3} maxLength={150} className="w-full rounded-lg border border-slate-300 px-4 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-50" />
            </div>
            <div className="min-w-0">
              <label htmlFor="productor-direccion" className="mb-2 block text-sm font-semibold text-slate-700">Dirección <span className="font-normal text-slate-500">(opcional)</span></label>
              <input id="productor-direccion" name="direccion" type="text" value={form.direccion} onChange={cambiarCampo} maxLength={200} className="w-full rounded-lg border border-slate-300 px-4 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-50" />
              {editando.direccion?.trim() && <p className="mt-2 text-xs leading-5 text-slate-500">Puedes reemplazar la dirección, pero todavía no quitarla.</p>}
            </div>
            <div className="min-w-0">
              <label htmlFor="productor-telefono" className="mb-2 block text-sm font-semibold text-slate-700">Teléfono <span className="font-normal text-slate-500">(opcional)</span></label>
              <input id="productor-telefono" name="telefono" type="tel" value={form.telefono} onChange={cambiarCampo} maxLength={20} className="w-full rounded-lg border border-slate-300 px-4 py-2 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 disabled:bg-slate-50" />
              {editando.telefono?.trim() && <p className="mt-2 text-xs leading-5 text-slate-500">Puedes reemplazar el teléfono, pero todavía no quitarlo.</p>}
            </div>
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <button type="submit" disabled={!rutValido} className="rounded-lg bg-frigorifico-900 px-5 py-2 text-sm font-semibold text-white hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">{guardando ? "Guardando…" : "Guardar"}</button>
              <button type="button" onClick={cerrarFormulario} className="rounded-lg border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">Cancelar</button>
            </div>
          </fieldset>
        </form>
      )}

      {/* Mantiene los controles utilizables en escritorio y en pantallas pequeñas. */}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5">
        <div className="w-full sm:w-auto">
          {/* La etiqueta visible identifica el selector también para lectores de pantalla. */}
          <label htmlFor="filtro-productores" className="mb-2 block text-sm font-semibold text-slate-700">Mostrar productores</label>
          <select
            id="filtro-productores"
            value={filtro}
            disabled={ocupado}
            onChange={(event) => setFiltro(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 outline-none focus:border-frigorifico-700 focus:ring-4 focus:ring-frigorifico-100 sm:min-w-48"
          >
            <option value="todos">Todos</option>
            <option value="activos">Activos</option>
            <option value="inactivos">Inactivos</option>
          </select>
        </div>
        {/* Conserva el filtro al recargar; el selector sigue habilitado durante la carga. */}
        <button
          type="button"
          onClick={() => setRecarga((anterior) => anterior + 1)}
          disabled={cargando || ocupado}
          className="rounded-lg bg-frigorifico-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Recargar
        </button>
      </div>

      {/* Los estados de consulta son excluyentes y anuncian cuándo se están cargando resultados. */}
      <div className="mt-6 min-w-0" aria-busy={cargando}>
        {cargando ? (
          <p role="status" className="rounded-2xl border border-slate-200 bg-white p-6 text-slate-500">Cargando productores…</p>
        ) : error ? (
          <p id="error-listado-productores" role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700">{error}</p>
        ) : productores.length === 0 ? (
          <p role="status" className="rounded-2xl border border-slate-200 bg-white p-6 text-slate-500">No hay productores con este filtro</p>
        ) : (
          // El desplazamiento de una tabla ancha queda dentro de su propio contenedor.
          <div role="region" aria-label="Listado de productores" tabIndex={0} className="overflow-x-auto rounded-2xl border border-slate-200 bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700">
            <table className="w-full min-w-[960px] text-left text-sm">
              <caption className="sr-only">Listado de productores según el filtro seleccionado</caption>
              <thead className="border-b border-slate-200 bg-frigorifico-50 text-frigorifico-950">
                <tr>
                  <th scope="col" className="px-5 py-4 font-semibold">RUT</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Razón social</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Dirección</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Teléfono</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Estado</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {/* Usa el id estable y conserva los textos recibidos sin interpretar HTML. */}
                {productores.map((productor) => (
                  <tr key={productor.id} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-5 py-4 font-medium text-frigorifico-900">{formatearRut(productor.rut)}</td>
                    <td className="px-5 py-4 text-slate-800">{productor.razon_social}</td>
                    <td className="px-5 py-4 text-slate-600">{productor.direccion || "—"}</td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">{productor.telefono || "—"}</td>
                    <td className="px-5 py-4">
                      {/* El texto distingue el estado además del color de su etiqueta. */}
                      <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${productor.activo ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-slate-100 text-slate-600 ring-slate-500/20"}`}>
                        {productor.activo ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      {/* Impide cambiar de registro o de estado mientras el panel está abierto. */}
                      <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={() => abrirFormulario(productor)} disabled={ocupado || editando !== null} aria-label={`Editar ${productor.razon_social}`} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-frigorifico-900 hover:bg-frigorifico-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50">Editar</button>
                        <button type="button" onClick={() => cambiarEstado(productor)} disabled={ocupado || editando !== null} aria-label={`${productor.activo ? "Desactivar" : "Activar"} ${productor.razon_social}`} className={`rounded-lg border px-3 py-2 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-frigorifico-700 disabled:cursor-not-allowed disabled:opacity-50 ${productor.activo ? "border-amber-300 text-amber-900 hover:bg-amber-50" : "border-emerald-300 text-emerald-800 hover:bg-emerald-50"}`}>
                          {cambiandoEstadoId === productor.id ? "Actualizando…" : productor.activo ? "Desactivar" : "Activar"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
