// Comparte las etiquetas de roles entre el encabezado, Inicio y Usuarios.
export const NOMBRE_ROL = {
  operador_recepcion: "Operador de recepción", // Presenta la especialidad de recepción.
  operador_proceso: "Operador de proceso", // Presenta la especialidad de proceso.
  gerencia: "Gerencia", // Identifica el perfil de consulta y gestión.
  administrador: "Administrador", // Identifica el perfil que mantiene los maestros.
};

// Todos los perfiles, para las opciones comunes.
const TODOS = ["operador_recepcion", "operador_proceso", "gerencia", "administrador"];

// Opciones del menú superior; Inicio muestra las demás como tarjetas con su descripción.
export const MENU = [
  {
    ruta: "/", // Panel principal.
    etiqueta: "Inicio", // Texto del enlace.
    roles: TODOS, // Disponible para los cuatro perfiles.
  },
  {
    ruta: "/productores", // La ruta también se protege por rol en App.jsx.
    etiqueta: "Productores", // Nombre visible del mantenimiento.
    descripcion: "Productores que entregan fruta: RUT, razón social, contacto y estado (E2).",
    roles: ["administrador"], // Solo este perfil puede ver la opción.
  },
  {
    ruta: "/mantenedores", // Catálogos agrupados en pestañas.
    etiqueta: "Mantenedores", // Nombre visible.
    descripcion: "Especies, variedades, calidades y sistemas productivos (E2).",
    roles: ["administrador"], // Las consultas también exigen este rol en la API.
  },
  {
    ruta: "/usuarios", // Administración de cuentas; la API también exige administrador.
    etiqueta: "Usuarios", // Alta, roles, estado y restablecer contraseña.
    descripcion: "Alta de cuentas, roles de acceso y restablecimiento de contraseñas (E1).",
    roles: ["administrador"], // Solo este perfil puede ver la opción.
  },
];

// Devuelve las opciones permitidas sin modificar el arreglo compartido.
export function opcionesPara(roles = []) {
  // Un usuario multirrol accede si al menos uno de sus roles está permitido.
  return MENU.filter((opcion) => opcion.roles.some((rol) => roles.includes(rol)));
}
