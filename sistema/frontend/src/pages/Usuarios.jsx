// Estado, efectos y referencias de React.
import { useEffect, useRef, useState } from "react";
// Sesión actual: el administrador no puede desactivarse ni quitarse su rol.
import { useAuth } from "../api/AuthContext";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Operaciones de usuarios.
import { actualizarUsuario, crearUsuario, listarUsuarios } from "../api/usuarios";
// Estilos y reglas compartidas con los catálogos.
import { BOTON_EDITAR, BOTON_PRINCIPAL, BOTON_SECUNDARIO, botonEstado, claseEstado, claseFila, confirmarCambioEstado, enfocar } from "../components/catalogo";
// Nombres legibles de cada rol.
import { NOMBRE_ROL } from "../components/menu";

// Los cuatro roles en el orden en que se muestran.
const ROLES = ["operador_recepcion", "operador_proceso", "gerencia", "administrador"];
// Formulario vacío para un alta.
const FORM_VACIO = { id: null, nombre_usuario: "", nombre_completo: "", password: "", roles: [] };
// Clases comunes de los campos de texto.
const CAMPO = "w-full rounded-lg border border-slate-300 px-4 py-2 outline-none focus:border-ambar focus:ring-2 focus:ring-ambar/20 disabled:bg-slate-100";

// Bytes UTF-8 de un texto: bcrypt admite hasta 72.
function bytesUtf8(texto) {
  return new TextEncoder().encode(texto).length;
}

