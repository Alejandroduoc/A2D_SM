// Estado y efectos de la hoja de impresión.
import { useEffect, useState } from "react";
// Enlaces de salida, datos de la navegación y parámetro de la ruta.
import { Link, useLocation, useParams } from "react-router-dom";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Detalle del proceso con sus tarjas.
import { obtenerProceso } from "../api/procesos";
// Clases comunes de botones, tablas y mensajes.
import { BOTON_EDITAR, BOTON_PRINCIPAL, CELDA, ENCABEZADO_TABLA, MENSAJE_ERROR, MENSAJE_EXITO } from "../components/catalogo";
// Presentación de cajas y kilos.
import { textoCajas, textoKilos } from "../components/procesamiento";

// Muestra una fecha YYYY-MM-DD como DD-MM-YYYY, sin pasar por zonas horarias.
function formatearFecha(valor) {
  // Separa las partes del texto.
  const [anio, mes, dia] = String(valor).split("-");
  // Las ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Comprobante de un proceso, sin el menú del sistema (patrón de HU16 y del Form30 del legado).
export default function ImprimirProceso() {
  // Id del proceso en la URL.
  const { id } = useParams();
  // Aviso que deja la pantalla de procesamiento al guardar.
  const { state: desdeProcesamiento } = useLocation();
  // Proceso que se muestra.
  const [proceso, setProceso] = useState(null);
  // Error al cargarlo.
  const [error, setError] = useState("");

  // Carga el proceso al abrir la hoja.
  useEffect(() => {
    // Descarta la respuesta si cambió el proceso o se cerró la hoja.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargar() {
      try {
        // Pide la cabecera y las tarjas.
        const datos = await obtenerProceso(id);
        // Guarda el proceso si la respuesta sigue vigente.
        if (vigente) setProceso(datos);
      } catch (errorRecibido) {
        // Muestra el error en vez de la hoja.
        if (vigente) setError(extraerMensajeError(errorRecibido, "No se pudo cargar el proceso"));
      }
    }
    // Inicia la consulta.
    cargar();
    // Marca como obsoleta la respuesta anterior.
    return () => { vigente = false; };
  }, [id]);

  // Mientras el comprobante está abierto, el título es solo "Socradex": es el nombre que se propone al guardar el PDF.
  useEffect(() => {
    // Recuerda el título de la aplicación para devolverlo al salir.
    const anterior = document.title;
    // Nombre de la empresa, sin "A2D SM | Trazabilidad" (decisión de Alejandro del 2026-11-08).
    document.title = "Socradex";
    // Al salir de la hoja vuelve el título de siempre.
    return () => { document.title = anterior; };
  }, []);

  // Sin proceso: muestra la carga, o el error con una salida.
  if (!proceso) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-8">
        {error
          ? <p className={MENSAJE_ERROR} role="alert">{error}</p>
          : <p className="text-center text-slate-400">Cargando…</p>}
        {error && <Link to="/procesamiento" className={BOTON_EDITAR}>Volver a Procesamiento</Link>}
      </main>
    );
  }

  // Datos generales como pares de etiqueta y valor.
  const datosGenerales = [
    ["Embalaje", proceso.embalaje],
    ["Fecha de elaboración", formatearFecha(proceso.fecha_elaboracion)],
    ["Total de cajas", textoCajas(proceso.cantidad_cajas)],
    ["Total de kilos", `${textoKilos(proceso.kilos_salida)} kg`],
    ["Registrado por", proceso.registrado_por],
  ];

  // Renderiza las acciones, que no se imprimen, y la hoja.
  return (
    // print:p-[12mm]: la página no tiene margen (index.css), así que el margen del papel lo pone la hoja.
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-8 print:max-w-none print:p-[12mm]">
      {/* Acciones de pantalla: print:hidden las deja fuera del papel. */}
      <div className="space-y-4 print:hidden">
        {/* Aviso al llegar desde Procesamiento. */}
        {desdeProcesamiento?.aviso && <p className={MENSAJE_EXITO} role="status">{desdeProcesamiento.aviso}</p>}
        {/* Enlaces de salida y botón de imprimir. */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to="/procesamiento" className={BOTON_EDITAR}>Volver a Procesamiento</Link>
          {/* Un proceso anulado no se imprime: no debe identificar fruta en la planta. */}
          {!proceso.anulado && <button type="button" onClick={() => window.print()} className={BOTON_PRINCIPAL}>Imprimir</button>}
        </div>
      </div>

      {/* Hoja del proceso: sin borde ni sombra en el papel. */}
      <article className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm print:border-none print:p-0 print:shadow-none">
        {/* Un proceso anulado se puede ver, pero queda marcado. */}
        {proceso.anulado && (
          <p className="mb-4 rounded border border-red-200 bg-red-50 py-1 text-center text-xs font-semibold tracking-widest text-red-700">PROCESO ANULADO</p>
        )}
        {/* Encabezado con la marca y el folio, lo más visible de la hoja. */}
        <header className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-ambar">A2D SM · Tarja de proceso</p>
          <h1 className="mt-2 text-3xl font-bold text-frigorifico-900">Proceso {proceso.folio}</h1>
        </header>
        {/* Datos en dos columnas, también en papel. */}
        <dl className="mb-6 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 print:grid-cols-2">
          {datosGenerales.map(([etiqueta, valor]) => (
            <div key={etiqueta}>
              <dt className="text-xs text-slate-500">{etiqueta}</dt>
              <dd className="break-words font-semibold text-frigorifico-900">{valor}</dd>
            </div>
          ))}
        </dl>
        {/* Tarjas de recepción del proceso; hace scroll solo en pantallas angostas. */}
        <div role="region" aria-label={`Tarjas del proceso ${proceso.folio}`} tabIndex={0} className="relative overflow-x-auto print:overflow-visible">
          <table className="w-full text-sm">
            <caption className="sr-only">Tarjas de recepción del proceso, con su productor, fruta, cajas y kilos</caption>
            <thead className={ENCABEZADO_TABLA}>
              <tr>
                <th scope="col" className={`${CELDA} text-right`}>Tarja</th>
                <th scope="col" className={CELDA}>Productor</th>
                <th scope="col" className={CELDA}>Fruta</th>
                <th scope="col" className={`${CELDA} text-right`}>Cajas</th>
                <th scope="col" className={`${CELDA} text-right`}>Kilos</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {proceso.tarjas.map((fila) => (
                <tr key={fila.tarja_id}>
                  <td className={`${CELDA} text-right font-medium text-slate-700`}>{fila.numero_tarja}</td>
                  <td className={`${CELDA} text-slate-600`}>{fila.productor_codigo} · {fila.productor_razon_social}</td>
                  <td className={`${CELDA} text-slate-600`}>{fila.especie} / {fila.variedad} · {fila.calidad} · {fila.sistema_productivo}</td>
                  <td className={`${CELDA} text-right text-slate-600`}>{textoCajas(fila.cantidad_cajas)}</td>
                  <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(fila.kilos_procesados)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </main>
  );
}
