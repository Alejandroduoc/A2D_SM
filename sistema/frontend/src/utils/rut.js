// Comparte la representación canónica del backend sin convertir el cuerpo a Number.
export function normalizarRut(valor) {
  if (typeof valor !== "string") return null;
  const limpio = valor.replace(/[.\-\s]/g, "").toUpperCase();
  // No elimina letras o símbolos inválidos para convertirlos en otro RUT.
  if (!/^\d+[0-9K]$/.test(limpio)) return null;
  const cuerpo = limpio.slice(0, -1).replace(/^0+(?=\d)/, "");
  const canonico = `${cuerpo}-${limpio.slice(-1)}`;
  // El contrato mide el largo después de quitar puntos y ceros iniciales.
  return canonico.length <= 12 ? canonico : null;
}

// Comprueba Módulo 11 para avisar localmente; la API conserva su validación.
export function validarRut(valor) {
  const canonico = normalizarRut(valor);
  if (!canonico) return false;
  const [cuerpo, ingresado] = canonico.split("-");
  let suma = 0;
  let factor = 2;
  for (let i = cuerpo.length - 1; i >= 0; i -= 1) {
    suma += Number(cuerpo[i]) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resto = 11 - (suma % 11);
  const esperado = resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  return ingresado === esperado;
}

// Presenta puntos y guion sin alterar una entrada con caracteres incorrectos.
export function formatearRut(valor) {
  const canonico = normalizarRut(valor);
  if (!canonico) return valor;
  const [cuerpo, dv] = canonico.split("-");
  return `${cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}-${dv}`;
}
