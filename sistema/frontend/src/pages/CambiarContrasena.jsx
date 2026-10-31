// Estado local del formulario.
import { useState } from "react";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Llamada a PUT /auth/me/password.
import { cambiarMiPassword } from "../api/usuarios";
// Mismos estilos de botón, campos y mensajes que los catálogos.
import { AYUDA, BOTON_PRINCIPAL, CAMPO, ETIQUETA, MENSAJE_ERROR, MENSAJE_EXITO } from "../components/catalogo";

// Bytes UTF-8 de un texto: bcrypt admite hasta 72 (una tilde ocupa 2).
function bytesUtf8(texto) {
  return new TextEncoder().encode(texto).length;
}

// Permite a cualquier perfil cambiar su propia contraseña.
export default function CambiarContrasena() {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  // Permite ver lo escrito para corregir errores de tipeo.
  const [ver, setVer] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [exito, setExito] = useState("");

  // Revisa en el navegador las mismas reglas que la API, para avisar antes de enviar.
  function validar() {
    if (nueva.length < 8) return "La contraseña nueva debe tener al menos 8 caracteres.";
    if (bytesUtf8(nueva) > 72) return "La contraseña nueva es demasiado larga (máximo 72 bytes; las tildes cuentan doble).";
    if (nueva !== confirmacion) return "La confirmación no coincide con la contraseña nueva.";
    if (nueva === actual) return "La contraseña nueva debe ser distinta de la actual.";
    return "";
  }

  // Envía el cambio y limpia el formulario si sale bien.
  async function enviar(event) {
    event.preventDefault();
    setError("");
    setExito("");
    const problema = validar();
    if (problema) {
      setError(problema);
      return;
    }
    setGuardando(true);
    try {
      await cambiarMiPassword(actual, nueva);
      setActual("");
      setNueva("");
      setConfirmacion("");
      setExito("Contraseña actualizada. Úsala la próxima vez que inicies sesión.");
    } catch (errorRecibido) {
      setError(extraerMensajeError(errorRecibido, "No se pudo cambiar la contraseña"));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <section aria-labelledby="titulo-cambiar-contrasena" className="max-w-xl">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">Mi cuenta</p>
      <h1 id="titulo-cambiar-contrasena" className="text-2xl font-bold text-frigorifico-900">Cambiar contraseña</h1>
      <p className="mt-2 text-sm text-slate-500">Por seguridad se pide tu contraseña actual.</p>

      {/* Formulario de un bloque, con el estilo de los formularios de la referencia. */}
      <form onSubmit={enviar} className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        {exito && <p role="status" className={`mb-4 ${MENSAJE_EXITO}`}>{exito}</p>}
        {error && <p role="alert" className={`mb-4 ${MENSAJE_ERROR}`}>{error}</p>}

        <fieldset disabled={guardando} className="grid gap-3">
          <div>
            <label htmlFor="password-actual" className={ETIQUETA}>Contraseña actual</label>
            <input id="password-actual" type={ver ? "text" : "password"} autoComplete="current-password" required maxLength={128} value={actual} onChange={(event) => setActual(event.target.value)} className={CAMPO} />
          </div>
          <div>
            <label htmlFor="password-nueva" className={ETIQUETA}>Contraseña nueva</label>
            <input id="password-nueva" type={ver ? "text" : "password"} autoComplete="new-password" required minLength={8} value={nueva} onChange={(event) => setNueva(event.target.value)} aria-describedby="ayuda-password-nueva" className={CAMPO} />
            <p id="ayuda-password-nueva" className={AYUDA}>Mínimo 8 caracteres. Mezcla letras, números y símbolos.</p>
          </div>
          <div>
            <label htmlFor="password-confirmacion" className={ETIQUETA}>Repite la contraseña nueva</label>
            <input id="password-confirmacion" type={ver ? "text" : "password"} autoComplete="new-password" required value={confirmacion} onChange={(event) => setConfirmacion(event.target.value)} className={CAMPO} />
          </div>
          {/* Un solo control muestra u oculta los tres campos. */}
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={ver} onChange={(event) => setVer(event.target.checked)} className="h-4 w-4" />
            Mostrar contraseñas
          </label>
          <div>
            <button type="submit" className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Cambiar contraseña"}</button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
