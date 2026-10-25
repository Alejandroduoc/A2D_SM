// Comparte las etiquetas de roles entre el encabezado y el perfil de Inicio.
export const NOMBRE_ROL = {
  operador_recepcion: "Operador de recepción", // Presenta la especialidad de recepción.
  operador_proceso: "Operador de proceso", // Presenta la especialidad de proceso.
  gerencia: "Gerencia", // Identifica el perfil de consulta y gestión.
  administrador: "Administrador", // Identifica el perfil que mantiene productores.
};

// Declara únicamente las opciones disponibles en este bloque de navegación.
export const MENU = [
  {
    ruta: "/", // Inicio permanece disponible para los cuatro perfiles autenticados.
    etiqueta: "Inicio", // Texto visible del enlace al panel principal.
    roles: ["operador_recepcion", "operador_proceso", "gerencia", "administrador"], // Valores técnicos de la API.
  },
  {
    ruta: "/productores", // La ruta también se protege por rol en App.jsx.
    etiqueta: "Productores", // Nombre visible del mantenimiento.
    roles: ["administrador"], // Solo este perfil puede ver la opción.
  },
  {
    ruta: "/especies-variedades", // Comparte la protección administrativa del enrutador.
    etiqueta: "Especies y variedades", // Identifica los dos catálogos relacionados.
    roles: ["administrador"], // Las consultas también exigen este rol en la API.
  },
  {
    ruta: "/calidades-sistemas-productivos",
    etiqueta: "Calidades y sistemas productivos",
    roles: ["administrador"],
  },
  {
    ruta: "/usuarios", // Administración de cuentas; la API también exige administrador.
    etiqueta: "Usuarios", // Alta, roles, estado y restablecer contraseña.
    roles: ["administrador"], // Solo este perfil puede ver la opción.
  },
  {
    ruta: "/cambiar-contrasena", // Cada persona cambia su propia contraseña.
    etiqueta: "Cambiar contraseña", // Disponible para todos los perfiles.
    roles: ["operador_recepcion", "operador_proceso", "gerencia", "administrador"],
  },
];

// Devuelve las opciones permitidas sin modificar el arreglo compartido.
export function opcionesPara(roles = []) {
  // Un usuario multirrol accede si al menos uno de sus roles está permitido.
  return MENU.filter((opcion) => opcion.roles.some((rol) => roles.includes(rol)));
}
