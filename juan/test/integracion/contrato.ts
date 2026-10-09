// Sección 1: lo que Odoo publica y el Worker lee (GET /config, GET /herramientas) y la forma de sus respuestas.

import { describe, expect, it } from "vitest";
import { dentroDeHorario, normalizarConfig } from "../../src/config";
import { planDeIntentos } from "../../src/motor/proveedores";
import { OdooCliente } from "../../src/odoo/cliente";
import { TOKEN_ODOO, apiOdoo, celularNuevo, enlaceDcasa } from "./ayuda";
import type { Escena } from "./escena";

export function seccionContrato(e: Escena) {
  describe("1. El Worker lee lo que Odoo publica", () => {
    const cliente = () => new OdooCliente(enlaceDcasa(e.w.enlace), TOKEN_ODOO);

    it("GET /config: el Worker entiende los nombres y tipos de Odoo (IA, modelos, precios, lecciones, horario, seguimiento)", async () => {
      await e.ajustes({
        lecciones_aprendidas: "Si preguntan por Yappy, di que una vendedora lo confirma.\nSaluda por el nombre.",
        precio_rapido_entrada_usd_mtok: 1.0,
        precio_rapido_salida_usd_mtok: 5.0,
        precio_rapido_cache_usd_mtok: 0.1,
        precio_inteligente_entrada_usd_mtok: 3.0,
        precio_inteligente_salida_usd_mtok: 15.0,
        precio_inteligente_cache_usd_mtok: 0.3,
      });
      const cfg = normalizarConfig(await cliente().config());

      expect(cfg.nombre_publico).toBe("el equipo de D'CASA");
      expect(cfg.bot_activo_global).toBe(true);
      expect(cfg.canales_activos).toMatchObject({ whatsapp_qr: true, telegram: true, whatsapp_cloud: false, messenger: false, instagram: false });
      expect(cfg.proveedor_ia).toBe("anthropic");
      expect(cfg.proveedor_respaldo_ia).toBeNull();
      expect(cfg.modelo_rapido).toBe("claude-haiku-4-5");
      expect(cfg.modelo_inteligente).toBe("claude-sonnet-5-5");
      expect(cfg.seguimiento).toEqual({ primero_horas: 5, segundo_dias: 5, solo_horario_laboral: true, maximo: 2 });
      expect(cfg.presupuesto_ia_mensual_usd).toBe(30);
      expect(cfg.pausa_por_defecto_minutos).toBe(120);
      expect(cfg.palabras_prohibidas).toEqual(["remate", "corre", "¡¡", "!!"]);
      expect(cfg.mensaje_bienvenida).toMatch(/asistente automático/i);
      expect(typeof cfg.texto_privacidad_corto).toBe("string"); // vacío por defecto: el primer mensaje es corto
      // Lecciones: una por línea en Odoo, lista en el Worker.
      expect(cfg.lecciones).toEqual(["Si preguntan por Yappy, di que una vendedora lo confirma.", "Saluda por el nombre."]);
      // Los precios que la dueña cargó en Odoo (por nivel) llegan al Worker por modelo.
      expect(cfg.precios_ia["claude-haiku-4-5"]).toEqual({ entrada: 1, salida: 5, entrada_cache: 0.1 });
      expect(cfg.precios_ia["claude-sonnet-5-5"]).toEqual({ entrada: 3, salida: 15, entrada_cache: 0.3 });
    });

    it("proveedor de respaldo y modelos: lo que Odoo publica es lo que el Worker usa para armar el plan de IA", async () => {
      await e.ajustes({ proveedor_respaldo_ia: "meta" });
      try {
        const cfg = normalizarConfig(await cliente().config());
        expect(cfg.proveedor_ia).toBe("anthropic");
        expect(cfg.proveedor_respaldo_ia).toBe("meta");
        // Odoo no tiene campos para los modelos del respaldo: el Worker usa los de siempre de ese proveedor.
        expect(planDeIntentos(cfg, "rapido", ["anthropic", "meta"]).map((s) => `${s.proveedor}/${s.modelo}`)).toEqual([
          "anthropic/claude-haiku-4-5",
          "meta/muse-spark-1.3",
        ]);
        const crudo = (await cliente().config()) as Record<string, any>;
        expect(crudo.modelos_por_defecto.anthropic).toEqual({ rapido: "claude-haiku-4-5", inteligente: "claude-sonnet-5-5" });
      } finally {
        await e.ajustes({ proveedor_respaldo_ia: false });
      }
    });

    it("el horario: los días de Odoo (0 = domingo) significan lo mismo para el Worker", async () => {
      await e.ajustes({ dia_domingo: false });
      try {
        const cfg = normalizarConfig(await cliente().config());
        expect(cfg.horario.dias).toEqual([1, 2, 3, 4, 5, 6]);
        const domingo = Date.parse("2026-10-11T15:00:00Z"); // domingo 10:00 en Panamá
        const lunes = Date.parse("2026-10-12T15:00:00Z"); // lunes 10:00 en Panamá
        expect(dentroDeHorario(cfg.horario, domingo)).toBe(false);
        expect(dentroDeHorario(cfg.horario, lunes)).toBe(true);
      } finally {
        await e.ajustes({ dia_domingo: true });
      }
    });

    it("GET /herramientas: el Worker las parsea con el mismo nombre con el que Odoo las ejecuta", async () => {
      const defs = await cliente().herramientas();
      expect(defs.map((d) => d.nombre).sort()).toEqual(
        [
          "anotar_conversacion", "buscar_conocimiento", "buscar_productos", "crear_oportunidad", "etiquetar_conversacion", "horario_y_tienda",
          "listar_categorias", "pasar_a_vendedora", "registrar_pregunta_sin_respuesta", "reglas_socios", "saldo_puntos", "ver_producto",
        ].sort(),
      );
      for (const d of defs) {
        expect(d.nombre.startsWith("juan_"), `${d.nombre} no debe llevar el prefijo interno`).toBe(false);
        expect(d.descripcion.length).toBeGreaterThan(10);
        expect(d.parametros).toMatchObject({ type: "object" });
      }
      const buscar = defs.find((d) => d.nombre === "buscar_productos")!;
      expect(buscar.parametros).toMatchObject({ properties: { consulta: { type: "string" } }, required: ["consulta"] });

      // Odoo las publica con claves duales (contrato + formato de Anthropic) bajo «herramientas».
      const crudo = await apiOdoo("GET", "/herramientas");
      expect(crudo.estado).toBe(200);
      expect(Object.keys(crudo.json.herramientas[0]).sort()).toEqual(["description", "descripcion", "input_schema", "name", "nombre", "parametros"].sort());

      // Y se ejecuta con ese mismo nombre.
      expect((await cliente().herramienta("listar_categorias", {}, null)).ok).toBe(true);
      const inexistente = await cliente().herramienta("no_existe", {}, null);
      expect(inexistente.ok).toBe(false);
      expect(inexistente.error).toMatch(/404/);
      // «juan_buscar_productos» es el nombre INTERNO (Brian): por la API pública no existe.
      expect((await cliente().herramienta("juan_buscar_productos", { consulta: "cama" }, null)).ok).toBe(false);
    });

    it("POST /mensaje: forma de la respuesta e idempotencia por id_mensaje", async () => {
      const celular = celularNuevo();
      const cuerpo = {
        canal: "whatsapp_qr", id_externo: celular, nombre: "Prueba Idempotencia", celular, id_mensaje: `wamid.idem.${celular}`, direccion: "entrante",
        autor: "cliente", texto: "Hola, ¿tienen camas queen?", ts: new Date().toISOString(),
      };
      const uno = await apiOdoo("POST", "/mensaje", { cuerpo });
      expect(uno.estado).toBe(200);
      expect(uno.json).toMatchObject({ ok: true, estado: "bot", bot_activo: true, pausada_hasta: null, dentro_de_horario: true, nota_para_el_bot: null });
      expect(typeof uno.json.conversacion_id).toBe("number");
      expect(typeof uno.json.partner_id).toBe("number");
      const dos = await apiOdoo("POST", "/mensaje", { cuerpo });
      expect(dos.json.conversacion_id).toBe(uno.json.conversacion_id);
      expect(dos.json.partner_id).toBe(uno.json.partner_id);
      expect((await e.mensajesDe(celular)).filter((m) => m.tipo === "mensaje")).toHaveLength(1);

      const estado = await apiOdoo("GET", `/estado?canal=whatsapp_qr&id_externo=${celular}`);
      expect(estado.json).toMatchObject({ ok: true, bot_activo: true, estado: "bot", pausada_hasta: null, dentro_de_horario: true, nota_para_el_bot: null });
    });
  });
}
