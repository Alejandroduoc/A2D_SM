// Importa el estado local del formulario.
import { useState } from "react";
// Importa redirección y navegación programática.
import { Navigate, useNavigate } from "react-router-dom";
// Importa la normalización de errores.
import { extraerMensajeError } from "../api/client";
// Importa el estado de autenticación.
import { useAuth } from "../api/AuthContext";

// Muestra el acceso institucional al sistema.
export default function Login() {
  const { usuario, login } = useAuth();
  const navigate = useNavigate();
  const [nombreUsuario, setNombreUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  // Evita mostrar el formulario a una persona ya autenticada.
  if (usuario) return <Navigate to="/" replace />;

  // Envía las credenciales sin recargar la página.
  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await login(nombreUsuario, password);
      navigate("/");
    } catch (err) {
      setError(extraerMensajeError(err, "Error al iniciar sesión"));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="fondo-tecnico flex min-h-screen items-center justify-center px-4 py-10">
      <section className="grid w-full max-w-5xl overflow-hidden rounded-2xl bg-white shadow-panel lg:grid-cols-[1.05fr_0.95fr]">
        <div className="relative hidden overflow-hidden bg-frigorifico-950 p-12 text-white lg:block">
          <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full border-[28px] border-white/10" />
          <div className="absolute -bottom-24 -left-20 h-72 w-72 rounded-full border-[36px] border-ambar/30" />
          <div className="relative flex h-full flex-col justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.3em] text-ambar">A2D SM</p>
              <h1 className="mt-8 max-w-md text-4xl font-semibold leading-tight">
                Trazabilidad con precisión y control.
              </h1>
              <p className="mt-6 max-w-md text-base leading-7 text-blue-100">
                Plataforma operativa para una planta procesadora de fruta, diseñada para mantener cada etapa bajo control.
              </p>
            </div>
            <div className="border-l-2 border-ambar pl-4 text-sm text-blue-100">
              <p className="font-semibold text-white">Sistema de gestión operacional</p>
              <p className="mt-1">Acceso seguro para personal autorizado</p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="p-8 sm:p-12">
          <div className="mb-10">
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-frigorifico-700">Acceso al sistema</p>
            <h2 className="mt-3 text-3xl font-semibold text-frigorifico-950">Iniciar sesión</h2>
            <p className="mt-2 text-sm text-slate-500">Ingresa tus credenciales para continuar.</p>
          </div>

          {error && (
            <div role="alert" className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <label htmlFor="nombre-usuario" className="mb-2 block text-sm font-semibold text-slate-700">
            Usuario
          </label>
          <input
            id="nombre-usuario"
            autoComplete="username"
            className="mb-5 w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-frigorifico-700 focus:bg-white focus:ring-4 focus:ring-frigorifico-100"
            value={nombreUsuario}
            onChange={(event) => setNombreUsuario(event.target.value)}
            autoFocus
            required
          />

          <label htmlFor="password" className="mb-2 block text-sm font-semibold text-slate-700">
            Contraseña
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="mb-8 w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-frigorifico-700 focus:bg-white focus:ring-4 focus:ring-frigorifico-100"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          <button
            type="submit"
            disabled={enviando}
            className="w-full rounded-lg bg-frigorifico-900 py-3 font-semibold text-white shadow-lg shadow-frigorifico-900/20 transition hover:bg-frigorifico-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {enviando ? "Validando..." : "Ingresar al sistema"}
          </button>
        </form>
      </section>
    </main>
  );
}
