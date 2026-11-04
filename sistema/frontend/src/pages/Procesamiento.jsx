// Estado, efectos y referencias de la pantalla.
import { useCallback, useEffect, useRef, useState } from "react";
// Enlace al comprobante y navegación al guardar.
import { Link, useNavigate } from "react-router-dom";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Usuario de la sesión: solo el administrador ve Anular.
import { useAuth } from "../api/AuthContext";
// Lecturas y escrituras del módulo.
import {
  anularProceso,
  editarProceso,
  listarEmbalajesProceso,
  listarProcesos,
  listarTarjasDisponibles,
  listarTarjasRebajadas,
  obtenerProceso,
  reabrirTarja,
  registrarProceso,
  terminarTarja,
} from "../api/procesos";
// Clases comunes de formularios, tablas y mensajes.
import {
  AYUDA,
  BOTON_EDITAR,
  BOTON_PELIGRO,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  CAMPO,
  CAMPO_ERROR,
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
// Cálculos de la pantalla, probados con node --test.
import { aCentimos, cajasParaSaldo, filasDeProceso, motivoMezcla, revisarFila, textoCajas, textoCentimos, textoKilos } from "../components/procesamiento";

// Mismo tope de filas que el backend.
const MAXIMO_FILAS = 200;
// Etiqueta de un proceso anulado, con el rojo de las tarjas anuladas.
const ETIQUETA_ANULADO = "rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-normal text-red-700";

// Obtiene YYYY-MM-DD usando el día de la planta y no la fecha UTC del navegador.
function hoyEnChile() {
  // en-CA entrega el orden año, mes y día.
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Santiago", // Zona horaria de la planta.
    year: "numeric", // Año con cuatro dígitos.
    month: "2-digit", // Mes con dos dígitos.
    day: "2-digit", // Día con dos dígitos.
  }).formatToParts(new Date());
  // Busca una de las partes por su tipo.
  const valor = (tipo) => partes.find((parte) => parte.type === tipo)?.value;
  // Arma el formato que usa el campo de fecha.
  return `${valor("year")}-${valor("month")}-${valor("day")}`;
}

