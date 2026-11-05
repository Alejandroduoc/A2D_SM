// Estado, efectos y referencias de la consulta.
import { useCallback, useEffect, useRef, useState } from "react";
// Traduce errores HTTP a mensajes visibles.
import { extraerMensajeError } from "../api/client";
// Consulta la bitácora y las listas de sus filtros.
import { consultarBitacora, consultarTablasAuditoria, consultarUsuariosAuditoria } from "../api/auditoria";
// Clases compartidas del patrón visual.
import {
  BOTON_EDITAR,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  CAMPO,
  CELDA,
  CELDA_AVISO,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  ETIQUETA,
  MENSAJE_ERROR,
  SELECTOR,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";

// Traduce acciones persistidas a textos de la pantalla.
const ACCIONES = { INSERT: "Crear", UPDATE: "Modificar", DELETE: "Eliminar" };
// Texto del enlace que despliega los datos del registro, según la acción.
const TEXTO_DATOS = { INSERT: "Ver datos creados", UPDATE: "Ver todos los datos", DELETE: "Ver datos eliminados" };
// Nombres legibles de las tablas; una tabla nueva se muestra con su nombre técnico.
const TEXTO_TABLA = {
  calidades: "Calidades",
  embalajes: "Embalajes",
  especies: "Especies",
  movimientos_bandeja: "Movimientos de bandejas",
  proceso_tarjas: "Tarjas en procesos",
  procesos: "Procesos",
  productores: "Productores",
  sistemas_productivos: "Sistemas productivos",
  tarjas: "Tarjas",
  tipos_bandeja: "Tipos de bandeja",
  usuarios: "Usuarios",
  variedades: "Variedades",
};
// Filas de cada página; la API admite hasta 100.
const FILAS_POR_PAGINA = 50;
// Filtros iniciales: sin filtros.
const FILTROS_VACIOS = { usuario_id: "", fecha_desde: "", fecha_hasta: "", tabla: "", accion: "" };
// Resultado sin eventos, también después de un error.
const SIN_RESULTADOS = { items: [], total: 0, limite: FILAS_POR_PAGINA, offset: 0, hay_mas: false };

// Formatea el instante UTC que entrega la API a la hora de Chile.
function fechaHoraChile(valor) {
  // La API lo entrega sin zona: se indica que es UTC.
  return new Date(`${valor}Z`).toLocaleString("es-CL", { timeZone: "America/Santiago" });
}

// Muestra qué cambió y, plegados, todos los datos del registro (criterio 2).
function DetalleEvento({ evento }) {
  // Una modificación puede no cambiar datos: el cambio de contraseña se explica en el motivo.
  const sinCambios = evento.accion === "UPDATE" && evento.cambios.length === 0;
  // Renderiza los cambios y los datos.
  return (
    <>
      {/* Solo lo que cambió, con su valor anterior y su valor nuevo. */}
      {evento.cambios.map((cambio) => (
        <span key={cambio.campo} className="block break-words">{cambio.campo}: {cambio.antes ?? "—"} → {cambio.despues ?? "—"}</span>
      ))}
      {sinCambios && <span className="block text-slate-400">Sin cambios en los datos</span>}
      {/* Los demás datos quedan plegados para que la tabla se pueda leer. */}
      {evento.datos.length > 0 && (
        <details className="mt-1">
          <summary className={`cursor-pointer ${BOTON_EDITAR}`}>{TEXTO_DATOS[evento.accion] ?? "Ver datos"}</summary>
          <dl className="mt-1 text-xs text-slate-500">
            {evento.datos.map((dato) => (
              <div key={dato.campo} className="flex flex-wrap gap-x-1">
                <dt className="font-semibold">{dato.campo}:</dt>
                <dd className="break-words">{dato.valor ?? "—"}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </>
  );
}

// Consulta de la bitácora para gerencia y administración (HU22).
export default function Auditoria() {
  // Filtros que se están escribiendo.
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  // Filtros de la última consulta: con ellos se pasa de página, no con lo que se esté escribiendo.
  const [filtrosAplicados, setFiltrosAplicados] = useState(FILTROS_VACIOS);
  // Listas de los selectores.
  const [usuarios, setUsuarios] = useState([]);
  const [tablas, setTablas] = useState([]);
  // Página actual y sus metadatos.
  const [resultado, setResultado] = useState(SIN_RESULTADOS);
  // Estados de carga y error; parte cargando porque consulta al abrir.
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  // Número de la última consulta: una respuesta antigua se descarta.
  const ultimaConsulta = useRef(0);

  // Pide una página con los filtros indicados.
  const consultar = useCallback(async (criterios, offset) => {
    // Marca esta consulta como la vigente.
    const consulta = ++ultimaConsulta.current;
    // Muestra la carga, limpia errores anteriores y recuerda los filtros usados.
    setCargando(true);
    setError("");
    setFiltrosAplicados(criterios);
    try {
      // Quita filtros vacíos antes de construir el query string.
      const parametros = Object.fromEntries(Object.entries(criterios).filter(([, valor]) => valor !== ""));
      // Pide la página.
      const pagina = await consultarBitacora({ ...parametros, limite: FILAS_POR_PAGINA, offset });
      // Guarda el resultado si sigue vigente.
      if (consulta === ultimaConsulta.current) setResultado(pagina);
    } catch (err) {
      // No deja resultados viejos junto al error.
      if (consulta === ultimaConsulta.current) {
        setResultado(SIN_RESULTADOS);
        setError(extraerMensajeError(err, "No se pudo consultar la bitácora"));
      }
    } finally {
      // Termina la carga de la consulta vigente.
      if (consulta === ultimaConsulta.current) setCargando(false);
    }
  }, []);

  // Al abrir la pantalla carga los selectores.
  useEffect(() => {
    // Pide las dos listas juntas.
    Promise.all([consultarUsuariosAuditoria(), consultarTablasAuditoria()])
      .then(([listaUsuarios, listaTablas]) => {
        // Llena los selectores.
        setUsuarios(listaUsuarios);
        setTablas(listaTablas);
      })
      // Sin selectores se puede seguir consultando sin esos filtros.
      .catch((err) => setError(extraerMensajeError(err, "No se pudieron cargar los filtros")));
  }, []);

  // Al abrir la pantalla muestra los cambios más recientes.
  useEffect(() => {
    consultar(FILTROS_VACIOS, 0);
  }, [consultar]);

  // Actualiza un filtro sin cambiar los demás.
  function cambiarFiltro(evento) {
    // El nombre del campo coincide con la clave del filtro.
    const { name, value } = evento.target;
    setFiltros((actuales) => ({ ...actuales, [name]: value }));
  }

  // Aplica los filtros del formulario desde la primera página.
  function aplicarFiltros(evento) {
    // Evita la navegación nativa.
    evento.preventDefault();
    // Consulta con lo escrito.
    consultar(filtros, 0);
  }

  // Quita los filtros y vuelve a los cambios más recientes.
  function limpiarFiltros() {
    setFiltros(FILTROS_VACIOS);
    consultar(FILTROS_VACIOS, 0);
  }

  // Última fila visible de la página.
  const ultimaFila = resultado.offset + resultado.items.length;

  // Renderiza filtros y resultados.
  return (
    <div className="space-y-6">
      {/* Encabezado del módulo de la Épica 4. */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E4 · Auditoría</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Bitácora de auditoría</h1>
        <p className="mt-2 text-sm text-slate-500">Consulte quién hizo cada cambio, cuándo ocurrió y los valores anterior y nuevo. Esta consulta no modifica datos.</p>
      </div>

      {/* Filtros: se combinan entre sí (criterio 1). */}
      <form onSubmit={aplicarFiltros} className={TARJETA}>
        <h2 className={`mb-3 ${SUBTITULO}`}>Filtros</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* Responsable: solo quienes tienen eventos. */}
          <div>
            <label htmlFor="bitacora-usuario" className={ETIQUETA}>Usuario</label>
            <select id="bitacora-usuario" name="usuario_id" value={filtros.usuario_id} onChange={cambiarFiltro} className={SELECTOR}>
              <option value="">Todos</option>
              {usuarios.map((usuario) => <option key={usuario.id} value={usuario.id}>{usuario.nombre_completo}</option>)}
            </select>
          </div>
          {/* Primer día, en hora de Chile. */}
          <div>
            <label htmlFor="bitacora-desde" className={ETIQUETA}>Desde</label>
            <input id="bitacora-desde" name="fecha_desde" type="date" value={filtros.fecha_desde} onChange={cambiarFiltro} className={CAMPO} />
          </div>
          {/* Último día, en hora de Chile. */}
          <div>
            <label htmlFor="bitacora-hasta" className={ETIQUETA}>Hasta</label>
            <input id="bitacora-hasta" name="fecha_hasta" type="date" value={filtros.fecha_hasta} onChange={cambiarFiltro} className={CAMPO} />
          </div>
          {/* Tabla: solo las que tienen eventos, con su nombre legible. */}
          <div>
            <label htmlFor="bitacora-tabla" className={ETIQUETA}>Tabla</label>
            <select id="bitacora-tabla" name="tabla" value={filtros.tabla} onChange={cambiarFiltro} className={SELECTOR}>
              <option value="">Todas</option>
              {tablas.map((tabla) => <option key={tabla} value={tabla}>{TEXTO_TABLA[tabla] ?? tabla}</option>)}
            </select>
          </div>
          {/* Crear, modificar o eliminar. */}
          <div>
            <label htmlFor="bitacora-accion" className={ETIQUETA}>Acción</label>
            <select id="bitacora-accion" name="accion" value={filtros.accion} onChange={cambiarFiltro} className={SELECTOR}>
              <option value="">Todas</option>
              {Object.entries(ACCIONES).map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
            </select>
          </div>
        </div>
        {/* Acciones de los filtros. */}
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="submit" disabled={cargando} className={BOTON_PRINCIPAL}>{cargando ? "Consultando…" : "Consultar"}</button>
          <button type="button" onClick={limpiarFiltros} className={BOTON_SECUNDARIO}>Limpiar</button>
        </div>
      </form>

      {/* Error de la consulta. */}
      {error && <p className={MENSAJE_ERROR} role="alert">{error}</p>}

      {/* Resultados. */}
      <section aria-labelledby="titulo-bitacora">
        {/* Total y posición dentro del total. */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="titulo-bitacora" className={SUBTITULO}>Registros ({resultado.total})</h2>
          {resultado.items.length > 0 && (
            <p className="text-xs text-slate-500">
              Mostrando {resultado.offset + 1} a {ultimaFila} de {resultado.total}.{resultado.hay_mas && " Use Siguiente para ver más."}
            </p>
          )}
        </div>
        {/* Tabla accesible; si no cabe, hace scroll dentro de su contenedor. */}
        <div role="region" aria-label="Registros de auditoría" aria-busy={cargando} tabIndex={0} className={CONTENEDOR_TABLA}>
          <table className="w-full text-sm">
            <caption className="sr-only">Bitácora de cambios con valores anterior y nuevo</caption>
            <thead className={ENCABEZADO_TABLA}>
              <tr>
                <th scope="col" className={CELDA}>Fecha</th>
                <th scope="col" className={CELDA}>Usuario</th>
                <th scope="col" className={CELDA}>Tabla / registro</th>
                <th scope="col" className={CELDA}>Acción</th>
                <th scope="col" className={CELDA}>Qué cambió</th>
                <th scope="col" className={CELDA}>Motivo</th>
              </tr>
            </thead>
            {/* Cargando y vacío ocupan una fila dentro de la tabla. */}
            <tbody className="divide-y divide-slate-100">
              {resultado.items.length === 0 ? (
                <tr><td colSpan={6} className={CELDA_AVISO}>{cargando ? "Cargando…" : error ? "Sin resultados: revise el mensaje de arriba." : "Sin registros para los filtros seleccionados."}</td></tr>
              ) : (
                resultado.items.map((evento) => (
                  <tr key={evento.id} className="align-top text-slate-600">
                    <td className={`${CELDA} whitespace-nowrap`}>{fechaHoraChile(evento.fecha_hora)}</td>
                    <td className={CELDA}>{evento.usuario}</td>
                    <td className={CELDA}>{TEXTO_TABLA[evento.tabla] ?? evento.tabla} / {evento.registro_id}</td>
                    <td className={CELDA}>{ACCIONES[evento.accion] ?? evento.accion}</td>
                    <td className={CELDA}><DetalleEvento evento={evento} /></td>
                    <td className={CELDA}>{evento.motivo ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {/* Paginación con los filtros de la última consulta. */}
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" disabled={cargando || resultado.offset === 0} className={BOTON_SECUNDARIO} onClick={() => consultar(filtrosAplicados, Math.max(0, resultado.offset - resultado.limite))}>Anterior</button>
          <button type="button" disabled={cargando || !resultado.hay_mas} className={BOTON_SECUNDARIO} onClick={() => consultar(filtrosAplicados, resultado.offset + resultado.limite)}>Siguiente</button>
        </div>
      </section>
    </div>
  );
}
