/**
 * WhatsApp Cloud: «otra app controla este chat» (131070, 2026-11-09/10). Quién contesta cada chat lo decide el «Enrutamiento de
 * conversaciones» de Meta; si Juan no es la app principal, Meta rechaza el envío con 131070. Juan pide el control del chat
 * (thread_control «take») una sola vez y, si Meta se lo da, manda otra vez lo que se rechazó. Pedido de la dueña: «¿no podemos
 * enviar llamados … para que la aplicación de Juan tome el control?».
 * Números y nombres de mentira; la forma de los avisos es la de la documentación de Meta (standby, messaging_handovers).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "../../src/env";
import {
  crearWhatsappCloud,
  ESPERA_CONTROL_POR_CLIENTE_MS,
  ESPERA_CONTROL_TRAS_RECHAZO_MS,
  resumenDeMeta,
  resumenDeTraspaso,
  URL_CONTROL_DEL_CHAT,
} from "../../src/canales/whatsappCloud";
import { hmacHex } from "../../src/seguridad";

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const TOKEN = "token-cloud-0123456789";
const NUMERO = "109876543210";
const CLIENTE = "50760001111";
const OTRO = "50760002222";
const TIENDA = "50760261919";
const env = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: "verificacion-0123456789", WHATSAPP_CLOUD_TOKEN: TOKEN, WHATSAPP_PHONE_NUMBER_ID: NUMERO } as unknown as Env;

interface Llamada {
  url: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

const RECHAZO_131070 = () =>
  Response.json(
    { error: { message: "(#131070) Another app is controlling this thread now", type: "OAuthException", code: 131070, fbtrace_id: "TRAZA1" } },
    { status: 400 },
  );
const OK = (n: number) => Response.json({ messages: [{ id: `wamid.OUT${n}` }] });
const esControl = (c: Llamada) => c.url.startsWith(URL_CONTROL_DEL_CHAT);

function nubeFalsa(responder: (c: Llamada, n: number) => Response | Promise<Response>) {
  const llamadas: Llamada[] = [];
  let reloj = 1_790_000_000_000;
  const f: typeof fetch = async (recurso, init) => {
    const c = {
      url: String(recurso),
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body ? JSON.parse(String(init.body)) : null,
    };
    llamadas.push(c);
    return responder(c, llamadas.length - 1);
  };
  return {
    llamadas,
    adelantar: (ms: number) => (reloj += ms),
    adaptador: crearWhatsappCloud({ fetch: f, dormir: async () => {}, ahora: () => reloj }),
  };
}

const texto = (para: string, cuerpo = "Hola") => ({ para, burbujas: [cuerpo], medios: [] }) as never;

function registro() {
  const avisos: string[] = [];
  vi.spyOn(console, "warn").mockImplementation((...a: unknown[]) => void avisos.push(a.map(String).join(" ")));
  return avisos;
}

afterEach(() => vi.restoreAllMocks());

describe("131070: Juan pide el control del chat y, si Meta se lo da, manda otra vez", () => {
  it("Meta lo da: un solo pedido de control (take, al endpoint de Thread Control) y el mensaje sale", async () => {
    const avisos = registro();
    let rechazado = false;
    const { llamadas, adaptador } = nubeFalsa((c, n) => {
      if (esControl(c)) return Response.json({ messaging_product: "whatsapp", request_id: "REQ-1" });
      if (!rechazado) {
        rechazado = true;
        return RECHAZO_131070();
      }
      return OK(n);
    });
    const r = await adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env);
    expect(r.ids).toEqual(["wamid.OUT2"]);
    expect(llamadas).toHaveLength(3);
    const [primero, control, segundo] = llamadas;
    expect(primero.url).toBe(`https://graph.facebook.com/v26.0/${NUMERO}/messages`);
    expect(control.url).toBe(`https://api.facebook.com/business/whatsapp/phone_numbers/${NUMERO}/thread_control`);
    expect(control.cabeceras).toMatchObject({ authorization: `Bearer ${TOKEN}`, "x-api-version": "1.0.0", "content-type": "application/json" });
    expect(control.cuerpo).toMatchObject({ messaging_product: "whatsapp", action: "take", to: CLIENTE });
    expect(control.cuerpo.recipient).toBeUndefined(); // Meta rechaza `to` y `recipient` juntos
    expect(segundo.cuerpo).toEqual(primero.cuerpo); // lo mismo, una sola vez más
    // Queda en el registro (para saber que funcionó), sin el número del cliente.
    expect(avisos.some((a) => a.includes("Meta se lo dio") && a.includes("REQ-1"))).toBe(true);
    expect(avisos.join("\n")).not.toContain(CLIENTE);
  });

  it("Meta dice que no (no es el socio de escalamiento): el error de siempre, con su 131070, y el «no» de Meta queda en el registro", async () => {
    const avisos = registro();
    const { llamadas, adaptador } = nubeFalsa((c) =>
      esControl(c)
        ? Response.json({ error: { message: `Not the escalation partner for ${CLIENTE}`, code: 2494191, fbtrace_id: "TRAZA2" } }, { status: 400 })
        : RECHAZO_131070(),
    );
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/código 131070/);
    expect(llamadas.filter(esControl)).toHaveLength(1);
    expect(llamadas.filter((c) => !esControl(c))).toHaveLength(1); // no se reintenta el envío
    const no = avisos.find((a) => a.includes("Meta dijo que no"));
    expect(no).toContain("código 2494191");
    expect(no).toContain("fbtrace_id TRAZA2");
    expect(avisos.join("\n")).not.toContain(CLIENTE); // ni aunque Meta lo ponga en su texto
  });

  it("tras un «no», nadie lo vuelve a pedir en 10 minutos; luego sí (otro cliente)", async () => {
    registro();
    const { llamadas, adaptador, adelantar } = nubeFalsa((c) => (esControl(c) ? Response.json({ error: { code: 2494191 } }, { status: 400 }) : RECHAZO_131070()));
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    await expect(adaptador.enviar("whatsapp_cloud", texto(OTRO), env)).rejects.toThrow(/131070/);
    adelantar(ESPERA_CONTROL_TRAS_RECHAZO_MS - 1);
    await expect(adaptador.enviar("whatsapp_cloud", texto(OTRO), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter(esControl)).toHaveLength(1);
    adelantar(1);
    await expect(adaptador.enviar("whatsapp_cloud", texto(OTRO), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter(esControl).map((c) => c.cuerpo.to)).toEqual([CLIENTE, OTRO]);
  });

  it("un mismo cliente: a lo más un pedido cada media hora (Odoo reintenta lo «por enviar» cada 5 min)", async () => {
    registro();
    // Meta da el control, pero el chat vuelve a rechazar (otra app lo recuperó): no se entra en un bucle de pedidos.
    const { llamadas, adaptador, adelantar } = nubeFalsa((c) => (esControl(c) ? Response.json({ messaging_product: "whatsapp" }) : RECHAZO_131070()));
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter((c) => !esControl(c))).toHaveLength(2); // el envío y UN reintento
    adelantar(5 * 60_000);
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter(esControl)).toHaveLength(1);
    adelantar(ESPERA_CONTROL_POR_CLIENTE_MS);
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter(esControl)).toHaveLength(2);
  });

  it("si el pedido de control se cae (red), se sigue con el error de siempre y se pausa", async () => {
    const avisos = registro();
    const { llamadas, adaptador } = nubeFalsa((c) => {
      if (esControl(c)) throw new TypeError("network error");
      return RECHAZO_131070();
    });
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    await expect(adaptador.enviar("whatsapp_cloud", texto(OTRO), env)).rejects.toThrow(/131070/);
    expect(llamadas.filter(esControl)).toHaveLength(1);
    expect(avisos.some((a) => a.includes("no se pudo pedir el control"))).toBe(true);
  });

  it("todo envío rechazado deja en el registro su código y su fbtrace_id (para soporte de Meta), sin el número del cliente", async () => {
    const avisos = registro();
    const { adaptador } = nubeFalsa(() => RECHAZO_131070());
    await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(/131070/);
    expect(avisos.some((a) => a.includes("Meta rechazó un envío") && a.includes("código 131070") && a.includes("fbtrace_id TRAZA1"))).toBe(true);
    expect(avisos.join("\n")).not.toContain(CLIENTE);
  });

  it("otros rechazos (24 h, pago, otro 400) no piden el control", async () => {
    registro();
    for (const code of [131047, 131042, 100]) {
      const { llamadas, adaptador } = nubeFalsa(() => Response.json({ error: { message: "no", code } }, { status: 400 }));
      await expect(adaptador.enviar("whatsapp_cloud", texto(CLIENTE), env)).rejects.toThrow(new RegExp(`código ${code}`));
      expect(llamadas.filter(esControl)).toHaveLength(0);
    }
  });

  it("varias burbujas: si la primera da 131070 y Meta da el control, salen todas y en orden", async () => {
    registro();
    let rechazos = 0;
    const { llamadas, adaptador } = nubeFalsa((c, n) => {
      if (esControl(c)) return Response.json({ messaging_product: "whatsapp" });
      if (rechazos === 0) {
        rechazos++;
        return RECHAZO_131070();
      }
      return OK(n);
    });
    const r = await adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["Uno", "Dos"], medios: [] } as never, env);
    expect(r.ids).toHaveLength(2);
    expect(llamadas.filter((c) => !esControl(c)).map((c) => c.cuerpo.text.body)).toEqual(["Uno", "Uno", "Dos"]);
  });
});

async function firmado(cuerpo: object) {
  const crudo = JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/whatsapp-cloud", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO, crudo)}` }, body: crudo });
}

const metadatos = { display_phone_number: TIENDA, phone_number_id: NUMERO };

describe("avisos del reparto de chats: solo al registro, nunca se contesta", () => {
  it("standby (otra app lleva el chat): ningún mensaje para Juan; el registro dice cuántos, sin datos de nadie", async () => {
    const avisos = registro();
    const { adaptador } = nubeFalsa(() => OK(0));
    const r = await adaptador.recibir(
      await firmado({
        object: "whatsapp_business_account",
        entry: [
          {
            id: "WABA",
            changes: [
              {
                field: "standby",
                value: {
                  messaging_product: "whatsapp",
                  metadata: metadatos,
                  standby: {
                    contacts: [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE, user_id: "PA.123" }],
                    messages: [{ from: CLIENTE, from_user_id: "PA.123", id: "wamid.SB1", timestamp: "1790000000", type: "text", text: { body: "Hola, ¿tienen camas?" } }],
                  },
                },
              },
            ],
          },
        ],
      }),
      env,
    );
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([]);
    expect(r.eventos).toBeUndefined();
    const sb = avisos.find((a) => a.includes("standby"));
    expect(sb).toContain("1 mensaje(s) del cliente");
    expect(avisos.join("\n")).not.toContain(CLIENTE);
    expect(avisos.join("\n")).not.toContain("camas");
  });

  it("messaging_handovers: solo el tipo y los ids de las apps; nada del cliente", async () => {
    const avisos = registro();
    const { adaptador } = nubeFalsa(() => OK(0));
    const r = await adaptador.recibir(
      await firmado({
        object: "whatsapp_business_account",
        entry: [
          {
            id: "WABA",
            changes: [
              {
                field: "messaging_handovers",
                value: {
                  messaging_product: "whatsapp",
                  metadata: metadatos,
                  messaging_handovers: [
                    { to: CLIENTE, type: "control_taken", control_taken: { previous_owner_app_id: "111", new_owner_app_id: "222", new_owner_business_id: "333", metadata: `cliente ${CLIENTE}` } },
                  ],
                },
              },
            ],
          },
        ],
      }),
      env,
    );
    expect(r.entrantes).toEqual([]);
    const h = avisos.find((a) => a.includes("cambió quién controla"));
    expect(h).toContain("type=control_taken");
    expect(h).toContain("previous_owner_app_id=111");
    expect(h).toContain("new_owner_app_id=222");
    expect(avisos.join("\n")).not.toContain(CLIENTE);
  });

  it("un aviso «messages» de siempre sigue entrando igual", async () => {
    registro();
    const { adaptador } = nubeFalsa(() => OK(0));
    const r = await adaptador.recibir(
      await firmado({
        object: "whatsapp_business_account",
        entry: [
          {
            id: "WABA",
            changes: [
              {
                field: "messages",
                value: {
                  messaging_product: "whatsapp",
                  metadata: metadatos,
                  contacts: [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE }],
                  messages: [{ from: CLIENTE, id: "wamid.M1", timestamp: "1790000000", type: "text", text: { body: "Hola" } }],
                },
              },
            ],
          },
        ],
      }),
      env,
    );
    expect(r.entrantes).toHaveLength(1);
    expect(r.entrantes[0]).toMatchObject({ id_externo: CLIENTE, texto: "Hola" });
  });
});

describe("resúmenes para el registro", () => {
  it("resumenDeMeta: forma de la Graph API y forma StandardError; tapa números largos", () => {
    expect(resumenDeMeta(400, { error: { message: "No para 50760001111", code: 2494191, error_subcode: 7, fbtrace_id: "T" } })).toBe(
      "HTTP 400 · código 2494191 · subcódigo 7 · No para … · fbtrace_id T",
    );
    expect(resumenDeMeta(401, { type: "about:blank", title: "Unauthorized", detail: "Token sin permiso", status: 401 })).toBe("HTTP 401 · Token sin permiso");
    expect(resumenDeMeta(200, { messaging_product: "whatsapp", request_id: "R" })).toBe("HTTP 200 · request_id R");
    expect(resumenDeMeta(502, "no es json")).toBe("HTTP 502");
  });

  it("resumenDeTraspaso: sin nada conocido dice «sin detalle»", () => {
    expect(resumenDeTraspaso(undefined)).toBe("sin detalle");
    expect(resumenDeTraspaso({ a: { b: { type: "control_passed", target_role: "ai_agent" } } })).toBe("type=control_passed · target_role=ai_agent");
  });
});
