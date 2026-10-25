// Importa el estado local del formulario.
import { useState } from "react";
// Importa redirección, navegación programática y lectura de la URL.
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
// Importa la normalización de errores.
import { extraerMensajeError } from "../api/client";
// Importa el estado de autenticación.
import { useAuth } from "../api/AuthContext";

// Clases comunes de los dos campos.
const CAMPO = "w-full rounded border border-slate-300 px-3 py-2.5 text-slate-800 outline-none transition focus:border-ambar focus:ring-2 focus:ring-ambar/20";

// Muestra el acceso institucional al sistema.
export default function Login() {
  const { usuario, login } = useAuth();
  const navigate = useNavigate();
  const [nombreUsuario, setNombreUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  // Permite ver la contraseña escrita para corregir errores de tipeo.
  const [verPassword, setVerPassword] = useState(false);
  // client.js agrega ?expirada=1 cuando la sesión ya no se pudo renovar.
  const [parametros] = useSearchParams();
  const sesionExpirada = parametros.get("expirada") === "1";

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
    <main className="flex min-h-[calc(100vh-50px)] items-center justify-center px-4 py-10">
      <div className="w-full max-w-4xl overflow-hidden rounded-xl border border-slate-200 bg-white/95 shadow-xl shadow-slate-900/10 md:grid md:grid-cols-[0.9fr_1.1fr]">
        {/* Panel de marca: azul marino con círculos decorativos (solo en pantallas medianas o más). */}
        <div className="relative hidden overflow-hidden bg-frigorifico-900 p-10 text-white md:flex md:flex-col md:justify-between">
          <div className="absolute -right-20 -top-20 h-56 w-56 rounded-full border border-ambar/40" aria-hidden="true" />
          <div className="absolute -bottom-24 -left-24 h-64 w-64 rounded-full border border-white/10" aria-hidden="true" />
          <div className="relative">
            <div className="mb-10 flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center border border-ambar text-lg font-bold text-ambar-claro">A</div>
              <div>
                <p className="font-serif text-lg tracking-wide">A2D SM</p>
                <p className="text-xs uppercase tracking-[0.22em] text-slate-300">Trazabilidad frutícola</p>
              </div>
            </div>
            <p className="max-w-xs text-sm leading-6 text-slate-300">
              Control preciso y seguro para cada etapa de la operación de la planta.
            </p>
          </div>
          <p className="relative text-xs uppercase tracking-[0.18em] text-ambar-claro">Acceso para personal autorizado</p>
        </div>

        <form onSubmit={handleSubmit} className="p-7 sm:p-10">
          <div className="mb-8">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">Acceso seguro</p>
            <h1 className="mb-2 text-2xl font-bold text-frigorifico-900">Bienvenido</h1>
            <p className="text-sm text-slate-500">Ingresa con tus credenciales para continuar.</p>
          </div>

          {/* Explica por qué se volvió al login sin que la persona cerrara sesión. */}
          {sesionExpirada && !error && (
            <div role="status" className="mb-5 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Tu sesión expiró. Vuelve a ingresar para continuar.
            </div>
          )}

          {error && (
            <div role="alert" className="mb-5 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <label htmlFor="nombre-usuario" className="mb-1 block text-sm font-semibold text-slate-700">
            Usuario
          </label>
          <input
            id="nombre-usuario"
            autoComplete="username"
            maxLength={50}
            className={`mb-5 ${CAMPO}`}
            value={nombreUsuario}
            onChange={(event) => setNombreUsuario(event.target.value)}
            autoFocus
            required
          />

          <label htmlFor="password" className="mb-1 block text-sm font-semibold text-slate-700">
            Contraseña
          </label>
          {/* El botón queda dentro del campo y alterna entre texto oculto y visible. */}
          <div className="relative mb-7">
            <input
              id="password"
              type={verPassword ? "text" : "password"}
              autoComplete="current-password"
              maxLength={128}
              className={`${CAMPO} pr-24`}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              type="button"
              onClick={() => setVerPassword((actual) => !actual)}
              aria-pressed={verPassword}
              aria-controls="password"
              className="absolute inset-y-0 right-2 my-auto h-8 rounded px-3 text-sm font-semibold text-frigorifico-800 hover:text-ambar focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar"
            >
              {verPassword ? "Ocultar" : "Mostrar"}
            </button>
          </div>

          <button
            type="submit"
            disabled={enviando}
            className="w-full rounded bg-frigorifico-900 py-2.5 font-semibold text-white transition hover:bg-frigorifico-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar disabled:cursor-not-allowed disabled:opacity-50"
          >
            {enviando ? "Ingresando..." : "Ingresar al sistema"}
          </button>
        </form>
      </div>
    </main>
  );
}
