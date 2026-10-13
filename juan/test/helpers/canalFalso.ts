// Un canal de mentira: guarda lo que el bot le manda al cliente.
import { EnvioParcialError, type AdaptadorCanal, type Capacidades, type CanalId, type ResultadoEnvio, type ResultadoWebhook, type Saliente } from "../../src/canales/tipos";

export class CanalFalso implements AdaptadorCanal {
  canales: readonly CanalId[];
  ruta = "/webhooks/falso";
  salidas: Saliente[] = [];
  escribiendoVeces = 0;
  /** Cuántos envíos fallan antes de funcionar. */
  fallar = 0;
  /** Lo que dice el error de un envío que falla (para probar que /salud no repite direcciones ni claves). */
  motivoDeFallo = "el canal falló";
  cap: Capacidades = { imagenes: true, documentos: true, ventana24h: false, maxTexto: 3500 };
  idsDevueltos = true;
  /** El próximo envío se corta a la mitad: salen solo estas burbujas y archivos y luego falla, como un canal que se cae a media respuesta. */
  cortarEn: { burbujas: number; medios?: number } | null = null;
  /** Mientras exista, el envío espera a que se resuelva (para probar dos envíos a la vez). */
  puerta: Promise<void> | null = null;
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
    if (this.puerta) await this.puerta;
    if (this.cortarEn) {
      const corte = this.cortarEn;
      this.cortarEn = null;
      const parte: Saliente = { ...salida, burbujas: salida.burbujas.slice(0, corte.burbujas), medios: salida.medios.slice(0, corte.medios ?? 0) };
      this.salidas.push(parte);
      throw new EnvioParcialError("el canal se cortó a la mitad", { burbujas: parte.burbujas.length, medios: parte.medios.length, ids: parte.burbujas.map(() => `m${++this.n}`) });
    }
    if (this.fallar > 0) {
      this.fallar--;
      throw new Error(this.motivoDeFallo);
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
