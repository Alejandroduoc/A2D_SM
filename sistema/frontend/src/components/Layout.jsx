// Permite navegar con enlaces activos y mostrar el contenido de las rutas hijas.
import { NavLink, Outlet } from "react-router-dom";
// Reutiliza el usuario validado y el cierre de sesión existentes.
import { useAuth } from "../api/AuthContext";
// Comparte el filtro de navegación y las etiquetas legibles del perfil.
import { NOMBRE_ROL, opcionesPara } from "./menu";

// Enlace del menú superior: subrayado dorado cuando está activo.
function claseEnlace({ isActive }) {
  return `whitespace-nowrap border-b-2 py-1 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ambar-claro ${
    isActive ? "border-ambar-claro font-semibold text-white" : "border-transparent text-slate-300 hover:text-white"
  }`;
}

// Presenta la estructura común de las pantallas privadas del sistema.
export default function Layout() {
  // La protección exterior espera a que termine la validación de la sesión.
  const { usuario, logout } = useAuth();
  // Calcula el menú a partir de los roles del usuario autenticado.
  const opciones = opcionesPara(usuario.roles);

  return (
    <div className="min-h-screen">
      {/* Barra superior azul marino con marca, menú y datos de la sesión. */}
      <header className="border-b border-frigorifico-700 bg-frigorifico-900 text-white shadow-lg shadow-slate-900/10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-4 sm:px-6">
          <div className="flex min-w-0 flex-wrap items-center gap-x-8 gap-y-3">
            {/* Marca: cuadro con la inicial en dorado, como en la referencia. */}
            <NavLink to="/" className="flex items-center gap-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar-claro">
              <span className="grid h-9 w-9 place-items-center border border-ambar text-lg font-bold text-ambar-claro">A</span>
              <span>
                <span className="block font-serif text-lg tracking-wide">A2D SM</span>
                <span className="block text-[10px] uppercase tracking-[0.2em] text-slate-300">Gestión y trazabilidad</span>
              </span>
            </NavLink>
            {/* Menú filtrado por rol; se ajusta en varias líneas en pantallas chicas. */}
            <nav aria-label="Navegación principal" className="flex flex-wrap items-center gap-x-6 gap-y-2">
              {opciones.map((opcion) => (
                <NavLink key={opcion.ruta} to={opcion.ruta} end={opcion.ruta === "/"} className={claseEnlace}>
                  {opcion.etiqueta}
                </NavLink>
              ))}
            </nav>
          </div>
          {/* Nombre, roles, cambio de contraseña y salida. */}
          <div className="flex items-center gap-4 text-sm">
            <div className="text-right">
              <p className="font-semibold text-slate-100">{usuario.nombre_completo}</p>
              <p className="text-xs text-slate-400">{usuario.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}</p>
            </div>
            {/* Disponible para todos los perfiles. */}
            <NavLink to="/cambiar-contrasena" className={claseEnlace}>Contraseña</NavLink>
            <button
              type="button"
              onClick={logout}
              className="rounded border border-slate-500/70 px-3 py-1.5 text-sm text-slate-200 transition hover:border-ambar-claro hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar-claro"
            >
              Salir
            </button>
          </div>
        </div>
      </header>

      {/* Las páginas hijas aportan su contenido sin repetir main ni el encabezado. */}
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
