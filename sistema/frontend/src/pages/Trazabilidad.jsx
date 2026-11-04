// Estado de la consulta.
import { useState } from "react";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Consulta de solo lectura.
import { consultarTrazabilidad } from "../api/trazabilidad";
// Clases comunes de formularios, tablas y mensajes.
import {
  AYUDA,
  BOTON_PRINCIPAL,
  CAMPO,
  CELDA,
  CELDA_AVISO,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  ETIQUETA,
  MENSAJE_ERROR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";
// Presentación de cajas y kilos.
import { textoCajas, textoKilos } from "../components/procesamiento";
// Presentación del RUT con puntos y guion.
import { formatearRut } from "../utils/rut";

// Textos visibles de los estados.
const TEXTO_ESTADO = { RECEPCIONADA: "Recepcionada", PARCIAL: "Parcial", PROCESADA: "Procesada", ANULADA: "Anulada" };

// Muestra una fecha YYYY-MM-DD como DD-MM-YYYY, sin pasar por zonas horarias.
function formatearFecha(valor) {
  // Separa las partes del texto.
  const [anio, mes, dia] = String(valor).split("-");
  // Las ordena como se leen en Chile.
  return `${dia}-${mes}-${anio}`;
}

// Muestra un momento guardado en UTC en la hora de la planta.
function formatearFechaHora(valor) {
  // La API lo entrega sin zona: se indica que es UTC.
  return new Date(`${valor}Z`).toLocaleString("es-CL", { timeZone: "America/Santiago" });
}

// Pares de etiqueta y valor en dos columnas.
function Datos({ filas }) {
  // Dos columnas desde pantallas medianas.
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {filas.map(([etiqueta, valor]) => (
        <div key={etiqueta} className="flex flex-wrap gap-x-2">
          <dt className="font-semibold text-slate-600">{etiqueta}:</dt>
          <dd className="break-words text-slate-700">{valor}</dd>
        </div>
      ))}
    </dl>
  );
}