// Muestra una fecha YYYY-MM-DD como DD-MM-YYYY, sin pasar por zonas horarias.
function formatearFecha(valor) {
  // Separa las partes del texto.
  const [anio, mes, dia] = String(valor).split("-");
  // Las ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Texto corto de la fruta de una tarja.
function textoFruta(tarja) {
  // Sistema productivo y calidad definen lo que se puede mezclar.
  return `${tarja.especie} / ${tarja.variedad} · ${tarja.calidad} · ${tarja.sistema_productivo}`;
}

// Registro de procesos de tarjas (HU18).
export default function Procesamiento() {
  // Abre el comprobante después de guardar.
  const navegar = useNavigate();
  // La API sigue siendo la autoridad; esto solo evita mostrar una acción que respondería 403.
  const { usuario } = useAuth();
  const esAdministrador = usuario.roles.includes("administrador");
  // Listas que vienen de la API.
  const [embalajes, setEmbalajes] = useState([]);
  const [disponibles, setDisponibles] = useState([]);
  const [rebajadas, setRebajadas] = useState([]);
  const [procesos, setProcesos] = useState([]);
  // Estado de carga inicial.
  const [cargando, setCargando] = useState(true);
  // Mensajes de la pantalla.
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");
  // Datos generales del proceso.
  const [embalajeId, setEmbalajeId] = useState("");
  const [fecha, setFecha] = useState(hoyEnChile);
  // Número escrito para sumar una tarja, como en el Form30 del legado.
  const [numero, setNumero] = useState("");
  // Una fila por cada tarja del proceso.
  const [detalle, setDetalle] = useState([]);
  // Bloquea los botones mientras responde la API.
  const [guardando, setGuardando] = useState(false);
  const [rebajandoId, setRebajandoId] = useState(null);
  // Proceso que se está corrigiendo; null al registrar uno nuevo.
  const [editando, setEditando] = useState(null);
  // Proceso abierto en el detalle.
  const [procesoAbierto, setProcesoAbierto] = useState(null);
  const [cargandoProceso, setCargandoProceso] = useState(null);
  // Campo del número, para volver a él con el teclado.
  const campoNumero = useRef(null);
  // Campo de cajas que debe recibir el foco después de pintar la fila nueva.
  const [enfocarCajas, setEnfocarCajas] = useState(null);

  // Embalaje elegido; al editar es el del proceso, aunque esté desactivado.
  const embalaje = editando
    ? { es_granel: editando.embalaje_kg_por_caja === null, kg_por_caja: editando.embalaje_kg_por_caja }
    : embalajes.find((opcion) => String(opcion.id) === embalajeId) ?? null;

  // Trae las tarjas disponibles y refresca los kilos de las filas ya agregadas.
  const cargarDisponibles = useCallback(async () => {
    // Pide la lista completa.
    const lista = await listarTarjasDisponibles();
    // La guarda para la tabla.
    setDisponibles(lista);
    // Una fila conserva sus datos si la tarja quedó fuera de las 200 listadas; al editar, su tope ya incluye lo que tiene.
    setDetalle((filas) => filas.map((fila) => (fila.kilos_originales === undefined ? { ...fila, tarja: lista.find((tarja) => tarja.id === fila.tarja.id) ?? fila.tarja } : fila)));
  }, []);

  // Al abrir la pantalla carga todo lo que necesita.
  useEffect(() => {
    // Descarta las respuestas si se cerró la pantalla.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargar() {
      try {
        // Pide las cuatro listas a la vez.
        const [listaEmbalajes, listaTarjas, listaProcesos, listaRebajadas] = await Promise.all([
          listarEmbalajesProceso(),
          listarTarjasDisponibles(),
          listarProcesos(),
          listarTarjasRebajadas(),
        ]);
        // Guarda el resultado si sigue vigente.
        if (vigente) {
          setEmbalajes(listaEmbalajes);
          setDisponibles(listaTarjas);
          setProcesos(listaProcesos);
          setRebajadas(listaRebajadas);
        }
      } catch (errorRecibido) {
        // Muestra el error sobre la pantalla.
        if (vigente) setError(extraerMensajeError(errorRecibido, "No se pudo cargar el procesamiento"));
      } finally {
        // Termina la carga.
        if (vigente) setCargando(false);
      }
    }
    // Inicia la consulta.
    cargar();
    // Marca como obsoleta la respuesta anterior.
    return () => { vigente = false; };
  }, []);

  // Lleva el foco a las cajas de la tarja recién agregada.
  useEffect(() => {
    // Solo actúa después de agregar una fila.
    if (enfocarCajas === null) return;
    // El campo ya está pintado.
    document.getElementById(`cajas-${enfocarCajas}`)?.focus();
    // Evita repetirlo.
    setEnfocarCajas(null);
  }, [enfocarCajas]);

  // Suma una tarja al detalle; devuelve false si no se pudo.
  function agregarTarja(tarja) {
    // Limpia los mensajes anteriores.
    setError("");
    setMensaje("");
    // Una tarja aparece una sola vez en cada proceso.
    if (detalle.some((fila) => fila.tarja.id === tarja.id)) {
      setError(`La tarja N° ${tarja.numero_tarja} ya está en este proceso.`);
      return false;
    }
    // La fruta del proceso debe ser la misma.
    const motivo = motivoMezcla(detalle, tarja);
    if (motivo) {
      setError(motivo);
      return false;
    }
    // Agrega la fila vacía.
    setDetalle((filas) => [...filas, { tarja, cantidad_cajas: "", kilos_procesados: "", tarja_terminada: false }]);
    // Después de pintar, el foco queda en sus cajas.
    setEnfocarCajas(tarja.id);
    return true;
  }

  // Suma por número la tarja escrita, con Enter.
  async function agregarPorNumero() {
    // Sin número no hay nada que buscar.
    const buscado = numero.trim();
    if (!buscado) return;
    // Limpia los mensajes anteriores.
    setError("");
    setMensaje("");
    try {
      // Busca también fuera de las 200 de la tabla.
      const [tarja] = await listarTarjasDisponibles(buscado);
      // Si no aparece, está anulada, terminada o no existe.
      if (!tarja) {
        setError(`La tarja N° ${buscado} no está disponible: no existe, está anulada o ya se terminó.`);
        return;
      }
      // Si se agregó, limpia el campo.
      if (agregarTarja(tarja)) setNumero("");
    } catch (errorRecibido) {
      // Muestra el error de la consulta.
      setError(extraerMensajeError(errorRecibido, "No se pudo buscar la tarja"));
    }
  }

  // Actualiza un campo de una fila.
  function cambiarFila(tarjaId, campo, valor) {
    // Solo cambia la fila indicada.
    setDetalle((filas) => filas.map((fila) => (fila.tarja.id === tarjaId ? { ...fila, [campo]: valor } : fila)));
  }

  // Quita una tarja del detalle.
  function quitarFila(tarjaId) {
    // Conserva las demás.
    setDetalle((filas) => filas.filter((fila) => fila.tarja.id !== tarjaId));
  }

  // Completa la fila para usar todos los kilos que le quedan a la tarja.
  function usarSaldo(fila) {
    // A granel los kilos se escriben; las cajas siguen siendo obligatorias.
    if (embalaje.es_granel) {
      // Pone los kilos disponibles.
      cambiarFila(fila.tarja.id, "kilos_procesados", textoKilos(fila.tarja.kilos_pendientes));
      // Si no hay cajas escritas, cuenta una.
      if (!String(fila.cantidad_cajas).trim()) cambiarFila(fila.tarja.id, "cantidad_cajas", "1");
      return;
    }
    // Calcula las cajas que dejan el saldo en 0.
    cambiarFila(fila.tarja.id, "cantidad_cajas", cajasParaSaldo(embalaje, fila.tarja.kilos_pendientes));
  }

  // Abre un proceso guardado en el formulario para corregirlo.
  async function iniciarEdicion(id) {
    // Marca la fila que se está cargando.
    setCargandoProceso(id);
    setError("");
    setMensaje("");
    try {
      // Trae las cajas y los kilos actuales de cada tarja.
      const proceso = await obtenerProceso(id);
      // Guarda el proceso y las filas originales, para saber qué se devuelve.
      setEditando({ ...proceso, originales: filasDeProceso(proceso) });
      // Carga las filas en el formulario.
      setDetalle(filasDeProceso(proceso));
      // El embalaje y la fecha son los del proceso.
      setFecha(proceso.fecha_elaboracion);
      // Lleva al operador al formulario.
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (errorRecibido) {
      // Muestra el error sobre la pantalla.
      setError(extraerMensajeError(errorRecibido, "No se pudo abrir el proceso"));
    } finally {
      // Libera la fila.
      setCargandoProceso(null);
    }
  }

  // Sale de la edición sin guardar.
  function cancelarEdicion() {
    // Vuelve a un proceso nuevo.
    setEditando(null);
    setDetalle([]);
    setEmbalajeId("");
    setFecha(hoyEnChile());
    setError("");
  }

  // Enter en cajas o kilos vuelve al número: el proceso no se guarda por accidente.
  function volverAlNumero(evento) {
    // Solo reacciona a Enter.
    if (evento.key !== "Enter") return;
    // Evita enviar el formulario.
    evento.preventDefault();
    // Deja el foco listo para la siguiente tarja.
    campoNumero.current?.focus();
  }

  // Revisa todas las filas una sola vez por render.
  const revisiones = detalle.map((fila) => revisarFila(embalaje, fila));
  // Totales que se muestran antes de guardar.
  const totalCajas = detalle.reduce((suma, fila) => suma + (aCentimos(fila.cantidad_cajas) ?? 0), 0);
  const totalCentimos = revisiones.reduce((suma, revision) => suma + (revision.kilos ?? 0), 0);
  // Al editar: tarjas quitadas del formulario, cuyos kilos vuelven completos.
  const quitadas = editando ? editando.originales.filter((original) => !detalle.some((fila) => fila.tarja.id === original.tarja.id)) : [];
  // Se puede guardar con embalaje, fecha y todas las filas correctas.
  const listoParaGuardar = Boolean(embalaje) && Boolean(fecha) && detalle.length > 0 && revisiones.every((revision) => revision.valida);

  // Registra el proceso.
  async function guardar(evento) {
    // Evita la navegación nativa del formulario.
    evento.preventDefault();
    // Enter con datos incompletos no hace nada.
    if (!listoParaGuardar || guardando) return;
    // Kilos que vuelven a sus tarjas de recepción al editar.
    const devoluciones = [
      ...detalle.map((fila, indice) => ({ numero: fila.tarja.numero_tarja, kilos: revisiones[indice].devueltos ?? 0 })).filter(({ kilos }) => kilos > 0),
      ...quitadas.map((original) => ({ numero: original.tarja.numero_tarja, kilos: aCentimos(original.kilos_originales) })),
    ];
    // Se confirma: una tarja cerrada con otros kilos vuelve a quedar pendiente.
    if (devoluciones.length > 0) {
      // Arma el texto con cada tarja y sus kilos.
      const textos = devoluciones.map(({ numero, kilos }) => `Tarja N° ${numero}: ${textoCentimos(kilos)} kg`).join("\n");
      // Sin confirmar, sigue editando.
      if (!window.confirm(`Estos kilos volverán a sus tarjas de recepción y quedarán pendientes:\n${textos}\n¿Guardar los cambios?`)) return;
    }
    // Lo que queda como merma por una marca nueva no vuelve solo: se confirma.
    const conMerma = detalle
      .map((fila, indice) => ({ fila, resto: revisiones[indice].resto }))
      .filter(({ fila, resto }) => fila.tarja_terminada && !fila.marca_original && resto > 0);
    if (conMerma.length > 0) {
      // Arma el texto con cada tarja y sus kilos.
      const textos = conMerma.map(({ fila, resto }) => `Tarja N° ${fila.tarja.numero_tarja}: ${textoCentimos(resto)} kg`).join("\n");
      // Sin confirmar, sigue editando.
      if (!window.confirm(`Estos kilos quedarán como merma:\n${textos}\n¿Registrar el proceso?`)) return;
    }
    // Bloquea el botón y limpia los mensajes.
    setGuardando(true);
    setError("");
    setMensaje("");
    try {
      // Filas como las espera la API: el backend calcula los kilos; a mano solo a granel.
      const tarjas = detalle.map((fila) => ({
        tarja_id: fila.tarja.id,
        cantidad_cajas: String(fila.cantidad_cajas).trim().replace(",", "."),
        // Con embalaje fijo no se envían kilos: la API los rechazaría.
        ...(embalaje.es_granel ? { kilos_procesados: String(fila.kilos_procesados).trim().replace(",", ".") } : {}),
        tarja_terminada: fila.tarja_terminada,
      }));
      // Al editar solo cambian las tarjas; al registrar, el backend asigna el folio.
      const proceso = editando
        ? await editarProceso(editando.id, { tarjas })
        : await registrarProceso({ embalaje_id: embalaje.id, fecha_elaboracion: fecha, tarjas });
      // Total de kilos devueltos, para contárselo al operador.
      const totalDevuelto = devoluciones.reduce((suma, { kilos }) => suma + kilos, 0);
      // Después de guardar se abre el comprobante, como en el Form30 del legado; el aviso viaja a esa hoja.
      navegar(`/procesamiento/${proceso.id}/imprimir`, {
        state: {
          aviso: editando
            ? `Proceso ${proceso.folio} actualizado: ${textoCajas(proceso.cantidad_cajas)} cajas y ${textoKilos(proceso.kilos_salida)} kg.${totalDevuelto > 0 ? ` Volvieron ${textoCentimos(totalDevuelto)} kg a sus tarjas de recepción.` : ""}`
            : `Proceso ${proceso.folio} registrado: ${textoCajas(proceso.cantidad_cajas)} cajas y ${textoKilos(proceso.kilos_salida)} kg.`,
        },
      });
    } catch (errorRecibido) {
      // Muestra el motivo, por ejemplo si otro operador consumió esos kilos.
      setError(extraerMensajeError(errorRecibido, editando ? "No se pudo actualizar el proceso" : "No se pudo registrar el proceso"));
      // Refresca los saldos para que el operador corrija con datos actuales.
      cargarDisponibles().catch(() => {});
    } finally {
      // Libera el botón.
      setGuardando(false);
    }
  }

  // Rebaja como merma los kilos que le quedan a una tarja.
  async function rebajarMerma(tarja) {
    // No vuelve solo: se pide confirmar.
    if (!window.confirm(`¿Rebajar como merma los ${textoKilos(tarja.kilos_pendientes)} kg pendientes de la tarja N° ${tarja.numero_tarja}? La tarja quedará terminada. Para revertirlo, se puede reabrir desde esta pantalla.`)) return;
    // Bloquea la fila y limpia los mensajes.
    setRebajandoId(tarja.id);
    setError("");
    setMensaje("");
    try {
      // La API marca la tarja y audita.
      const resultado = await terminarTarja(tarja.id);
      // Informa el resultado.
      setMensaje(`Tarja N° ${resultado.numero_tarja} terminada: ${textoKilos(resultado.kilos_merma)} kg rebajados como merma.`);
      // Una tarja terminada ya no puede seguir en el proceso nuevo; al editar, Rebajar no se ofrece.
      quitarFila(tarja.id);
      // Refresca las dos tablas.
      const [listaTarjas, listaRebajadas] = await Promise.all([listarTarjasDisponibles(), listarTarjasRebajadas()]);
      setDisponibles(listaTarjas);
      setRebajadas(listaRebajadas);
    } catch (errorRecibido) {
      // Muestra el motivo del rechazo.
      setError(extraerMensajeError(errorRecibido, "No se pudo rebajar la tarja"));
    } finally {
      // Libera la fila.
      setRebajandoId(null);
    }
  }

  // Deshace una merma rebajada por error.
  async function reabrir(tarja) {
    // Se pide confirmar: sus kilos vuelven a quedar pendientes.
    if (!window.confirm(`¿Reabrir la tarja N° ${tarja.numero_tarja}? Se deshace la merma y sus ${textoKilos(tarja.kilos_pendientes)} kg vuelven a quedar pendientes.`)) return;
    // Bloquea la fila y limpia los mensajes.
    setRebajandoId(tarja.id);
    setError("");
    setMensaje("");
    try {
      // La API recalcula el estado y audita.
      const resultado = await reabrirTarja(tarja.id);
      // Informa el resultado.
      setMensaje(`Tarja N° ${resultado.numero_tarja} reabierta: sus kilos quedaron pendientes.`);
      // Refresca las dos tablas.
      const [listaTarjas, listaRebajadas] = await Promise.all([listarTarjasDisponibles(), listarTarjasRebajadas()]);
      setDisponibles(listaTarjas);
      setRebajadas(listaRebajadas);
    } catch (errorRecibido) {
      // Muestra el motivo del rechazo.
      setError(extraerMensajeError(errorRecibido, "No se pudo reabrir la tarja"));
    } finally {
      // Libera la fila.
      setRebajandoId(null);
    }
  }

  // Anula un proceso, previa confirmación (HU25).
  async function anular(proceso) {
    // Es irreversible: se pide confirmar. No se exige motivo.
    if (!window.confirm(`¿Anular el proceso ${proceso.folio}? Sus ${textoKilos(proceso.kilos_salida)} kg vuelven a sus tarjas de recepción, que quedan pendientes y pierden su merma rebajada. Esta acción no se puede deshacer.`)) return;
    // Bloquea la fila y limpia los mensajes.
    setCargandoProceso(proceso.id);
    setError("");
    setMensaje("");
    try {
      // La API anula el proceso, devuelve los kilos y audita en una sola transacción.
      const anulado = await anularProceso(proceso.id);
      // Informa el resultado.
      setMensaje(`Proceso ${anulado.folio} anulado: ${textoKilos(anulado.kilos_salida)} kg volvieron a sus tarjas de recepción.`);
      // Si su detalle estaba abierto, lo actualiza.
      setProcesoAbierto((abierto) => (abierto?.id === anulado.id ? anulado : abierto));
      // Refresca las tres tablas.
      const [listaTarjas, listaRebajadas, listaProcesos] = await Promise.all([listarTarjasDisponibles(), listarTarjasRebajadas(), listarProcesos()]);
      setDisponibles(listaTarjas);
      setRebajadas(listaRebajadas);
      setProcesos(listaProcesos);
    } catch (errorRecibido) {
      // Muestra el motivo del rechazo.
      setError(extraerMensajeError(errorRecibido, "No se pudo anular el proceso"));
    } finally {
      // Libera la fila.
      setCargandoProceso(null);
    }
  }

  // Abre el detalle de un proceso.
  async function verProceso(id) {
    // Marca la fila que se está cargando.
    setCargandoProceso(id);
    setError("");
    try {
      // Muestra el proceso con sus tarjas.
      setProcesoAbierto(await obtenerProceso(id));
    } catch (errorRecibido) {
      // Muestra el error sobre la pantalla.
      setError(extraerMensajeError(errorRecibido, "No se pudo consultar el proceso"));
    } finally {
      // Libera la fila.
      setCargandoProceso(null);
    }
  }

  // Renderiza el encabezado, el formulario y los listados.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 4. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E4 · Proceso</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Procesamiento</h1>
        <p className="mt-2 text-sm text-slate-500">Registre qué tarjas entran a proceso y cuántas cajas salen de cada una. Una tarja se puede consumir en varios procesos.</p>
      </div>

      {/* Mensajes generales. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}
      {mensaje && <p className={MENSAJE_EXITO} role="status">{mensaje}</p>}

      {/* Formulario grande, con el patrón de Procesamiento de socradex. */}
      <form onSubmit={guardar} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-5">
          <h2 className="font-semibold text-frigorifico-900">{editando ? `Editar proceso ${editando.folio}` : "Nuevo proceso"}</h2>
          <p className="mt-1 text-xs text-slate-500">
            {editando
              ? "Ajuste las cajas, agregue tarjas o quítelas. Los kilos que salgan vuelven a su tarja de recepción. El folio, el embalaje y la fecha no cambian."
              : "El folio y los kilos los asigna el sistema. Solo a granel se ingresan los kilos a mano."}
          </p>
        </div>

        {/* Datos generales: un embalaje y una fecha por proceso. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="proceso-embalaje" className={ETIQUETA}>Embalaje</label>
            {/* Al editar se muestra el embalaje del proceso, sin poder cambiarlo. */}
            <select id="proceso-embalaje" value={editando ? "actual" : embalajeId} disabled={Boolean(editando)} onChange={(evento) => setEmbalajeId(evento.target.value)} className={SELECTOR}>
              {editando ? (
                <option value="actual">{editando.embalaje}</option>
              ) : (
                <>
                  <option value="">Seleccione…</option>
                  {embalajes.map((opcion) => (
                    <option key={opcion.id} value={opcion.id}>
                      {opcion.nombre}{opcion.es_granel ? " (a granel)" : ` (${textoKilos(opcion.kg_por_caja)} kg)`}
                    </option>
                  ))}
                </>
              )}
            </select>
          </div>
          <div>
            <label htmlFor="proceso-fecha" className={ETIQUETA}>Fecha de elaboración</label>
            <input id="proceso-fecha" type="date" max={hoyEnChile()} value={fecha} disabled={Boolean(editando)} onChange={(evento) => setFecha(evento.target.value)} className={CAMPO} />
          </div>
          {/* Enter suma la tarja, como en el Form30 del legado. */}
          <div>
            <label htmlFor="proceso-numero" className={ETIQUETA}>Agregar tarja por número</label>
            <input
              id="proceso-numero"
              ref={campoNumero}
              type="number"
              min="1"
              step="1"
              value={numero}
              onChange={(evento) => setNumero(evento.target.value)}
              onKeyDown={(evento) => {
                // Enter busca la tarja y no envía el formulario.
                if (evento.key === "Enter") {
                  evento.preventDefault();
                  agregarPorNumero();
                }
              }}
              aria-describedby="proceso-numero-ayuda"
              className={CAMPO}
            />
            <p id="proceso-numero-ayuda" className={AYUDA}>Escriba el número y presione Enter, o use Agregar en la tabla de abajo.</p>
          </div>
        </div>

        {/* Tarjas de este proceso. */}
        <div className="mt-6 border-t border-slate-200 pt-5">
          <h3 className={`mb-3 ${SUBTITULO}`}>Tarjas de este proceso</h3>
          <div role="region" aria-label="Tarjas de este proceso" tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Tarjas del proceso con sus cajas y kilos</caption>
              <thead className={ENCABEZADO_TABLA}>
                <tr>
                  <th scope="col" className={`${CELDA} text-right`}>N°</th>
                  <th scope="col" className={CELDA}>Fruta</th>
                  <th scope="col" className={`${CELDA} text-right`}>Disponibles</th>
                  <th scope="col" className={CELDA}>Cajas</th>
                  <th scope="col" className={CELDA}>Kilos</th>
                  <th scope="col" className={CELDA}>Terminada</th>
                  <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {detalle.length === 0 ? (
                  <tr><td colSpan={7} className={CELDA_AVISO}>Agregue al menos una tarja.</td></tr>
                ) : (
                  detalle.map((fila, indice) => {
                    // Resultado de revisar esta fila.
                    const revision = revisiones[indice];
                    // Número visible de la tarja, para los lectores de pantalla.
                    const numeroTarja = fila.tarja.numero_tarja;
                    // Los mensajes se muestran bajo la fila.
                    return (
                      <tr key={fila.tarja.id} className="align-top">
                        <td className={`${CELDA} text-right font-medium text-slate-700`}>{numeroTarja}</td>
                        <td className={`${CELDA} text-slate-600`}>
                          <span className="block">{textoFruta(fila.tarja)}</span>
                          <span className="block text-xs text-slate-500">{fila.tarja.productor_codigo} · {fila.tarja.productor_razon_social}</span>
                        </td>
                        <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(fila.tarja.kilos_pendientes)} kg</td>
                        <td className={CELDA}>
                          {/* Con decimales: una caja se puede armar con fruta de dos tarjas. */}
                          <input
                            id={`cajas-${fila.tarja.id}`}
                            type="text"
                            inputMode="decimal"
                            aria-label={`Cajas de la tarja ${numeroTarja}`}
                            value={fila.cantidad_cajas}
                            onChange={(evento) => cambiarFila(fila.tarja.id, "cantidad_cajas", evento.target.value)}
                            onKeyDown={volverAlNumero}
                            aria-invalid={Boolean(revision.error)}
                            className={`${revision.error ? CAMPO_ERROR : CAMPO} !mt-0 min-w-20`}
                          />
                          {/* Los mensajes van bajo el campo, sin ensanchar la tabla. */}
                          {revision.error && <p className="mt-1 min-w-40 text-xs text-red-700" role="alert">{revision.error}</p>}
                          {revision.aviso && <p className="mt-1 min-w-40 text-xs text-amber-800" role="status">{revision.aviso}</p>}
                          {/* Calcula las cajas que dejan la tarja en 0. */}
                          {embalaje && (
                            <button type="button" onClick={() => usarSaldo(fila)} aria-label={`Usar todo el saldo de la tarja ${numeroTarja}`} className={`mt-1 block whitespace-nowrap ${BOTON_EDITAR}`}>Usar todo</button>
                          )}
                        </td>
                        {/* A granel se escriben; con peso fijo los calcula el sistema. */}
                        <td className={`${CELDA} whitespace-nowrap text-slate-600`}>
                          {embalaje?.es_granel ? (
                            <input
                              type="text"
                              inputMode="decimal"
                              aria-label={`Kilos a granel de la tarja ${numeroTarja}`}
                              value={fila.kilos_procesados}
                              onChange={(evento) => cambiarFila(fila.tarja.id, "kilos_procesados", evento.target.value)}
                              onKeyDown={volverAlNumero}
                              className={`${CAMPO} !mt-0 min-w-24`}
                            />
                          ) : revision.kilos !== null && revision.kilos !== undefined ? `${textoCentimos(revision.kilos)} kg` : "—"}
                        </td>
                        <td className={CELDA}>
                          <input
                            type="checkbox"
                            aria-label={`La tarja ${numeroTarja} se termina en este proceso`}
                            checked={fila.tarja_terminada}
                            onChange={(evento) => cambiarFila(fila.tarja.id, "tarja_terminada", evento.target.checked)}
                            className="h-4 w-4 accent-frigorifico-900"
                          />
                        </td>
                        <td className={`${CELDA} text-right`}>
                          <button type="button" onClick={() => quitarFila(fila.tarja.id)} aria-label={`Quitar la tarja ${numeroTarja}`} className={BOTON_EDITAR}>Quitar</button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
              {/* Totales antes de guardar. */}
              {detalle.length > 0 && (
                <tfoot className="border-t border-slate-200 bg-frigorifico-50 text-sm font-semibold text-frigorifico-900">
                  <tr>
                    <td className={CELDA} colSpan={3}>Totales</td>
                    <td className={CELDA}>{textoCajas((totalCajas / 100).toFixed(2))}</td>
                    <td className={`${CELDA} whitespace-nowrap`}>{textoCentimos(totalCentimos)} kg</td>
                    <td className={CELDA} colSpan={2}></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
          {/* Sin embalaje no hay cálculo: se explica por qué no se puede guardar. */}
          {detalle.length > 0 && !embalaje && <p className={AYUDA}>Elija el embalaje para calcular los kilos.</p>}
          {/* Las tarjas quitadas ya no se ven en la tabla: se dice qué pasa con sus kilos. */}
          {quitadas.length > 0 && (
            <p className="mt-2 text-xs text-amber-800" role="status">
              Se quitan del proceso: {quitadas.map((original) => `tarja N° ${original.tarja.numero_tarja} (vuelven ${textoKilos(original.kilos_originales)} kg)`).join(", ")}.
            </p>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-3">
          {editando && <button type="button" onClick={cancelarEdicion} disabled={guardando} className={BOTON_SECUNDARIO}>Cancelar</button>}
          <button type="submit" disabled={!listoParaGuardar || guardando} className={BOTON_PRINCIPAL}>
            {guardando ? "Guardando…" : editando ? "Guardar cambios" : "Registrar proceso"}
          </button>
        </div>
      </form>

      {/* Tarjas que se pueden procesar (HU18 criterio 3). */}
      <div>
        <h2 className={`mb-1 ${SUBTITULO}`}>Tarjas por procesar</h2>
        <p className="mb-3 text-xs text-slate-500">Una tarja queda aquí hasta llegar a 0 kg o hasta que sus kilos se rebajen como merma. Lo que no pasa a proceso se rebaja aquí, no en el proceso.</p>
        <div role="region" aria-label="Tarjas por procesar" aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
          <table className="w-full text-sm">
            <caption className="sr-only">Tarjas recepcionadas o parciales con sus kilos pendientes</caption>
            <thead className={ENCABEZADO_TABLA}>
              <tr>
                <th scope="col" className={`${CELDA} text-right`}>N°</th>
                <th scope="col" className={CELDA}>Recepción</th>
                <th scope="col" className={CELDA}>Productor</th>
                <th scope="col" className={CELDA}>Fruta</th>
                <th scope="col" className={`${CELDA} text-right`}>Netos</th>
                <th scope="col" className={`${CELDA} text-right`}>Pendientes</th>
                <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cargando ? (
                <tr><td colSpan={7} className={CELDA_AVISO}>Cargando…</td></tr>
              ) : disponibles.length === 0 ? (
                <tr><td colSpan={7} className={CELDA_AVISO}>No hay tarjas por procesar.</td></tr>
              ) : (
                disponibles.map((tarja) => (
                  <tr key={tarja.id} className="hover:bg-slate-50">
                    <td className={`${CELDA} text-right font-medium text-slate-700`}>{tarja.numero_tarja}</td>
                    <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{formatearFecha(tarja.fecha_recepcion)}</td>
                    <td className={`${CELDA} text-slate-600`}>{tarja.productor_codigo} · {tarja.productor_razon_social}</td>
                    <td className={`${CELDA} text-slate-600`}>{textoFruta(tarja)}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{tarja.kilos_netos}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.kilos_pendientes)}</td>
                    <td className={`${CELDA} text-right`}>
                      <div className="flex flex-wrap justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => agregarTarja(tarja)}
                          disabled={detalle.some((fila) => fila.tarja.id === tarja.id)}
                          aria-label={`Agregar la tarja ${tarja.numero_tarja} al proceso`}
                          className={`whitespace-nowrap ${BOTON_EDITAR}`}
                        >
                          Agregar
                        </button>
                        {/* También una tarja sin procesos: toda su fruta pudo descartarse en la selección. */}
                        {/* Al editar no se ofrece: sacaría del formulario una fila del proceso y devolvería sus kilos. */}
                        {!editando && aCentimos(tarja.kilos_pendientes) > 0 && (
                          <button
                            type="button"
                            onClick={() => rebajarMerma(tarja)}
                            disabled={rebajandoId === tarja.id}
                            aria-label={`Rebajar como merma el saldo de la tarja ${tarja.numero_tarja}`}
                            className={`whitespace-nowrap ${BOTON_PELIGRO}`}
                          >
                            {rebajandoId === tarja.id ? "Rebajando…" : "Rebajar a merma"}
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
        {!cargando && disponibles.length === MAXIMO_FILAS && (
          <p className={AYUDA}>Se muestran las {MAXIMO_FILAS} más antiguas; las demás se agregan escribiendo su número.</p>
        )}
      </div>

      {/* Tarjas rebajadas como merma: desde aquí se deshace un error. */}
      {rebajadas.length > 0 && (
        <div>
          <h2 className={`mb-3 ${SUBTITULO}`}>Tarjas rebajadas como merma</h2>
          <div role="region" aria-label="Tarjas rebajadas como merma" tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Tarjas con merma rebajada, con sus kilos</caption>
              <thead className={ENCABEZADO_TABLA}>
                <tr>
                  <th scope="col" className={`${CELDA} text-right`}>N°</th>
                  <th scope="col" className={CELDA}>Productor</th>
                  <th scope="col" className={CELDA}>Fruta</th>
                  <th scope="col" className={`${CELDA} text-right`}>Netos</th>
                  <th scope="col" className={`${CELDA} text-right`}>Procesados</th>
                  <th scope="col" className={`${CELDA} text-right`}>Merma</th>
                  <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rebajadas.map((tarja) => (
                  <tr key={tarja.id} className="hover:bg-slate-50">
                    <td className={`${CELDA} text-right font-medium text-slate-700`}>{tarja.numero_tarja}</td>
                    <td className={`${CELDA} text-slate-600`}>{tarja.productor_codigo} · {tarja.productor_razon_social}</td>
                    <td className={`${CELDA} text-slate-600`}>{textoFruta(tarja)}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{tarja.kilos_netos}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.kilos_procesados)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.kilos_pendientes)}</td>
                    <td className={`${CELDA} text-right`}>
                      {/* Al editar no se ofrece: cambiaría los kilos de lo que se está corrigiendo. */}
                      {!editando && (
                        <button
                          type="button"
                          onClick={() => reabrir(tarja)}
                          disabled={rebajandoId === tarja.id}
                          aria-label={`Reabrir la tarja ${tarja.numero_tarja}`}
                          className={`whitespace-nowrap ${BOTON_EDITAR}`}
                        >
                          {rebajandoId === tarja.id ? "Reabriendo…" : "Reabrir"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detalle de un proceso (HU18 criterio 7). */}
      {procesoAbierto && (
        <section aria-labelledby="titulo-proceso" className={TARJETA}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="titulo-proceso" className="font-semibold text-frigorifico-900">Proceso {procesoAbierto.folio}</h2>
              {/* Un proceso anulado se sigue viendo, marcado. */}
              {procesoAbierto.anulado && <span className={ETIQUETA_ANULADO}>Anulado</span>}
            </div>
            <button type="button" onClick={() => setProcesoAbierto(null)} className={BOTON_EDITAR}>Cerrar</button>
          </div>
          <p className="mb-3 text-sm text-slate-600">
            {procesoAbierto.embalaje} · Elaborado el {formatearFecha(procesoAbierto.fecha_elaboracion)} · {textoCajas(procesoAbierto.cantidad_cajas)} cajas · {textoKilos(procesoAbierto.kilos_salida)} kg · Registrado por {procesoAbierto.registrado_por}
          </p>
          <div role="region" aria-label={`Tarjas del proceso ${procesoAbierto.folio}`} tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Tarjas del proceso con su productor, cajas y kilos</caption>
              <thead className={ENCABEZADO_TABLA}>
                <tr>
                  <th scope="col" className={`${CELDA} text-right`}>N°</th>
                  <th scope="col" className={CELDA}>Productor</th>
                  <th scope="col" className={CELDA}>Fruta</th>
                  <th scope="col" className={`${CELDA} text-right`}>Cajas</th>
                  <th scope="col" className={`${CELDA} text-right`}>Kilos</th>
                  <th scope="col" className={CELDA}>Terminada aquí</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {procesoAbierto.tarjas.map((fila) => (
                  <tr key={fila.tarja_id}>
                    <td className={`${CELDA} text-right font-medium text-slate-700`}>{fila.numero_tarja}</td>
                    <td className={`${CELDA} text-slate-600`}>{fila.productor_codigo} · {fila.productor_razon_social}</td>
                    <td className={`${CELDA} text-slate-600`}>{fila.especie} / {fila.variedad}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{textoCajas(fila.cantidad_cajas)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(fila.kilos_procesados)}</td>
                    <td className={`${CELDA} text-slate-600`}>{fila.tarja_terminada ? "Sí" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Procesos registrados, los más recientes primero. */}
      <div>
        <h2 className={`mb-3 ${SUBTITULO}`}>Procesos registrados</h2>
        <div role="region" aria-label="Procesos registrados" aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
          <table className="w-full text-sm">
            <caption className="sr-only">Procesos registrados con sus totales</caption>
            <thead className={ENCABEZADO_TABLA}>
              <tr>
                <th scope="col" className={CELDA}>Folio</th>
                <th scope="col" className={CELDA}>Elaboración</th>
                <th scope="col" className={CELDA}>Embalaje</th>
                <th scope="col" className={`${CELDA} text-right`}>Cajas</th>
                <th scope="col" className={`${CELDA} text-right`}>Kilos</th>
                <th scope="col" className={CELDA}>Registrado por</th>
                <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cargando ? (
                <tr><td colSpan={7} className={CELDA_AVISO}>Cargando…</td></tr>
              ) : procesos.length === 0 ? (
                <tr><td colSpan={7} className={CELDA_AVISO}>Sin procesos registrados todavía.</td></tr>
              ) : (
                procesos.map((proceso) => (
                  <tr key={proceso.id} className="hover:bg-slate-50">
                    <td className={`${CELDA} font-medium text-slate-700`}>
                      {proceso.folio}
                      {/* Un proceso anulado se sigue viendo, marcado. */}
                      {proceso.anulado && <span className={`ml-2 ${ETIQUETA_ANULADO}`}>Anulado</span>}
                    </td>
                    <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{formatearFecha(proceso.fecha_elaboracion)}</td>
                    <td className={`${CELDA} text-slate-600`}>{proceso.embalaje}</td>
                    <td className={`${CELDA} text-right text-slate-600`}>{textoCajas(proceso.cantidad_cajas)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(proceso.kilos_salida)}</td>
                    <td className={`${CELDA} text-slate-600`}>{proceso.registrado_por}</td>
                    <td className={`${CELDA} text-right`}>
                      <div className="flex flex-wrap justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => verProceso(proceso.id)}
                          disabled={cargandoProceso === proceso.id}
                          aria-label={`Ver detalle del proceso ${proceso.folio}`}
                          className={`whitespace-nowrap ${BOTON_EDITAR}`}
                        >
                          {cargandoProceso === proceso.id ? "Cargando…" : "Ver detalle"}
                        </button>
                        {/* Un proceso anulado no se edita. */}
                        {!proceso.anulado && (
                          <button
                            type="button"
                            onClick={() => iniciarEdicion(proceso.id)}
                            disabled={cargandoProceso === proceso.id || editando?.id === proceso.id}
                            aria-label={`Editar el proceso ${proceso.folio}`}
                            className={`whitespace-nowrap ${BOTON_EDITAR}`}
                          >
                            Editar
                          </button>
                        )}
                        {/* Comprobante del proceso, como el botón Imprimir del Form30 del legado. */}
                        {!proceso.anulado && (
                          <Link to={`/procesamiento/${proceso.id}/imprimir`} aria-label={`Imprimir el proceso ${proceso.folio}`} className={`whitespace-nowrap ${BOTON_EDITAR}`}>Imprimir</Link>
                        )}
                        {/* Solo el administrador (HU25 criterio 1); al editar no se ofrece. */}
                        {esAdministrador && !proceso.anulado && !editando && (
                          <button
                            type="button"
                            onClick={() => anular(proceso)}
                            disabled={cargandoProceso === proceso.id}
                            aria-label={`Anular el proceso ${proceso.folio}`}
                            className={`whitespace-nowrap ${BOTON_PELIGRO}`}
                          >
                            Anular
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
        {!cargando && procesos.length === MAXIMO_FILAS && (
          <p className={AYUDA}>Se muestran los {MAXIMO_FILAS} más recientes.</p>
        )}
      </div>
    </div>
  );
}
