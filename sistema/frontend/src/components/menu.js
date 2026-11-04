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
    ruta: "/recepcion", // Registro real de tarjas; la ruta también se protege en App.jsx.
    etiqueta: "Recepción", // Nombre visible sin la marca de vista previa.
    descripcion: "Registro de tarjas, numeración automática y cálculo de kilos netos (E3).",
    roles: ["operador_recepcion", "administrador"], // Coincide con /opciones y /tarjas.
  },
  {
    ruta: "/bandejas", // Saldo de bandejas (HU15); la ruta también se protege en App.jsx.
    etiqueta: "Bandejas", // Nombre visible.
    descripcion: "Saldo de bandejas de cada productor, por tipo de bandeja (E3).",
    roles: ["operador_recepcion", "administrador"], // Los mismos roles que exige /tarjas en la API.
  },
  {
    ruta: "/tarjas", // Consulta de tarjas (HU17); la ruta también se protege en App.jsx.
    etiqueta: "Tarjas", // Nombre visible.
    descripcion: "Búsqueda de tarjas por número, productor, fecha y estado, con su detalle y sus kilos (E3).",
    roles: ["operador_recepcion", "administrador"], // Los mismos roles que exige /tarjas en la API.
  },
  {
    ruta: "/procesamiento", // Registro de procesos (HU18); la ruta también se protege en App.jsx.
    etiqueta: "Procesamiento", // Nombre visible.
    descripcion: "Procesos de tarjas: folio, embalaje, cajas, consumo parcial y merma (E4).",
    roles: ["operador_proceso", "administrador"], // Los mismos roles que exige /procesos en la API.
  },
  {
    ruta: "/rendimiento", // Rendimiento y merma (HU19); la ruta también se protege en App.jsx.
    etiqueta: "Rendimiento", // Nombre visible.
    descripcion: "Rendimiento y merma de las tarjas de recepción, por folio de proceso (E4).",
    roles: ["operador_proceso", "administrador"], // Los mismos roles que exige /procesos en la API.
  },
  {
    ruta: "/trazabilidad", // Recorrido de una tarja (HU23); la ruta también se protege en App.jsx.
    etiqueta: "Trazabilidad", // Nombre visible.
    descripcion: "Recorrido completo de una tarja: recepción, procesos, kilos e historial de cambios (E4).",
    roles: ["gerencia", "administrador"], // Los mismos roles que exige /trazabilidad en la API.
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
