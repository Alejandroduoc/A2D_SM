// Usa el ejecutor de pruebas de Node sin agregar dependencias al proyecto.
import test from "node:test";
// Compara resultados y tipos con las aserciones estrictas de Node.
import assert from "node:assert/strict";
// Comprueba las funciones de presentación, normalización y validación del RUT.
import { formatearRut, normalizarRut, validarRut } from "../src/utils/rut.js";

// Distintas entradas del mismo RUT deben compartir valor canónico y presentación.
test("acepta las presentaciones equivalentes y genera puntos y guion", () => {
  for (const valor of ["123456785", "12345678-5", "12.345.678-5", " 00012345678-5 "]) {
    assert.equal(validarRut(valor), true);
    assert.equal(normalizarRut(valor), "12345678-5");
    assert.equal(formatearRut(valor), "12.345.678-5");
  }
});

// Cubre K minúscula, dígito cero y cuerpos cortos admitidos por el backend.
test("valida dígitos K y cero, incluidos cuerpos de distinto largo", () => {
  for (const [entrada, presentacion] of [["1000005k", "1.000.005-K"], ["140", "14-0"], ["6k", "6-K"]]) {
    assert.equal(validarRut(entrada), true, entrada);
    assert.equal(formatearRut(entrada), presentacion);
  }
});

// Las entradas inválidas se rechazan sin borrar caracteres para fabricar otro RUT.
test("rechaza entradas vacías, incompletas, símbolos, letras y dígitos incorrectos", () => {
  for (const valor of ["", " ", "1", "12345678-", "12.345.678-4", "12A345678-5", "12345678-X", "12345678-5!", "K", null, 123456785]) {
    assert.equal(validarRut(valor), false, String(valor));
  }
  assert.equal(formatearRut("12A345678-5"), "12A345678-5");
});

// El límite se aplica al valor normalizado, no al texto con ceros iniciales.
test("aplica el largo canónico del backend después de quitar ceros iniciales", () => {
  assert.equal(validarRut("0".repeat(30) + "12345678-5"), true);
  assert.equal(normalizarRut("12345678901-5"), null);
});