// Recorrido completo de una tarja, de solo lectura (HU23).
export default function Trazabilidad() {
  // Número escrito.
  const [numero, setNumero] = useState("");
  // Resultado de la última consulta.
  const [recorrido, setRecorrido] = useState(null);
  // Estado de carga y error.
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  // Pide el recorrido al enviar el formulario.
  async function consultar(evento) {
    // Evita la navegación nativa del formulario.
    evento.preventDefault();
    // Sin número no hay nada que consultar.
    const buscado = numero.trim();
    if (!buscado) {
      setError("Ingrese el número de la tarja.");
      setRecorrido(null);
      return;
    }
    // Muestra la carga y limpia el error anterior.
    setCargando(true);
    setError("");
    try {
      // La API reúne la recepción, los procesos y el historial.
      setRecorrido(await consultarTrazabilidad(buscado));
    } catch (errorRecibido) {
      // Un resultado anterior no debe seguir a la vista junto al error.
      setRecorrido(null);
      setError(extraerMensajeError(errorRecibido, "No se pudo consultar la tarja"));
    } finally {
      // Libera el botón.
      setCargando(false);
    }
  }

  // Datos de la tarja consultada.
  const tarja = recorrido?.tarja;

  // Renderiza el encabezado, el formulario y el recorrido.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 4. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E4 · Consultas</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Trazabilidad de una tarja</h1>
        <p className="mt-2 text-sm text-slate-500">Revise el recorrido completo de una tarja de recepción, para responder reclamos y consultas de productores. Esta consulta no modifica datos.</p>
      </div>

      {/* Formulario de la consulta. */}
      <form onSubmit={consultar} className={TARJETA}>
        <label htmlFor="trazabilidad-numero" className={ETIQUETA}>Número de tarja</label>
        <input
          id="trazabilidad-numero"
          type="number"
          min="1"
          step="1"
          autoFocus
          value={numero}
          onChange={(evento) => setNumero(evento.target.value)}
          aria-describedby="trazabilidad-numero-ayuda"
          className={`${CAMPO} sm:max-w-xs`}
        />
        <p id="trazabilidad-numero-ayuda" className={AYUDA}>Escriba el número y presione Enter.</p>
        <button type="submit" disabled={cargando} className={`mt-4 ${BOTON_PRINCIPAL}`}>{cargando ? "Consultando…" : "Consultar"}</button>
      </form>

      {/* Error de la consulta. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {tarja && (
        <>
          {/* Productor y datos de la recepción. */}
          <section aria-labelledby="titulo-recepcion" className={TARJETA}>
            <h2 id="titulo-recepcion" className={`mb-3 ${SUBTITULO}`}>Tarja N° {tarja.numero_tarja} · {TEXTO_ESTADO[tarja.estado] ?? tarja.estado}</h2>
            <Datos filas={[
              ["Productor", `${tarja.productor_codigo} · ${formatearRut(tarja.productor_rut)} · ${tarja.productor_razon_social}`],
              ["Fecha de recepción", formatearFecha(tarja.fecha_recepcion)],
              ["Sistema productivo", tarja.sistema_productivo],
              ["Especie", tarja.especie],
              ["Variedad", tarja.variedad],
              ["Calidad", tarja.calidad],
              ["Calidad visual", `${tarja.porcentaje_calidad} %`],
              ["Tipo de bandeja", tarja.tipo_bandeja],
              ["Cantidad de bandejas", tarja.cantidad_bandejas],
              ["Tara por bandeja", `${textoKilos(tarja.tara_kg)} kg`],
              ["Peso del pallet", `${textoKilos(tarja.peso_pallet_kg)} kg`],
              ["Kilos de balanza", `${textoKilos(tarja.kilos_brutos)} kg`],
              ["Registrada por", tarja.registrada_por],
              ["Registrada", formatearFechaHora(tarja.fecha_hora)],
            ]} />
          </section>

          {/* Kilos de la tarja. */}
          <section aria-labelledby="titulo-kilos" className={TARJETA}>
            <h2 id="titulo-kilos" className={`mb-3 ${SUBTITULO}`}>Kilos</h2>
            <Datos filas={[
              ["Kilos netos", `${tarja.kilos_netos} kg`],
              ["Kilos procesados", `${textoKilos(tarja.kilos_procesados)} kg`],
              ["Kilos pendientes", `${textoKilos(tarja.kilos_pendientes)} kg`],
              // Una tarja anulada no tiene merma; mientras tenga kilos, la merma es provisional.
              ["Merma", recorrido.merma === null ? "No aplica: tarja anulada" : `${textoKilos(recorrido.merma)} kg${recorrido.merma_provisional ? " (provisional)" : ""}`],
            ]} />
          </section>

          {/* Procesos en que entró (criterio 1). */}
          <div>
            <h2 className={`mb-3 ${SUBTITULO}`}>Procesos en que entró</h2>
            <div role="region" aria-label="Procesos de la tarja" tabIndex={0} className={CONTENEDOR_TABLA}>
              <table className="w-full text-sm">
                <caption className="sr-only">Procesos de la tarja con su resultado</caption>
                <thead className={ENCABEZADO_TABLA}>
                  <tr>
                    <th scope="col" className={CELDA}>Folio</th>
                    <th scope="col" className={CELDA}>Elaboración</th>
                    <th scope="col" className={CELDA}>Embalaje</th>
                    <th scope="col" className={`${CELDA} text-right`}>Cajas</th>
                    <th scope="col" className={`${CELDA} text-right`}>Kilos</th>
                    <th scope="col" className={CELDA}>Registrado por</th>
                    <th scope="col" className={CELDA}>Situación</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {recorrido.procesos.length === 0 ? (
                    <tr><td colSpan={7} className={CELDA_AVISO}>Esta tarja no ha entrado a ningún proceso.</td></tr>
                  ) : (
                    recorrido.procesos.map((proceso) => (
                      <tr key={proceso.id} className={proceso.anulado ? "text-slate-400" : "text-slate-600"}>
                        <td className={`${CELDA} font-medium`}>{proceso.folio}</td>
                        <td className={`whitespace-nowrap ${CELDA}`}>{formatearFecha(proceso.fecha_elaboracion)}</td>
                        <td className={CELDA}>{proceso.embalaje}</td>
                        <td className={`${CELDA} text-right`}>{textoCajas(proceso.cantidad_cajas)}</td>
                        <td className={`whitespace-nowrap ${CELDA} text-right`}>{textoKilos(proceso.kilos_procesados)}</td>
                        <td className={CELDA}>{proceso.registrado_por}</td>
                        <td className={CELDA}>
                          {/* Un proceso anulado no cuenta en los kilos. */}
                          {proceso.anulado
                            ? <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-700">Anulado: no cuenta</span>
                            : proceso.tarja_terminada ? "Terminada aquí" : "Vigente"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Historial de cambios (criterio 2). */}
          <div>
            <h2 className={`mb-3 ${SUBTITULO}`}>Historial de cambios</h2>
            <div role="region" aria-label="Historial de la tarja" tabIndex={0} className={CONTENEDOR_TABLA}>
              <table className="w-full text-sm">
                <caption className="sr-only">Quién hizo cada cambio, cuándo y qué cambió</caption>
                <thead className={ENCABEZADO_TABLA}>
                  <tr>
                    <th scope="col" className={CELDA}>Fecha y hora</th>
                    <th scope="col" className={CELDA}>Usuario</th>
                    <th scope="col" className={CELDA}>Qué pasó</th>
                    <th scope="col" className={CELDA}>Qué cambió</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {recorrido.historial.length === 0 ? (
                    <tr><td colSpan={4} className={CELDA_AVISO}>Sin cambios registrados.</td></tr>
                  ) : (
                    recorrido.historial.map((evento, indice) => (
                      <tr key={indice} className="align-top text-slate-600">
                        <td className={`whitespace-nowrap ${CELDA}`}>{formatearFechaHora(evento.fecha_hora)}</td>
                        <td className={CELDA}>{evento.usuario}</td>
                        <td className={CELDA}>{evento.descripcion}</td>
                        <td className={CELDA}>
                          {/* Valor anterior y valor nuevo de cada campo. */}
                          {evento.cambios.map((cambio) => (
                            <span key={cambio.campo} className="block whitespace-nowrap">{cambio.campo}: {cambio.antes ?? "—"} → {cambio.despues ?? "—"}</span>
                          ))}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
