// Cálculos de la pantalla de procesamiento (HU18), sin React para poder probarlos con node --test.
// Solo orientan al operador: la API vuelve a calcular y validar todo al guardar.

// Convierte un decimal escrito a centésimos exactos; null indica entrada incompleta o inválida.
export function aCentimos(valor) {
  // Acepta la coma decimal que escribe el operador.
  const texto = String(valor ?? "").trim().replace(",", ".");
  // Solo dígitos con hasta dos decimales, sin signo.
  if (!/^\d+(?:\.\d{0,2})?$/.test(texto)) return null;
  // Separa enteros y decimales para no pasar por float.
  const [enteros, decimales = ""] = texto.split(".");
  // Completa los decimales a dos dígitos y suma los centésimos.
  return Number(enteros) * 100 + Number(decimales.padEnd(2, "0"));
}

// Muestra centésimos como kilos con coma: 120 pasa a "1,20".
export function textoCentimos(centimos) {
  // Parte entera.
  const enteros = Math.floor(centimos / 100);
  // Parte decimal, siempre con dos dígitos.
  const decimales = String(centimos % 100).padStart(2, "0");
  // Une ambas con la coma de Chile.
  return `${enteros},${decimales}`;
}

// Muestra un peso decimal de la API con coma, sin pasar por float.
export function textoKilos(valor) {
  // La API entrega los decimales como texto.
  return String(valor).replace(".", ",");
}

// Muestra una cantidad de cajas: 92.00 pasa a "92" y 0.50 a "0,5".
export function textoCajas(valor) {
  // Quita los ceros que no aportan y usa la coma.
  return String(valor).replace(/\.?0+$/, "").replace(".", ",");
}

// Divide por 100 con el mismo redondeo bancario de la API.
function centesimosRedondeados(producto) {
  // Parte entera.
  const entero = Math.floor(producto / 100);
  // Lo que falta dividir.
  const resto = producto % 100;
  // Bajo la mitad baja y sobre la mitad sube.
  if (resto !== 50) return resto < 50 ? entero : entero + 1;
  // Justo en la mitad va al par.
  return entero % 2 === 0 ? entero : entero + 1;
}

// Calcula los centésimos de kilo de una fila; null si todavía no se puede.
export function centimosDeFila(embalaje, fila) {
  // Sin embalaje no hay cálculo.
  if (!embalaje) return null;
  // A granel los kilos se ingresan a mano.
  if (embalaje.es_granel) return aCentimos(fila.kilos_procesados);
  // Las cajas admiten dos decimales.
  const cajas = aCentimos(fila.cantidad_cajas);
  if (cajas === null || cajas <= 0) return null;
  // Cajas por kilos de cada caja, igual que la API.
  return centesimosRedondeados(cajas * aCentimos(embalaje.kg_por_caja));
}

// Cajas que dejan el saldo exacto en 0, redondeadas hacia arriba a un centésimo de caja.
export function cajasParaSaldo(embalaje, pendientes) {
  // Kilos que quedan.
  const saldo = aCentimos(pendientes);
  // Kilos de cada caja.
  const caja = aCentimos(embalaje.kg_por_caja);
  // Centésimos de caja necesarios.
  const centesimos = Math.ceil((saldo * 100) / caja);
  // Se escribe con la coma que usa el operador.
  return textoCentimos(centesimos);
}

