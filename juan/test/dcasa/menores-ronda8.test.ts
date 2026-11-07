/**
 * Issue #24 · Menores:
 *   · `alFallarLaIA` registraba `e.message` tal cual: algunos proveedores repiten la clave mal escrita en el error (`limpiarError`).
 *     Lo mismo el envío fallido por el canal (Telegram lleva el token del bot en la dirección): `motivoDeEnvio`.
 *   · `.replace("{{LECCIONES}}", …)` interpreta `$&`, `$'` y `` $` `` dentro de una lección: se usa una función de reemplazo.
 */
import { describe, expect, it } from "vitest";
import { normalizarConfig } from "../../src/config";
import { promptEstable } from "../../src/dcasa/prompt";
import { crearMundo, type Mundo } from "../helpers/mundo";

const CLAVE = "sk-ant-api03-SECRETOabcdef1234567890";
const TOKEN_BOT = "123456789:AAFakeTokenDePruebaNoReal_abcdefghijk";

function conRegistroCompleto(m: Mundo) {
  const todo: string[] = [];
  m.deps.log = (nivel, mensaje, extra) => {
    todo.push(`${nivel} ${mensaje} ${typeof extra === "string" ? extra : JSON.stringify(extra ?? "")}`);
  };
  return todo;
}

describe("los registros no repiten claves ni tokens (issue #24)", () => {
  it("cuando la IA falla, el registro no trae la clave que el proveedor repitió en su error", async () => {
    const m = crearMundo();
    const todo = conRegistroCompleto(m);
    m.guion([{ error: new Error(`401 invalid x-api-key: ${CLAVE}`) }]);
    await m.conversar("hola");
    expect(todo.some((l) => l.includes("la IA falló"))).toBe(true);
    expect(todo.join("\n")).not.toContain("SECRETOabcdef1234567890");
  });

  it("cuando el canal no deja enviar, el registro no trae el token del bot ni la dirección", async () => {
    const m = crearMundo({ canal: "telegram", idExterno: "321", config: { canales_activos: { telegram: true } } });
    const todo = conRegistroCompleto(m);
    m.canal.fallar = 10;
    m.canal.motivoDeFallo = `fetch failed: https://api.telegram.org/bot${TOKEN_BOT}/sendMessage`;
    m.guion([{ texto: "Hola, ¿qué buscas?" }]);
    await m.conversar("hola");
    expect(todo.some((l) => l.includes("no salió por el canal") || l.includes("no se pudo enviar"))).toBe(true);
    expect(todo.join("\n")).not.toContain("AAFakeTokenDePruebaNoReal");
  });
});

describe("las lecciones van al prompt tal cual las escribió Gerencia (issue #24)", () => {
  it("«$&», «$'» y «$`» en una lección no repiten pedazos del prompt", () => {
    const leccion = "Si preguntan por el precio de lista, di $& y $' y $` tal cual";
    const p = promptEstable(normalizarConfig({ lecciones: leccion }));
    expect(p).toContain(`- ${leccion}`);
    expect(p).not.toContain("{{LECCIONES}}");
    // Sin la función de reemplazo, «$'» metía TODO el resto del prompt dentro de la lección.
    expect(p.split("<ultimo_recordatorio>").length).toBe(2);
  });
});
