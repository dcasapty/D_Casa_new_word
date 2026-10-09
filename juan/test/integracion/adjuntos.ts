// Sección 4: adjuntos en los dos sentidos.
//   · Cliente → Worker → Odoo: el Worker guarda el archivo y expone GET /media/<conv>/<id>?exp&sig (firmado con JUAN_WORKER_TOKEN,
//     2 días); Odoo lo baja y lo guarda como ir.attachment.
//   · Odoo → Worker → puente: la vendedora adjunta desde Odoo; Odoo manda a POST /odoo/enviar una URL firmada de 15 minutos del
//     dominio de D'CASA y el puente (con su validación real) la baja.

import { createHmac } from "node:crypto";
import { beforeAll, describe, expect, it } from "vitest";
import { claveDeConversacion, firmarUrlMedio } from "../../src/motor/mediosUrl";
import { DOMINIOS_DEL_PUENTE, JUAN_PUERTO, OdooRpc, ODOO_URL, TOKEN_WORKER, celularNuevo, fetchReal, PNG_BASE64, sha1 } from "./ayuda";
import type { Escena } from "./escena";

export function seccionAdjuntos(e: Escena) {
  describe("4. Adjuntos en los dos sentidos", () => {
    let admin: OdooRpc;
    let ventas: OdooRpc;
    beforeAll(() => {
      admin = e.admin;
      ventas = e.ventas;
    });

    describe("cliente → Worker → Odoo", () => {
      const celular = celularNuevo();
      const bytes = Buffer.from(PNG_BASE64, "base64");
      let urlDelWorker: string;

      it("una foto del cliente: el Worker la guarda, Odoo la baja con la URL firmada y queda como adjunto; la IA nunca la ve", async () => {
        e.w.ia.guionar([{ texto: "Recibí tu archivo. Una vendedora lo revisa y te confirma." }]);
        const r = await e.w.cliente(celular, "Aquí está mi comprobante", {
          tipo: "imagen",
          medio: { base64: PNG_BASE64, mime: "image/png", nombre: "comprobante.png" },
        });
        expect(r.status).toBe(200);
        await e.w.quieta(celular);

        // Lo que el Worker le mandó a Odoo: una URL propia, firmada, de /media.
        const registro = e.w.enlace.peticiones.find((p) => p.ruta.endsWith("/mensaje") && p.cuerpo?.id_externo === celular && p.cuerpo?.adjuntos?.length);
        expect(registro, "el Worker registró el mensaje con adjunto").toBeTruthy();
        const adjunto = registro!.cuerpo.adjuntos[0];
        expect(adjunto).toMatchObject({ tipo: "imagen", nombre: "comprobante.png", mime: "image/png" });
        urlDelWorker = adjunto.url as string;
        const u = new URL(urlDelWorker);
        expect(u.origin).toBe(`http://127.0.0.1:${JUAN_PUERTO}`);
        expect(u.pathname).toMatch(/^\/media\/[A-Za-z0-9_-]+\/[a-f0-9]{16,64}$/);
        expect(u.searchParams.get("exp")).toMatch(/^\d+$/);
        expect(u.searchParams.get("sig")).toMatch(/^[a-f0-9]{64}$/);
        const vida = Number(u.searchParams.get("exp")) - Date.now();
        expect(vida).toBeGreaterThan(47 * 3600_000);
        expect(vida).toBeLessThanOrEqual(48 * 3600_000 + 5_000); // 2 días

        // Odoo la bajó (200 en /media) y la guardó como ir.attachment del mensaje, con el mismo contenido.
        expect(e.w.entradas.some((x) => x.metodo === "GET" && x.ruta.startsWith("/media/") && x.estado === 200)).toBe(true);
        const mensajes = (await e.mensajesDe(celular)).filter((m) => m.autor === "cliente");
        expect(mensajes).toHaveLength(1);
        expect(mensajes[0].adjuntos_fallidos).toBe(0);
        expect(mensajes[0].adjunto_ids).toHaveLength(1);
        const [archivo] = await admin.leer("ir.attachment", mensajes[0].adjunto_ids, ["name", "mimetype", "checksum", "file_size", "res_model", "public"]);
        expect(archivo).toMatchObject({ name: "comprobante.png", mimetype: "image/png", res_model: "dcasa.mensaje", public: false, file_size: bytes.length });
        expect(archivo.checksum).toBe(sha1(bytes));

        // La IA no recibió el archivo ni su contenido, solo el aviso (regla 5 de docs/JUAN.md).
        const alModelo = JSON.stringify(e.w.ia.peticiones.map((p) => p.cuerpo));
        expect(alModelo).not.toContain(PNG_BASE64.slice(0, 40));
        expect(alModelo).not.toContain("/media/");
        expect(alModelo).toMatch(/NO lo ves/);
        // Y quedó anotado para una vendedora en la ficha del cliente.
        const conv = (await e.conversacionDe(celular))!;
        const notas = await admin.buscar("mail.message", [["model", "=", "res.partner"], ["res_id", "=", conv.partner_id[0]], ["body", "ilike", "comprobante de pago"]], ["body"]);
        expect(notas.length).toBeGreaterThan(0);
      });

      it("la URL del Worker solo sirve con su firma, antes de vencer y para su conversación", async () => {
        const u = new URL(urlDelWorker);
        const bien = await fetchReal(urlDelWorker);
        expect(bien.status).toBe(200);
        expect(bien.headers.get("content-type")).toBe("image/png");
        expect(Buffer.from(await bien.arrayBuffer()).equals(bytes)).toBe(true);

        const malaFirma = new URL(u);
        malaFirma.searchParams.set("sig", "0".repeat(64));
        expect((await fetchReal(malaFirma)).status).toBe(403);
        const sinFirma = new URL(u);
        sinFirma.searchParams.delete("sig");
        expect((await fetchReal(sinFirma)).status).toBe(403);
        const otraFecha = new URL(u);
        otraFecha.searchParams.set("exp", String(Number(u.searchParams.get("exp")) + 1));
        expect((await fetchReal(otraFecha)).status).toBe(403);

        // Firma buena, pero vencida: 410.
        const [, , clave, id] = u.pathname.split("/");
        const vieja = await firmarUrlMedio(`http://127.0.0.1:${JUAN_PUERTO}`, TOKEN_WORKER, clave, id, Date.now() - 3 * 24 * 3600_000);
        expect((await fetchReal(vieja)).status).toBe(410);
        // Firma buena para OTRA conversación: no existe ahí ese archivo (404).
        const otra = await firmarUrlMedio(`http://127.0.0.1:${JUAN_PUERTO}`, TOKEN_WORKER, claveDeConversacion("whatsapp_qr", celularNuevo()), id, Date.now());
        expect((await fetchReal(otra)).status).toBe(404);
      });

      it("un archivo que el Worker no puede entregar (sin su dirección pública) no hace perder el mensaje", async () => {
        const otro = celularNuevo();
        const publica = e.w.cluster.env.URL_PUBLICA;
        // Sin URL_PUBLICA (una variable que pega la dueña) el Worker guarda el archivo pero Odoo recibe url: null.
        delete e.w.cluster.env.URL_PUBLICA;
        try {
          e.w.ia.guionar([{ texto: "Lo recibí; una vendedora lo revisa." }]);
          const r = await e.w.cliente(otro, "Mi cédula", { tipo: "documento", medio: { base64: PNG_BASE64, mime: "application/pdf", nombre: "cedula.pdf" } });
          expect(r.status).toBe(200);
          await e.w.quieta(otro);
        } finally {
          e.w.cluster.env.URL_PUBLICA = publica;
        }
        const registro = e.w.enlace.peticiones.find((p) => p.ruta.endsWith("/mensaje") && p.cuerpo?.id_externo === otro && p.cuerpo?.adjuntos?.length);
        expect(registro!.cuerpo.adjuntos[0].url).toBeFalsy();
        expect(registro!.estado).toBe(200);
        const mensajes = (await e.mensajesDe(otro)).filter((m) => m.autor === "cliente");
        expect(mensajes).toHaveLength(1); // el mensaje se guardó
        expect(mensajes[0]).toMatchObject({ adjuntos_fallidos: 1, adjunto_ids: [] }); // y la burbuja dice que el archivo no se pudo traer
      });
    });

    describe("vendedora → Odoo → Worker → puente", () => {
      const celular = celularNuevo();
      let convId: number;
      const pdf = Buffer.from(`%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n% ${celular}\n`);

      const subir = async (nombre: string, contenido: Buffer, mimetype: string): Promise<number> => {
        const id = await ventas.llamar<number | number[]>("ir.attachment", "create", [{ name: nombre, datas: contenido.toString("base64"), mimetype }]);
        return Array.isArray(id) ? id[0] : id;
      };

      it("una cotización en PDF: Odoo manda una URL firmada de 15 min de dcasapty.com; el puente (validación real) la baja", async () => {
        e.w.ia.guionar([{ texto: "Claro, ya te escribe una vendedora." }]);
        await e.w.cliente(celular, "Hola, quiero una cotización", { nombre: "Marisol" });
        await e.w.quieta(celular);
        convId = (await e.conversacionDe(celular))!.id;

        const adjuntoId = await subir("cotizacion.pdf", pdf, "application/pdf");
        const antes = e.w.puente.envios.length;
        const r = await ventas.llamar("dcasa.conversacion", "enviar_respuesta", [convId, "Te mando la cotización.", [adjuntoId]]);
        expect(e.w.puente.rechazos).toEqual([]);
        expect(r.enviado).toBe(true);
        expect(e.w.puente.envios.length).toBe(antes + 1);
        const envio = e.w.puente.envios.at(-1)!;
        expect(envio.para).toBe(celular);
        expect(envio.chunks).toEqual(["Te mando la cotización."]);
        expect(envio.medios).toHaveLength(1);
        expect(envio.medios[0]).toMatchObject({ tipo: "documento", nombre: "cotizacion.pdf" });

        // La URL: https, del dominio permitido del puente, con la ruta firmada de Odoo y vida de 15 minutos.
        const url = new URL(envio.medios[0].url);
        expect(url.protocol).toBe("https:");
        expect(DOMINIOS_DEL_PUENTE.split(",")).toContain(url.hostname);
        const m = /^\/dcasa\/adjunto\/(\d+)\/(\d+)\/([0-9a-f]{64})\/cotizacion\.pdf$/.exec(url.pathname);
        expect(m, url.pathname).toBeTruthy();
        expect(Number(m![1])).toBe(adjuntoId);
        const vida = Number(m![2]) * 1000 - Date.now();
        expect(vida).toBeGreaterThan(14 * 60_000);
        expect(vida).toBeLessThanOrEqual(15 * 60_000 + 2_000);

        // El puente bajó el archivo tal cual.
        expect(envio.descargas).toHaveLength(1);
        expect(envio.descargas[0].estado).toBe(200);
        expect(envio.descargas[0].mime).toBe("application/pdf");
        expect(Buffer.from(envio.descargas[0].bytes).equals(pdf)).toBe(true);

        // En Odoo: enviado, con el adjunto, y la conversación quedó en manos de la vendedora.
        const delOdoo = (await e.mensajesDe(celular)).filter((x) => x.autor === "vendedora" && x.tipo === "mensaje");
        expect(delOdoo).toHaveLength(1);
        expect(delOdoo[0]).toMatchObject({ estado_envio: "enviado", origen: "odoo" });
        expect(delOdoo[0].adjunto_ids).toEqual([adjuntoId]);
        expect((await e.conversacionDe(celular))!.estado).toBe("humano");
      });

      it("la URL firmada solo vale con su firma; el puente no acepta un host que no sea de D'CASA ni una IP", async () => {
        const url = new URL(e.w.puente.envios.at(-1)!.medios[0].url);
        const local = `${ODOO_URL}${url.pathname}`;
        expect((await fetchReal(local)).status).toBe(200);
        const partes = url.pathname.split("/");
        partes[4] = (partes[4][0] === "0" ? "1" : "0") + partes[4].slice(1);
        expect((await fetchReal(`${ODOO_URL}${partes.join("/")}`)).status, "firma alterada").toBe(404);
        partes[4] = url.pathname.split("/")[4];
        partes[3] = String(Number(partes[3]) + 60);
        expect((await fetchReal(`${ODOO_URL}${partes.join("/")}`)).status, "vencimiento alterado").toBe(404);
        const otroId = url.pathname.split("/");
        otroId[2] = String(Number(otroId[2]) + 1);
        expect((await fetchReal(`${ODOO_URL}${otroId.join("/")}`)).status, "otro adjunto").toBe(404);

        // El mismo contrato visto desde el puente: lo que no es del dominio permitido se rechaza con 422.
        const rechazo = async (medioUrl: string) =>
          (await e.w.puente.fetcher.fetch("https://puente/api/enviar", {
            method: "POST",
            headers: { "content-type": "application/json", "x-wa-token-b64": Buffer.from(e.w.waToken).toString("base64") },
            body: JSON.stringify({ para: celular, chunks: [], medios: [{ tipo: "documento", url: medioUrl, nombre: "x.pdf" }] }),
          })).status;
        expect(await rechazo("https://otro-sitio.example.com/x.pdf")).toBe(422);
        expect(await rechazo("http://dcasapty.com/dcasa/adjunto/1/2/3/x.pdf")).toBe(422);
        expect(await rechazo(`http://127.0.0.1:${JUAN_PUERTO}/x.pdf`)).toBe(422);
        e.w.puente.rechazos.length = 0;
      });

      it("una foto (imagen) sale como imagen; el caso del archivo que Odoo no puede darle a nadie no se pierde", async () => {
        const png = Buffer.from(PNG_BASE64, "base64");
        const adjuntoId = await subir("foto.png", png, "image/png");
        const antes = e.w.puente.envios.length;
        await ventas.llamar("dcasa.conversacion", "enviar_respuesta", [convId, "", [adjuntoId]]);
        expect(e.w.puente.envios.length).toBe(antes + 1);
        const envio = e.w.puente.envios.at(-1)!;
        expect(envio.medios[0].tipo).toBe("imagen");
        expect(envio.chunks).toEqual([]);
        expect(Buffer.from(envio.descargas[0].bytes).equals(png)).toBe(true);
      });

      it("el administrador puede ver la clave de firma, y la firma de Odoo se verifica igual que en el servidor (HMAC-SHA256)", async () => {
        const [param] = await admin.buscar("ir.config_parameter", [["key", "=", "database.secret"]], ["value"]);
        const url = new URL(e.w.puente.envios.find((x) => x.medios[0]?.nombre === "cotizacion.pdf")!.medios[0].url);
        const [, , , id, vence, firma] = url.pathname.split("/");
        const [adjunto] = await admin.leer("ir.attachment", [Number(id)], ["checksum"]);
        const esperada = createHmac("sha256", param.value).update(`dcasa_adjunto:${id}:${vence}:${adjunto.checksum}`).digest("hex");
        expect(firma).toBe(esperada);
      });
    });
  });
}