// Revisa una fila: error impide guardar y aviso solo orienta.
export function revisarFila(embalaje, fila) {
  // Sin nada escrito no se avisa, pero tampoco se puede guardar.
  const cajasEscritas = String(fila.cantidad_cajas ?? "").trim();
  // Las cajas son obligatorias, también a granel.
  const cajas = aCentimos(cajasEscritas);
  const cajasValidas = cajas !== null && cajas > 0;
  // Con algo escrito que no sirve, se explica.
  if (cajasEscritas !== "" && !cajasValidas) return { valida: false, error: "Ingrese las cajas con hasta dos decimales." };
  // Calcula los kilos de la fila.
  let kilos = centimosDeFila(embalaje, fila);
  // Datos incompletos: sin mensaje, el botón queda desactivado.
  if (!cajasValidas || kilos === null) return { valida: false, kilos: null };
  // A granel, los kilos deben ser mayores que cero.
  if (kilos <= 0) return { valida: false, kilos, error: "Ingrese los kilos de la tarja." };
  // Lo que puede usar: lo pendiente y, al editar, lo que la fila ya tiene.
  const pendientes = aCentimos(fila.tarja.kilos_pendientes);
  // Una diferencia menor que un centésimo de caja es redondeo: la API usa el saldo exacto.
  if (!embalaje.es_granel && kilos > pendientes && (kilos - pendientes) * 100 < aCentimos(embalaje.kg_por_caja)) kilos = pendientes;
  // HU18 criterio 4: nunca más de lo disponible.
  if (kilos > pendientes) return { valida: false, kilos, error: `Supera los ${textoCentimos(pendientes)} kg disponibles.` };
  // Lo que quedaría después de este proceso.
  const resto = pendientes - kilos;
  // Al editar, lo que se baja vuelve a la tarja de recepción.
  const originales = fila.kilos_originales === undefined ? null : aCentimos(fila.kilos_originales);
  const devueltos = originales !== null && kilos < originales ? originales - kilos : 0;
  // Reúne lo que el operador debe saber.
  const avisos = [];
  // Primero, los kilos que vuelven.
  if (devueltos > 0) avisos.push(`Vuelven ${textoCentimos(devueltos)} kg a la tarja de recepción.`);
  // Justo lo que queda: se cierra sola.
  if (resto === 0) avisos.push("Queda en 0 kg: la tarja se cierra sola.");
  // Con la marca, el resto pasa a merma.
  else if (fila.tarja_terminada) avisos.push(`${textoCentimos(resto)} kg quedarán como merma.`);
  // No alcanza para otra caja: el operador debe saberlo ahora.
  else if (!embalaje.es_granel && resto < aCentimos(embalaje.kg_por_caja)) avisos.push(`Quedarán ${textoCentimos(resto)} kg pendientes: póngalos en otro proceso o rebájelos como merma.`);
  // Entrega el resultado.
  return { valida: true, kilos, resto, devueltos, ...(avisos.length > 0 ? { aviso: avisos.join(" ") } : {}) };
}

// Indica por qué una tarja no se puede sumar al detalle; vacío si se puede.
export function motivoMezcla(detalle, tarja) {
  // La primera tarja del detalle es la referencia, igual que en la API.
  const primera = detalle[0]?.tarja;
  // Con el detalle vacío no hay con qué comparar.
  if (!primera) return "";
  // Mismo sistema productivo.
  if (tarja.sistema_productivo !== primera.sistema_productivo) return `La tarja N° ${tarja.numero_tarja} tiene otro sistema productivo: no se puede mezclar en el mismo proceso.`;
  // Misma especie.
  if (tarja.especie !== primera.especie) return `La tarja N° ${tarja.numero_tarja} es de otra especie: no se puede mezclar en el mismo proceso.`;
  // Misma calidad; la variedad sí puede variar.
  if (tarja.calidad !== primera.calidad) return `La tarja N° ${tarja.numero_tarja} tiene otra calidad: no se puede mezclar en el mismo proceso.`;
  // Se puede sumar.
  return "";
}

// Separa los folios que escribe el operador, con comas, punto y coma o espacios.
export function separarFolios(texto) {
  // La validación del formato la hace la API, que explica cuál no sirve.
  return String(texto ?? "").split(/[\s,;]+/).filter(Boolean);
}

// Convierte un proceso guardado en las filas del formulario de edición.
export function filasDeProceso(proceso) {
  // Una fila por cada tarja del proceso.
  return proceso.tarjas.map((fila) => ({
    // Lo que la pantalla necesita mostrar; lo disponible ya incluye lo que tiene esta fila.
    tarja: {
      id: fila.tarja_id, // Identificador que se envía al guardar.
      numero_tarja: fila.numero_tarja, // Número visible.
      kilos_pendientes: fila.kilos_disponibles, // Tope de la fila al editar.
      productor_codigo: fila.productor_codigo, // Código del productor.
      productor_razon_social: fila.productor_razon_social, // Nombre del productor.
      sistema_productivo: fila.sistema_productivo, // Sistema productivo.
      especie: fila.especie, // Especie.
      variedad: fila.variedad, // Variedad.
      calidad: fila.calidad, // Calidad.
    },
    cantidad_cajas: textoCajas(fila.cantidad_cajas), // Cajas actuales.
    kilos_procesados: textoKilos(fila.kilos_procesados), // Solo se usa a granel.
    tarja_terminada: fila.tarja_terminada, // Marca actual.
    kilos_originales: fila.kilos_procesados, // Para saber cuánto vuelve a la recepción.
    marca_original: fila.tarja_terminada, // Para no pedir confirmar una marca que ya estaba.
  }));
}
