import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// Guardas de lo que NO se puede probar ejecutándolo (no se despliega nada): la configuración de Cloudflare, el
// workflow, la imagen del contenedor y la higiene de secretos. Si alguien rompe una de estas reglas, falla aquí.

const RAIZ = new URL("..", import.meta.url).pathname; // puente-wa/
const REPO = join(RAIZ, "..");
const leer = (ruta: string) => readFileSync(join(RAIZ, ruta), "utf8");

/** Quita comentarios `//` y `/* *​/` de un JSONC respetando las cadenas (las URL llevan «//»). */
function quitarComentarios(texto: string): string {
  let salida = "";
  let enCadena = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    const n = texto[i + 1];
    if (enCadena) {
      salida += c;
      if (c === "\\") salida += texto[++i];
      else if (c === '"') enCadena = false;
    } else if (c === '"') {
      enCadena = true;
      salida += c;
    } else if (c === "/" && n === "/") {
      while (i < texto.length && texto[i] !== "\n") i++;
      salida += "\n";
    } else if (c === "/" && n === "*") {
      i += 2;
      while (i < texto.length && !(texto[i] === "*" && texto[i + 1] === "/")) i++;
      i++;
    } else salida += c;
  }
  return salida.replace(/,(\s*[}\]])/g, "$1");
}
const wrangler = JSON.parse(quitarComentarios(leer("wrangler.jsonc")));

describe("wrangler.jsonc: producción y staging", () => {
  it("nombres de los Workers", () => {
    expect(wrangler.name).toBe("dcasa-puente-wa");
    expect(wrangler.env.staging.name).toBe("dcasa-puente-wa-staging");
  });

  it("el service binding JUAN apunta a dcasa-juan (producción) y dcasa-juan-staging (staging)", () => {
    expect(wrangler.services).toEqual([{ binding: "JUAN", service: "dcasa-juan" }]);
    expect(wrangler.env.staging.services).toEqual([{ binding: "JUAN", service: "dcasa-juan-staging" }]);
  });

  it.each([
    ["producción", () => wrangler],
    ["staging", () => wrangler.env.staging],
  ])("%s: un solo contenedor `lite`, un solo Durable Object con SQLite, cron cada minuto", (_n, cual) => {
    const c = cual();
    expect(c.containers).toHaveLength(1);
    expect(c.containers[0]).toMatchObject({
      class_name: "PuenteWa",
      image: "./contenedor/Dockerfile",
      instance_type: "lite",
      max_instances: 1, // dos sockets sobre el mismo número se expulsan en bucle
      scheduling_policy: "default",
    });
    expect(c.durable_objects.bindings).toEqual([{ name: "WA", class_name: "PuenteWa" }]);
    expect(c.migrations).toEqual([{ tag: "v1", new_sqlite_classes: ["PuenteWa"] }]);
    expect(c.triggers.crons).toEqual(["* * * * *"]);
  });

  it("la URL pública de cada entorno es la de su propio Worker (el contenedor vuelve a entrar por ahí)", () => {
    expect(wrangler.vars.PUENTE_BASE_URL).toBe("https://dcasa-puente-wa.dcasapty.workers.dev");
    expect(wrangler.env.staging.vars.PUENTE_BASE_URL).toBe("https://dcasa-puente-wa-staging.dcasapty.workers.dev");
  });

  it("staging repite TODAS las variables de producción (los entornos no heredan `vars`)", () => {
    expect(Object.keys(wrangler.env.staging.vars).sort()).toEqual(Object.keys(wrangler.vars).sort());
  });

  it("la copia a R2 está APAGADA y el bucket sin enlazar (R2 es una decisión de la dueña)", () => {
    expect(wrangler.vars.COPIA_R2).toBe("off");
    expect(wrangler.env.staging.vars.COPIA_R2).toBe("off");
    expect(wrangler.r2_buckets).toBeUndefined();
    expect(wrangler.env.staging.r2_buckets).toBeUndefined();
  });

  it("no se crea ningún recurso extra: ni D1, ni KV, ni Vectorize, ni Workers AI", () => {
    for (const c of [wrangler, wrangler.env.staging]) {
      for (const clave of ["d1_databases", "kv_namespaces", "vectorize", "ai", "queues", "hyperdrive", "r2_buckets"]) {
        expect(c[clave]).toBeUndefined();
      }
    }
  });

  it("los secretos NO están en el archivo (ni como variables) y no se exigen con `secrets.required`", () => {
    const texto = quitarComentarios(leer("wrangler.jsonc"));
    expect(texto).not.toContain("secrets");
    for (const c of [wrangler.vars, wrangler.env.staging.vars]) {
      for (const secreto of ["WA_TOKEN", "WA_SESION_CLAVE", "WA_SESION_CLAVE_ANTERIOR", "TELEGRAM_BOT_TOKEN_JUAN", "ALERTA_TELEGRAM_CHAT"]) {
        expect(c).not.toHaveProperty(secreto);
      }
    }
  });

  it("el ritmo por defecto es conservador y las descargas están limitadas a los dominios de D'CASA", () => {
    for (const v of [wrangler.vars, wrangler.env.staging.vars]) {
      expect(Number(v.LIMITE_POR_MINUTO)).toBeLessThanOrEqual(12);
      expect(Number(v.LIMITE_POR_DIA)).toBeLessThanOrEqual(500);
      expect(Number(v.LIMITE_FRIOS_DIA)).toBeLessThanOrEqual(20);
      expect(v.MEDIOS_HOSTS_PERMITIDOS).toBe("dcasapty.com,dcasapty.workers.dev");
      expect(v.PUENTE_ACTIVO).toBe("on"); // el interruptor de emergencia; sin secretos igual no enciende nada
    }
  });
});

