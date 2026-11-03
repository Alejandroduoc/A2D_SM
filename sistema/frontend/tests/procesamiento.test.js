// Usa el ejecutor de pruebas de Node sin agregar dependencias al proyecto.
import test from "node:test";
// Compara resultados con las aserciones estrictas de Node.
import assert from "node:assert/strict";
// Funciones de cálculo de la pantalla de procesamiento.
import { aCentimos, cajasParaSaldo, centimosDeFila, filasDeProceso, motivoMezcla, revisarFila, textoCajas, textoCentimos, textoKilos } from "../src/components/procesamiento.js";

// Embalaje fijo igual al 5x5 libras del legado.
const CAJA = { es_granel: false, kg_por_caja: "11.35" };
// Embalaje de 10 kg.
const CAJA_10 = { es_granel: false, kg_por_caja: "10.00" };
// Embalaje a granel.
const GRANEL = { es_granel: true, kg_por_caja: null };
// Tarja de ejemplo con 1.000 kg pendientes.
const TARJA = { numero_tarja: 7, kilos_pendientes: "1000.00", sistema_productivo: "Orgánico", especie: "Cereza", calidad: "Primera" };
// Arma una fila con los cambios indicados.
const fila = (cambios) => ({ tarja: TARJA, cantidad_cajas: "", kilos_procesados: "", tarja_terminada: false, ...cambios });

// Los centésimos no pasan por float.
test("convierte y muestra kilos y cajas sin perder centésimos", () => {
  assert.equal(aCentimos("998.80"), 99880);
  assert.equal(aCentimos("1,2"), 120);
  assert.equal(aCentimos("-1"), null);
  assert.equal(aCentimos("1.234"), null);
  assert.equal(textoCentimos(120), "1,20");
  assert.equal(textoCentimos(5), "0,05");
  assert.equal(textoKilos("998.80"), "998,80");
  assert.equal(textoCajas("92.00"), "92");
  assert.equal(textoCajas("0.50"), "0,5");
  assert.equal(textoCajas("100.00"), "100");
  assert.equal(textoCajas("13.25"), "13,25");
});

// Criterio 2: cajas por kilos de cada caja, también con decimales; a mano solo a granel.
test("calcula los kilos según el embalaje", () => {
  assert.equal(centimosDeFila(CAJA, fila({ cantidad_cajas: "88" })), 99880);
  assert.equal(centimosDeFila(CAJA, fila({ cantidad_cajas: "0,5" })), 568);
  // 1,5 × 11,35 = 17,025: redondeo bancario igual que la API.
  assert.equal(centimosDeFila(CAJA, fila({ cantidad_cajas: "1.5" })), 1702);
  assert.equal(centimosDeFila(CAJA, fila({ cantidad_cajas: "abc" })), null);
  assert.equal(centimosDeFila(GRANEL, fila({ cantidad_cajas: "1", kilos_procesados: "5,25" })), 525);
  assert.equal(centimosDeFila(null, fila({ cantidad_cajas: "1" })), null);
});

// Criterio 4 y cierre de la tarja.
test("revisa el saldo y orienta sobre lo que quedará", () => {
  // Más de lo pendiente no se puede guardar.
  assert.equal(revisarFila(CAJA, fila({ cantidad_cajas: "89" })).valida, false);
  // Menos que una caja: avisa antes de guardar.
  assert.match(revisarFila(CAJA, fila({ cantidad_cajas: "88" })).aviso, /1,20 kg pendientes: póngalos en otro proceso o rebájelos/);
  // Con la marca, el resto queda como merma.
  assert.match(revisarFila(CAJA, fila({ cantidad_cajas: "88", tarja_terminada: true })).aviso, /1,20 kg quedarán como merma/);
  // Con saldo suficiente no hay aviso.
  assert.equal(revisarFila(CAJA, fila({ cantidad_cajas: "10" })).aviso, undefined);
  // Justo lo pendiente se cierra sola.
  assert.match(revisarFila(GRANEL, fila({ cantidad_cajas: "1", kilos_procesados: "1000" })).aviso, /se cierra sola/);
  // Sin cajas, a granel tampoco se puede guardar.
  assert.equal(revisarFila(GRANEL, fila({ kilos_procesados: "5" })).valida, false);
  // Cero kilos a granel se rechaza.
  assert.equal(revisarFila(GRANEL, fila({ cantidad_cajas: "1", kilos_procesados: "0" })).valida, false);
  // Tres decimales se explican.
  assert.match(revisarFila(CAJA, fila({ cantidad_cajas: "1.234" })).error, /dos decimales/);
});

