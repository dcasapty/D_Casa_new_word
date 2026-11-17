// Revisión adversarial de Andrés vendedor (A2, A4; 2026-11-16): la guardia de «ya lo hice» del carrito y del envío, y lo
// que NO debe borrar (las preguntas en subjuntivo, lo que se dice del ITBMS).
import { describe, expect, it } from "vitest";
import { afirmaCarrito } from "../../src/tienda/bloques";

describe("rv: la guardia de lo que el modelo dice que hizo en el carrito o la cotización", () => {
  it("una afirmación de que ya sumó el envío o cambió el carrito se para (Odoo no lo confirmó)", () => {
    for (const t of [
      "Listo, ya agregué el envío a tu cotización.",
      "Ya incluí el envío en tu cotización.",
      "El envío ya está en tu cotización.",
      "Listo, cambié la cantidad a 1.",
      "Ya retiré la cama del carrito.",
      "Ya lo tienes incluido en tu cotización.",
      "Listo, dejé una sola en tu carrito.",
    ])
      expect(afirmaCarrito(t), t).toBe(true);
  });
  it("una pregunta en subjuntivo no es una afirmación (no se borra)", () => {
    for (const t of ["¿Quieres que te lo quite del carrito?", "¿Quieres que te lo sume a la cotización?", "¿Prefieres que la saque del carrito?"])
      expect(afirmaCarrito(t), t).toBe(false);
  });
  it("lo que no habla de haber hecho algo en el carrito tampoco se borra", () => {
    for (const t of ["El ITBMS ya está incluido en la cotización.", "Si quieres, te lo sumo a la cotización.", "Quieres que te lo quite del carrito?", "Puedo quitarlo del carrito si me dices."])
      expect(afirmaCarrito(t), t).toBe(false);
    // Una confirmación inventada seguida de una pregunta sigue siendo una afirmación.
    expect(afirmaCarrito("Ya te lo puse en el carrito, ¿te ayudo con algo más?")).toBe(true);
  });
  it("escribir sin «¿» no sirve para colar una confirmación (segunda revisión, 2026-11-16)", () => {
    for (const t of [
      "Listo, ya te lo quité del carrito y lo dejé en 2, ok?",
      "Ya agregué el envío a tu cotización, te parece?",
      "Cambié la cantidad a 3, está bien?",
    ])
      expect(afirmaCarrito(t), t).toBe(true);
  });
  it("una pregunta en medio no tapa lo que viene después", () => {
    expect(afirmaCarrito("Perfecto, ¿seguimos? ya te sumé el envío a tu cotización.")).toBe(true);
    expect(afirmaCarrito("¿Te muestro más camas? ya retiré la otra del carrito.")).toBe(true);
  });
  it("ofrecer en presente sigue sin ser una afirmación, con «?» o sin él", () => {
    for (const t of ["Te lo quito del carrito?", "Te lo dejo en 2?", "¿Te lo quito del carrito?"])
      expect(afirmaCarrito(t), t).toBe(false);
  });
});
