// Estilos y reglas compartidas por las pantallas de mantenedores (productores, especies,
// variedades, calidades, sistemas productivos y usuarios), con el estilo de la referencia:
// azul marino, acentos dorados y acciones de fila como enlaces subrayados.

// Foco visible al navegar con teclado, igual en todos los botones.
const FOCO = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar";

// Botón principal (Guardar, Crear, Recargar).
export const BOTON_PRINCIPAL = `rounded bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Botón secundario (Cancelar).
export const BOTON_SECUNDARIO = `rounded border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-ambar hover:text-frigorifico-900 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

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