// Los kilos que sobran entran a otro proceso y llegan a 0.
test("calcula las cajas que dejan el saldo en 0", () => {
  // 1,20 kg con cajas de 11,35 kg son 0,11 cajas.
  assert.equal(cajasParaSaldo(CAJA, "1.20"), "0,11");
  // 5 kg con cajas de 10 kg son media caja.
  assert.equal(cajasParaSaldo(CAJA_10, "5.00"), "0,50");
  // El redondeo no deja saldo: 0,11 cajas calculan 1,25 kg y se usa el saldo exacto.
  const saldo = revisarFila(CAJA, { ...fila({ cantidad_cajas: "0,11" }), tarja: { ...TARJA, kilos_pendientes: "1.20" } });
  assert.equal(saldo.valida, true);
  assert.equal(saldo.kilos, 120);
  assert.match(saldo.aviso, /se cierra sola/);
  // Un centésimo de caja exacto de más ya no es redondeo.
  const pasado = revisarFila(CAJA_10, { ...fila({ cantidad_cajas: "92,01" }), tarja: { ...TARJA, kilos_pendientes: "920.00" } });
  assert.equal(pasado.valida, false);
});

// Edición: el caso de los 15 kilos de más.
test("al editar, lo que se baja vuelve a la tarja de recepción", () => {
  // Proceso con 15 cajas de 10 kg de una tarja de 920 kg.
  const [editada] = filasDeProceso({
    tarjas: [{ tarja_id: 1, numero_tarja: 7, kilos_disponibles: "920.00", productor_codigo: 1, productor_razon_social: "QA", sistema_productivo: "S", especie: "E", variedad: "V", calidad: "C", cantidad_cajas: "15.00", kilos_procesados: "150.00", tarja_terminada: false }],
  });
  // Las cajas actuales se muestran sin ceros que no aportan.
  assert.equal(editada.cantidad_cajas, "15");
  // Bajar 1,5 cajas devuelve 15 kg.
  const revision = revisarFila(CAJA_10, { ...editada, cantidad_cajas: "13,5" });
  assert.equal(revision.valida, true);
  assert.equal(revision.kilos, 13500);
  assert.equal(revision.devueltos, 1500);
  assert.match(revision.aviso, /Vuelven 15,00 kg a la tarja de recepción/);
  // Sin cambios no vuelve nada.
  assert.equal(revisarFila(CAJA_10, editada).devueltos, 0);
  // Subir usa lo disponible, que ya incluye lo que tiene la fila.
  assert.equal(revisarFila(CAJA_10, { ...editada, cantidad_cajas: "92" }).valida, true);
  assert.equal(revisarFila(CAJA_10, { ...editada, cantidad_cajas: "93" }).valida, false);
});

// Misma fruta en todo el proceso, como en la API.
test("no deja mezclar sistema productivo, especie ni calidad", () => {
  const detalle = [fila({})];
  assert.equal(motivoMezcla([], TARJA), "");
  assert.equal(motivoMezcla(detalle, { ...TARJA, numero_tarja: 8 }), "");
  assert.match(motivoMezcla(detalle, { ...TARJA, calidad: "Segunda" }), /otra calidad/);
  assert.match(motivoMezcla(detalle, { ...TARJA, especie: "Arándano" }), /otra especie/);
  assert.match(motivoMezcla(detalle, { ...TARJA, sistema_productivo: "Convencional" }), /otro sistema productivo/);
});
