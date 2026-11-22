// Permite navegar con enlaces activos y mostrar el contenido de las rutas hijas.
import { useEffect, useRef, useState } from "react";
// Permite detectar la ruta activa además de navegar y mostrar rutas hijas.
import { NavLink, Outlet, useLocation } from "react-router-dom";
// Reutiliza el usuario validado y el cierre de sesión existentes.
import { useAuth } from "../api/AuthContext";
// Comparte el filtro de navegación y las etiquetas legibles del perfil.
import { menuPara, NOMBRE_ROL } from "./menu";

// Enlace del menú superior: subrayado dorado cuando está activo.
function claseEnlace({ isActive }) {
  return `whitespace-nowrap border-b-2 py-1 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ambar-claro ${
    isActive ? "border-ambar-claro font-semibold text-white" : "border-transparent text-slate-300 hover:text-white"
  }`;
}

// Botón de un grupo: conserva el subrayado dorado cuando una de sus rutas está activa.
function claseGrupoMenu(activo) {
  // Usa las mismas dimensiones y foco que los enlaces simples del menú.
  return `whitespace-nowrap border-b-2 py-1 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ambar-claro ${
    activo ? "border-ambar-claro font-semibold text-white" : "border-transparent text-slate-300 hover:text-white"
  }`;
}

// Dibuja un grupo desplegable mediante el Popover nativo, sin roles ARIA de menú.
function GrupoMenu({ entrada, rutaActual }) {
  // Crea un identificador estable para conectar el botón con su panel nativo.
  const idPanel = `grupo-${entrada.grupo.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")}`;
  // Conserva el panel para escuchar su estado y cerrarlo al navegar.
  const panelRef = useRef(null);
  // Refleja en aria-expanded el estado real del popover.
  const [abierto, setAbierto] = useState(false);
  // Destaca el grupo si la ruta pertenece a alguna de sus opciones.
  const activo = entrada.opciones.some((opcion) => rutaActual === opcion.ruta || rutaActual.startsWith(`${opcion.ruta}/`));

  // React no administra el evento toggle del Popover API en esta versión.
  useEffect(() => {
    // Lee el panel una vez montado.
    const panel = panelRef.current;
    // Sin panel todavía no hay listener que registrar.
    if (!panel) return undefined;
    // Sincroniza el atributo de accesibilidad con el estado nativo.
    const sincronizar = (evento) => setAbierto(evento.newState === "open");
    // Registra el evento nativo del panel.
    panel.addEventListener("toggle", sincronizar);
    // Libera el listener al desmontar el grupo.
    return () => panel.removeEventListener("toggle", sincronizar);
  }, []);

  // Cierra el panel antes de que React cambie de ruta sin recargar la página.
  function cerrarAlNavegar() {
    // hidePopover existe junto al atributo popover que usa el panel.
    panelRef.current?.hidePopover();
  }

  return (
    <div className="relative">
      {/* commandfor y command llegan en minúscula al HTML para invocar el Popover API nativo. */}
      <button type="button" commandfor={idPanel} command="toggle-popover" aria-expanded={abierto} className={claseGrupoMenu(activo)}>
        {entrada.grupo} <span aria-hidden="true">▾</span>
      </button>
      {/* El panel queda inmediatamente después de su botón, como requiere el anclaje nativo. */}
      <div ref={panelRef} id={idPanel} popover="auto" className="menu-grupo-panel min-w-48 rounded border border-slate-200 bg-white p-2 shadow-lg">
        {/* Cada opción sigue siendo un enlace normal para Tab, Enter y lectores de pantalla. */}
        {entrada.opciones.map((opcion) => (
          <NavLink
            key={opcion.ruta}
            to={opcion.ruta}
            onClick={cerrarAlNavegar}
            className={({ isActive }) => `block rounded px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar ${
              isActive ? "bg-frigorifico-50 font-semibold text-frigorifico-900" : "text-frigorifico-900 hover:bg-frigorifico-50"
            }`}
          >
            {opcion.etiqueta}
          </NavLink>
        ))}
      </div>
    </div>
  );
}

// Presenta la estructura común de las pantallas privadas del sistema.
export default function Layout() {
  // La protección exterior espera a que termine la validación de la sesión.
  const { usuario, logout } = useAuth();
  // Lee la ruta actual para destacar un grupo cuando una de sus pantallas está abierta.
  const ubicacion = useLocation();
  // Calcula el menú a partir de los roles del usuario autenticado.
  const opciones = menuPara(usuario.roles);

  return (
    <div className="min-h-screen">
      {/* Barra superior azul marino en dos filas fijas: marca y sesión arriba, menú abajo. */}
      {/* Socradex usa una sola fila, pero con las 10 opciones del administrador la sesión bajaba desordenada. */}
      <header className="border-b border-frigorifico-700 bg-frigorifico-900 text-white shadow-lg shadow-slate-900/10">
        {/* Mismo ancho y márgenes laterales que el contenido de la página. */}
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          {/* Fila 1: si no cabe (teléfono), la sesión pasa abajo de la marca y sigue a la derecha. */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 py-4">
            {/* Marca: cuadro con la inicial en dorado, como en la referencia; nunca se achica. */}
            <NavLink to="/" className="flex shrink-0 items-center gap-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar-claro">
              <span className="grid h-9 w-9 place-items-center border border-ambar text-lg font-bold text-ambar-claro">A</span>
              <span>
                <span className="block font-serif text-lg tracking-wide">A2D SM</span>
                <span className="block text-[10px] uppercase tracking-[0.2em] text-slate-300">Gestión y trazabilidad</span>
              </span>
            </NavLink>
            {/* Nombre, roles, cambio de contraseña y salida; ml-auto los mantiene a la derecha aunque queden solos. */}
            <div className="ml-auto flex min-w-0 max-w-full items-center gap-4 text-sm">
              {/* min-w-0 permite que un nombre muy largo se recorte en vez de empujar los botones. */}
              <div className="min-w-0 text-right">
                {/* truncate corta con puntos suspensivos; title muestra el nombre completo al pasar el mouse. */}
                <p className="truncate font-semibold text-slate-100" title={usuario.nombre_completo}>{usuario.nombre_completo}</p>
                {/* Los roles se recortan igual si un usuario tiene varios. */}
                <p className="truncate text-xs text-slate-400">{usuario.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}</p>
              </div>
              {/* Disponible para todos los perfiles; shrink-0 evita que se parta en dos líneas. */}
              <NavLink to="/cambiar-contrasena" className={(estado) => `shrink-0 ${claseEnlace(estado)}`}>Contraseña</NavLink>
              <button
                type="button"
                onClick={logout}
                className="shrink-0 rounded border border-slate-500/70 px-3 py-1.5 text-sm text-slate-200 transition hover:border-ambar-claro hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar-claro"
              >
                Salir
              </button>
            </div>
          </div>
          {/* Fila 2: menú filtrado por rol, separado por una línea; se ajusta en varias líneas si no cabe. */}
          <nav aria-label="Navegación principal" className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-frigorifico-700 py-3">
            {opciones.map((opcion) => opcion.grupo ? (
              <GrupoMenu key={opcion.grupo} entrada={opcion} rutaActual={ubicacion.pathname} />
            ) : (
              <NavLink key={opcion.ruta} to={opcion.ruta} end={opcion.ruta === "/"} className={claseEnlace}>
                {opcion.etiqueta}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Las páginas hijas aportan su contenido sin repetir main ni el encabezado. */}
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
