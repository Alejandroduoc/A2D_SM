// Mantiene dos catálogos de peso con ciclos de consulta y escritura independientes.
import { useEffect, useRef, useState } from "react";
// Convierte errores de FastAPI en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Operaciones del catálogo de embalajes.
import { actualizarEmbalaje, crearEmbalaje, listarEmbalajes } from "../api/embalajes";
// Operaciones del catálogo de bandejas.
import { actualizarTipoBandeja, crearTipoBandeja, listarTiposBandeja } from "../api/tiposBandeja";
// Reutiliza los patrones visuales y accesibles de los demás mantenedores.
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

// Estado inicial común de los formularios de peso.
const FORMULARIO_VACIO = { id: null, nombre: "", peso: "", granel: false };

// Traduce el filtro visible al valor esperado por la API.
function activoDesdeFiltro(filtro) {
  // Todos omite el parámetro; los otros valores se convierten en booleano.
  return filtro === "todos" ? null : filtro === "activos";
}

// Valida un decimal positivo con hasta dos posiciones y límite de enteros.
function validarPeso(valor, maximoEnteros) {
  // Admite coma para facilitar digitación local y la normaliza antes de enviar.
  const normalizado = valor.trim().replace(",", ".");
  // Exige al menos un dígito y no más de dos decimales.
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalizado)) return null;
  // Separa la parte entera para aplicar el mismo rango del schema backend.
  const [enteros] = normalizado.split(".");
  // Rechaza números que excedan la precisión configurada.
  if (enteros.length > maximoEnteros) return null;
  // Exige un valor estrictamente mayor que cero.
  if (Number(normalizado) <= 0) return null;
  // Devuelve un texto decimal compatible con Pydantic y sin pérdida binaria.
  return normalizado;
}

// Presenta un peso con dos decimales y unidad kg.
function mostrarPeso(valor) {
  // Number se usa sólo para presentación; la API conserva Decimal.
  return `${Number(valor).toFixed(2)} kg`;
}

