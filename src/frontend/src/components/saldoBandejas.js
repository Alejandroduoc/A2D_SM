// Situación del saldo de bandejas, compartida por Recepción y por la consulta de bandejas (HU15).
// Mismos textos y colores que el semáforo del legado (Form4.vb): verde, rojo y naranjo.
export function situacionBandejas(saldo) {
  // Base común de la etiqueta.
  const base = "rounded-full border px-2 py-0.5 text-xs";
  // Negativo: el productor se llevó más bandejas de las que trajo.
  if (saldo < 0) return { texto: "Productor debe bandejas", clase: `${base} border-red-200 bg-red-50 text-red-700` };
  // Positivo: la empresa tiene bandejas del productor.
  if (saldo > 0) return { texto: "Socradex debe bandejas", clase: `${base} border-amber-200 bg-amber-50 text-amber-700` };
  // Cero: no se deben bandejas.
  return { texto: "Bandejas al día", clase: `${base} border-emerald-200 bg-emerald-50 text-emerald-700` };
}
