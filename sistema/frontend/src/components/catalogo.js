// Estilos y reglas compartidas por las pantallas de mantenedores (productores, especies,
// variedades, calidades, sistemas productivos y usuarios), con el estilo de la referencia:
// azul marino, acentos dorados y acciones de fila como enlaces subrayados.

// Foco visible al navegar con teclado, igual en todos los botones.
const FOCO = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar";

// Botón principal (Guardar, Crear, Recargar).
export const BOTON_PRINCIPAL = `rounded bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Botón secundario (Cancelar): contorno azul marino que se rellena al pasar el mouse.
export const BOTON_SECUNDARIO = `rounded border border-frigorifico-900 bg-white px-4 py-2 text-sm font-semibold text-frigorifico-900 transition hover:bg-frigorifico-900 hover:text-white ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Etiqueta de un campo: texto pequeño en gris; el campo va justo debajo.
export const ETIQUETA = "block text-xs font-semibold text-slate-600";

// Campo de texto o número; el borde dorado al enfocar y el gris deshabilitado son agregados de A2D SM.
export const CAMPO = "mt-1 w-full rounded border border-slate-300 px-2.5 py-2 text-sm outline-none focus:border-ambar focus:ring-2 focus:ring-ambar/20 disabled:bg-slate-100";

// Campo con un dato inválido: mismo tamaño, con borde y foco en rojo.
export const CAMPO_ERROR = "mt-1 w-full rounded border border-red-500 px-2.5 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-100 disabled:bg-slate-100";

// Lista desplegable: igual que el campo, con fondo blanco.
export const SELECTOR = `${CAMPO} bg-white disabled:cursor-not-allowed`;

// Texto de ayuda bajo un campo.
export const AYUDA = "mt-1 text-xs text-slate-500";

// Tarjeta blanca que envuelve un formulario.
export const TARJETA = "rounded-lg border border-slate-200 bg-white p-5 shadow-sm";

// Subtítulo dentro de una tarjeta o sobre un listado ("Nueva especie", "Registradas").
export const SUBTITULO = "text-sm font-semibold text-frigorifico-900";

// Mensaje de error (se usa con role="alert").
export const MENSAJE_ERROR = "rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700";

// Mensaje de éxito (se usa con role="status").
export const MENSAJE_EXITO = "rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700";

// Contenedor de una tabla: si no cabe, hace scroll dentro de sí mismo y no en la página.
export const CONTENEDOR_TABLA = `overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm ${FOCO}`;

// Encabezado de una tabla.
export const ENCABEZADO_TABLA = "bg-frigorifico-50 text-left text-xs uppercase tracking-wide text-slate-500";

// Celda de encabezado o de datos.
export const CELDA = "px-4 py-2";

// Opción de una lista de resultados (buscador de productores; luego, tarjas en E3).
// El contorno de foco va hacia adentro (-outline-offset-2): la lista hace scroll y recortaría uno hacia afuera.
export const OPCION_LISTA = "block w-full px-2.5 py-2 text-left text-sm text-slate-600 transition hover:bg-frigorifico-50 focus-visible:bg-frigorifico-50 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ambar";

// Celda única que ocupa toda la fila para "Cargando…" o "Sin registros".
export const CELDA_AVISO = "px-4 py-6 text-center text-slate-400";

// Acción "Editar" de una fila: enlace subrayado.
export const BOTON_EDITAR = `rounded text-sm text-slate-600 underline underline-offset-2 transition hover:text-frigorifico-900 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Acción de estado: también enlace; desactivar en ámbar oscuro para distinguirlo.
export function botonEstado(activo) {
  const color = activo ? "text-amber-800 hover:text-amber-950" : "text-emerald-700 hover:text-emerald-900";
  return `rounded text-sm underline underline-offset-2 transition ${color} ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;
}

// Etiqueta de estado (activo/inactivo) con borde, como en la referencia.
export function claseEstado(activo) {
  return `inline-flex rounded-full border px-2 py-0.5 text-xs ${activo ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-100 text-slate-500"}`;
}

// Fila que se está editando: se resalta para saber qué registro cambia.
export function claseFila(editando) {
  return editando ? "bg-amber-50/70 ring-1 ring-inset ring-ambar/40" : "hover:bg-slate-50";
}

// Solo desactivar pide confirmación (igual que Productores); activar se puede deshacer fácil.
export function confirmarCambioEstado(activo, descripcion) {
  if (!activo) return true;
  return window.confirm(`¿Desactivar ${descripcion}? Se conservarán sus datos y su historial.`);
}

// Lleva el foco al campo del formulario después de pulsar "Editar".
export function enfocar(ref) {
  // Espera a que React pinte el formulario con el nombre cargado.
  requestAnimationFrame(() => {
    ref.current?.focus();
    ref.current?.select();
  });
}
