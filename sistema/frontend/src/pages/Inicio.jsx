// Importa el estado del usuario autenticado.
import { useAuth } from "../api/AuthContext";

// Reutiliza las mismas etiquetas de roles que muestra el encabezado compartido.
import { NOMBRE_ROL } from "../components/menu";

// Muestra la pantalla protegida mínima de E1.
export default function Inicio() {
  // La estructura común proporciona el cierre de sesión desde Layout.
  const { usuario } = useAuth();

  return (
    <>
      {/* Conserva el saludo dentro del contenido del layout, sin otro main. */}
      <div className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-widest text-frigorifico-700">Panel principal</p>
        <h1 className="mt-2 break-words text-3xl font-semibold text-frigorifico-950">Bienvenido, {usuario.nombre_completo}</h1>
        <p className="mt-2 text-slate-500">Tu sesión está activa y tus credenciales fueron verificadas.</p>
      </div>

      {/* Mantiene los datos públicos de la cuenta y sus roles asignados. */}
      <section aria-label="Perfil de usuario" className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <div className="flex items-center gap-4 border-b border-slate-100 pb-5">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-frigorifico-100 text-xl font-bold text-frigorifico-900">
              {usuario.nombre_completo.charAt(0).toUpperCase()}
            </div>
            <div>
              <h2 className="font-semibold text-frigorifico-950">Datos de la cuenta</h2>
              <p className="text-sm text-slate-500">Información de tu perfil.</p>
            </div>
          </div>
          <dl className="mt-5 grid gap-5 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">Usuario</dt>
              <dd className="mt-1 break-words font-medium text-slate-700">{usuario.nombre_usuario}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">Estado</dt>
              <dd className="mt-1 font-medium text-emerald-700">{usuario.activo ? "Activo" : "Inactivo"}</dd>
            </div>
          </dl>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <h2 className="font-semibold text-frigorifico-950">Roles asignados</h2>
          <p className="mt-1 text-sm text-slate-500">Permisos asociados a tu cuenta.</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {usuario.roles.map((rol) => (
              <span key={rol} className="rounded-full bg-frigorifico-50 px-3 py-2 text-sm font-medium text-frigorifico-900 ring-1 ring-frigorifico-100">
                {NOMBRE_ROL[rol] ?? rol}
              </span>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
