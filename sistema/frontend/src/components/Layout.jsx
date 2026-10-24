// Permite navegar con enlaces activos y mostrar el contenido de las rutas hijas.
import { NavLink, Outlet } from "react-router-dom";
// Reutiliza el usuario validado y el cierre de sesión existentes.
import { useAuth } from "../api/AuthContext";
// Comparte el filtro de navegación y las etiquetas legibles del perfil.
import { NOMBRE_ROL, opcionesPara } from "./menu";

// Presenta la estructura común de las pantallas privadas del sistema.
export default function Layout() {
  // La protección exterior espera a que termine la validación de la sesión.
  const { usuario, logout } = useAuth();
  // Calcula el menú a partir de los roles del usuario autenticado.
  const opciones = opcionesPara(usuario.roles);

  // Mantiene un único encabezado, navegación y contenido principal compartidos.
  return (
    <div className="min-h-screen bg-hielo">
      {/* Conserva la marca y adapta la identidad y la salida al ancho disponible. */}
      <header className="bg-frigorifico-950 text-white shadow-lg">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          {/* Identidad visual que antes estaba dentro de Inicio. */}
          <div className="shrink-0">
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-ambar">A2D SM</p>
            <p className="mt-1 text-sm text-blue-100">Trazabilidad operacional</p>
          </div>
          {/* Permite que nombre y roles se ajusten sin ocultar el cierre de sesión. */}
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 sm:justify-end sm:gap-5">
            <div className="min-w-0 flex-1 sm:text-right">
              <p className="break-words text-sm font-semibold">{usuario.nombre_completo}</p>
              <p className="mt-1 break-words text-xs leading-5 text-blue-100">
                {usuario.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}
              </p>
            </div>
            {/* Reutiliza logout y conserva el botón visible en pantallas pequeñas. */}
            <button
              type="button"
              onClick={logout}
              className="shrink-0 rounded-lg border border-white/30 px-4 py-2 text-sm font-semibold transition hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ambar"
            >
              Cerrar sesión
            </button>
          </div>
        </div>
      </header>

      {/* El menú se ajusta en varias líneas y tiene un nombre para lectores de pantalla. */}
      <nav aria-label="Navegación principal" className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap gap-2 px-5 py-3 sm:px-8">
          {/* La ruta identifica cada opción y end evita marcar Inicio en Productores. */}
          {opciones.map((opcion) => (
            <NavLink
              key={opcion.ruta}
              to={opcion.ruta}
              end={opcion.ruta === "/"}
              className={({ isActive }) =>
                `rounded-lg px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-frigorifico-700 ${
                  isActive
                    ? "bg-frigorifico-900 text-white"
                    : "text-frigorifico-800 hover:bg-frigorifico-50"
                }`
              }
            >
              {opcion.etiqueta}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Las páginas hijas aportan su contenido sin repetir main ni el encabezado. */}
      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <Outlet />
      </main>
    </div>
  );
}
