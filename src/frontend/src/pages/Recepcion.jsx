// Estado, efectos y referencia del formulario de recepción.
import { useEffect, useRef, useState } from "react";
// Lleva a la hoja de impresión al guardar y recibe lo que se conserva de la tarja anterior.
import { useLocation, useNavigate, useParams } from "react-router-dom";
// Traduce errores HTTP a mensajes legibles sin borrar lo escrito.
import { extraerMensajeError } from "../api/client";
// Catálogos activos usados por la recepción.
import { listarCalidades, listarEspecies, listarSistemasProductivos, listarTiposBandeja, listarVariedades } from "../api/opciones";
// Escritura de tarjas y acumulados del productor.
import { editarTarja, obtenerTarja, pendientesProductor, registrarTarja, saldoBandejasProductor } from "../api/tarjas";
// Selectores compartidos de HU11.
import SelectorCatalogo from "../components/SelectorCatalogo";
import SelectorProductor from "../components/SelectorProductor";
// Semáforo del saldo de bandejas, igual que el del legado.
import { situacionBandejas } from "../components/saldoBandejas";
// Clases comunes de formularios y mensajes.
import { AYUDA, BOTON_PRINCIPAL, BOTON_SECUNDARIO, CAMPO, CAMPO_ERROR, ETIQUETA, MENSAJE_ERROR, SUBTITULO } from "../components/catalogo";

// Capacidades técnicas de SQL Server y de los DECIMAL definidos en TarjaCreate.
// La planta confirmó que no existen máximos operativos para estos tres valores.
// Mayor cantidad de bandejas que admite una columna INT.
const MAX_INT_SQL_SERVER = 2147483647;
// Mayor pallet que admite DECIMAL(8,2), en centésimos.
const MAX_PALLET_CENTIMOS = 99999999;
// Mayor peso de balanza que admite DECIMAL(10,2), en centésimos.
const MAX_BALANZA_CENTIMOS = 9999999999;

// Obtiene YYYY-MM-DD usando el día de la planta y no la fecha UTC del navegador.
// Sin argumento usa el momento actual; con un instante, entrega el día de ese instante en Chile.
function hoyEnChile(instante = new Date()) {
  // en-CA entrega el orden año, mes y día.
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Santiago", // Zona horaria de la planta.
    year: "numeric", // Año con cuatro dígitos.
    month: "2-digit", // Mes con dos dígitos.
    day: "2-digit", // Día con dos dígitos.
  }).formatToParts(instante);
  // Busca una de las partes por su tipo.
  const valor = (tipo) => partes.find((parte) => parte.type === tipo)?.value;
  // Arma el formato que usa el campo de fecha.
  return `${valor("year")}-${valor("month")}-${valor("day")}`;
}

// Día en Chile de una fecha y hora que la API entrega en UTC sin zona (por ejemplo fecha_hora).
function diaEnChile(valorUtc) {
  // Sin la "Z", el navegador la leería como hora local; si ya trae zona, se respeta.
  const conZona = /(Z|[+-]\d{2}:\d{2})$/i.test(valorUtc) ? valorUtc : `${valorUtc}Z`;
  // Convierte el instante al día de la planta.
  return hoyEnChile(new Date(conZona));
}

