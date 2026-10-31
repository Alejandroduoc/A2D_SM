// Estado, efectos y referencias de React.
import { useEffect, useRef, useState } from "react";
// Sesión actual: el administrador no puede desactivarse ni quitarse su rol.
import { useAuth } from "../api/AuthContext";
// Convierte errores de la API en mensajes legibles.
import { extraerMensajeError } from "../api/client";
// Operaciones de usuarios.
import { actualizarUsuario, crearUsuario, listarUsuarios } from "../api/usuarios";
// Estilos y reglas compartidas con los catálogos.
import {
  AYUDA,
  BOTON_EDITAR,
  BOTON_PRINCIPAL,
  BOTON_SECUNDARIO,
  botonEstado,
  CAMPO,
  CELDA,
  CELDA_AVISO,
  claseEstado,
  claseFila,
  confirmarCambioEstado,
  CONTENEDOR_TABLA,
  ENCABEZADO_TABLA,
  enfocar,
  ETIQUETA,
  MENSAJE_ERROR,
  MENSAJE_EXITO,
  SUBTITULO,
  TARJETA,
} from "../components/catalogo";
// Nombres legibles de cada rol.
import { NOMBRE_ROL } from "../components/menu";

// Los cuatro roles en el orden en que se muestran.
const ROLES = ["operador_recepcion", "operador_proceso", "gerencia", "administrador"];
// Formulario vacío para un alta.
const FORM_VACIO = { id: null, nombre_usuario: "", nombre_completo: "", password: "", roles: [] };

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

      {mensaje && <p role="status" className={`mt-6 ${MENSAJE_EXITO}`}>{mensaje}</p>}
      {error && form === null && <p role="alert" className={`mt-6 ${MENSAJE_ERROR}`}>{error}</p>}

      {/* Tarjeta del formulario de alta o edición: campos en grilla y botones debajo. */}
      {form !== null && (
        <form onSubmit={guardar} aria-labelledby="titulo-form-usuario" className={`mt-6 ${TARJETA}`}>
          <h2 id="titulo-form-usuario" className={`mb-3 ${SUBTITULO}`}>{form.id === null ? "Nuevo usuario" : `Editar «${form.nombre_usuario}»`}</h2>
          {error && <p role="alert" className={`mb-3 ${MENSAJE_ERROR}`}>{error}</p>}
          <fieldset disabled={guardando} className="min-w-0">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="usuario-nombre-usuario" className={ETIQUETA}>Nombre de usuario</label>
                {/* El nombre de login no se cambia después del alta. */}
                <input id="usuario-nombre-usuario" type="text" autoComplete="off" autoFocus required minLength={3} maxLength={50} value={form.nombre_usuario} onChange={(event) => setForm((actual) => ({ ...actual, nombre_usuario: event.target.value }))} disabled={form.id !== null} className={CAMPO} />
              </div>
              <div>
                <label htmlFor="usuario-nombre-completo" className={ETIQUETA}>Nombre completo</label>
                <input ref={primerCampo} id="usuario-nombre-completo" type="text" required minLength={3} maxLength={150} value={form.nombre_completo} onChange={(event) => setForm((actual) => ({ ...actual, nombre_completo: event.target.value }))} className={CAMPO} />
              </div>
              <fieldset className="sm:col-span-2">
                <legend className={ETIQUETA}>Roles</legend>
                <div className="mt-1 flex flex-wrap gap-4">
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
                <p className="text-xs text-slate-500 sm:col-span-2">Tu propia contraseña se cambia en «Cambiar contraseña».</p>
              ) : (
                <div className="sm:col-span-2">
                  <label htmlFor="usuario-password" className={ETIQUETA}>{form.id === null ? "Contraseña inicial" : "Restablecer contraseña"} {form.id !== null && <span className="font-normal text-slate-500">(opcional)</span>}</label>
                  <input id="usuario-password" type="password" autoComplete="new-password" required={form.id === null} value={form.password} onChange={(event) => setForm((actual) => ({ ...actual, password: event.target.value }))} aria-describedby="ayuda-usuario-password" className={CAMPO} />
                  <p id="ayuda-usuario-password" className={AYUDA}>{form.id === null ? "Mínimo 8 caracteres. Entrégala a la persona por un canal seguro." : "Déjalo vacío para no cambiarla. Úsalo si la persona olvidó su contraseña."}</p>
                </div>
              )}
            </div>
            {/* Botones debajo de los campos, como en la referencia. */}
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="submit" className={BOTON_PRINCIPAL}>{guardando ? "Guardando…" : "Guardar"}</button>
              <button type="button" onClick={() => { setForm(null); setError(""); }} className={BOTON_SECUNDARIO}>Cancelar</button>
            </div>
          </fieldset>
        </form>
      )}

      {/* Encabezado del listado: subtítulo a la izquierda; búsqueda y recarga a la derecha. */}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className={SUBTITULO}>Registrados</h2>
        <div className="flex w-full flex-wrap items-end gap-3 sm:w-auto">
          <div className="w-full sm:w-56">
            <label htmlFor="buscar-usuarios" className={ETIQUETA}>Buscar</label>
            <input id="buscar-usuarios" type="search" value={busqueda} onChange={(event) => setBusqueda(event.target.value)} placeholder="Usuario o nombre" className={CAMPO} />
          </div>
          <button type="button" onClick={() => setRecarga((valor) => valor + 1)} disabled={cargando || ocupado} className={BOTON_PRINCIPAL}>Recargar</button>
        </div>
      </div>

      {/* El error de consulta se muestra como mensaje; la tabla queda con su aviso. */}
      {errorListado && <p role="alert" className={`mt-4 ${MENSAJE_ERROR}`}>{errorListado}</p>}
      {/* Sin ancho mínimo: si la tabla no cabe, el desplazamiento queda dentro de su contenedor. */}
      <div role="region" aria-label="Listado de usuarios" aria-busy={cargando} tabIndex={0} className={`mt-4 ${CONTENEDOR_TABLA}`}>
        <table className="w-full text-sm">
          <caption className="sr-only">Usuarios del sistema</caption>
          <thead className={ENCABEZADO_TABLA}>
            <tr>
              <th scope="col" className={CELDA}>Usuario</th>
              <th scope="col" className={CELDA}>Nombre completo</th>
              <th scope="col" className={CELDA}>Roles</th>
              <th scope="col" className={CELDA}>Estado</th>
              <th scope="col" className={CELDA}><span className="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {/* Cargando, error y vacío son una fila dentro de la tabla, como en la referencia. */}
            {cargando ? <tr><td colSpan={5} className={CELDA_AVISO}>Cargando…</td></tr>
              : errorListado ? <tr><td colSpan={5} className={CELDA_AVISO}>No se pudo cargar el listado.</td></tr>
                : visibles.length === 0 ? <tr><td colSpan={5} className={CELDA_AVISO}>Sin usuarios que coincidan.</td></tr>
                  : visibles.map((cuenta) => (
                    <tr key={cuenta.id} className={claseFila(form?.id === cuenta.id)} aria-current={form?.id === cuenta.id ? "true" : undefined}>
                      <td className={`whitespace-nowrap ${CELDA} text-slate-600`}>{cuenta.nombre_usuario}{cuenta.id === yo.id && <span className="ml-2 text-xs text-slate-400">(tú)</span>}</td>
                      <td className={`${CELDA} text-slate-600`}>{cuenta.nombre_completo}</td>
                      <td className={`${CELDA} text-slate-600`}>{cuenta.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}</td>
                      <td className={CELDA}>
                        <span className={claseEstado(cuenta.activo)}>{cuenta.activo ? "Activo" : "Inactivo"}</span>
                      </td>
                      <td className={`${CELDA} text-right`}>
                        <div className="flex flex-wrap justify-end gap-3">
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
    </section>
  );
}