// Panel reutilizable para bandejas y embalajes, sin compartir sus estados.
function PanelPeso({
  clave,
  titulo,
  singular,
  femenino,
  campoPeso,
  etiquetaPeso,
  ayudaPeso,
  maximoEnteros,
  permiteGranel,
  listar,
  crear,
  actualizar,
}) {
  // Filas, filtro y contador utilizado para recargar.
  const [filas, setFilas] = useState([]);
  const [filtro, setFiltro] = useState("todos");
  const [recarga, setRecarga] = useState(0);
  // Estados de lectura del listado.
  const [cargando, setCargando] = useState(true);
  const [errorListado, setErrorListado] = useState("");
  // Estado del formulario de alta o edición.
  const [form, setForm] = useState(FORMULARIO_VACIO);
  const [errorPeso, setErrorPeso] = useState("");
  // Estados de escritura y mensajes visibles.
  const [guardando, setGuardando] = useState(false);
  const [cambiandoId, setCambiandoId] = useState(null);
  const [mensaje, setMensaje] = useState("");
  const [errorOperacion, setErrorOperacion] = useState("");
  // Impide envíos repetidos antes de que React actualice disabled.
  const escrituraEnCurso = useRef(false);
  // Permite enfocar el nombre al editar una fila.
  const campoNombre = useRef(null);

  // Limpia el formulario y sus errores locales.
  function limpiarFormulario() {
    // Crea un objeto nuevo para que React actualice los campos.
    setForm({ ...FORMULARIO_VACIO });
    // Elimina el aviso de peso inválido anterior.
    setErrorPeso("");
  }

  // Carga una fila en el formulario de edición.
  function editar(fila) {
    // Limpia mensajes de una operación anterior.
    setMensaje("");
    setErrorOperacion("");
    setErrorPeso("");
    // Un peso nulo identifica un embalaje a granel.
    const esGranel = permiteGranel && fila[campoPeso] === null;
    // Conserva el decimal como texto editable.
    setForm({
      id: fila.id,
      nombre: fila.nombre,
      peso: esGranel ? "" : String(fila[campoPeso]),
      granel: esGranel,
    });
    // Lleva el foco al primer campo del formulario.
    enfocar(campoNombre);
  }

  // Carga las filas al abrir el panel, cambiar el filtro o recargar.
  useEffect(() => {
    // Evita que una respuesta antigua cambie un componente desmontado.
    let vigente = true;
    // Encapsula la operación asíncrona del efecto.
    async function cargar() {
      // Muestra la fila de carga dentro de la tabla.
      setCargando(true);
      setErrorListado("");
      setFilas([]);
      try {
        // Consulta el estado seleccionado.
        const resultado = await listar(activoDesdeFiltro(filtro));
        // Conserva sólo la respuesta vigente.
        if (vigente) setFilas(resultado);
      } catch (error) {
        // Presenta un mensaje útil sin detalles internos.
        if (vigente) setErrorListado(extraerMensajeError(error, `No se pudo cargar ${titulo.toLowerCase()}`));
      } finally {
        // Finaliza la carga sólo si el efecto sigue activo.
        if (vigente) setCargando(false);
      }
    }
    // Inicia la carga del listado.
    cargar();
    // Marca como obsoleta cualquier respuesta posterior al desmontaje.
    return () => { vigente = false; };
  }, [filtro, recarga, listar, titulo]);

  // Valida al salir del campo para entregar retroalimentación inmediata.
  function validarPesoVisible() {
    // Granel no requiere kilos por caja.
    if (permiteGranel && form.granel) {
      setErrorPeso("");
      return true;
    }
    // Comprueba precisión, rango y valor positivo.
    const valido = validarPeso(form.peso, maximoEnteros) !== null;
    // Muestra un aviso en línea, sin popup.
    setErrorPeso(valido ? "" : `${etiquetaPeso} debe ser mayor que cero y tener hasta dos decimales.`);
    // Permite reutilizar el resultado al guardar.
    return valido;
  }

  // Crea o edita el registro según el id del formulario.
  async function guardar(event) {
    // Evita la navegación nativa del formulario.
    event.preventDefault();
    // Ignora un envío repetido mientras otro sigue pendiente.
    if (escrituraEnCurso.current) return;
    // Normaliza sólo los espacios exteriores; la API unifica espacios internos.
    const nombre = form.nombre.trim();
    // Limpia mensajes anteriores antes de validar.
    setMensaje("");
    setErrorOperacion("");
    // Replica el límite público del nombre.
    if (!nombre || nombre.length > 50) {
      setErrorOperacion("El nombre es obligatorio y admite hasta 50 caracteres.");
      return;
    }
    // Granel envía null; las demás modalidades exigen un decimal válido.
    const peso = permiteGranel && form.granel ? null : validarPeso(form.peso, maximoEnteros);
    // Impide guardar hasta corregir el peso.
    if (peso === null && !(permiteGranel && form.granel)) {
      validarPesoVisible();
      return;
    }
    // Quita el aviso local cuando la entrada ya es correcta.
    setErrorPeso("");
    // Bloquea inmediatamente un segundo envío.
    escrituraEnCurso.current = true;
    setGuardando(true);
    try {
      // Construye el cuerpo con el nombre de campo esperado por cada API.
      const datos = { nombre, [campoPeso]: peso };
      // Crea o actualiza conservando null explícito para granel.
      const resultado = form.id === null
        ? await crear(datos)
        : await actualizar(form.id, datos);
      // Informa la operación confirmada por el backend.
      setMensaje(`${singular} «${resultado.nombre}» ${form.id === null ? (femenino ? "creada" : "creado") : (femenino ? "actualizada" : "actualizado")}.`);
      // Reinicia el formulario y vuelve a consultar la tabla.
      limpiarFormulario();
      setRecarga((valor) => valor + 1);
    } catch (error) {
      // Incluye conflictos 409 y validaciones 422 enviados por la API.
      setErrorOperacion(extraerMensajeError(error, `No se pudo guardar ${singular.toLowerCase()}`));
    } finally {
      // Libera el formulario incluso cuando la API falla.
      escrituraEnCurso.current = false;
      setGuardando(false);
    }
  }

  // Activa o desactiva sin borrar físicamente.
  async function cambiarEstado(fila) {
    // Evita superponer escrituras.
    if (escrituraEnCurso.current) return;
    // Sólo desactivar solicita confirmación.
    if (!confirmarCambioEstado(fila.activo, `${singular.toLowerCase()} «${fila.nombre}»`)) return;
    // Bloquea acciones de fila mientras responde la API.
    escrituraEnCurso.current = true;
    setCambiandoId(fila.id);
    setMensaje("");
    setErrorOperacion("");
    try {
      // Invierte únicamente el estado actual.
      const resultado = await actualizar(fila.id, { activo: !fila.activo });
      // Comunica el nuevo estado confirmado.
      setMensaje(`${singular} «${resultado.nombre}» ${resultado.activo ? (femenino ? "activada" : "activado") : (femenino ? "desactivada" : "desactivado")}.`);
      // Recarga para respetar el filtro seleccionado.
      setRecarga((valor) => valor + 1);
    } catch (error) {
      // Presenta el error sin eliminar la fila actual.
      setErrorOperacion(extraerMensajeError(error, `No se pudo cambiar el estado de ${singular.toLowerCase()}`));
    } finally {
      // Habilita nuevamente las acciones.
      escrituraEnCurso.current = false;
      setCambiandoId(null);
    }
  }

  // Renderiza el mantenedor apilado: formulario, filtro y tabla.
  return (
    <section aria-labelledby={`titulo-${clave}`} className="min-w-0 space-y-4">
      <h2 id={`titulo-${clave}`} className="text-lg font-bold text-frigorifico-900">{titulo}</h2>
      {mensaje && <p role="status" className={MENSAJE_EXITO}>{mensaje}</p>}
      {errorOperacion && <p role="alert" className={MENSAJE_ERROR}>{errorOperacion}</p>}

      {/* Formulario de alta y edición conforme al patrón de catálogos. */}
      <form onSubmit={guardar} className={TARJETA} noValidate>
        <h3 className={`mb-3 ${SUBTITULO}`}>{form.id === null ? `${femenino ? "Nueva" : "Nuevo"} ${singular.toLowerCase()}` : `Editar ${singular.toLowerCase()}`}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor={`nombre-${clave}`} className={ETIQUETA}>Nombre</label>
            <input ref={campoNombre} id={`nombre-${clave}`} type="text" required maxLength={50} value={form.nombre} onChange={(event) => setForm((actual) => ({ ...actual, nombre: event.target.value }))} disabled={guardando} className={CAMPO} />
          </div>
          {permiteGranel && <div>
            <label htmlFor={`modalidad-${clave}`} className={ETIQUETA}>Modalidad</label>
            <select id={`modalidad-${clave}`} value={form.granel ? "granel" : "fijo"} onChange={(event) => { const granel = event.target.value === "granel"; setForm((actual) => ({ ...actual, granel, peso: granel ? "" : actual.peso })); setErrorPeso(""); }} disabled={guardando} className={SELECTOR}>
              <option value="fijo">Kilos fijos por caja</option>
              <option value="granel">A granel</option>
            </select>
          </div>}
          <div>
            <label htmlFor={`peso-${clave}`} className={ETIQUETA}>{etiquetaPeso}</label>
            <input id={`peso-${clave}`} type="text" inputMode="decimal" value={form.peso} onChange={(event) => { setForm((actual) => ({ ...actual, peso: event.target.value })); if (errorPeso) setErrorPeso(""); }} onBlur={validarPesoVisible} disabled={guardando || (permiteGranel && form.granel)} aria-invalid={Boolean(errorPeso)} aria-describedby={`ayuda-${clave}${errorPeso ? ` error-${clave}` : ""}`} className={errorPeso ? CAMPO_ERROR : CAMPO} placeholder="0,00" />
            <p id={`ayuda-${clave}`} className={AYUDA}>{permiteGranel && form.granel ? "En granel los kilos se informarán durante el proceso." : ayudaPeso}</p>
            {errorPeso && <p id={`error-${clave}`} role="alert" className="mt-1 text-xs text-red-600">{errorPeso}</p>}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="submit" disabled={guardando || Boolean(errorPeso)} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
          {form.id !== null && <button type="button" onClick={limpiarFormulario} disabled={guardando} className={BOTON_SECUNDARIO}>Cancelar</button>}
        </div>
      </form>

      {/* Encabezado del listado con filtro de estado y recarga manual. */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h3 className={SUBTITULO}>{femenino ? "Registradas" : "Registrados"}</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full sm:w-48">
            <label htmlFor={`filtro-${clave}`} className={ETIQUETA}>Mostrar</label>
            <select id={`filtro-${clave}`} value={filtro} onChange={(event) => setFiltro(event.target.value)} className={SELECTOR}>
              <option value="todos">Todos</option>
              <option value="activos">Activos</option>
              <option value="inactivos">Inactivos</option>
            </select>
          </div>
          <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando} className={BOTON_PRINCIPAL}>Recargar</button>
        </div>
      </div>

      {/* Tabla accesible; los estados de carga y vacío ocupan una fila. */}
      {errorListado && <p role="alert" className={MENSAJE_ERROR}>{errorListado}</p>}
      <div role="region" aria-label={`Listado de ${titulo.toLowerCase()}`} aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
        <table className="w-full text-sm">
          <caption className="sr-only">{titulo} según el filtro seleccionado</caption>
          <thead className={ENCABEZADO_TABLA}>
            <tr><th scope="col" className={CELDA}>Nombre</th><th scope="col" className={`${CELDA} text-right`}>{etiquetaPeso}</th><th scope="col" className={CELDA}>Estado</th><th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {cargando ? <tr><td colSpan={4} className={CELDA_AVISO}>Cargando…</td></tr>
              : errorListado ? <tr><td colSpan={4} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                : filas.length === 0 ? <tr><td colSpan={4} className={CELDA_AVISO}>Sin registros con este filtro.</td></tr>
                  : filas.map((fila) => <tr key={fila.id} className={claseFila(form.id === fila.id)} aria-current={form.id === fila.id ? "true" : undefined}>
                    <td className={`${CELDA} text-slate-600`}>{fila.nombre}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{permiteGranel && fila[campoPeso] === null ? "Granel" : mostrarPeso(fila[campoPeso])}</td>
                    <td className={CELDA}><span className={claseEstado(fila.activo)}>{fila.activo ? (femenino ? "Activa" : "Activo") : (femenino ? "Inactiva" : "Inactivo")}</span></td>
                    <td className={`${CELDA} text-right`}><div className="flex flex-wrap justify-end gap-3">
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

// Pestaña de HU10 con ambos mantenedores apilados.
export default function BandejasEmbalajes() {
  // Conserva una sola columna y separación uniforme entre los catálogos.
  return (
    <section aria-labelledby="titulo-bandejas-embalajes" className="min-w-0">
      <h2 id="titulo-bandejas-embalajes" className="sr-only">Bandejas y embalajes</h2>
      <p className="text-sm text-slate-500">Catálogos de tara de bandejas y peso de embalajes utilizados en recepción y proceso.</p>
      <div className="mt-6 min-w-0 space-y-10">
        <PanelPeso clave="tipos-bandeja" titulo="Tipos de bandeja" singular="Tipo de bandeja" femenino={false} campoPeso="peso_tara_kg" etiquetaPeso="Tara (kg)" ayudaPeso="Peso propio de una bandeja, mayor que cero." maximoEnteros={4} permiteGranel={false} listar={listarTiposBandeja} crear={crearTipoBandeja} actualizar={actualizarTipoBandeja} />
        <PanelPeso clave="embalajes" titulo="Embalajes" singular="Embalaje" femenino={false} campoPeso="kg_por_caja" etiquetaPeso="Kilos por caja" ayudaPeso="Peso fijo por caja, mayor que cero." maximoEnteros={6} permiteGranel listar={listarEmbalajes} crear={crearEmbalaje} actualizar={actualizarEmbalaje} />
      </div>
    </section>
  );
}
