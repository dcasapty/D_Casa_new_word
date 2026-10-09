// Un canal de mentira: guarda lo que el bot le manda al cliente.
import type { AdaptadorCanal, Capacidades, CanalId, ResultadoEnvio, ResultadoWebhook, Saliente } from "../../src/canales/tipos";

export class CanalFalso implements AdaptadorCanal {
  canales: readonly CanalId[];
  ruta = "/webhooks/falso";
  salidas: Saliente[] = [];
  escribiendoVeces = 0;
  /** Cuántos envíos fallan antes de funcionar. */
  fallar = 0;
  cap: Capacidades = { imagenes: true, documentos: true, ventana24h: false, maxTexto: 3500 };
  idsDevueltos = true;
  /** Cuántas veces el motor pidió la foto de perfil, y qué contesta el canal (lanza si es un Error, `null` = sin foto). */
  fotosPedidas = 0;
  foto: { bytes: Uint8Array; mime: string } | Error | null = null;
  private n = 0;

  constructor(canal: CanalId = "whatsapp_qr") {
    this.canales = [canal];
  }

  capacidades(): Capacidades {
    return this.cap;
  }
  faltantes(): string[] {
    return [];
  }
  configurado(): boolean {
    return true;
  }
  async recibir(): Promise<ResultadoWebhook> {
    throw new Error("no se usa en las pruebas del motor");
  }
  async enviar(_canal: CanalId, salida: Saliente): Promise<ResultadoEnvio> {
    if (this.fallar > 0) {
      this.fallar--;
      throw new Error("el canal falló");
    }
    this.salidas.push(salida);
    return { ids: this.idsDevueltos ? salida.burbujas.map(() => `m${++this.n}`) : [] };
  }
  async escribiendo(): Promise<void> {
    this.escribiendoVeces++;
  }

  async fotoDePerfil(): Promise<{ bytes: Uint8Array; mime: string } | null> {
    this.fotosPedidas++;
    if (this.foto instanceof Error) throw this.foto;
    return this.foto;
  }

  /** Un canal sin foto de perfil (WhatsApp Cloud): se le quita el método. */
  sinFotoDePerfil(): this {
    (this as { fotoDePerfil?: unknown }).fotoDePerfil = undefined;
    return this;
  }

  /** Un canal sin «escribiendo…» (WhatsApp por QR): se le quita el método. */
  sinEscribiendo(): this {
    (this as { escribiendo?: unknown }).escribiendo = undefined;
    return this;
  }

  /** Todo el texto enviado, burbuja por burbuja. */
  get textos(): string[] {
    return this.salidas.flatMap((s) => s.burbujas);
  }
  get ultimaSalida(): Saliente | undefined {
    return this.salidas[this.salidas.length - 1];
  }
  get medios() {
    return this.salidas.flatMap((s) => s.medios);
  }
}
