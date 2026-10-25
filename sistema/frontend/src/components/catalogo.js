// Estilos y reglas compartidas por las pantallas de catálogos (especies, variedades,
// calidades y sistemas productivos), para que se vean y se comporten igual que Productores.

// Foco visible al navegar con teclado, igual en todos los botones.
const FOCO = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700";

// Botón principal (Guardar, Recargar).
export const BOTON_PRINCIPAL = `rounded-lg bg-frigorifico-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-frigorifico-800 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Botón secundario (Cancelar).
export const BOTON_SECUNDARIO = `rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Botón "Editar" de una fila.
export const BOTON_EDITAR = `rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-frigorifico-900 transition hover:bg-frigorifico-50 ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;

// Botón de estado: ámbar para desactivar y verde para activar (no se confunden).
export function botonEstado(activo) {
  const color = activo
    ? "border-amber-300 text-amber-900 hover:bg-amber-50"
    : "border-emerald-300 text-emerald-800 hover:bg-emerald-50";
  return `rounded-lg border px-3 py-2 text-xs font-semibold transition ${color} ${FOCO} disabled:cursor-not-allowed disabled:opacity-50`;
}

// Fila que se está editando: se resalta para saber qué registro cambia.
export function claseFila(editando) {
  return editando ? "bg-amber-50 ring-1 ring-inset ring-amber-200" : "hover:bg-slate-50";
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
