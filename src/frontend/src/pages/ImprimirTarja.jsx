// Estado y efectos de la hoja de impresión.
import { useEffect, useState } from "react";
// Enlaces de salida, datos de la navegación y parámetro de la ruta.
import { Link, useLocation, useParams } from "react-router-dom";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Detalle de la tarja y registro de cada impresión.
import { obtenerTarja, registrarImpresion } from "../api/tarjas";
// Clases comunes de botones y mensajes.
import { BOTON_EDITAR, BOTON_PRINCIPAL, MENSAJE_ERROR, MENSAJE_EXITO } from "../components/catalogo";
// Presentación del RUT con puntos y guion.
import { formatearRut } from "../utils/rut";

// Muestra una fecha YYYY-MM-DD como DD-MM-YYYY, sin pasar por zonas horarias.
function formatearFecha(valor) {
  // Separa las partes del texto.
  const [anio, mes, dia] = String(valor).split("-");
  // Las ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Muestra un peso decimal con coma, sin pasar por float.
function kilos(valor) {
  // La API entrega los decimales como texto.
  return `${String(valor).replace(".", ",")} kg`;
}

// Tarja como hoja imprimible, sin el menú del sistema (HU16; patrón de socradex y del Form4 del legado).
export default function ImprimirTarja() {
  // Id de la tarja en la URL.
  const { id } = useParams();
  // Datos que deja Recepción al guardar: el aviso y lo que se conserva para la siguiente tarja.
  const { state: desdeRecepcion } = useLocation();
  // Tarja que se muestra.
  const [tarja, setTarja] = useState(null);
  // Error al cargar la tarja o al registrar la impresión.
  const [error, setError] = useState("");
  // Bloquea el botón mientras responde la API.
  const [registrando, setRegistrando] = useState(false);
  // Indica que la impresión ya se registró y falta abrir el diálogo.
  const [listaParaImprimir, setListaParaImprimir] = useState(false);

  // Carga la tarja al abrir la hoja.
  useEffect(() => {
    // Descarta la respuesta si cambió la tarja o se cerró la hoja.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargar() {
      try {
        // Pide el detalle con los nombres de los catálogos.
        const datos = await obtenerTarja(id);
        // Guarda la tarja si la respuesta sigue vigente.
        if (vigente) setTarja(datos);
      } catch (errorRecibido) {
        // Muestra el error en vez de la hoja.
        if (vigente) setError(extraerMensajeError(errorRecibido, "No se pudo cargar la tarja"));
      }
    }
    // Inicia la consulta.
    cargar();
    // Marca como obsoleta la respuesta anterior.
    return () => { vigente = false; };
  }, [id]);

  // Mientras la hoja está abierta, el título es solo "Socradex": es el nombre que se propone al guardar el PDF.
  useEffect(() => {
    // Recuerda el título de la aplicación para devolverlo al salir.
    const anterior = document.title;
    // Nombre de la empresa, sin "A2D SM | Trazabilidad" (decisión de Alejandro del 2026-11-08).
    document.title = "Socradex";
    // Al salir de la hoja vuelve el título de siempre.
    return () => { document.title = anterior; };
  }, []);

  // Abre el diálogo después de pintar la hoja con el contador nuevo.
  useEffect(() => {
    // Solo actúa después de registrar la impresión.
    if (!listaParaImprimir) return;
    // Evita abrir el diálogo dos veces.
    setListaParaImprimir(false);
    // Así la reimpresión ya sale con su marca.
    window.print();
  }, [listaParaImprimir]);

  // Registra la impresión y después abre el diálogo del navegador (HU16 criterio 3).
  async function imprimir() {
    // Bloquea el botón.
    setRegistrando(true);
    setError("");
    try {
      // La API suma la impresión y la audita; devuelve la tarja actualizada.
      setTarja(await registrarImpresion(id));
      // El efecto abre el diálogo después de pintar.
      setListaParaImprimir(true);
    } catch (errorRecibido) {
      // Si no se pudo registrar, no se imprime.
      setError(extraerMensajeError(errorRecibido, "No se pudo registrar la impresión"));
    } finally {
      // Libera el botón.
      setRegistrando(false);
    }
  }

  // Lleva a Recepción el productor y la fecha, para seguir con la siguiente tarja.
  const estadoRecepcion = desdeRecepcion?.productor
    ? { productor: desdeRecepcion.productor, fecha_recepcion: desdeRecepcion.fecha_recepcion }
    : undefined;

  // Sin tarja: muestra la carga, o el error con una salida.
  if (!tarja) {
    return (
      <main className="mx-auto max-w-2xl space-y-4 px-4 py-8">
        {error
          ? <p className={MENSAJE_ERROR} role="alert">{error}</p>
          : <p className="text-center text-slate-400">Cargando…</p>}
        {error && <Link to="/tarjas" className={BOTON_EDITAR}>Volver a Tarjas</Link>}
      </main>
    );
  }

  // Una tarja anulada no se imprime: no debe identificar fruta en la planta.
  const anulada = tarja.estado === "ANULADA";
  // Datos de la hoja como pares de etiqueta y valor (HU16 criterio 1).
  const filas = [
    ["Productor", `${tarja.productor_codigo} · ${tarja.productor_razon_social}`],
    ["RUT", formatearRut(tarja.productor_rut)],
    ["Fecha de recepción", formatearFecha(tarja.fecha_recepcion)],
    ["Sistema productivo", tarja.sistema_productivo],
    ["Especie", tarja.especie],
    ["Variedad", tarja.variedad],
    ["Calidad", tarja.calidad],
    ["Calidad visual", `${tarja.porcentaje_calidad} %`],
    ["Tipo de bandeja", tarja.tipo_bandeja],
    ["Cantidad de bandejas", tarja.cantidad_bandejas],
    ["Tara por bandeja", kilos(tarja.tara_kg)],
    ["Peso del pallet", kilos(tarja.peso_pallet_kg)],
    ["Kilos de balanza", kilos(tarja.kilos_brutos)],
    ["Kilos netos", `${tarja.kilos_netos} kg`],
    ["Promedio por bandeja", kilos(tarja.kg_promedio_bandeja)],
    ["Registrada por", tarja.registrada_por],
  ];

  // Renderiza las acciones, que no se imprimen, y la hoja.
  return (
    // print:p-[12mm]: la página no tiene margen (index.css), así que el margen del papel lo pone la hoja.
    <main className="mx-auto max-w-2xl space-y-4 px-4 py-8 print:max-w-none print:p-[12mm]">
      {/* Acciones de pantalla: print:hidden las deja fuera del papel. */}
      <div className="space-y-4 print:hidden">
        {/* Aviso al llegar desde Recepción. */}
        {desdeRecepcion?.recienRegistrada && (
          <p className={MENSAJE_EXITO} role="status">Tarja N° {tarja.numero_tarja} registrada: {tarja.kilos_netos} kg netos</p>
        )}
        {/* Aviso al llegar desde una corrección (HU20 criterio 6): la hoja del pallet quedó con datos antiguos. */}
        {desdeRecepcion?.recienCorregida && (
          <p className={MENSAJE_EXITO} role="status">Tarja N° {tarja.numero_tarja} corregida: {tarja.kilos_netos} kg netos. Reimprima la hoja y reemplace la del pallet.</p>
        )}
        {/* Error al registrar la impresión. */}
        {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}
        {/* Enlaces de salida y botón de imprimir. */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-4">
            <Link to="/recepcion" state={estadoRecepcion} className={BOTON_EDITAR}>Registrar otra tarja</Link>
            <Link to="/tarjas" className={BOTON_EDITAR}>Ver tarjas</Link>
          </div>
          {/* El texto cambia cuando ya se imprimió alguna vez. */}
          {!anulada && (
            <button type="button" onClick={imprimir} disabled={registrando} className={BOTON_PRINCIPAL}>
              {registrando ? "Preparando…" : tarja.veces_impresa > 0 ? "Reimprimir" : "Imprimir"}
            </button>
          )}
        </div>
      </div>

      {/* Hoja de la tarja: sin borde ni sombra en el papel. */}
      <article className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm print:border-none print:p-0 print:shadow-none">
        {/* Una tarja anulada se puede ver, pero queda marcada. */}
        {anulada && (
          <p className="mb-4 rounded border border-red-200 bg-red-50 py-1 text-center text-xs font-semibold tracking-widest text-red-700">TARJA ANULADA</p>
        )}
        {/* Desde la segunda impresión, la hoja dice que es una copia; una anulada ya no se imprime. */}
        {!anulada && tarja.veces_impresa > 1 && (
          <p className="mb-4 rounded border border-amber-200 bg-amber-50 py-1 text-center text-xs font-semibold tracking-widest text-amber-700 print:bg-transparent">
            REIMPRESIÓN (N° {tarja.veces_impresa})
          </p>
        )}
        {/* Encabezado con la marca y el número, lo más visible de la hoja. */}
        <header className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ambar">A2D SM · Tarja de recepción</p>
          <h1 className="mt-2 text-3xl font-bold text-frigorifico-900">Tarja N° {tarja.numero_tarja}</h1>
        </header>
        {/* Datos en dos columnas, también en papel. */}
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 print:grid-cols-2">
          {filas.map(([etiqueta, valor]) => (
            <div key={etiqueta}>
              <dt className="text-xs text-slate-500">{etiqueta}</dt>
              <dd className="break-words font-semibold text-frigorifico-900">{valor}</dd>
            </div>
          ))}
        </dl>
      </article>
    </main>
  );
}
