/**
 * La bandeja de Meta (WhatsApp Cloud, Messenger, Instagram). El webhook guarda el mensaje crudo en el Durable Object ANTES de
 * contestarle 200 a Meta (`guardarRecibido`) y lo atiende después. Si el Worker no alcanza (se reinicia, se le acaba el tiempo,
 * falla el Durable Object a mitad), la alarma lo atiende desde la bandeja: nada se pierde y nada se contesta dos veces.
 */
import { describe, expect, it } from "vitest";
import type { Entrante } from "../../src/canales/tipos";
import { crearMundo } from "../helpers/mundo";

const MINUTO = 60_000;
const RESCATE = 2 * MINUTO;
const ENCENDIDO = { canales_activos: { whatsapp_cloud: true } };

function nube(op: Parameters<typeof crearMundo>[0] = {}) {
  const m = crearMundo({ canal: "whatsapp_cloud", config: ENCENDIDO, ...op });
  m.guion([{ texto: "Claro, ¿qué medida de cama buscas?" }]);
  return m;
}

describe("guardar antes del 200", () => {
  it("guarda el mensaje crudo sin bajar nada ni llamar a Odoo, y arma la alarma de rescate", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    expect(await m.motor.guardarRecibido(e)).toEqual({ nuevo: true });
    expect(m.motor.resumen().bandeja).toBe(1);
    expect(m.alarmaProgramada()).toBe(m.ahora() + RESCATE);
    expect(m.odoo.mensajes).toEqual([]);
    expect(m.odoo.pedidosDeConfig).toBe(0);
  });

  it("el mismo id (Meta reintenta) no es nuevo: ni mientras espera en la bandeja ni después de atenderlo", async () => {
    const m = nube();
    const e = m.entrante("Hola");
    expect((await m.motor.guardarRecibido(e)).nuevo).toBe(true);
    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
    await m.motor.ingest(e); // lo que hace el Worker justo después del 200
    expect(m.motor.resumen().bandeja).toBe(0);
    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
  });

  it("un mensaje sin id_mensaje no se guarda (no se podría reconocer su reintento): el webhook contesta 500", async () => {
    const m = nube();
    await expect(m.motor.guardarRecibido(m.entrante("hola", { id_mensaje: "" }))).rejects.toThrow(/id_mensaje/);
  });

  it("lo normal: el Worker lo atiende enseguida, se borra de la bandeja y se contesta UNA vez", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    await m.motor.guardarRecibido(e);
    await m.motor.ingest(e);
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => x.id_mensaje)).toEqual([e.id_mensaje]);
  });
});

