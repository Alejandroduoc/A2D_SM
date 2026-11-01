// Estado, efectos y referencia del formulario de recepción.
import { useEffect, useRef, useState } from "react";
// Traduce errores HTTP a mensajes legibles sin borrar lo escrito.
import { extraerMensajeError } from "../api/client";
// Catálogos activos usados por la recepción.
import { listarCalidades, listarEspecies, listarSistemasProductivos, listarTiposBandeja, listarVariedades } from "../api/opciones";
// Escritura de tarjas y acumulados del productor.
import { pendientesProductor, registrarTarja } from "../api/tarjas";
// Selectores compartidos de HU11.
import SelectorCatalogo from "../components/SelectorCatalogo";
import SelectorProductor from "../components/SelectorProductor";
// Clases comunes de formularios y mensajes.
import { AYUDA, BOTON_PRINCIPAL, CAMPO, CAMPO_ERROR, ETIQUETA, MENSAJE_ERROR, MENSAJE_EXITO, SUBTITULO } from "../components/catalogo";

// Límites acordados provisionalmente con el backend de A1.
const MAX_BANDEJAS = 500;
const MAX_PALLET_CENTIMOS = 10000;
const MAX_BALANZA_CENTIMOS = 500000;

// Obtiene YYYY-MM-DD usando el día de la planta y no la fecha UTC del navegador.
function hoyEnChile() {
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Santiago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const valor = (tipo) => partes.find((parte) => parte.type === tipo)?.value;
  return `${valor("year")}-${valor("month")}-${valor("day")}`;
}

