// Administra el estado de la consulta y su ciclo de vida dentro de la página.
import { useEffect, useRef, useState } from "react";
// Presenta los errores con los mismos mensajes usados por el resto del sistema.
import { extraerMensajeError } from "../api/client";
// Consulta la API administrativa mediante el cliente autenticado existente.
import { actualizarProductor, crearProductor, listarProductores } from "../api/productores";
// Presenta el RUT y anticipa errores sin sustituir los controles del servidor.
import { formatearRut, normalizarRut, validarRut } from "../utils/rut";
// Estilos compartidos con los demás mantenedores.
import {
  AYUDA,
  BOTON_EDITAR,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  botonEstado,
  CAMPO,
  CAMPO_ERROR,
  CELDA,
  CELDA_AVISO,
  claseEstado,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  ETIQUETA,
  MENSAJE_ERROR,
  MENSAJE_EXITO,
  SELECTOR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";

// Valores iniciales de los cuatro campos de negocio del formulario.
const FORM_VACIO = { rut: "", razon_social: "", direccion: "", telefono: "" };

// Quita tildes y mayúsculas para que "agricola" encuentre "Agrícola".
function sinTildes(texto) {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// Indica si un productor coincide con la búsqueda por razón social o por RUT.
function coincide(productor, busqueda) {
  const termino = sinTildes(busqueda.trim());
  // Sin texto de búsqueda se muestran todos.
  if (!termino) return true;
  // El RUT se compara sin puntos ni guion: "12.345" encuentra "12345678-5".
  const rutBuscado = termino.replace(/[^0-9k]/g, "");
  const rutProductor = productor.rut.toLowerCase().replace(/[^0-9k]/g, "");
  return sinTildes(productor.razon_social).includes(termino) || (rutBuscado !== "" && rutProductor.includes(rutBuscado));
}

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
  // Texto del buscador; filtra en el navegador la lista ya cargada.
  const [busqueda, setBusqueda] = useState("");
  const visibles = productores.filter((productor) => coincide(productor, busqueda));

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
        // No envía campos idénticos. Un contacto borrado viaja como "" y la API lo
        // guarda como NULL (decisión D3 del 2026-10-31).
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
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E2 · Maestros</p>
          <h1 id="titulo-productores" className="text-2xl font-bold text-frigorifico-900">Productores</h1>
          <p className="mt-2 text-sm text-slate-500">Gestión de los datos y el estado de los productores de la planta.</p>
        </div>
        <button type="button" onClick={() => abrirFormulario()} disabled={ocupado || editando !== null} className={BOTON_PRINCIPAL}>Nuevo productor</button>
      </div>

      {/* La confirmación de escritura permanece visible aunque falle el listado. */}
      {mensajeExito && <p id="mensaje-productores" role="status" className={`mt-6 ${MENSAJE_EXITO}`}>{mensajeExito}</p>}
      {/* Los errores de estado no se confunden con los del formulario o la consulta. */}
      {errorOperacion && <p id="error-operacion-productor" role="alert" className={`mt-6 ${MENSAJE_ERROR}`}>{errorOperacion}</p>}

      {/* Tarjeta del formulario: campos en grilla y botones debajo; conserva el registro original al editar. */}
      {editando !== null && (
        <form onSubmit={guardar} aria-labelledby="titulo-form-productor" className={`mt-6 ${TARJETA}`}>
          <h2 id="titulo-form-productor" className={`mb-3 ${SUBTITULO}`}>{editando.id !== undefined ? "Editar productor" : "Nuevo productor"}</h2>
          {errorForm && <p id="error-form-productor" role="alert" className={`mb-3 ${MENSAJE_ERROR}`}>{errorForm}</p>}
          {/* El bloqueo nativo incluye inputs, Guardar y Cancelar durante la escritura. */}
          <fieldset disabled={ocupado} className="min-w-0">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="min-w-0">
                <label htmlFor="productor-rut" className={ETIQUETA}>RUT</label>
                {/* Con un RUT inválido el campo cambia a borde rojo, con el mismo tamaño. */}
                <input id="productor-rut" name="rut" type="text" value={form.rut} onChange={cambiarCampo} onBlur={revisarRut} onInvalid={(event) => { event.preventDefault(); setRutRevisado(true); }} required autoFocus aria-invalid={Boolean(errorRut)} aria-describedby={`ayuda-rut-productor${errorRut ? " error-rut-productor" : ""}`} className={errorRut ? CAMPO_ERROR : CAMPO} />
                <p id="ayuda-rut-productor" className={AYUDA}>Puedes escribirlo con o sin puntos y guion. Al salir se mostrará como 12.345.678-5.</p>
                {errorRut && <p id="error-rut-productor" role="alert" className="mt-1 text-xs text-red-700">{errorRut}</p>}
              </div>
              <div className="min-w-0">
                <label htmlFor="productor-razon-social" className={ETIQUETA}>Razón social</label>
                <input id="productor-razon-social" name="razon_social" type="text" value={form.razon_social} onChange={cambiarCampo} required minLength={3} maxLength={150} className={CAMPO} />
              </div>
              <div className="min-w-0">
                <label htmlFor="productor-direccion" className={ETIQUETA}>Dirección <span className="font-normal text-slate-500">(opcional)</span></label>
                <input id="productor-direccion" name="direccion" type="text" value={form.direccion} onChange={cambiarCampo} maxLength={200} className={CAMPO} />
              </div>
              <div className="min-w-0">
                <label htmlFor="productor-telefono" className={ETIQUETA}>Teléfono <span className="font-normal text-slate-500">(opcional)</span></label>
                <input id="productor-telefono" name="telefono" type="tel" value={form.telefono} onChange={cambiarCampo} maxLength={20} className={CAMPO} />
              </div>
            </div>
            {/* Botones debajo de los campos, como en la referencia. */}
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="submit" disabled={!rutValido} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
              <button type="button" onClick={cerrarFormulario} className={BOTON_SECUNDARIO}>Cancelar</button>
            </div>
          </fieldset>
        </form>
      )}

      {/* Encabezado del listado: subtítulo a la izquierda; filtro, búsqueda y recarga a la derecha. */}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className={SUBTITULO}>Registrados</h2>
        <div className="flex w-full flex-wrap items-end gap-3 sm:w-auto">
          <div className="w-full sm:w-40">
            {/* La etiqueta visible identifica el selector también para lectores de pantalla. */}
            <label htmlFor="filtro-productores" className={ETIQUETA}>Mostrar</label>
            <select id="filtro-productores" value={filtro} disabled={ocupado} onChange={(event) => setFiltro(event.target.value)} className={SELECTOR}>
              <option value="todos">Todos</option>
              <option value="activos">Activos</option>
              <option value="inactivos">Inactivos</option>
            </select>
          </div>
          {/* Busca por razón social (sin importar tildes) o por parte del RUT. */}
          <div className="w-full sm:w-56">
            <label htmlFor="buscar-productores" className={ETIQUETA}>Buscar</label>
            <input id="buscar-productores" type="search" value={busqueda} onChange={(event) => setBusqueda(event.target.value)} placeholder="Razón social o RUT" className={CAMPO} />
          </div>
          {/* Conserva el filtro al recargar; el selector sigue habilitado durante la carga. */}
          <button type="button" onClick={() => setRecarga((anterior) => anterior + 1)} disabled={cargando || ocupado} className={BOTON_PRINCIPAL}>Recargar</button>
        </div>
      </div>

      {/* El error de consulta se muestra como mensaje; la tabla queda con su aviso. */}
      {error && <p id="error-listado-productores" role="alert" className={`mt-4 ${MENSAJE_ERROR}`}>{error}</p>}
      {/* Sin ancho mínimo: si la tabla no cabe, el desplazamiento queda dentro de su contenedor. */}
      <div role="region" aria-label="Listado de productores" aria-busy={cargando} tabIndex={0} className={`mt-4 ${CONTENEDOR_TABLA}`}>
        <table className="w-full text-sm">
          <caption className="sr-only">Listado de productores según el filtro seleccionado</caption>
          <thead className={ENCABEZADO_TABLA}>
            <tr>
              <th scope="col" className={CELDA}>RUT</th>
              <th scope="col" className={CELDA}>Razón social</th>
              <th scope="col" className={CELDA}>Dirección</th>
              <th scope="col" className={CELDA}>Teléfono</th>
              <th scope="col" className={CELDA}>Estado</th>
              <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {/* Cargando, error, vacío y búsqueda sin resultados son una fila dentro de la tabla. */}
            {cargando ? <tr><td colSpan={6} className={CELDA_AVISO}>Cargando…</td></tr>
              : error ? <tr><td colSpan={6} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                : productores.length === 0 ? <tr><td colSpan={6} className={CELDA_AVISO}>Sin productores con este filtro.</td></tr>
                  : visibles.length === 0 ? <tr><td colSpan={6} className={CELDA_AVISO}>Ningún productor coincide con «{busqueda.trim()}».</td></tr>
                    // Usa el id estable y conserva los textos recibidos sin interpretar HTML.
                    : visibles.map((productor) => (
                      <tr key={productor.id} className="hover:bg-slate-50">
                        <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{formatearRut(productor.rut)}</td>
                        <td className={`${CELDA} text-slate-600`}>{productor.razon_social}</td>
                        <td className={`${CELDA} text-slate-600`}>{productor.direccion || "—"}</td>
                        <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{productor.telefono || "—"}</td>
                        <td className={CELDA}>
                          {/* El texto distingue el estado además del color de su etiqueta. */}
                          <span className={claseEstado(productor.activo)}>
                            {productor.activo ? "Activo" : "Inactivo"}
                          </span>
                        </td>
                        <td className={`${CELDA} text-right`}>
                          {/* Impide cambiar de registro o de estado mientras el panel está abierto. */}
                          <div className="flex flex-wrap justify-end gap-3">
                            <button type="button" onClick={() => abrirFormulario(productor)} disabled={ocupado || editando !== null} aria-label={`Editar ${productor.razon_social}`} className={BOTON_EDITAR}>Editar</button>
                            <button type="button" onClick={() => cambiarEstado(productor)} disabled={ocupado || editando !== null} aria-label={`${productor.activo ? "Desactivar" : "Activar"} ${productor.razon_social}`} className={botonEstado(productor.activo)}>
                              {cambiandoEstadoId === productor.id ? "Actualizando…" : productor.activo ? "Desactivar" : "Activar"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
