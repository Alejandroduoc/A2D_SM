// Estado de la consulta.
import { useState } from "react";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Consulta de solo lectura.
import { consultarRendimiento } from "../api/procesos";
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
// Presentación de kilos y lectura de los folios escritos.
import { separarFolios, textoKilos } from "../components/procesamiento";

// Etiqueta que distingue un resultado todavía abierto de uno definitivo.
function Situacion({ provisional }) {
  // Ámbar si la tarja sigue pendiente; gris si ya terminó.
  return provisional
    ? <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-700">Provisional</span>
    : <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs text-slate-500">Definitivo</span>;
}

// Rendimiento y merma de las tarjas asociadas a uno o varios folios (HU19).
export default function Rendimiento() {
  // Folios escritos por el operador.
  const [texto, setTexto] = useState("");
  // Resultado de la última consulta.
  const [resultado, setResultado] = useState(null);
  // Estado de carga y error.
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  // Pide el cálculo al enviar el formulario.
  async function consultar(evento) {
    // Evita la navegación nativa del formulario.
    evento.preventDefault();
    // Separa los folios escritos.
    const folios = separarFolios(texto);
    // Sin folios no hay nada que consultar.
    if (folios.length === 0) {
      setError("Ingrese al menos un folio.");
      setResultado(null);
      return;
    }
    // Muestra la carga y limpia el error anterior.
    setCargando(true);
    setError("");
    try {
      // El cálculo se hace en la API, con los procesos vigentes (criterio 5).
      setResultado(await consultarRendimiento(folios));
    } catch (errorRecibido) {
      // Un resultado anterior no debe seguir a la vista junto al error.
      setResultado(null);
      setError(extraerMensajeError(errorRecibido, "No se pudo calcular el rendimiento"));
    } finally {
      // Libera el botón.
      setCargando(false);
    }
  }

  // Renderiza el encabezado, el formulario y el resultado.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 4. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E4 · Proceso</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Rendimiento y merma</h1>
        <p className="mt-2 text-sm text-slate-500">Ingrese uno o varios folios de proceso. El sistema busca sus tarjas de recepción y calcula su rendimiento y su merma.</p>
      </div>

      {/* Formulario de la consulta. */}
      <form onSubmit={consultar} className={TARJETA}>
        <label htmlFor="rendimiento-folios" className={ETIQUETA}>Folios de proceso</label>
        <input
          id="rendimiento-folios"
          type="text"
          autoFocus
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          aria-describedby="rendimiento-folios-ayuda"
          className={CAMPO}
        />
        <p id="rendimiento-folios-ayuda" className={AYUDA}>Por ejemplo: P12, P13 o P12 P13. Presione Enter para calcular.</p>
        <button type="submit" disabled={cargando} className={`mt-4 ${BOTON_PRINCIPAL}`}>{cargando ? "Calculando…" : "Calcular"}</button>
      </form>

      {/* Error de la consulta. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {/* Folios que no entran en el cálculo. */}
      {resultado?.folios_no_encontrados.length > 0 && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" role="status">No existen: {resultado.folios_no_encontrados.join(", ")}.</p>
      )}
      {resultado?.folios_anulados.length > 0 && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" role="status">Anulados, no cuentan en el cálculo: {resultado.folios_anulados.join(", ")}.</p>
      )}

      {/* Resultado por tarja de recepción. */}
      {resultado && (
        <div>
          <h2 className={`mb-1 ${SUBTITULO}`}>Tarjas de recepción asociadas</h2>
          <p className="mb-3 text-xs text-slate-500">Cuenta todos los procesos vigentes de cada tarja, también los de folios que no ingresó. Es provisional mientras la tarja tenga kilos pendientes.</p>
          {/* Tabla accesible; si no cabe, hace scroll dentro de su contenedor. */}
          <div role="region" aria-label="Rendimiento por tarja" tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Kilos de entrada, kilos procesados, merma y rendimiento de cada tarja</caption>
              <thead className={ENCABEZADO_TABLA}>
                <tr>
                  <th scope="col" className={`${CELDA} text-right`}>Tarja</th>
                  <th scope="col" className={CELDA}>Productor</th>
                  <th scope="col" className={CELDA}>Fruta</th>
                  <th scope="col" className={CELDA}>Folios</th>
                  <th scope="col" className={`${CELDA} text-right`}>Entrada (kg)</th>
                  <th scope="col" className={`${CELDA} text-right`}>Procesados (kg)</th>
                  <th scope="col" className={`${CELDA} text-right`}>Merma (kg)</th>
                  <th scope="col" className={`${CELDA} text-right`}>Rendimiento</th>
                  <th scope="col" className={CELDA}>Situación</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {resultado.tarjas.length === 0 ? (
                  <tr><td colSpan={9} className={CELDA_AVISO}>Esos folios no tienen tarjas para calcular.</td></tr>
                ) : (
                  resultado.tarjas.map((tarja) => (
                    <tr key={tarja.tarja_id}>
                      <td className={`${CELDA} text-right font-medium text-slate-700`}>{tarja.numero_tarja}</td>
                      <td className={`${CELDA} text-slate-600`}>{tarja.productor_codigo} · {tarja.productor_razon_social}</td>
                      <td className={`${CELDA} text-slate-600`}>{tarja.especie} / {tarja.variedad} · {tarja.calidad}</td>
                      <td className={`${CELDA} text-slate-600`}>{tarja.folios.join(", ")}</td>
                      <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.kilos_entrada)}</td>
                      <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.kilos_procesados)}</td>
                      <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.merma)}</td>
                      <td className={`${CELDA} whitespace-nowrap text-right text-slate-600`}>{textoKilos(tarja.rendimiento)} %</td>
                      <td className={CELDA}><Situacion provisional={tarja.provisional} /></td>
                    </tr>
                  ))
                )}
              </tbody>
              {/* Total de las tarjas consultadas (criterio 3). */}
              {resultado.tarjas.length > 0 && (
                <tfoot className="border-t border-slate-200 bg-frigorifico-50 text-sm font-semibold text-frigorifico-900">
                  <tr>
                    <td className={CELDA} colSpan={4}>Total de {resultado.tarjas.length} {resultado.tarjas.length === 1 ? "tarja" : "tarjas"}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right`}>{textoKilos(resultado.total.kilos_entrada)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right`}>{textoKilos(resultado.total.kilos_procesados)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right`}>{textoKilos(resultado.total.merma)}</td>
                    <td className={`${CELDA} whitespace-nowrap text-right`}>{textoKilos(resultado.total.rendimiento)} %</td>
                    <td className={CELDA}><Situacion provisional={resultado.total.provisional} /></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
