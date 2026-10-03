// Importa el estado del usuario autenticado.
import { useAuth } from "../api/AuthContext";

// Traduce los valores técnicos de roles a nombres para la interfaz.
const NOMBRE_ROL = {
  operador_recepcion: "Operador de recepción",
  operador_proceso: "Operador de proceso",
  gerencia: "Gerencia",
  administrador: "Administrador",
};

// Muestra la pantalla protegida mínima de E1.
export default function Inicio() {
  const { usuario, logout } = useAuth();

  return (
    <div className="min-h-screen bg-hielo">
      <header className="bg-frigorifico-950 text-white shadow-lg">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.28em] text-ambar">A2D SM</p>
            <p className="mt-1 text-sm text-blue-100">Trazabilidad operacional</p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg border border-white/30 px-4 py-2 text-sm font-semibold transition hover:bg-white/10"
          >
            Cerrar sesión
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <div className="mb-8">
          <p className="text-sm font-semibold uppercase tracking-widest text-frigorifico-700">Panel principal</p>
          <h1 className="mt-2 text-3xl font-semibold text-frigorifico-950">Bienvenido, {usuario.nombre_completo}</h1>
          <p className="mt-2 text-slate-500">Tu sesión está activa y tus credenciales fueron verificadas.</p>
        </div>

        <section className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
            <div className="flex items-center gap-4 border-b border-slate-100 pb-5">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-frigorifico-100 text-xl font-bold text-frigorifico-900">
                {usuario.nombre_completo.charAt(0).toUpperCase()}
              </div>
              <div>
                <h2 className="font-semibold text-frigorifico-950">Datos de la cuenta</h2>
                <p className="text-sm text-slate-500">Información obtenida desde /auth/me</p>
              </div>
            </div>
            <dl className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">Usuario</dt>
                <dd className="mt-1 font-medium text-slate-700">{usuario.nombre_usuario}</dd>
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
      </main>
    </div>
  );
}
