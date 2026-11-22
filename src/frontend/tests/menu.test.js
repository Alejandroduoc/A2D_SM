// Usa el ejecutor nativo de Node sin agregar dependencias al proyecto.
import test from "node:test";
// Compara estructuras y valores con aserciones estrictas.
import assert from "node:assert/strict";
// Prueba el filtrado del menú y la lista plana que consume Inicio.
import { menuPara, opcionesPara } from "../src/components/menu.js";

// Obtiene los nombres visibles de las entradas simples y los grupos.
function nombresMenu(roles) {
  // Convierte cada entrada a un nombre verificable por la prueba.
  return menuPara(roles).map((entrada) => entrada.grupo ?? entrada.etiqueta);
}

// Comprueba que recepción solo muestra su grupo y sus enlaces permitidos.
test("menú de operador de recepción", () => {
  // Busca la única agrupación del perfil de recepción.
  const recepcion = menuPara(["operador_recepcion"]).find((entrada) => entrada.grupo === "Recepción");
  // Conserva Inicio, Recepción y Bandejas, sin Control ni módulos de otros roles.
  assert.deepEqual(nombresMenu(["operador_recepcion"]), ["Inicio", "Recepción", "Bandejas"]);
  // El grupo contiene registro y consulta de tarjas.
  assert.deepEqual(recepcion.opciones.map((opcion) => opcion.etiqueta), ["Registrar tarja", "Consultar tarjas"]);
});

// Comprueba que proceso no recibe grupos que no le corresponden.
test("menú de operador de proceso", () => {
  // Mantiene únicamente el flujo de proceso como enlaces simples.
  assert.deepEqual(nombresMenu(["operador_proceso"]), ["Inicio", "Procesamiento", "Rendimiento"]);
});

// Comprueba que gerencia recibe solo el grupo de control.
test("menú de gerencia", () => {
  // Busca el grupo de consultas autorizado para gerencia.
  const control = menuPara(["gerencia"]).find((entrada) => entrada.grupo === "Control");
  // No aparecen módulos operativos ni administrativos.
  assert.deepEqual(nombresMenu(["gerencia"]), ["Inicio", "Control"]);
  // Control conserva sus dos consultas.
  assert.deepEqual(control.opciones.map((opcion) => opcion.etiqueta), ["Trazabilidad", "Auditoría"]);
});

// Comprueba que administrador recibe ambos grupos y todas las opciones restantes.
test("menú de administrador", () => {
  // Mantiene el orden funcional del menú completo.
  assert.deepEqual(nombresMenu(["administrador"]), ["Inicio", "Recepción", "Bandejas", "Procesamiento", "Rendimiento", "Control", "Productores", "Mantenedores", "Usuarios"]);
});

// Comprueba que Inicio conserva las rutas planas de los grupos del administrador.
test("lista plana de Inicio para administrador", () => {
  // Obtiene las rutas que Inicio utiliza para construir sus tarjetas.
  const rutas = opcionesPara(["administrador"]).map((opcion) => opcion.ruta);
  // Evita que una futura refactorización entregue objetos de grupo a Inicio.
  assert.deepEqual(rutas, ["/", "/recepcion", "/tarjas", "/bandejas", "/procesamiento", "/rendimiento", "/trazabilidad", "/auditoria", "/productores", "/mantenedores", "/usuarios"]);
});

// Comprueba que un usuario multirrol conserva ambos grupos.
test("menú de recepción y gerencia", () => {
  // No mezcla permisos, pero reúne las áreas de ambos roles.
  assert.deepEqual(nombresMenu(["operador_recepcion", "gerencia"]), ["Inicio", "Recepción", "Bandejas", "Control"]);
});