// Muestra YYYY-MM-DD como dd-mm-aaaa, el formato de los mensajes.
function formatearDia(iso) {
  // Separa año, mes y día.
  const [anio, mes, dia] = iso.split("-");
  // Los ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Agrega a una lista de activos el valor que la tarja ya tenía, si después se desactivó (HU20, B3).
// Solo ese valor aparece: los demás inactivos siguen fuera de la lista.
function conValorDeLaTarja(opciones, id, nombre, aviso) {
  // Sin valor original, o si sigue activo, la lista no cambia.
  if (id == null || opciones.some((opcion) => String(opcion.id) === String(id))) return opciones;
  // Lo agrega al final con un aviso visible.
  return [...opciones, { id, nombre: `${nombre} (${aviso})` }];
}

// Convierte un decimal escrito a centésimos exactos; null indica entrada incompleta.
function aCentimos(valor) {
  // Acepta la coma decimal que escribe el operador.
  const texto = String(valor ?? "").trim().replace(",", ".");
  // Solo dígitos con hasta dos decimales, sin signo.
  if (!/^\d+(?:\.\d{0,2})?$/.test(texto)) return null;
  // Separa enteros y decimales para no pasar por float.
  const [enteros, decimales = ""] = texto.split(".");
  // Completa los decimales a dos dígitos y suma los centésimos.
  return Number(enteros) * 100 + Number(decimales.padEnd(2, "0"));
}

// Redondea una fracción al entero par más cercano, igual que ROUND_HALF_EVEN.
export function redondearBancario(numerador, denominador = 100) {
  // Conserva el signo para aplicarlo al final.
  const signo = numerador < 0 ? -1 : 1;
  // Trabaja con el valor absoluto.
  const absoluto = Math.abs(numerador);
  // Parte entera de la división.
  const entero = Math.floor(absoluto / denominador);
  // Lo que falta dividir.
  const resto = absoluto % denominador;
  // Compara el resto con la mitad sin usar decimales.
  const dobleResto = resto * 2;
  // Bajo la mitad baja, sobre la mitad sube y justo en la mitad va al par.
  const redondeado = dobleResto < denominador
    ? entero
    : dobleResto > denominador
      ? entero + 1
      : entero % 2 === 0 ? entero : entero + 1;
  // Devuelve el resultado con su signo.
  return signo * redondeado;
}

// Formatea centésimos como kilos con dos decimales y coma visible.
function formatearCentimos(centimos) {
  // Solo para mostrar; el cálculo ya se hizo con enteros.
  return (centimos / 100).toFixed(2).replace(".", ",");
}

// Valores que se limpian después de registrar, conservando la fecha aparte.
function formularioVacio(fecha) {
  // Todos son texto hasta el momento de enviarlos.
  return {
    porcentaje_calidad: "", // Calidad visual, sin valor inicial.
    cantidad_bandejas: "", // Cantidad de bandejas, sin valor inicial.
    peso_pallet_kg: "0", // La fruta puede llegar sin pallet.
    kilos_brutos: "", // Peso de balanza, sin valor inicial.
    fecha_recepcion: fecha, // Fecha indicada por el llamador.
  };
}

// Formulario operativo para registrar tarjas de recepción.
export default function Recepcion() {
  // Navegación a la hoja de impresión.
  const navigate = useNavigate();
  // Identifica la tarja cuando esta misma pantalla se usa para corregirla.
  const { id: tarjaId } = useParams();
  // Distingue registro nuevo de edición sin confiar solo en la URL visual.
  const editando = Boolean(tarjaId);
  // Productor y fecha que vuelven desde la hoja, para seguir con la siguiente tarja.
  const { state: anterior } = useLocation();
  // Día de hoy en la planta, para el valor inicial y el máximo de la fecha.
  const fechaHoy = hoyEnChile();
  // Permite recorrer los campos del formulario al presionar Enter.
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
  const [productor, setProductor] = useState(anterior?.productor ?? null);
  const [sistemaId, setSistemaId] = useState("");
  const [especieId, setEspecieId] = useState("");
  const [variedadId, setVariedadId] = useState("");
  const [calidadId, setCalidadId] = useState("");
  const [bandejaId, setBandejaId] = useState("");
  // Datos numéricos y fecha que escribe el operador.
  const [form, setForm] = useState(() => formularioVacio(anterior?.fecha_recepcion ?? fechaHoy));
  // Acumulados del productor.
  const [pendientes, setPendientes] = useState(null);
  const [cargandoPendientes, setCargandoPendientes] = useState(false);
  const [errorPendientes, setErrorPendientes] = useState("");
  // Saldo de bandejas del productor, por tipo (HU15).
  const [saldos, setSaldos] = useState([]);
  const [errorSaldos, setErrorSaldos] = useState("");
  // Estado de escritura y mensaje de error; el éxito se avisa en la hoja de impresión.
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  // Conserva la tara histórica y el detalle inicial durante una corrección.
  const [tarjaOriginal, setTarjaOriginal] = useState(null);
  // Explica la corrección y el backend también la valida como obligatoria.
  const [motivo, setMotivo] = useState("");

  // Carga el detalle al editar y llena el mismo formulario operativo de recepción.
  useEffect(() => {
    // Una recepción nueva no necesita detalle previo.
    if (!editando || cargando) return undefined;
    // Evita escribir estado si la ruta cambia antes de responder.
    let vigente = true;
    // Obtiene la tarja protegida por los mismos permisos del backend.
    async function cargarTarja() {
      try {
        // Pide el detalle completo con los nombres que necesita el formulario.
        const detalle = await obtenerTarja(tarjaId);
        // Una respuesta tardía no debe sobrescribir otra pantalla.
        if (!vigente) return;
        // Conserva la tara propia, que puede diferir de la tara vigente del catálogo.
        setTarjaOriginal(detalle);
        // Arma el productor en el formato que consume SelectorProductor.
        setProductor({ id: detalle.productor_id, codigo: detalle.productor_codigo, rut: detalle.productor_rut, razon_social: detalle.productor_razon_social });
        // Precarga cada selector con el valor guardado en la tarja.
        setSistemaId(String(detalle.sistema_productivo_id));
        // La especie se elige por id, no por nombre: así funciona aunque esté desactivada (B3).
        setEspecieId(String(detalle.especie_id));
        setVariedadId(String(detalle.variedad_id));
        setCalidadId(String(detalle.calidad_id));
        setBandejaId(String(detalle.tipo_bandeja_id));
        // Mantiene los decimales como texto, igual que el registro nuevo.
        setForm({ cantidad_bandejas: String(detalle.cantidad_bandejas), peso_pallet_kg: String(detalle.peso_pallet_kg), kilos_brutos: String(detalle.kilos_brutos), porcentaje_calidad: String(detalle.porcentaje_calidad), fecha_recepcion: detalle.fecha_recepcion });
      } catch (errorRecibido) {
        // Informa el bloqueo o la ausencia sin mostrar valores inventados.
        if (vigente) setError(extraerMensajeError(errorRecibido, "No se pudo cargar la tarja para corregir"));
      }
    }
    // Inicia la carga de la tarja elegida.
    cargarTarja();
    // Marca obsoleta la petición al desmontar.
    return () => { vigente = false; };
  }, [cargando, editando, tarjaId]);

  // Al volver con el productor ya elegido, el cursor parte en el primer catálogo,
  // cuando terminan de cargar las listas: antes esa lista está deshabilitada.
  useEffect(() => {
    if (!cargando && anterior?.productor) document.getElementById("recepcion-sistema")?.focus();
    // Solo cuando termina la carga inicial.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargando]);

  // Carga en paralelo los catálogos que no dependen de otra selección.
  useEffect(() => {
    // Evita actualizar el estado si la pantalla ya se cerró.
    let vigente = true;
    // Encapsula la carga asíncrona del efecto.
    async function cargarCatalogos() {
      try {
        // Las cuatro listas se piden a la vez.
        const [listaEspecies, listaCalidades, listaSistemas, listaBandejas] = await Promise.all([
          listarEspecies(),
          listarCalidades(),
          listarSistemasProductivos(),
          listarTiposBandeja(),
        ]);
        // Guarda las listas solo si la pantalla sigue abierta.
        if (vigente) {
          setEspecies(listaEspecies);
          setCalidades(listaCalidades);
          setSistemas(listaSistemas);
          setBandejas(listaBandejas);
        }
      } catch (errorRecibido) {
        // Muestra el error de carga sobre el formulario.
        if (vigente) setErrorCarga(extraerMensajeError(errorRecibido, "No se pudieron cargar las listas"));
      } finally {
        // Termina el estado de carga en ambos casos.
        if (vigente) setCargando(false);
      }
    }
    // Inicia la carga.
    cargarCatalogos();
    // Marca como obsoleta cualquier respuesta posterior al cierre.
    return () => { vigente = false; };
  }, []);

  // Obtiene las variedades activas cada vez que cambia la especie.
  useEffect(() => {
    // Sin especie no hay variedades que pedir.
    if (!especieId) {
      setVariedades([]);
      setErrorVariedades("");
      return undefined;
    }
    // Descarta la respuesta si la especie cambió mientras llegaba.
    let vigente = true;
    // Encapsula la carga asíncrona del efecto.
    async function cargarVariedades() {
      // Limpia la lista de la especie anterior.
      setCargandoVariedades(true);
      setErrorVariedades("");
      setVariedades([]);
      try {
        // Pide las variedades de la especie elegida.
        const lista = await listarVariedades(Number(especieId));
        // Guarda la lista si la especie no cambió.
        if (vigente) setVariedades(lista);
      } catch (errorRecibido) {
        // Muestra el error bajo los selectores.
        if (vigente) setErrorVariedades(extraerMensajeError(errorRecibido, "No se pudieron cargar las variedades"));
      } finally {
        // Termina el estado de carga en ambos casos.
        if (vigente) setCargandoVariedades(false);
      }
    }
    // Inicia la carga.
    cargarVariedades();
    // Marca como obsoleta la respuesta de la especie anterior.
    return () => { vigente = false; };
  }, [especieId]);

  // Muestra los acumulados del productor elegido.
  useEffect(() => {
    // Sin productor no hay acumulados.
    if (!productor) {
      setPendientes(null);
      setErrorPendientes("");
      return undefined;
    }
    // Descarta la respuesta si el productor cambió mientras llegaba.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargarPendientes() {
      // Muestra el aviso de consulta.
      setCargandoPendientes(true);
      setErrorPendientes("");
      try {
        // Pide las tarjas y kilos sin procesar (decisión D).
        const acumulados = await pendientesProductor(productor.id);
        // Guarda el resultado si el productor no cambió.
        if (vigente) setPendientes(acumulados);
      } catch (errorRecibido) {
        // Un error aquí no impide registrar la tarja.
        if (vigente) {
          setPendientes(null);
          setErrorPendientes(extraerMensajeError(errorRecibido, "No se pudieron consultar los pendientes"));
        }
      } finally {
        // Termina el estado de consulta en ambos casos.
        if (vigente) setCargandoPendientes(false);
      }
    }
    // Inicia la consulta.
    cargarPendientes();
    // Marca como obsoleta la respuesta del productor anterior.
    return () => { vigente = false; };
  }, [productor]);

  // Consulta el saldo de bandejas del productor elegido (HU15).
  useEffect(() => {
    // Sin productor no hay saldo.
    if (!productor) {
      setSaldos([]);
      setErrorSaldos("");
      return undefined;
    }
    // Descarta la respuesta si el productor cambió mientras llegaba.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargarSaldos() {
      setErrorSaldos("");
      try {
        // Pide el saldo por tipo de bandeja.
        const lista = await saldoBandejasProductor(productor.id);
        // Guarda el resultado si sigue vigente.
        if (vigente) setSaldos(lista);
      } catch (errorRecibido) {
        // Un error aquí no impide registrar la tarja.
        if (vigente) {
          setSaldos([]);
          setErrorSaldos(extraerMensajeError(errorRecibido, "No se pudo consultar el saldo de bandejas"));
        }
      }
    }
    // Inicia la consulta.
    cargarSaldos();
    // Marca como obsoleta la respuesta anterior.
    return () => { vigente = false; };
  }, [productor]);

  // Selecciona la bandeja completa para leer su tara sin usar float.
  const bandeja = bandejas.find((opcion) => String(opcion.id) === bandejaId);
  // Al corregir, indica si se conserva el tipo de bandeja que tenía la tarja.
  const mismaBandeja = Boolean(editando && tarjaOriginal && bandejaId === String(tarjaOriginal.tipo_bandeja_id));
  // Igual que el backend (criterio 4): mismo tipo, tara de la tarja; otro tipo, tara vigente del catálogo.
  const taraCentimos = mismaBandeja ? aCentimos(tarjaOriginal.tara_kg) : bandeja ? aCentimos(bandeja.peso_tara_kg) : null;
  // Pesos en centésimos enteros, igual de exactos que los Decimal del backend.
  const palletCentimos = aCentimos(form.peso_pallet_kg);
  const brutosCentimos = aCentimos(form.kilos_brutos);
  // Valores numéricos de los campos enteros.
  const cantidad = Number(form.cantidad_bandejas);
  const calidad = Number(form.porcentaje_calidad);
  // Validación en el momento, con los mismos límites técnicos de TarjaCreate.
  const cantidadValida = Number.isInteger(cantidad) && cantidad > 0 && cantidad <= MAX_INT_SQL_SERVER;
  const calidadValida = form.porcentaje_calidad !== ""
    && Number.isInteger(calidad)
    && calidad >= 0
    && calidad <= 100;
  const palletValido = palletCentimos !== null && palletCentimos >= 0 && palletCentimos <= MAX_PALLET_CENTIMOS;
  const brutosValidos = brutosCentimos !== null && brutosCentimos > 0 && brutosCentimos <= MAX_BALANZA_CENTIMOS;
  // Al corregir, la recepción no puede quedar después del día en que se registró la tarja (B2).
  const diaRegistro = editando && tarjaOriginal ? diaEnChile(tarjaOriginal.fecha_hora) : null;
  // En un registro nuevo el máximo sigue siendo hoy.
  const fechaMaxima = diaRegistro ?? fechaHoy;
  // Las fechas YYYY-MM-DD se pueden comparar como texto.
  const fechaValida = form.fecha_recepcion !== "" && form.fecha_recepcion <= fechaMaxima;
  // Neto = brutos − bandejas × tara − pallet, en cuanto estén los datos.
  const netoCentimos = cantidadValida && taraCentimos !== null && palletCentimos !== null && brutosCentimos !== null
    ? brutosCentimos - cantidad * taraCentimos - palletCentimos
    : null;
  // Mismo redondeo bancario del backend; Math.round daría otro resultado en las mitades.
  const kilosNetos = netoCentimos === null ? null : redondearBancario(netoCentimos);
  // Promedio por bandeja con dos decimales (HU14 criterio 3).
  const promedioCentimos = kilosNetos !== null && cantidadValida
    ? redondearBancario(kilosNetos * 100, cantidad)
    : null;
  // HU14 criterio 2: el neto no puede ser negativo ni cero.
  const netoValido = kilosNetos !== null && kilosNetos > 0;
  // Solo una tarja recepcionada se corrige; una parcial, procesada o anulada muestra el bloqueo (B4).
  const corregible = !editando || tarjaOriginal?.estado === "RECEPCIONADA";
  // Criterio 7: al corregir hay que cambiar al menos un dato. Los pesos se comparan en centésimos ("20" = "20.00").
  const hayCambios = !editando || Boolean(tarjaOriginal && (
    productor?.id !== tarjaOriginal.productor_id
    || sistemaId !== String(tarjaOriginal.sistema_productivo_id)
    || variedadId !== String(tarjaOriginal.variedad_id)
    || calidadId !== String(tarjaOriginal.calidad_id)
    || bandejaId !== String(tarjaOriginal.tipo_bandeja_id)
    || cantidad !== tarjaOriginal.cantidad_bandejas
    || calidad !== tarjaOriginal.porcentaje_calidad
    || palletCentimos !== aCentimos(tarjaOriginal.peso_pallet_kg)
    || brutosCentimos !== aCentimos(tarjaOriginal.kilos_brutos)
    || form.fecha_recepcion !== tarjaOriginal.fecha_recepcion
  ));
  // Guardar se habilita solo con todo completo y correcto.
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
    && netoValido
    // Al corregir, además: tarja corregible, motivo escrito y algún dato cambiado.
    && (!editando || (corregible && motivo.trim() !== "" && hayCambios)),
  );

  // Saldo actual del productor en la bandeja elegida; sin movimientos, está al día.
  const saldoActual = saldos.find((fila) => String(fila.tipo_bandeja_id) === bandejaId)?.saldo ?? 0;
  // En edición, el saldo ya incluye la entrada original cuando se conserva productor y bandeja.
  const reemplazaMovimientoOriginal = Boolean(
    editando
    && tarjaOriginal
    && productor?.id === tarjaOriginal.productor_id
    && String(bandejaId) === String(tarjaOriginal.tipo_bandeja_id),
  );
  // Sustituye la cantidad original por la corregida; al cambiar productor o bandeja, suma una nueva entrada.
  const saldoProyectado = cantidadValida
    ? saldoActual + cantidad - (reemplazaMovimientoOriginal ? tarjaOriginal.cantidad_bandejas : 0)
    : null;
  // Semáforo del saldo, igual que el Form4 del legado.
  const situacionSaldo = situacionBandejas(saldoActual);

  // Etiquetas de bandeja con la tara que se usará, para anticipar el cálculo.
  const opcionesBandeja = bandejas.map((opcion) => ({
    id: opcion.id, // Identificador que se envía a la API.
    // Al corregir, el tipo original muestra la tara de la tarja; los demás, la vigente del catálogo.
    nombre: `${opcion.nombre} (${String(editando && tarjaOriginal && opcion.id === tarjaOriginal.tipo_bandeja_id ? tarjaOriginal.tara_kg : opcion.peso_tara_kg).replace(".", ",")} kg)`,
  }));
  // Al corregir, cada lista incluye el valor original aunque se haya desactivado (B3).
  const opcionesSistema = editando && tarjaOriginal ? conValorDeLaTarja(sistemas, tarjaOriginal.sistema_productivo_id, tarjaOriginal.sistema_productivo, "inactivo") : sistemas;
  const opcionesEspecie = editando && tarjaOriginal ? conValorDeLaTarja(especies, tarjaOriginal.especie_id, tarjaOriginal.especie, "inactiva") : especies;
  // La variedad original solo pertenece a la lista de su propia especie.
  const opcionesVariedad = editando && tarjaOriginal && especieId === String(tarjaOriginal.especie_id)
    ? conValorDeLaTarja(variedades, tarjaOriginal.variedad_id, tarjaOriginal.variedad, "inactiva")
    : variedades;
  const opcionesCalidad = editando && tarjaOriginal ? conValorDeLaTarja(calidades, tarjaOriginal.calidad_id, tarjaOriginal.calidad, "inactiva") : calidades;
  // El tipo de bandeja original, si se desactivó, aparece con la tara de la tarja.
  const opcionesBandejaFinal = editando && tarjaOriginal
    ? conValorDeLaTarja(opcionesBandeja, tarjaOriginal.tipo_bandeja_id, `${tarjaOriginal.tipo_bandeja} (${String(tarjaOriginal.tara_kg).replace(".", ",")} kg)`, "inactivo")
    : opcionesBandeja;
  // Primer texto de los selectores según el estado de carga.
  const textoVacio = cargando ? "Cargando…" : "Seleccione…";
  // Primer texto del selector de variedades según la especie.
  const textoVariedad = !especieId
    ? "Elija primero una especie"
    : cargandoVariedades ? "Cargando…" : variedades.length ? "Seleccione…" : "Sin variedades activas";

  // Cambia una entrada sin convertirla prematuramente a float.
  function cambiarCampo(evento) {
    // El nombre del campo coincide con la clave del formulario.
    const { name, value } = evento.target;
    // Actualiza solo ese campo.
    setForm((anterior) => ({ ...anterior, [name]: value }));
    // Un cambio deja obsoleto el error anterior.
    setError("");
  }

  // Una especie nueva invalida la variedad que pertenecía a la anterior.
  function cambiarEspecie(id) {
    setEspecieId(id);
    setVariedadId("");
  }

  // Tras elegir con clic o Enter, continúa en el primer catálogo del flujo.
  function cambiarProductor(productorElegido) {
    // Guarda el productor elegido, o null al cambiarlo.
    setProductor(productorElegido);
    // Espera a que el formulario se actualice antes de mover el foco.
    if (productorElegido) {
      requestAnimationFrame(() => document.getElementById("recepcion-sistema")?.focus());
    }
  }

  // Enter avanza al siguiente campo y nunca envía el formulario desde un campo (HU12 criterio 6).
  function avanzarConEnter(evento) {
    // Las demás teclas siguen su comportamiento normal.
    if (evento.key !== "Enter") return;
    // En un botón, Enter hace lo normal: pulsarlo (Guardar, Cambiar o un resultado de la búsqueda).
    if (evento.target.tagName === "BUTTON") return;
    // En un campo, Enter no debe enviar el formulario.
    // El motivo admite varias líneas y Enter debe conservar su edición natural.
    if (evento.target.tagName === "TEXTAREA") return;
    evento.preventDefault();
    // El buscador de productores maneja su propio Enter.
    if (evento.target.type === "search") return;
    // Recorre los campos en orden y termina en Guardar; incluye el motivo para que el último campo lleve a él (O2).
    const campos = [...formularioRef.current.querySelectorAll("input, select, textarea, button[type='submit']")]
      .filter((campo) => !campo.disabled && campo.type !== "search");
    // Posición del campo actual.
    const indice = campos.indexOf(evento.target);
    // Pasa al siguiente; en el último no hace nada.
    campos[indice + 1]?.focus();
  }

  // Envía solo los campos admitidos por TarjaCreate.
  async function guardar(evento) {
    // Evita la navegación nativa del formulario.
    evento.preventDefault();
    // El backend vuelve a validar, pero aquí no se envía nada incompleto.
    if (!formularioValido || guardando) {
      setError("Complete los datos y corrija los valores antes de guardar.");
      return;
    }
    // Bloquea el formulario mientras responde la API.
    setGuardando(true);
    setError("");
    try {
      // Número, tara, kilos netos, estado y usuario los pone el sistema.
      const datosTarja = {
        productor_id: productor.id, // Productor elegido.
        sistema_productivo_id: Number(sistemaId), // Sistema productivo elegido.
        variedad_id: Number(variedadId), // Variedad elegida.
        calidad_id: Number(calidadId), // Calidad elegida.
        tipo_bandeja_id: Number(bandejaId), // Tipo de bandeja elegido.
        cantidad_bandejas: cantidad, // Cantidad de bandejas.
        peso_pallet_kg: form.peso_pallet_kg.replace(",", "."), // Decimal como texto, sin float.
        kilos_brutos: form.kilos_brutos.replace(",", "."), // Decimal como texto, sin float.
        porcentaje_calidad: calidad, // Calidad visual.
        fecha_recepcion: form.fecha_recepcion, // Día de llegada de la fruta.
      };
      // La corrección conserva el número y abre la hoja para reimprimirla (criterio 6).
      if (editando) {
        // La API devuelve la tarja corregida.
        const corregida = await editarTarja(tarjaId, { ...datosTarja, motivo: motivo.trim() });
        // La hoja pegada en el pallet quedó con los datos antiguos: se abre para reemplazarla.
        navigate(`/tarjas/${corregida.id}/imprimir`, { state: { recienCorregida: true } });
        return;
      }
      // El registro nuevo abre su hoja de impresión al terminar.
      const registrada = await registrarTarja(datosTarja);
      // Igual que el legado y socradex: al guardar se abre la tarja para imprimirla (HU16).
      navigate(`/tarjas/${registrada.id}/imprimir`, {
        state: {
          recienRegistrada: true, // La hoja avisa que se registró.
          productor, // Se conserva para la siguiente tarja.
          fecha_recepcion: form.fecha_recepcion, // También la fecha.
        },
      });
    } catch (errorRecibido) {
      // Muestra el error sin borrar lo escrito.
      setError(extraerMensajeError(errorRecibido, editando ? "No se pudo corregir la tarja" : "No se pudo registrar la tarja"));
    } finally {
      // Libera el formulario en ambos casos.
      setGuardando(false);
    }
  }

  // Renderiza el encabezado, los mensajes y el formulario grande.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 3. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E3 · Recepción</p>
        {/* Al corregir, el título nombra la tarja apenas carga (B4). */}
        <h1 className="text-2xl font-bold text-frigorifico-900">{editando ? `Corregir tarja N° ${tarjaOriginal?.numero_tarja ?? "…"}` : "Recepción"}</h1>
        <p className="mt-2 text-sm text-slate-500">{editando ? "Corrija el dato digitado e indique el motivo. Si cambia el tipo de bandeja, se usa la tara vigente del tipo nuevo." : "Registre la fruta recibida y revise los kilos netos antes de guardar."}</p>
      </div>

      {/* Errores de carga y de la última escritura. */}
      {errorCarga && <p className={MENSAJE_ERROR} role="alert">{errorCarga}</p>}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {/* Una tarja parcial, procesada (también con merma rebajada) o anulada no muestra el formulario (B4). */}
      {editando && tarjaOriginal && !corregible ? (
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <p className={MENSAJE_ERROR} role="alert">La tarja N° {tarjaOriginal.numero_tarja} está {tarjaOriginal.estado.toLowerCase()} y no se puede corregir.</p>
          {/* Salida sin guardar nada. */}
          <button type="button" onClick={() => navigate("/tarjas")} className={BOTON_SECUNDARIO}>Volver a Tarjas</button>
        </div>
      ) : (
      /* Formulario grande dividido según el flujo operativo. */
      <form
        ref={formularioRef}
        onSubmit={guardar}
        onKeyDown={avanzarConEnter}
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
      >
        {/* Mientras se guarda, ningún campo se puede cambiar. */}
        <fieldset disabled={guardando}>
          {/* Cabecera del formulario. */}
          <div className="mb-5">
            <h2 className="font-semibold text-frigorifico-900">Datos de la recepción</h2>
            <p className="mt-1 text-xs text-slate-500">El número, la tara histórica y los kilos netos los confirma el sistema.</p>
          </div>

          {/* Productor, buscado por código, RUT o razón social. */}
          <SelectorProductor
            id="recepcion-productor"
            valor={productor}
            onChange={cambiarProductor}
            elegirPrimeroConEnter
          />
          {/* Acumulados del productor elegido (decisión D). */}
          {productor && (
            <div className="mt-3 rounded border border-slate-200 bg-frigorifico-50 px-3 py-2 text-sm text-slate-600" role="status" aria-live="polite">
              {cargandoPendientes
                ? "Consultando pendientes…"
                : errorPendientes
                  ? <span className="text-red-700">{errorPendientes}</span>
                  // Desde HU18 los kilos traen decimales: ",00" no aporta y los demás se muestran con coma.
                  : `${pendientes?.tarjas_sin_procesar ?? 0} tarjas y ${String(pendientes?.kilos_sin_procesar ?? 0).replace(/\.00$/, "").replace(".", ",")} kg sin procesar`}
            </div>
          )}

          {/* Información de la fruta y calidad visual. */}
          <section className="mt-6 border-t border-slate-200 pt-5">
            <h3 className={SUBTITULO}>Fruta</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {/* Sistema productivo activo. */}
              <SelectorCatalogo
                id="recepcion-sistema"
                etiqueta="Sistema productivo"
                opciones={opcionesSistema}
                valor={sistemaId}
                onChange={setSistemaId}
                deshabilitado={cargando}
                textoVacio={textoVacio}
              />
              {/* Especie activa; al cambiarla se limpia la variedad. */}
              <SelectorCatalogo
                id="recepcion-especie"
                etiqueta="Especie"
                opciones={opcionesEspecie}
                valor={especieId}
                onChange={cambiarEspecie}
                deshabilitado={cargando}
                textoVacio={textoVacio}
              />
              {/* Variedades de la especie elegida. */}
              <SelectorCatalogo
                id="recepcion-variedad"
                etiqueta="Variedad"
                opciones={opcionesVariedad}
                valor={variedadId}
                onChange={setVariedadId}
                deshabilitado={!especieId || cargandoVariedades}
                textoVacio={textoVariedad}
              />
              {/* Calidad activa. */}
              <SelectorCatalogo
                id="recepcion-calidad"
                etiqueta="Calidad"
                opciones={opcionesCalidad}
                valor={calidadId}
                onChange={setCalidadId}
                deshabilitado={cargando}
                textoVacio={textoVacio}
              />
              {/* Calidad visual de 0 a 100 (decisión B). */}
              <div>
                <label htmlFor="recepcion-porcentaje" className={ETIQUETA}>Calidad visual (%)</label>
                <input
                  id="recepcion-porcentaje"
                  name="porcentaje_calidad"
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={form.porcentaje_calidad}
                  onChange={cambiarCampo}
                  className={form.porcentaje_calidad && !calidadValida ? CAMPO_ERROR : CAMPO}
                  aria-invalid={form.porcentaje_calidad !== "" && !calidadValida}
                  aria-describedby={form.porcentaje_calidad && !calidadValida ? "recepcion-porcentaje-error" : undefined}
                  required
                />
                {/* Aviso en línea, solo si ya se escribió algo. */}
                {form.porcentaje_calidad && !calidadValida && (
                  <p id="recepcion-porcentaje-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un entero entre 0 y 100.</p>
                )}
              </div>
            </div>
            {/* Error al cargar las variedades de la especie elegida. */}
            {errorVariedades && <p className={`mt-3 ${MENSAJE_ERROR}`} role="alert">{errorVariedades}</p>}
          </section>

          {/* Pesos de balanza, bandejas, pallet y fecha operacional. */}
          <section className="mt-6 border-t border-slate-200 pt-5">
            <h3 className={SUBTITULO}>Pesos</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {/* Tipo de bandeja activo, con su tara. */}
              <SelectorCatalogo
                id="recepcion-bandeja"
                etiqueta="Tipo de bandeja"
                opciones={opcionesBandejaFinal}
                valor={bandejaId}
                onChange={setBandejaId}
                deshabilitado={cargando}
                textoVacio={textoVacio}
                // Al corregir, la tara depende de si el tipo cambia (criterio 4).
                ayuda={editando ? "Entre paréntesis, la tara que se usará: la de la tarja si no cambia el tipo; la vigente si elige otro." : "Entre paréntesis se muestra la tara que se copiará."}
              />
              {/* Cantidad de bandejas. */}
              <div>
                <label htmlFor="recepcion-cantidad" className={ETIQUETA}>Cantidad de bandejas</label>
                <input
                  id="recepcion-cantidad"
                  name="cantidad_bandejas"
                  type="number"
                  min="1"
                  max={MAX_INT_SQL_SERVER}
                  step="1"
                  value={form.cantidad_bandejas}
                  onChange={cambiarCampo}
                  className={form.cantidad_bandejas && !cantidadValida ? CAMPO_ERROR : CAMPO}
                  aria-invalid={form.cantidad_bandejas !== "" && !cantidadValida}
                  aria-describedby={form.cantidad_bandejas && !cantidadValida ? "recepcion-cantidad-error" : undefined}
                  required
                />
                {/* Aviso en línea, solo si ya se escribió algo. */}
                {form.cantidad_bandejas && !cantidadValida && (
                  <p id="recepcion-cantidad-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese una cantidad entera positiva.</p>
                )}
              </div>
              {/* Peso del pallet; parte en 0. */}
              <div>
                <label htmlFor="recepcion-pallet" className={ETIQUETA}>Peso del pallet (kg)</label>
                <input
                  id="recepcion-pallet"
                  name="peso_pallet_kg"
                  type="number"
                  min="0"
                  max="999999.99"
                  step="0.01"
                  value={form.peso_pallet_kg}
                  onChange={cambiarCampo}
                  className={!palletValido ? CAMPO_ERROR : CAMPO}
                  aria-invalid={!palletValido}
                  aria-describedby={!palletValido ? "recepcion-pallet-error" : undefined}
                  required
                />
                {/* Aviso en línea. */}
                {!palletValido && (
                  <p id="recepcion-pallet-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un peso no negativo con hasta dos decimales.</p>
                )}
              </div>
              {/* Peso de balanza. */}
              <div>
                <label htmlFor="recepcion-brutos" className={ETIQUETA}>Kilos de balanza</label>
                <input
                  id="recepcion-brutos"
                  name="kilos_brutos"
                  type="number"
                  min="0.01"
                  max="99999999.99"
                  step="0.01"
                  value={form.kilos_brutos}
                  onChange={cambiarCampo}
                  className={form.kilos_brutos && !brutosValidos ? CAMPO_ERROR : CAMPO}
                  aria-invalid={form.kilos_brutos !== "" && !brutosValidos}
                  aria-describedby={form.kilos_brutos && !brutosValidos ? "recepcion-brutos-error" : undefined}
                  required
                />
                {/* Aviso en línea, solo si ya se escribió algo. */}
                {form.kilos_brutos && !brutosValidos && (
                  <p id="recepcion-brutos-error" className="mt-1 text-xs text-red-700" role="alert">Ingrese un peso mayor que cero con hasta dos decimales.</p>
                )}
              </div>
              {/* Fecha de recepción: por defecto hoy, editable y nunca futura (decisión C); al corregir, no posterior al registro. */}
              <div>
                <label htmlFor="recepcion-fecha" className={ETIQUETA}>Fecha de recepción</label>
                <input
                  id="recepcion-fecha"
                  name="fecha_recepcion"
                  type="date"
                  max={fechaMaxima}
                  value={form.fecha_recepcion}
                  onChange={cambiarCampo}
                  className={!fechaValida ? CAMPO_ERROR : CAMPO}
                  aria-invalid={!fechaValida}
                  aria-describedby={!fechaValida ? "recepcion-fecha-error" : undefined}
                  required
                />
                {/* Aviso en línea. */}
                {!fechaValida && (
                  <p id="recepcion-fecha-error" className="mt-1 text-xs text-red-700" role="alert">
                    {diaRegistro ? `La fecha no puede ser posterior al registro de la tarja (${formatearDia(diaRegistro)}).` : "La fecha no puede ser posterior a hoy."}
                  </p>
                )}
              </div>
            </div>
          </section>

          {/* HU20 exige una justificación visible antes de confirmar la corrección. */}
          {editando && (
            <section className="mt-6 border-t border-slate-200 pt-5">
              <h3 className={SUBTITULO}>Motivo de la corrección</h3>
              <label htmlFor="recepcion-motivo" className={ETIQUETA}>Explique el error corregido</label>
              <textarea
                id="recepcion-motivo"
                value={motivo}
                onChange={(evento) => setMotivo(evento.target.value)}
                maxLength={255}
                rows={3}
                className={motivo.trim() ? CAMPO : CAMPO_ERROR}
                aria-invalid={!motivo.trim()}
                aria-describedby="recepcion-motivo-ayuda"
                required
              />
              <p id="recepcion-motivo-ayuda" className={AYUDA}>Obligatorio. Quedará registrado junto al antes y después de la tarja.</p>
            </section>
          )}

          {/* Saldo de bandejas del productor en el tipo elegido, como el semáforo del legado (HU15). */}
          {productor && bandejaId && (
            <section className="mt-6 border-t border-slate-200 pt-5" aria-live="polite">
              <h3 className={SUBTITULO}>Bandejas del productor</h3>
              {errorSaldos ? (
                <p className={`mt-3 ${MENSAJE_ERROR}`} role="alert">{errorSaldos}</p>
              ) : (
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded border border-slate-200 bg-frigorifico-50 px-4 py-3 text-sm text-slate-600">
                  <span className={situacionSaldo.clase}>{situacionSaldo.texto}</span>
                  <span>Saldo actual: <strong className="text-frigorifico-900">{saldoActual}</strong></span>
                  {/* Con esta tarja, el saldo sube según la cantidad escrita. */}
                  {saldoProyectado !== null && <span>Saldo proyectado: <strong className="text-frigorifico-900">{saldoProyectado}</strong></span>}
                </div>
              )}
            </section>
          )}

          {/* Vista previa calculada con el mismo redondeo bancario del backend (HU14 criterio 3). */}
          <section className="mt-6 border-t border-slate-200 pt-5" aria-live="polite">
            <h3 className={SUBTITULO}>Cálculo</h3>
            {/* El recuadro pasa a rojo si el neto es cero o negativo. */}
            <div className={`mt-3 rounded border px-4 py-3 ${kilosNetos !== null && !netoValido ? "border-red-200 bg-red-50" : "border-slate-200 bg-frigorifico-50"}`}>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {/* Kilos netos redondeados a entero. */}
                <div>
                  <dt className="text-xs font-semibold text-slate-500">Kilos netos</dt>
                  <dd className={`mt-1 text-2xl font-bold ${kilosNetos !== null && !netoValido ? "text-red-700" : "text-frigorifico-900"}`}>{kilosNetos === null ? "—" : `${kilosNetos} kg`}</dd>
                </div>
                {/* Promedio por bandeja con dos decimales. */}
                <div>
                  <dt className="text-xs font-semibold text-slate-500">Promedio por bandeja</dt>
                  <dd className="mt-1 text-2xl font-bold text-frigorifico-900">{promedioCentimos === null ? "—" : `${formatearCentimos(promedioCentimos)} kg`}</dd>
                </div>
                {/* En edición se declara qué tara se usa: la de la tarja o la vigente del tipo elegido (criterio 4). */}
                {editando && (
                  <div>
                    <dt className="text-xs font-semibold text-slate-500">{mismaBandeja || !bandeja ? "Tara de la tarja" : "Tara vigente del tipo elegido"}</dt>
                    {/* "Cargando…" mientras llega la tarja; "—" si se dejó el tipo sin elegir. */}
                    <dd className="mt-1 text-lg font-bold text-frigorifico-900">{!tarjaOriginal ? "Cargando…" : taraCentimos === null ? "—" : `${formatearCentimos(taraCentimos)} kg`}</dd>
                  </div>
                )}
              </dl>
              {/* Explica por qué Guardar sigue deshabilitado. */}
              {kilosNetos !== null && !netoValido && <p className="mt-2 text-sm text-red-700">Los kilos netos deben ser mayores que cero; revise los pesos.</p>}
            </div>
          </section>

          {/* Guardar es la única acción que envía el formulario. */}
          <div className="mt-6 border-t border-slate-200 pt-5">
            <div className="flex flex-wrap gap-3">
              <button type="submit" disabled={!formularioValido || guardando} className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
              {/* Al corregir, Cancelar vuelve a Tarjas sin guardar nada (B4). */}
              {editando && <button type="button" onClick={() => navigate("/tarjas")} className={BOTON_SECUNDARIO}>Cancelar</button>}
            </div>
            {/* Explica por qué Guardar sigue deshabilitado si no se cambió nada (criterio 7). */}
            {editando && tarjaOriginal && !hayCambios && <p className={AYUDA}>Cambie al menos un dato para guardar la corrección.</p>}
            <p className={AYUDA}>
              {editando
                ? "Enter avanza al siguiente campo hasta el motivo. Guardar registra la corrección y abre la hoja para reimprimirla."
                : "Enter avanza al siguiente campo hasta Guardar; solo este botón registra la tarja y abre su hoja de impresión."}
            </p>
          </div>
        </fieldset>
      </form>
      )}
    </div>
  );
}
