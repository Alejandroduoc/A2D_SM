// Comparte las etiquetas de roles entre el encabezado, Inicio y Usuarios.
export const NOMBRE_ROL = {
  operador_recepcion: "Operador de recepción", // Presenta la especialidad de recepción.
  operador_proceso: "Operador de proceso", // Presenta la especialidad de proceso.
  gerencia: "Gerencia", // Identifica el perfil de consulta y gestión.
  administrador: "Administrador", // Identifica el perfil que mantiene los maestros.
};

// Todos los perfiles pueden entrar al panel principal.
const TODOS = ["operador_recepcion", "operador_proceso", "gerencia", "administrador"];

// Define una opción individual para reutilizarla en el menú y las tarjetas de Inicio.
function opcion(ruta, etiqueta, descripcion, roles) {
  // Conserva los cuatro datos que consumen Layout, Inicio y las pruebas.
  return { ruta, etiqueta, descripcion, roles };
}

// Opciones del menú superior; las entradas con grupo se despliegan en Layout.
export const MENU = [
  opcion("/", "Inicio", undefined, TODOS), // Panel principal.
  {
    grupo: "Recepción", // Agrupa el flujo de ingreso de fruta.
    opciones: [
      opcion("/recepcion", "Registrar tarja", "Registro de tarjas, numeración automática y cálculo de kilos netos (E3).", ["operador_recepcion", "administrador"]),
      opcion("/tarjas", "Consultar tarjas", "Búsqueda de tarjas por número, productor, fecha y estado, con su detalle y sus kilos (E3).", ["operador_recepcion", "administrador"]),
    ], // Registro y consulta comparten los mismos permisos.
  },
  opcion("/bandejas", "Bandejas", "Saldo de bandejas de cada productor, por tipo de bandeja (E3).", ["operador_recepcion", "administrador"]), // Saldo de recepción.
  opcion("/procesamiento", "Procesamiento", "Procesos de tarjas: folio, embalaje, cajas, consumo parcial y merma (E4).", ["operador_proceso", "administrador"]), // Flujo de proceso.
  opcion("/rendimiento", "Rendimiento", "Rendimiento y merma de las tarjas de recepción, por folio de proceso (E4).", ["operador_proceso", "administrador"]), // Consulta de proceso.
  {
    grupo: "Control", // Agrupa las consultas de supervisión.
    opciones: [
      opcion("/trazabilidad", "Trazabilidad", "Recorrido completo de una tarja: recepción, procesos, kilos e historial de cambios (E4).", ["gerencia", "administrador"]),
      opcion("/auditoria", "Auditoría", "Consulta de cambios con usuario, fecha, tabla, acción y valores (E4).", ["gerencia", "administrador"]),
    ], // Ambas consultas usan los mismos roles.
  },
  opcion("/productores", "Productores", "Productores que entregan fruta: RUT, razón social, contacto y estado (E2).", ["administrador"]), // Mantenimiento administrativo.
  opcion("/mantenedores", "Mantenedores", "Especies, variedades, calidades y sistemas productivos (E2).", ["administrador"]), // Catálogos maestros.
  opcion("/usuarios", "Usuarios", "Alta de cuentas, roles de acceso y restablecimiento de contraseñas (E1).", ["administrador"]), // Gestión de cuentas.
];

// Comprueba que un usuario tenga al menos un rol autorizado para una opción.
function opcionPermitida(opcionMenu, roles) {
  // El rol vigente de la base es la autoridad; aquí solo se oculta navegación no disponible.
  return opcionMenu.roles.some((rol) => roles.includes(rol));
}

// Devuelve entradas simples y grupos sin opciones que el usuario no puede visitar.
export function menuPara(roles = []) {
  // Recorre sin modificar MENU para conservarlo como definición compartida.
  return MENU.flatMap((entrada) => {
    // Una entrada simple se muestra solo con algún rol permitido.
    if (!entrada.grupo) return opcionPermitida(entrada, roles) ? [entrada] : [];
    // Filtra las opciones internas antes de decidir si el grupo aparece.
    const opciones = entrada.opciones.filter((opcionMenu) => opcionPermitida(opcionMenu, roles));
    // Un grupo sin opciones permitidas no se dibuja.
    return opciones.length ? [{ ...entrada, opciones }] : [];
  });
}

// Devuelve una lista plana para Inicio, incluyendo las opciones dentro de grupos.
export function opcionesPara(roles = []) {
  // Convierte cada grupo filtrado en sus enlaces internos sin alterar sus descripciones.
  return menuPara(roles).flatMap((entrada) => entrada.grupo ? entrada.opciones : [entrada]);
}