// Administración de cuentas: alta, edición, roles, estado y restablecer contraseña.
export default function Usuarios() {
  const { usuario: yo } = useAuth();
  const [usuarios, setUsuarios] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [errorListado, setErrorListado] = useState("");
  const [recarga, setRecarga] = useState(0);
  const [busqueda, setBusqueda] = useState("");
  // null = formulario cerrado; id null = alta; un id = edición.
  const [form, setForm] = useState(null);
  const [guardando, setGuardando] = useState(false);
  const [cambiandoId, setCambiandoId] = useState(null);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  // Evita dobles envíos.
  const escrituraEnCurso = useRef(false);
  // Campo de nombre completo, para enfocarlo al editar.
  const primerCampo = useRef(null);

  // Carga la lista al entrar y al pedir una recarga.
  useEffect(() => {
    let vigente = true;
    async function cargar() {
      setCargando(true);
      setErrorListado("");
      try {
        const filas = await listarUsuarios();
        if (vigente) setUsuarios(filas);
      } catch (errorRecibido) {
        if (vigente) setErrorListado(extraerMensajeError(errorRecibido, "No se pudo cargar la lista de usuarios"));
      } finally {
        if (vigente) setCargando(false);
      }
    }
    cargar();
    return () => { vigente = false; };
  }, [recarga]);

  // Filtra en el navegador por nombre de usuario o nombre completo.
  const termino = busqueda.trim().toLowerCase();
  const visibles = usuarios.filter((u) => !termino || u.nombre_usuario.toLowerCase().includes(termino) || u.nombre_completo.toLowerCase().includes(termino));
  // Indica si el formulario abierto es la propia cuenta.
  const editandoMiCuenta = form?.id === yo.id;

  // Abre el formulario vacío o con los datos de una cuenta.
  function abrir(cuenta = null) {
    if (escrituraEnCurso.current) return;
    setMensaje("");
    setError("");
    setForm(cuenta ? { id: cuenta.id, nombre_usuario: cuenta.nombre_usuario, nombre_completo: cuenta.nombre_completo, password: "", roles: [...cuenta.roles], original: cuenta } : { ...FORM_VACIO });
    // En el alta el foco va al nombre de usuario (autoFocus); al editar, al nombre completo.
    if (cuenta) enfocar(primerCampo);
  }

  // Marca o desmarca un rol en el formulario.
  function alternarRol(rol) {
    setForm((actual) => ({ ...actual, roles: actual.roles.includes(rol) ? actual.roles.filter((r) => r !== rol) : [...actual.roles, rol] }));
  }

  // Valida en el navegador las mismas reglas que la API.
  function validar(datos, esAlta) {
    if (esAlta && (datos.nombre_usuario.length < 3 || datos.nombre_usuario.length > 50)) return "El nombre de usuario debe tener entre 3 y 50 caracteres.";
    if (datos.nombre_completo.length < 3 || datos.nombre_completo.length > 150) return "El nombre completo debe tener entre 3 y 150 caracteres.";
    if (datos.roles.length === 0) return "Elige al menos un rol.";
    if ((esAlta || datos.password) && datos.password.length < 8) return "La contraseña debe tener al menos 8 caracteres.";
    if (datos.password && bytesUtf8(datos.password) > 72) return "La contraseña es demasiado larga (máximo 72 bytes; las tildes cuentan doble).";
    return "";
  }

  // Crea o edita enviando solo lo que cambió.
  async function guardar(event) {
    event.preventDefault();
    if (escrituraEnCurso.current || form === null) return;
    const esAlta = form.id === null;
    const datos = { ...form, nombre_usuario: form.nombre_usuario.trim(), nombre_completo: form.nombre_completo.trim() };
    const problema = validar(datos, esAlta);
    setError("");
    setMensaje("");
    if (problema) {
      setError(problema);
      return;
    }
    // Orden fijo de roles para comparar sin importar en qué orden se marcaron.
    const roles = ROLES.filter((rol) => datos.roles.includes(rol));
    let cuerpo;
    if (esAlta) {
      cuerpo = { nombre_usuario: datos.nombre_usuario, nombre_completo: datos.nombre_completo, password: datos.password, roles };
    } else {
      cuerpo = {};
      if (datos.nombre_completo !== form.original.nombre_completo) cuerpo.nombre_completo = datos.nombre_completo;
      if (roles.join() !== ROLES.filter((rol) => form.original.roles.includes(rol)).join()) cuerpo.roles = roles;
      if (datos.password) cuerpo.password = datos.password;
      if (Object.keys(cuerpo).length === 0) {
        setForm(null);
        setMensaje("No había cambios para guardar.");
        return;
      }
    }
    escrituraEnCurso.current = true;
    setGuardando(true);
    try {
      const resultado = esAlta ? await crearUsuario(cuerpo) : await actualizarUsuario(form.id, cuerpo);
      setMensaje(esAlta ? `Usuario «${resultado.nombre_usuario}» creado.` : `Usuario «${resultado.nombre_usuario}» actualizado${cuerpo.password ? " (contraseña restablecida)" : ""}.`);
      setForm(null);
      setRecarga((valor) => valor + 1);
    } catch (errorRecibido) {
      setError(extraerMensajeError(errorRecibido, "No se pudo guardar el usuario"));
    } finally {
      escrituraEnCurso.current = false;
      setGuardando(false);
    }
  }

  // Activa o desactiva una cuenta (no se borra).
  async function cambiarEstado(cuenta) {
    if (escrituraEnCurso.current || form !== null) return;
    if (!confirmarCambioEstado(cuenta.activo, `la cuenta «${cuenta.nombre_usuario}»`)) return;
    escrituraEnCurso.current = true;
    setCambiandoId(cuenta.id);
    setMensaje("");
    setError("");
    try {
      const resultado = await actualizarUsuario(cuenta.id, { activo: !cuenta.activo });
      setMensaje(`Usuario «${resultado.nombre_usuario}» ${resultado.activo ? "activado" : "desactivado"}.`);
      setRecarga((valor) => valor + 1);
    } catch (errorRecibido) {
      setError(extraerMensajeError(errorRecibido, "No se pudo cambiar el estado del usuario"));
    } finally {
      escrituraEnCurso.current = false;
      setCambiandoId(null);
    }
  }

  const ocupado = guardando || cambiandoId !== null;

  return (
    <section aria-labelledby="titulo-usuarios" className="min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E1 · Accesos</p>
          <h1 id="titulo-usuarios" className="text-2xl font-bold text-frigorifico-900">Usuarios</h1>
          <p className="mt-2 text-sm text-slate-500">Cuentas, roles y estado del personal que usa el sistema.</p>
        </div>
        <button type="button" onClick={() => abrir()} disabled={ocupado || form !== null} className={BOTON_PRINCIPAL}>Nuevo usuario</button>
      </div>

      {mensaje && <p role="status" className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{mensaje}</p>}
      {error && form === null && <p role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}

      {/* Formulario de alta o edición. */}
      {form !== null && (
        <form onSubmit={guardar} aria-labelledby="titulo-form-usuario" className="mt-6 rounded-lg border border-slate-200 bg-white shadow-sm p-5 sm:p-6">
          <h2 id="titulo-form-usuario" className="text-lg font-bold text-frigorifico-900">{form.id === null ? "Nuevo usuario" : `Editar «${form.nombre_usuario}»`}</h2>
          {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}
          <fieldset disabled={guardando} className="mt-5 grid min-w-0 gap-5 sm:grid-cols-2">
            <div>
              <label htmlFor="usuario-nombre-usuario" className="mb-2 block text-sm font-semibold text-slate-700">Nombre de usuario</label>
              {/* El nombre de login no se cambia después del alta. */}
              <input id="usuario-nombre-usuario" type="text" autoComplete="off" autoFocus required minLength={3} maxLength={50} value={form.nombre_usuario} onChange={(event) => setForm((actual) => ({ ...actual, nombre_usuario: event.target.value }))} disabled={form.id !== null} className={CAMPO} />
            </div>
            <div>
              <label htmlFor="usuario-nombre-completo" className="mb-2 block text-sm font-semibold text-slate-700">Nombre completo</label>
              <input ref={primerCampo} id="usuario-nombre-completo" type="text" required minLength={3} maxLength={150} value={form.nombre_completo} onChange={(event) => setForm((actual) => ({ ...actual, nombre_completo: event.target.value }))} className={CAMPO} />
            </div>
            <fieldset className="sm:col-span-2">
              <legend className="mb-2 text-sm font-semibold text-slate-700">Roles</legend>
              <div className="flex flex-wrap gap-4">
                {ROLES.map((rol) => (
                  <label key={rol} className="flex items-center gap-2 text-sm text-slate-700">
                    {/* El administrador no puede quitarse su propio rol de administrador. */}
                    <input type="checkbox" checked={form.roles.includes(rol)} onChange={() => alternarRol(rol)} disabled={editandoMiCuenta && rol === "administrador"} className="h-4 w-4" />
                    {NOMBRE_ROL[rol]}
                  </label>
                ))}
              </div>
            </fieldset>
            {editandoMiCuenta ? (
              <p className="text-sm text-slate-500 sm:col-span-2">Tu propia contraseña se cambia en «Cambiar contraseña».</p>
            ) : (
              <div className="sm:col-span-2">
                <label htmlFor="usuario-password" className="mb-2 block text-sm font-semibold text-slate-700">{form.id === null ? "Contraseña inicial" : "Restablecer contraseña"} {form.id !== null && <span className="font-normal text-slate-500">(opcional)</span>}</label>
                <input id="usuario-password" type="password" autoComplete="new-password" required={form.id === null} value={form.password} onChange={(event) => setForm((actual) => ({ ...actual, password: event.target.value }))} aria-describedby="ayuda-usuario-password" className={CAMPO} />
                <p id="ayuda-usuario-password" className="mt-2 text-xs text-slate-500">{form.id === null ? "Mínimo 8 caracteres. Entrégala a la persona por un canal seguro." : "Déjalo vacío para no cambiarla. Úsalo si la persona olvidó su contraseña."}</p>
              </div>
            )}
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <button type="submit" className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
              <button type="button" onClick={() => { setForm(null); setError(""); }} className={BOTON_SECUNDARIO}>Cancelar</button>
            </div>
          </fieldset>
        </form>
      )}

      {/* Buscador y recarga. */}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-4 rounded-lg border border-slate-200 bg-white shadow-sm p-5">
        <div className="w-full min-w-0 flex-1 sm:w-auto">
          <label htmlFor="buscar-usuarios" className="mb-2 block text-sm font-semibold text-slate-700">Buscar</label>
          <input id="buscar-usuarios" type="search" value={busqueda} onChange={(event) => setBusqueda(event.target.value)} placeholder="Usuario o nombre" className={CAMPO} />
        </div>
        <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando || ocupado} className={BOTON_PRINCIPAL}>Recargar</button>
      </div>

      {/* Tabla con estados de carga, error y vacío. */}
      <div className="mt-6 min-w-0" aria-busy={cargando}>
        {cargando ? (
          <p role="status" className="rounded-lg border border-slate-200 bg-white shadow-sm p-6 text-slate-500">Cargando usuarios…</p>
        ) : errorListado ? (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">{errorListado}</p>
        ) : visibles.length === 0 ? (
          <p role="status" className="rounded-lg border border-slate-200 bg-white shadow-sm p-6 text-slate-500">No hay usuarios que coincidan</p>
        ) : (
          <div role="region" aria-label="Listado de usuarios" tabIndex={0} className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar">
            <table className="w-full min-w-[760px] text-left text-sm">
              <caption className="sr-only">Usuarios del sistema</caption>
              <thead className="border-b border-slate-200 bg-frigorifico-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-5 py-4 font-semibold">Usuario</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Nombre completo</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Roles</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Estado</th>
                  <th scope="col" className="px-5 py-4 font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibles.map((cuenta) => (
                  <tr key={cuenta.id} className={claseFila(form?.id === cuenta.id)} aria-current={form?.id === cuenta.id ? "true" : undefined}>
                    <td className="whitespace-nowrap px-5 py-4 font-medium text-frigorifico-900">{cuenta.nombre_usuario}{cuenta.id === yo.id && <span className="ml-2 text-xs font-normal text-slate-500">(tú)</span>}</td>
                    <td className="px-5 py-4 text-slate-800">{cuenta.nombre_completo}</td>
                    <td className="px-5 py-4 text-slate-600">{cuenta.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}</td>
                    <td className="px-5 py-4">
                      <span className={claseEstado(cuenta.activo)}>{cuenta.activo ? "Activo" : "Inactivo"}</span>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={() => abrir(cuenta)} disabled={ocupado || form !== null} aria-label={`Editar ${cuenta.nombre_usuario}`} className={BOTON_EDITAR}>Editar</button>
                        {/* Nadie puede desactivar su propia cuenta. */}
                        {cuenta.id !== yo.id && (
                          <button type="button" onClick={() => cambiarEstado(cuenta)} disabled={ocupado || form !== null} aria-label={`${cuenta.activo ? "Desactivar" : "Activar"} ${cuenta.nombre_usuario}`} className={botonEstado(cuenta.activo)}>
                            {cambiandoId === cuenta.id ? "Actualizando…" : cuenta.activo ? "Desactivar" : "Activar"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