describe("el rescate (el Worker no alcanzó a atenderlo)", () => {
  it("pasados 2 minutos la alarma lo atiende: se registra en Odoo y se contesta una vez; un reintento de Meta no lo repite", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    await m.motor.guardarRecibido(e);
    await m.pasar(RESCATE - 1000);
    expect(m.odoo.mensajes).toEqual([]); // todavía le toca al Worker
    await m.pasar(1000 + 20_000); // rescate + ráfaga de 15 s
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => [x.id_mensaje, x.texto])).toEqual([[e.id_mensaje, "Hola, ¿tienen camas?"]]);
    expect(m.canal.salidas).toHaveLength(1);
    expect(m.registros.some((r) => /no alcanzó a atender/.test(r.mensaje))).toBe(true);

    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
    await m.motor.ingest({ ...e }); // y si el Worker llega tarde, es un repetido
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("con la configuración de Odoo desconocida no decide (el canal parecería apagado): espera y lo atiende cuando Odoo vuelve", async () => {
    const m = nube();
    m.odoo.caido = true; // Odoo dormido y ninguna copia de la configuración
    const e = m.entrante("Hola");
    await m.motor.guardarRecibido(e);
    await m.pasar(RESCATE + 1000);
    expect(m.motor.resumen().bandeja).toBe(1);
    expect(m.motor.bandeja.vencidas(m.ahora() + 24 * 3600_000)[0].intentos).toBe(1);
    expect(m.canal.salidas).toEqual([]);
    expect(m.registros.some((r) => r.nivel === "warn" && /mensaje guardado de Meta/.test(r.mensaje))).toBe(true);

    m.odoo.caido = false;
    await m.pasar(10 * MINUTO);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(1);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("si atenderlo falla, se reintenta con esperas cada vez más largas (no se descarta)", async () => {
    const m = nube();
    const e = m.entrante("Hola");
    await m.motor.guardarRecibido(e);
    const original = m.motor.ingest.bind(m.motor);
    let fallas = 2;
    m.motor.ingest = async (x: Entrante) => {
      if (fallas-- > 0) throw new Error("el motor falló");
      return original(x);
    };
    await m.pasar(RESCATE);
    const [f1] = m.motor.bandeja.vencidas(m.ahora() + 24 * 3600_000);
    expect([f1.intentos, f1.proximo - m.ahora()]).toEqual([1, RESCATE]);
    await m.pasar(RESCATE);
    const [f2] = m.motor.bandeja.vencidas(m.ahora() + 24 * 3600_000);
    expect([f2.intentos, f2.proximo - m.ahora()]).toEqual([2, 2 * RESCATE]);
    await m.pasar(2 * RESCATE + 20_000);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("canal APAGADO en Odoo: se suelta sin registrar ni contestar (como el webhook)", async () => {
    const m = nube({ config: { canales_activos: { whatsapp_cloud: false } } });
    await m.motor.guardarRecibido(m.entrante("Hola"));
    await m.pasar(RESCATE + 20_000);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes).toEqual([]);
    expect(m.motor.mensajes.ultimos(10)).toEqual([]);
    expect(m.canal.salidas).toEqual([]);
  });

  it("el archivo se vuelve a pedir al canal por su `ref` (el media_id) y queda para Odoo", async () => {
    const m = nube({ urlPublica: "https://juan.example" });
    const pedidos: string[] = [];
    Object.assign(m.canal, {
      descargar: async (ref: string) => {
        pedidos.push(ref);
        return { bytes: new Uint8Array([1, 2, 3]), mime: "image/jpeg" };
      },
    });
    await m.motor.guardarRecibido(m.entrante("así la quiero", { adjuntos: [{ tipo: "imagen", mime: "image/jpeg", ref: "MEDIA9" }] }));
    await m.pasar(RESCATE + 1000);
    expect(pedidos).toEqual(["MEDIA9"]);
    const [cliente] = m.odoo.mensajes.filter((x) => x.autor === "cliente");
    expect(cliente.adjuntos?.[0]).toMatchObject({ tipo: "imagen", mime: "image/jpeg" });
    expect(cliente.adjuntos?.[0].url).toMatch(/^https:\/\/juan\.example\/media\//);
  });

  it("no toca un mensaje que se está atendiendo en ese momento (una nota de voz lenta): no se procesa dos veces", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    let transcripciones = 0;
    const m = nube({
      transcribir: async () => {
        transcripciones++;
        await puerta;
        return "busco una cama queen";
      },
    });
    const e = m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", bytes: new Uint8Array([5, 5, 5]) }] });
    await m.motor.guardarRecibido(e);
    const atendiendo = m.motor.ingest(e); // el Worker, todavía transcribiendo
    await m.pasar(RESCATE + 1000); // vence el rescate mientras tanto
    expect(m.motor.resumen().bandeja).toBe(1);
    abrir();
    await atendiendo;
    await m.pasar(RESCATE + 20_000);
    expect(transcripciones).toBe(1);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(1);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("«Borrar mis datos» también vacía la bandeja", async () => {
    const m = nube();
    await m.motor.guardarRecibido(m.entrante("Hola"));
    await m.motor.olvidar();
    expect(m.motor.resumen().bandeja).toBe(0);
  });
});