// Convierte un decimal escrito a centésimos exactos; null indica entrada incompleta.
function aCentimos(valor) {
  const texto = String(valor ?? "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d{0,2})?$/.test(texto)) return null;
  const [enteros, decimales = ""] = texto.split(".");
  return Number(enteros) * 100 + Number(decimales.padEnd(2, "0"));
}

// Redondea una fracción al entero par más cercano, igual que ROUND_HALF_EVEN.
export function redondearBancario(numerador, denominador = 100) {
  const signo = numerador < 0 ? -1 : 1;
  const absoluto = Math.abs(numerador);
  const entero = Math.floor(absoluto / denominador);
  const resto = absoluto % denominador;
  const dobleResto = resto * 2;
  const redondeado = dobleResto < denominador
    ? entero
    : dobleResto > denominador
      ? entero + 1
      : entero % 2 === 0 ? entero : entero + 1;
  return signo * redondeado;
}

// Formatea centésimos como kilos con dos decimales y coma visible.
function formatearCentimos(centimos) {
  return (centimos / 100).toFixed(2).replace(".", ",");
}

// Valores que se limpian después de registrar, conservando la fecha aparte.
function formularioVacio(fecha) {
  return {
    porcentaje_calidad: "",
    cantidad_bandejas: "",
    peso_pallet_kg: "0",
    kilos_brutos: "",
    fecha_recepcion: fecha,
  };
}

// Formulario operativo para registrar tarjas de recepción.
export default function Recepcion() {
  const fechaHoy = hoyEnChile();
  const formularioRef = useRef(null);
  // Catálogos independientes y sus estados de carga.
  const [especies, setEspecies] = useState([]);
  const [calidades, setCalidades] = useState([]);
  const [sistemas, setSistemas] = useState([]);
  const [bandejas, setBandejas] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState("");
  // Variedades dependen de la especie seleccionada.
  const [variedades, setVariedades] = useState([]);
  const [cargandoVariedades, setCargandoVariedades] = useState(false);
  const [errorVariedades, setErrorVariedades] = useState("");
  // Identidades elegidas para la tarja.
  const [productor, setProductor] = useState(null);
  const [sistemaId, setSistemaId] = useState("");
  const [especieId, setEspecieId] = useState("");
  const [variedadId, setVariedadId] = useState("");
  const [calidadId, setCalidadId] = useState("");
  const [bandejaId, setBandejaId] = useState("");
  // Datos numéricos y fecha que escribe el operador.
  const [form, setForm] = useState(() => formularioVacio(fechaHoy));
  // Acumulados del productor y recarga posterior a una nueva tarja.
  const [pendientes, setPendientes] = useState(null);
  const [cargandoPendientes, setCargandoPendientes] = useState(false);
  const [errorPendientes, setErrorPendientes] = useState("");
  const [recargaPendientes, setRecargaPendientes] = useState(0);
  // Estados de escritura y mensajes de resultado.
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [exito, setExito] = useState("");

  // Carga en paralelo los catálogos que no dependen de otra selección.
  useEffect(() => {
    let vigente = true;
    async function cargarCatalogos() {
      try {
        const [listaEspecies, listaCalidades, listaSistemas, listaBandejas] = await Promise.all([
          listarEspecies(),
          listarCalidades(),
          listarSistemasProductivos(),
          listarTiposBandeja(),
        ]);
        if (vigente) {
          setEspecies(listaEspecies);
          setCalidades(listaCalidades);
          setSistemas(listaSistemas);
          setBandejas(listaBandejas);
        }
      } catch (errorRecibido) {
        if (vigente) setErrorCarga(extraerMensajeError(errorRecibido, "No se pudieron cargar las listas"));
      } finally {
        if (vigente) setCargando(false);
      }
    }
    cargarCatalogos();
    return () => { vigente = false; };
  }, []);

  // Obtiene las variedades activas cada vez que cambia la especie.
  useEffect(() => {
    if (!especieId) {
      setVariedades([]);
      setErrorVariedades("");
      return undefined;
    }
    let vigente = true;
    async function cargarVariedades() {
      setCargandoVariedades(true);
      setErrorVariedades("");
      setVariedades([]);
      try {
        const lista = await listarVariedades(Number(especieId));
        if (vigente) setVariedades(lista);
      } catch (errorRecibido) {
        if (vigente) setErrorVariedades(extraerMensajeError(errorRecibido, "No se pudieron cargar las variedades"));
      } finally {
        if (vigente) setCargandoVariedades(false);
      }
    }
    cargarVariedades();
    return () => { vigente = false; };
  }, [especieId]);

  // Muestra los acumulados del productor elegido y los actualiza tras guardar.
  useEffect(() => {
    if (!productor) {
      setPendientes(null);
      setErrorPendientes("");
      return undefined;
    }
    let vigente = true;
    async function cargarPendientes() {
      setCargandoPendientes(true);
      setErrorPendientes("");
      try {
        const acumulados = await pendientesProductor(productor.id);
        if (vigente) setPendientes(acumulados);
      } catch (errorRecibido) {
        if (vigente) {
          setPendientes(null);
          setErrorPendientes(extraerMensajeError(errorRecibido, "No se pudieron consultar los pendientes"));
        }
      } finally {
        if (vigente) setCargandoPendientes(false);
      }
    }
    cargarPendientes();
    return () => { vigente = false; };
  }, [productor, recargaPendientes]);

  // Selecciona la bandeja completa para leer su tara sin usar float.
  const bandeja = bandejas.find((opcion) => String(opcion.id) === bandejaId);
  const taraCentimos = bandeja ? aCentimos(bandeja.peso_tara_kg) : null;
  const palletCentimos = aCentimos(form.peso_pallet_kg);
  const brutosCentimos = aCentimos(form.kilos_brutos);
  const cantidad = Number(form.cantidad_bandejas);
  const calidad = Number(form.porcentaje_calidad);
  const cantidadValida = Number.isInteger(cantidad) && cantidad > 0 && cantidad <= MAX_BANDEJAS;
  const calidadValida = form.porcentaje_calidad !== ""
    && Number.isInteger(calidad)
    && calidad >= 0
    && calidad <= 100;
  const palletValido = palletCentimos !== null && palletCentimos >= 0 && palletCentimos <= MAX_PALLET_CENTIMOS;
  const brutosValidos = brutosCentimos !== null && brutosCentimos > 0 && brutosCentimos <= MAX_BALANZA_CENTIMOS;
  const fechaValida = form.fecha_recepcion !== "" && form.fecha_recepcion <= fechaHoy;
  const netoCentimos = cantidadValida && taraCentimos !== null && palletCentimos !== null && brutosCentimos !== null
    ? brutosCentimos - cantidad * taraCentimos - palletCentimos
    : null;
  const kilosNetos = netoCentimos === null ? null : redondearBancario(netoCentimos);
  const promedioCentimos = kilosNetos !== null && cantidadValida
    ? redondearBancario(kilosNetos * 100, cantidad)
    : null;
  const netoValido = kilosNetos !== null && kilosNetos > 0;
  const formularioValido = Boolean(
    productor
    && sistemaId
    && especieId
    && variedadId
    && calidadId
    && bandejaId
    && cantidadValida
    && calidadValida
    && palletValido
    && brutosValidos
    && fechaValida
    && netoValido,
  );

  // Etiquetas de bandeja con la tara visible para anticipar el cálculo.
  const opcionesBandeja = bandejas.map((opcion) => ({
    id: opcion.id,
    nombre: `${opcion.nombre} (${String(opcion.peso_tara_kg).replace(".", ",")} kg)`,
  }));
  const textoVacio = cargando ? "Cargando…" : "Seleccione…";
  const textoVariedad = !especieId
    ? "Elija primero una especie"
    : cargandoVariedades ? "Cargando…" : variedades.length ? "Seleccione…" : "Sin variedades activas";

  // Cambia una entrada sin convertirla prematuramente a float.
  function cambiarCampo(evento) {
    const { name, value } = evento.target;
    setForm((anterior) => ({ ...anterior, [name]: value }));
    setError("");
    setExito("");
  }

  // Una especie nueva invalida la variedad que pertenecía a la anterior.
  function cambiarEspecie(id) {
    setEspecieId(id);
    setVariedadId("");
  }

  // Tras elegir con clic o Enter, continúa en el primer catálogo del flujo.
  function cambiarProductor(productorElegido) {
    setProductor(productorElegido);
    if (productorElegido) {
      requestAnimationFrame(() => document.getElementById("recepcion-sistema")?.focus());
    }
  }

  // Enter avanza al siguiente input o select y nunca envía el formulario.
  function avanzarConEnter(evento) {
    if (evento.key !== "Enter") return;
    evento.preventDefault();
    if (evento.target.type === "search") return;
    const campos = [...formularioRef.current.querySelectorAll("input, select")]
      .filter((campo) => !campo.disabled && campo.type !== "search");
    const indice = campos.indexOf(evento.target);
    campos[indice + 1]?.focus();
  }

  // Envía solo los campos admitidos por TarjaCreate.
  async function guardar(evento) {
    evento.preventDefault();
    if (!formularioValido || guardando) {
      setError("Complete los datos y corrija los valores antes de guardar.");
      return;
    }
    setGuardando(true);
    setError("");
    setExito("");
    try {
      const registrada = await registrarTarja({
        productor_id: productor.id,
        sistema_productivo_id: Number(sistemaId),
        variedad_id: Number(variedadId),
        calidad_id: Number(calidadId),
        tipo_bandeja_id: Number(bandejaId),
        cantidad_bandejas: cantidad,
        peso_pallet_kg: form.peso_pallet_kg.replace(",", "."),
        kilos_brutos: form.kilos_brutos.replace(",", "."),
        porcentaje_calidad: calidad,
        fecha_recepcion: form.fecha_recepcion,
      });
      setExito(`Tarja N° ${registrada.numero_tarja} registrada: ${registrada.kilos_netos} kg netos`);
      // Conserva productor y fecha; limpia los demás datos de la recepción.
      setSistemaId("");
      setEspecieId("");
      setVariedadId("");
      setCalidadId("");
      setBandejaId("");
      setForm(formularioVacio(form.fecha_recepcion));
      setRecargaPendientes((valor) => valor + 1);
    } catch (errorRecibido) {
      setError(extraerMensajeError(errorRecibido, "No se pudo registrar la tarja"));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 3. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E3 · Recepción</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Recepción</h1>
        <p className="mt-2 text-sm text-slate-500">Registre la fruta recibida y revise los kilos netos antes de guardar.</p>
      </div>

      {errorCarga && <p className={MENSAJE_ERROR} role="alert">{errorCarga}</p>}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}
      {exito && <p className={MENSAJE_EXITO} role="status">{exito}</p>}

      {/* Formulario grande dividido según el flujo operativo. */}
      <form ref={formularioRef} onSubmit={guardar} onKeyDown={avanzarConEnter} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <fieldset disabled={guardando}>
          <div className="mb-5">
            <h2 className="font-semibold text-frigorifico-900">Datos de la recepción</h2>
            <p className="mt-1 text-xs text-slate-500">El número, la tara histórica y los kilos netos los confirma el sistema.</p>
          </div>

          {/* Productor y acumulados pendientes. */}
          <SelectorProductor
            id="recepcion-productor"
            valor={productor}
            onChange={cambiarProductor}
            elegirPrimeroConEnter
          />
          {productor && (
            <div className="mt-3 rounded border border-slate-200 bg-frigorifico-50 px-3 py-2 text-sm text-slate-600" role="status" aria-live="polite">
              {cargandoPendientes
                ? "Consultando pendientes…"
                : errorPendientes
                  ? <span className="text-red-700">{errorPendientes}</span>
                  : `${pendientes?.tarjas_sin_procesar ?? 0} tarjas y ${pendientes?.kilos_sin_procesar ?? 0} kg sin procesar`}
            </div>
          )}

          {/* Información de la fruta y calidad visual. */}
          <section className="mt-6 border-t border-slate-200 pt-5">
            <h3 className={SUBTITULO}>Fruta</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <SelectorCatalogo id="recepcion-sistema" etiqueta="Sistema productivo" opciones={sistemas} valor={sistemaId} onChange={setSistemaId} deshabilitado={cargando} textoVacio={textoVacio} />
              <SelectorCatalogo id="recepcion-especie" etiqueta="Especie" opciones={especies} valor={especieId} onChange={cambiarEspecie} deshabilitado={cargando} textoVacio={textoVacio} />
              <SelectorCatalogo id="recepcion-variedad" etiqueta="Variedad" opciones={variedades} valor={variedadId} onChange={setVariedadId} deshabilitado={!especieId || cargandoVariedades} textoVacio={textoVariedad} />
              <SelectorCatalogo id="recepcion-calidad" etiqueta="Calidad" opciones={calidades} valor={calidadId} onChange={setCalidadId} deshabilitado={cargando} textoVacio={textoVacio} />
              <div>
                <label htmlFor="recepcion-porcentaje" className={ETIQUETA}>Calidad visual (%)</label>
                <input id="recepcion-porcentaje" name="porcentaje_calidad" type="number" min="0" max="100" step="1" value={form.porcentaje_calidad} onChange={cambiarCampo} className={form.porcentaje_calidad && !calidadValida ? CAMPO_ERROR : CAMPO} aria-invalid={form.porcentaje_calidad !== "" && !calidadValida} aria-describedby={form.porcentaje_calidad && !calidadValida ? "recepcion-porcentaje-error" : undefined} required />
                {form.porcentaje_calidad && !calidadValida && <p id="recepcion-porcentaje-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un entero entre 0 y 100.</p>}
              </div>
            </div>
            {errorVariedades && <p className={`mt-3 ${MENSAJE_ERROR}`} role="alert">{errorVariedades}</p>}
          </section>

          {/* Pesos de balanza, bandejas, pallet y fecha operacional. */}
          <section className="mt-6 border-t border-slate-200 pt-5">
            <h3 className={SUBTITULO}>Pesos</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <SelectorCatalogo id="recepcion-bandeja" etiqueta="Tipo de bandeja" opciones={opcionesBandeja} valor={bandejaId} onChange={setBandejaId} deshabilitado={cargando} textoVacio={textoVacio} ayuda="Entre paréntesis se muestra la tara que se copiará." />
              <div>
                <label htmlFor="recepcion-cantidad" className={ETIQUETA}>Cantidad de bandejas</label>
                <input id="recepcion-cantidad" name="cantidad_bandejas" type="number" min="1" max={MAX_BANDEJAS} step="1" value={form.cantidad_bandejas} onChange={cambiarCampo} className={form.cantidad_bandejas && !cantidadValida ? CAMPO_ERROR : CAMPO} aria-invalid={form.cantidad_bandejas !== "" && !cantidadValida} aria-describedby={form.cantidad_bandejas && !cantidadValida ? "recepcion-cantidad-error" : undefined} required />
                {form.cantidad_bandejas && !cantidadValida && <p id="recepcion-cantidad-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese entre 1 y {MAX_BANDEJAS} bandejas.</p>}
              </div>
              <div>
                <label htmlFor="recepcion-pallet" className={ETIQUETA}>Peso del pallet (kg)</label>
                <input id="recepcion-pallet" name="peso_pallet_kg" type="number" min="0" max="100" step="0.01" value={form.peso_pallet_kg} onChange={cambiarCampo} className={!palletValido ? CAMPO_ERROR : CAMPO} aria-invalid={!palletValido} aria-describedby={!palletValido ? "recepcion-pallet-error" : undefined} required />
                {!palletValido && <p id="recepcion-pallet-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un peso entre 0 y 100 kg.</p>}
              </div>
              <div>
                <label htmlFor="recepcion-brutos" className={ETIQUETA}>Kilos de balanza</label>
                <input id="recepcion-brutos" name="kilos_brutos" type="number" min="0.01" max="5000" step="0.01" value={form.kilos_brutos} onChange={cambiarCampo} className={form.kilos_brutos && !brutosValidos ? CAMPO_ERROR : CAMPO} aria-invalid={form.kilos_brutos !== "" && !brutosValidos} aria-describedby={form.kilos_brutos && !brutosValidos ? "recepcion-brutos-error" : undefined} required />
                {form.kilos_brutos && !brutosValidos && <p id="recepcion-brutos-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un peso mayor que 0 y hasta 5.000 kg.</p>}
              </div>
              <div>
                <label htmlFor="recepcion-fecha" className={ETIQUETA}>Fecha de recepción</label>
                <input id="recepcion-fecha" name="fecha_recepcion" type="date" max={fechaHoy} value={form.fecha_recepcion} onChange={cambiarCampo} className={!fechaValida ? CAMPO_ERROR : CAMPO} aria-invalid={!fechaValida} aria-describedby={!fechaValida ? "recepcion-fecha-error" : undefined} required />
                {!fechaValida && <p id="recepcion-fecha-error" className="mt-1 text-xs text-red-700" role="alert">La fecha no puede ser posterior a hoy.</p>}
              </div>
            </div>
          </section>

          {/* Vista previa calculada con el mismo redondeo bancario del backend. */}
          <section className="mt-6 border-t border-slate-200 pt-5" aria-live="polite">
            <h3 className={SUBTITULO}>Cálculo</h3>
            <div className={`mt-3 rounded border px-4 py-3 ${kilosNetos !== null && !netoValido ? "border-red-200 bg-red-50" : "border-slate-200 bg-frigorifico-50"}`}>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-semibold text-slate-500">Kilos netos</dt>
                  <dd className={`mt-1 text-2xl font-bold ${kilosNetos !== null && !netoValido ? "text-red-700" : "text-frigorifico-900"}`}>{kilosNetos === null ? "—" : `${kilosNetos} kg`}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-slate-500">Promedio por bandeja</dt>
                  <dd className="mt-1 text-2xl font-bold text-frigorifico-900">{promedioCentimos === null ? "—" : `${formatearCentimos(promedioCentimos)} kg`}</dd>
                </div>
              </dl>
              {kilosNetos !== null && !netoValido && <p className="mt-2 text-sm text-red-700">Los kilos netos deben ser mayores que cero; revise los pesos.</p>}
            </div>
          </section>

          {/* Guardar es la única acción que envía el formulario. */}
          <div className="mt-6 border-t border-slate-200 pt-5">
            <button type="submit" disabled={!formularioValido || guardando} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
            <p className={AYUDA}>Enter avanza al siguiente campo; solo este botón registra la tarja.</p>
          </div>
        </fieldset>
      </form>
    </div>
  );
}
