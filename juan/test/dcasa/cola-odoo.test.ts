/**
 * Ola 1 · «que no falle». Lo que Odoo no pudo recibir (está dormido, se reinició, se despliega) espera en la cola del Worker.
 * Antes se descartaba tras ~1,75 h de intentos; ahora NUNCA: pasa a un reintento lento y se avisa en /salud.
 */
import { describe, expect, it } from "vitest";
import { OdooError, type CuerpoMensaje } from "../../src/odoo/cliente";
import { crearMundo } from "../helpers/mundo";

const HORA = 3600_000;

function mensajeDeCliente(texto: string): CuerpoMensaje {
  return { canal: "whatsapp_qr", id_externo: "50760261919", id_mensaje: `w-${texto}`, direccion: "entrante", autor: "cliente", texto, ts: new Date(Date.UTC(2026, 9, 9, 15)).toISOString() };
}

function conMensajeEnCola() {
  const m = crearMundo();
  m.odoo.caido = true;
  m.motor.cola.agregar("mensaje", mensajeDeCliente("Hola, busco una cama"), m.ahora());
  return m;
}

describe("Odoo no contesta durante mucho tiempo", () => {
  it("el mensaje NO se descarta tras los intentos rápidos: pasa a un reintento cada 6 horas", async () => {
    const m = conMensajeEnCola();
    await m.motor.programar();
    await m.pasar(10 * HORA); // de sobra para gastar los 12 intentos rápidos
    expect(m.motor.cola.vencidas(m.ahora() + 100 * HORA)).toHaveLength(1);
    const fila = m.motor.cola.vencidas(m.ahora() + 100 * HORA)[0];
    expect(fila.intentos).toBeGreaterThanOrEqual(12);
    expect(fila.proximo - m.ahora()).toBeGreaterThan(HORA); // ya no insiste cada pocos minutos
    expect(m.registros.some((r) => r.nivel === "error" && /cada 6 horas/.test(r.mensaje))).toBe(true);
  });

  it("al volver Odoo, lo guardado se entrega completo y el aviso de /salud se retira", async () => {
    const m = conMensajeEnCola();
    await m.motor.programar();
    await m.pasar(10 * HORA);
    expect(m.motor.kv.bandera("cola_estancada")).toBe(true);
    expect(m.gastoGlobal.leerSalud<{ tipo: string }>("cola_estancada")?.valor.tipo).toBe("mensaje");

    m.odoo.caido = false;
    await m.pasar(7 * HORA); // el siguiente reintento lento
    expect(m.odoo.mensajes.map((x) => x.texto)).toEqual(["Hola, busco una cama"]);
    expect(m.motor.resumen().cola).toBe(0);
    expect(m.motor.kv.bandera("cola_estancada")).toBe(false);
    expect(m.gastoGlobal.leerSalud<{ resuelto?: boolean }>("cola_estancada")?.valor.resuelto).toBe(true);
  });

  it("un mensaje al que Odoo contesta con un 4xx tampoco se descarta (es historial: se avisa y se reintenta)", async () => {
    const m = crearMundo();
    m.odoo.falloDeMensaje = new OdooError("Odoo respondió 400", 400, false);
    m.motor.cola.agregar("mensaje", mensajeDeCliente("importante"), m.ahora());
    await m.motor.programar();
    await m.pasar(10 * HORA);
    expect(m.motor.resumen().cola).toBe(1);
    m.odoo.falloDeMensaje = null; // Odoo se corrigió con un despliegue
    await m.pasar(7 * HORA);
    expect(m.odoo.mensajes.map((x) => x.texto)).toEqual(["importante"]);
  });

  it("una etiqueta que Odoo rechaza (no es un fallo de red) se deja tras unos intentos, sin molestar a /salud", async () => {
    const m = crearMundo();
    m.motor.kv.poner("conversacion_id", 12);
    m.motor.cola.agregar("herramienta", { nombre: "herramienta_que_no_existe", argumentos: {} }, m.ahora());
    await m.motor.programar();
    await m.pasar(HORA);
    expect(m.motor.resumen().cola).toBe(0);
    expect(m.motor.kv.bandera("cola_estancada")).toBe(false);
  });

  it("pasar_a_vendedora que no pudo llegar porque Odoo estaba caído SÍ espera (si no, nadie se entera de que el cliente quiere a una persona)", async () => {
    const m = crearMundo();
    m.motor.kv.poner("conversacion_id", 12);
    m.odoo.caido = true;
    m.motor.cola.agregar("herramienta", { nombre: "pasar_a_vendedora", argumentos: { motivo: "pidió una persona" } }, m.ahora());
    await m.motor.programar();
    await m.pasar(2 * HORA);
    expect(m.motor.resumen().cola).toBe(1);
    m.odoo.caido = false;
    await m.pasar(7 * HORA);
    expect(m.odoo.llamadas.map((x) => x.nombre)).toEqual(["pasar_a_vendedora"]);
    expect(m.motor.resumen().cola).toBe(0);
  });

  it("los mensajes se conservan 30 días; las escrituras sueltas, 3", async () => {
    const m = crearMundo();
    m.odoo.caido = true;
    m.motor.kv.poner("conversacion_id", 12);
    m.motor.cola.agregar("mensaje", mensajeDeCliente("viejo"), m.ahora());
    m.motor.cola.agregar("herramienta", { nombre: "anotar_conversacion", argumentos: { nota: "x" } }, m.ahora());
    await m.motor.programar();
    for (let i = 0; i < 5; i++) await m.pasar(24 * HORA); // `pasar` atiende a lo más 100 alarmas por llamada
    const quedan = m.motor.cola.vencidas(m.ahora() + 1000 * HORA).map((f) => f.tipo);
    expect(quedan).toEqual(["mensaje"]);
    for (let i = 0; i < 30; i++) await m.pasar(24 * HORA);
    expect(m.motor.cola.vencidas(m.ahora() + 1000 * HORA)).toEqual([]);
  });
});
