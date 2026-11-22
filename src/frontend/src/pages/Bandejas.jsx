// Estado y efectos de la consulta.
import { useEffect, useState } from "react";
// Traduce errores HTTP a mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Saldo de bandejas del productor.
import { saldoBandejasProductor } from "../api/tarjas";
// Buscador compartido de productores (HU11).
import SelectorProductor from "../components/SelectorProductor";
// Clases comunes de formularios, tablas y mensajes.
import {
  AYUDA,
  CELDA,
  CELDA_AVISO,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  MENSAJE_ERROR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";
// Semáforo del saldo, igual que el del legado.
import { situacionBandejas } from "../components/saldoBandejas";

// Consulta del saldo de bandejas de un productor, por tipo de bandeja (HU15 criterio 3).
export default function Bandejas() {
  // Productor elegido.
  const [productor, setProductor] = useState(null);
  // Filas del saldo.
  const [saldos, setSaldos] = useState([]);
  // Estado de carga y error.
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  // Consulta el saldo cada vez que cambia el productor.
  useEffect(() => {
    // Sin productor no hay nada que mostrar.
    if (!productor) {
      setSaldos([]);
      setError("");
      return undefined;
    }
    // Descarta la respuesta si el productor cambió mientras llegaba.
    let vigente = true;
    // Encapsula la consulta asíncrona del efecto.
    async function cargar() {
      // Muestra la fila de carga.
      setCargando(true);
      setError("");
      try {
        // Pide el saldo por tipo de bandeja.
        const lista = await saldoBandejasProductor(productor.id);
        // Guarda el resultado si sigue vigente.
        if (vigente) setSaldos(lista);
      } catch (errorRecibido) {
        // Muestra el error y deja la tabla vacía.
        if (vigente) {
          setSaldos([]);
          setError(extraerMensajeError(errorRecibido, "No se pudo consultar el saldo de bandejas"));
        }
      } finally {
        // Termina la carga.
        if (vigente) setCargando(false);
      }
    }
    // Inicia la consulta.
    cargar();
    // Marca como obsoleta la respuesta anterior.
    return () => { vigente = false; };
  }, [productor]);

  // Renderiza el encabezado, el buscador y la tabla.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 3. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E3 · Recepción</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Bandejas</h1>
        <p className="mt-2 text-sm text-slate-500">Consulte cuántas bandejas tiene cada productor, por tipo de bandeja.</p>
      </div>

      {/* Productor, por código, RUT o razón social; Enter elige el primero. */}
      <div className={TARJETA}>
        <SelectorProductor id="bandejas-productor" valor={productor} onChange={setProductor} elegirPrimeroConEnter />
      </div>

      {/* Error de la consulta. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {/* El saldo se muestra al elegir un productor. */}
      {productor && (
        <div>
          <h2 className={`mb-3 ${SUBTITULO}`}>Saldo por tipo de bandeja</h2>
          {/* Tabla accesible; si no cabe, hace scroll dentro de su contenedor. */}
          <div role="region" aria-label="Saldo de bandejas" aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
            <table className="w-full text-sm">
              <caption className="sr-only">Saldo de bandejas del productor elegido</caption>
              {/* Encabezados. */}
              <thead className={ENCABEZADO_TABLA}>
                <tr>
                  <th scope="col" className={CELDA}>Tipo de bandeja</th>
                  <th scope="col" className={`${CELDA} text-right`}>Entradas</th>
                  <th scope="col" className={`${CELDA} text-right`}>Salidas</th>
                  <th scope="col" className={`${CELDA} text-right`}>Saldo</th>
                  <th scope="col" className={CELDA}>Situación</th>
                </tr>
              </thead>
              {/* Cargando y vacío ocupan una fila dentro de la tabla. */}
              <tbody className="divide-y divide-slate-100">
                {cargando ? (
                  <tr><td colSpan={5} className={CELDA_AVISO}>Cargando…</td></tr>
                ) : saldos.length === 0 ? (
                  <tr><td colSpan={5} className={CELDA_AVISO}>Este productor no tiene movimientos de bandejas.</td></tr>
                ) : (
                  saldos.map((fila) => {
                    // Texto y color del semáforo.
                    const situacion = situacionBandejas(fila.saldo);
                    return (
                      <tr key={fila.tipo_bandeja_id} className="hover:bg-slate-50">
                        <td className={`${CELDA} text-slate-600`}>{fila.tipo_bandeja}</td>
                        <td className={`${CELDA} text-right text-slate-600`}>{fila.entradas}</td>
                        <td className={`${CELDA} text-right text-slate-600`}>{fila.salidas}</td>
                        <td className={`${CELDA} text-right font-medium text-slate-700`}>{fila.saldo}</td>
                        <td className={CELDA}><span className={`whitespace-nowrap ${situacion.clase}`}>{situacion.texto}</span></td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          {/* Aclara por qué las salidas están en cero (HU15 criterio 4). */}
          <p className={AYUDA}>Por ahora solo se registran entradas: las devoluciones al productor llegarán con la guía. Las tarjas anuladas no suman.</p>
        </div>
      )}
    </div>
  );
}