describe("workflow .github/workflows/desplegar-puente.yml", () => {
  const wf = readFileSync(join(REPO, ".github/workflows/desplegar-puente.yml"), "utf8");
  const sinComentarios = wf.replace(/^\s*#.*$/gm, "").replace(/\s+#\s.*$/gm, "");

  it("solo a mano (workflow_dispatch), con ensayo por defecto", () => {
    expect(sinComentarios).toMatch(/^on:\s*\n\s+workflow_dispatch:/m);
    for (const otro of ["push:", "pull_request:", "schedule:", "workflow_call:", "workflow_run:"]) expect(sinComentarios).not.toContain(otro);
    expect(sinComentarios).toMatch(/accion:[\s\S]*?default: dry-run/);
    expect(sinComentarios).toContain("if: inputs.accion == 'desplegar'");
  });

  it("solo usa los dos secretos de GitHub que ya existen para desplegar", () => {
    const usados = [...sinComentarios.matchAll(/secrets\.([A-Z0-9_]+)/g)].map((m) => m[1]);
    expect([...new Set(usados)].sort()).toEqual(["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]);
  });

  it("no sube secretos: nada de --secrets-file ni de secrets.required", () => {
    expect(sinComentarios).not.toContain("--secrets-file");
    expect(sinComentarios).not.toContain("secrets.required");
    expect(sinComentarios).not.toMatch(/wrangler secret/);
    for (const nombre of ["WA_TOKEN", "WA_SESION_CLAVE", "TELEGRAM_BOT_TOKEN_JUAN"]) expect(sinComentarios).not.toContain(nombre);
  });

  it("permisos mínimos, acciones fijadas por SHA, entorno con aprobación y un despliegue a la vez", () => {
    expect(sinComentarios).toMatch(/^permissions:\s*\n\s+contents: read/m);
    for (const m of sinComentarios.matchAll(/uses: ([\w./-]+)@(\S+)/g)) expect(m[2]).toMatch(/^[0-9a-f]{40}$/);
    expect(sinComentarios).toContain("environment:");
    expect(sinComentarios).toContain("group: desplegar-puente-${{ inputs.entorno }}");
    expect(sinComentarios).toContain("cancel-in-progress: false");
  });

  it("el despliegue va por el wrangler fijado en el package-lock (npm ci + npx local), nunca `wrangler@latest`", () => {
    expect(sinComentarios).toContain("npm ci");
    expect(sinComentarios).not.toMatch(/wrangler@/);
    expect(sinComentarios).not.toMatch(/npx -y|npm i -g/);
  });

  it("comprueba que el Worker juan existe antes de desplegar y NO borra ni imprime secretos", () => {
    expect(sinComentarios).toContain("workers/scripts/${juan}");
    expect(sinComentarios).not.toMatch(/echo[^\n]*\$\{?CLOUDFLARE_API_TOKEN/);
  });
});

describe("la imagen del contenedor", () => {
  const dockerfile = leer("contenedor/Dockerfile");
  const lineas = dockerfile.split("\n").filter((l) => !l.trim().startsWith("#"));

  it("copia TODO lo que servidor.mjs y nucleo.mjs importan", () => {
    const copiados = lineas.filter((l) => l.startsWith("COPY ") && !l.includes("--from")).join(" ");
    const importados = new Set<string>();
    const recorrer = (archivo: string) => {
      for (const m of leer(archivo).matchAll(/from "\.\/([^"]+)"/g)) importados.add(m[1]);
    };
    recorrer("contenedor/servidor.mjs");
    recorrer("contenedor/nucleo.mjs");
    expect(importados.size).toBeGreaterThan(5);
    for (const imp of importados) {
      const [raiz] = imp.split("/");
      expect(copiados, `falta copiar «${raiz}» a la imagen`).toMatch(new RegExp(`(^|\\s)${raiz.replace(".", "\\.")}(\\s|$)`));
    }
    // y todo lo que hay en lib/ se importa por alguno de los módulos (nada de archivos huérfanos que no viajan)
    for (const f of readdirSync(join(RAIZ, "contenedor/lib"))) {
      const usado = [...readdirSync(join(RAIZ, "contenedor/lib")).map((x) => `contenedor/lib/${x}`), "contenedor/servidor.mjs", "contenedor/nucleo.mjs"].some((a) => leer(a).includes(`/${f}"`));
      expect(usado, `lib/${f} no lo importa nadie`).toBe(true);
    }
  });

  it("Node 22, dependencias exactas del lock (npm ci), proceso sin root y sin init", () => {
    expect(lineas.filter((l) => l.startsWith("FROM ")).every((l) => /node:22-/.test(l))).toBe(true);
    expect(dockerfile).toContain("npm ci --omit=dev");
    expect(lineas.join("\n")).toMatch(/USER node/);
    expect(lineas.join("\n")).toMatch(/CMD \["node", "servidor\.mjs"\]/);
    expect(lineas.join("\n")).not.toMatch(/:latest|ADD http|curl .*\| *sh/);
  });

  it("Baileys va fijado exacto y a una versión sin el aviso de seguridad GHSA-qvv5-jq5g-4cgg (≥ rc12)", () => {
    const pkg = JSON.parse(leer("contenedor/package.json"));
    expect(pkg.dependencies["@whiskeysockets/baileys"]).toBe("7.0.0-rc14");
    const lock = JSON.parse(leer("contenedor/package-lock.json"));
    const version = lock.packages["node_modules/@whiskeysockets/baileys"].version as string;
    expect(version).toBe("7.0.0-rc14");
    expect(Number(/rc\.?(\d+)/.exec(version)![1])).toBeGreaterThanOrEqual(12);
    // sin dependencias desde git (necesitarían git y claves SSH en la imagen)
    expect(JSON.stringify(lock)).not.toMatch(/git\+|github:/);
  });

  it("servidor.mjs, nucleo.mjs y lib/*.mjs son JavaScript válido para Node", () => {
    const archivos = ["contenedor/servidor.mjs", "contenedor/nucleo.mjs", ...readdirSync(join(RAIZ, "contenedor/lib")).map((f) => `contenedor/lib/${f}`)];
    for (const a of archivos) execFileSync(process.execPath, ["--check", join(RAIZ, a)]);
  });

  it("hay .dockerignore (no viaja node_modules ni nada de más)", () => {
    expect(readFileSync(join(RAIZ, "contenedor/.dockerignore"), "utf8")).toContain("node_modules");
  });
});

// ── Higiene de secretos ──────────────────────────────────────────────────────

function archivos(dir: string, salida: string[] = []): string[] {
  for (const nombre of readdirSync(dir)) {
    if (["node_modules", ".wrangler", "package-lock.json"].includes(nombre)) continue;
    const ruta = join(dir, nombre);
    if (statSync(ruta).isDirectory()) archivos(ruta, salida);
    else salida.push(ruta);
  }
  return salida;
}
const propios = [
  ...archivos(RAIZ),
  join(REPO, ".github/workflows/desplegar-puente.yml"),
  ...(existsSync(join(REPO, "docs/JUAN_PUENTE.md")) ? [join(REPO, "docs/JUAN_PUENTE.md")] : []),
];

describe("higiene: ningún valor de secreto en el repositorio ni en los registros", () => {
  it("no hay tokens, claves privadas ni valores asignados a un secreto (salvo valores de PRUEBA en las pruebas)", () => {
    expect(propios.length).toBeGreaterThan(30);
    const sospechosos: string[] = [];
    for (const ruta of propios) {
      const texto = readFileSync(ruta, "utf8");
      const rel = relative(REPO, ruta);
      if (/-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(texto)) sospechosos.push(`${rel}: clave privada`);
      if (/sk-ant-[A-Za-z0-9_-]{10,}/.test(texto)) sospechosos.push(`${rel}: llave de Anthropic`);
      if (/\b\d{8,10}:[A-Za-z0-9_-]{35}\b/.test(texto)) sospechosos.push(`${rel}: token de bot de Telegram`);
      if (/\bcfut_[A-Za-z0-9]{20,}/.test(texto) || /\bcfat_[A-Za-z0-9]{20,}/.test(texto)) sospechosos.push(`${rel}: token de Cloudflare`);
      for (const m of texto.matchAll(/\b(\w*(?:TOKEN|CLAVE|SECRET|PASSWORD|API_KEY)\w*)\s*[:=]\s*["'`]([^"'`$]{16,})["'`]/g)) {
        // Las pruebas usan valores que dicen «prueba»/«falso» a propósito; fuera de ellas no debe haber ninguno.
        if (!/prueba|falso|example|ejemplo|\.\.\./i.test(m[2])) sospechosos.push(`${rel}: ${m[1]} tiene un valor escrito`);
      }
    }
    expect(sospechosos).toEqual([]);
  });

  it("el código no manda a los registros el QR, las credenciales ni los tokens", () => {
    const codigo = propios.filter((r) => /\/(src|contenedor)\/.*\.(ts|mjs)$/.test(r) && !r.includes("/test/"));
    const prohibido = /\b(WA_TOKEN|WA_SESION_CLAVE|PUENTE_TOKEN|qrActual|qr|creds|valor|texto|cuerpo|payload)\b/;
    const culpables: string[] = [];
    for (const ruta of codigo) {
      const lineas = readFileSync(ruta, "utf8").split("\n");
      lineas.forEach((l, i) => {
        if (!/\b(console\.(log|error|warn|info)|log\.(log|error))\(/.test(l)) return;
        // Lo que se escribe a los registros: las cadenas literales sin interpolar ni nombres de variable sensibles.
        const args = l.slice(l.indexOf("("));
        const sinLiterales = args.replace(/"[^"]*"/g, '""').replace(/`[^`]*`/g, (t) => t.replace(/[^$]*\$\{([^}]*)\}[^$]*/g, "$1 "));
        if (prohibido.test(sinLiterales)) culpables.push(`${relative(REPO, ruta)}:${i + 1}: ${l.trim()}`);
      });
    }
    expect(culpables).toEqual([]);
  });

  it("el QR se sirve solo por /api/qr (con token), y el único log del QR dice su número de orden", () => {
    const nucleo = leer("contenedor/nucleo.mjs");
    expect(nucleo).toContain("QR nuevo disponible (#${qrGenerados}).");
    const logs = [...nucleo.matchAll(/log\.(?:log|error)\(([^)]*)\)/g)].map((m) => m[1]);
    expect(logs.join("\n")).not.toMatch(/\bqr\b|toDataURL/);
  });
});
