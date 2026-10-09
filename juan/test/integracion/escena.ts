// La «escena» compartida por todas las secciones de la prueba de integración: el Worker levantado, dos sesiones de Odoo
// (administración y una vendedora real) y atajos para mirar qué quedó en Odoo.

import { OdooRpc, levantarWorker, type Mundo } from "./ayuda";

const CLAVE_ADMIN = process.env.INTEGRACION_CLAVE_ADMIN ?? "";
const CLAVE_VENDEDORA = process.env.INTEGRACION_CLAVE_VENDEDORA ?? "";

export class Escena {
  w!: Mundo;
  /** Administración: ajustes, crons y auditoría. */
  admin!: OdooRpc;
  /** Una vendedora de verdad (usuario interno del equipo de ventas): la que usa la pantalla de conversaciones. */
  ventas!: OdooRpc;
  ajustesId!: number;

  async iniciar(): Promise<void> {
    this.w = await levantarWorker();
    this.admin = await new OdooRpc("admin", CLAVE_ADMIN).autenticar();
    this.ventas = await new OdooRpc("vendedora_integra", CLAVE_VENDEDORA).autenticar();
    [{ id: this.ajustesId }] = await this.admin.buscar("dcasa.juan.ajustes", [], ["id"]);
    // La prueba corre a cualquier hora: el horario laboral abarca todo el día, todos los días (salvo que un caso diga otra cosa).
    await this.ajustes({
      horario_inicio: 0.0,
      horario_fin: 23.98,
      dia_domingo: true,
      dia_lunes: true,
      dia_martes: true,
      dia_miercoles: true,
      dia_jueves: true,
      dia_viernes: true,
      dia_sabado: true,
      pausa_por_defecto_minutos: 120,
    });
  }

  async cerrar(): Promise<void> {
    await this.w?.cerrar();
  }

  /** Cambia los ajustes de Juan en Odoo (como la dueña) y hace que el Worker los vuelva a pedir. */
  async ajustes(valores: Record<string, unknown>): Promise<void> {
    await this.admin.escribir("dcasa.juan.ajustes", [this.ajustesId], valores);
    this.w.refrescarConfig();
  }

  async conversacionDe(celular: string): Promise<Record<string, any> | undefined> {
    const [c] = await this.ventas.buscar(
      "dcasa.conversacion",
      [["canal", "=", "whatsapp_qr"], ["id_externo", "=", celular]],
      [
        "estado", "pausada_hasta", "partner_id", "oportunidad_id", "etiqueta_ids", "nota_para_el_bot", "seguimiento_proximo", "seguimientos_enviados",
        "seguimiento_pedido_en", "ultimo_mensaje_autor", "asignada_a", "ultima_actividad", "bot_atiende", "ultimo_seguimiento_en", "estado_pendiente_de_avisar",
      ],
    );
    return c;
  }

  async mensajesDe(celular: string): Promise<Record<string, any>[]> {
    const c = await this.conversacionDe(celular);
    if (!c) return [];
    return this.ventas.buscar(
      "dcasa.mensaje",
      [["conversacion_id", "=", c.id]],
      ["tipo", "autor", "direccion", "texto", "id_mensaje", "estado_envio", "adjunto_ids", "origen", "usuario_id", "adjuntos_fallidos", "tiene_sensible"],
      { order: "id" },
    );
  }

  async textosDe(celular: string, autor: "cliente" | "bot" | "vendedora"): Promise<string[]> {
    return (await this.mensajesDe(celular)).filter((m) => m.tipo === "mensaje" && m.autor === autor).map((m) => m.texto as string);
  }
}
