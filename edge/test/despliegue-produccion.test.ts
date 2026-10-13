/**
 * A producción NUNCA se despliega sola. GitHub no ofrece «Required reviewers» en repositorios privados de los planes
 * Free, Pro ni Team, así que la aprobación es el clic de quien lanza *Run workflow* con `desplegar_en = produccion`,
 * y solo desde `main`. Un merge (push a `main`) corre las pruebas y nada más.
 *
 * Estas pruebas leen los workflows tal como están en el repositorio: si alguien vuelve a enganchar producción a un
 * `push`, fallan.
 */
import { describe, expect, it } from "vitest";
import ci from "../../.github/workflows/ci.yml?raw";
import desplegar from "../../.github/workflows/desplegar.yml?raw";
import desplegarJuan from "../../.github/workflows/desplegar-juan.yml?raw";
import desplegarPuente from "../../.github/workflows/desplegar-puente.yml?raw";
import upMedia from "../../.github/workflows/up-media.yml?raw";

/** El texto de un trabajo (`  nombre:` con dos espacios, bajo `jobs:`) hasta el siguiente trabajo. */
function trabajo(yaml: string, nombre: string): string {
  const inicio = yaml.indexOf(`\n  ${nombre}:\n`);
  expect(inicio, `no existe el trabajo ${nombre}`).toBeGreaterThan(-1);
  const resto = yaml.slice(inicio + 1);
  const siguiente = resto.slice(1).search(/\n {2}[a-z0-9-]+:\n/);
  return siguiente === -1 ? resto : resto.slice(0, siguiente + 1);
}

/** El bloque `on:` de un workflow: sus disparos. */
function disparos(yaml: string): string {
  const bloque = /\non:\n((?:[ \t]+.*\n|[ \t]*\n)+)/.exec(yaml);
  expect(bloque, "el workflow no tiene bloque on:").not.toBeNull();
  return bloque![1];
}

describe("el despliegue a producción es solo a mano y desde main", () => {
  it("el trabajo de producción exige disparo manual, la opción «produccion» y la rama main", () => {
    const produccion = trabajo(ci, "desplegar-produccion");
    expect(produccion).toContain("github.event_name == 'workflow_dispatch'");
    expect(produccion).toContain("inputs.desplegar_en == 'produccion'");
    expect(produccion).toContain("github.ref == 'refs/heads/main'");
    expect(produccion).not.toContain("'push'");
    expect(produccion).toContain("entorno: production");
  });

  it("ci.yml llama una sola vez a producción", () => {
    expect(ci.match(/entorno: production/g) ?? []).toHaveLength(1);
  });

  it("un push a main sigue corriendo las pruebas, pero no guarda la imagen para desplegar", () => {
    expect(disparos(ci)).toMatch(/push:\n\s+branches: \[main\]/);
    const linea = ci.split("\n").find((l) => l.includes("SE_DESPLIEGA:"));
    expect(linea).toBeDefined();
    expect(linea).toContain("github.event_name == 'workflow_dispatch'");
    expect(linea).not.toContain("'push'");
    expect(linea).toContain("inputs.desplegar_en == 'produccion' && github.ref == 'refs/heads/main'");
  });

  it("el disparo manual ofrece «produccion»", () => {
    expect(ci).toMatch(/options: \[[^\]]*\bproduccion\b[^\]]*\]/);
  });

  it("pedir producción desde otra rama falla con un aviso claro, no se omite en silencio", () => {
    const aviso = trabajo(ci, "produccion-solo-desde-main");
    expect(aviso).toContain("inputs.desplegar_en == 'produccion' && github.ref != 'refs/heads/main'");
    expect(aviso).toContain("::error::");
    expect(aviso).toContain("exit 1");
  });

  it("desplegar.yml solo se llama desde otros workflows o a mano (volver atrás): nada lo dispara solo", () => {
    const entradas = disparos(desplegar);
    expect(entradas).toContain("workflow_call:");
    expect(entradas).toContain("workflow_dispatch:");
    expect(entradas).not.toContain("push:");
    expect(entradas).not.toContain("schedule:");
    expect(entradas).not.toContain("pull_request");
  });

  it("Juan y el puente (que pueden llegar a producción) son solo a mano", () => {
    for (const [nombre, yaml] of [["desplegar-juan", desplegarJuan], ["desplegar-puente", desplegarPuente]] as const) {
      const entradas = disparos(yaml);
      expect(entradas, nombre).toContain("workflow_dispatch:");
      expect(entradas, nombre).not.toContain("push:");
      expect(entradas, nombre).not.toContain("schedule:");
      expect(entradas, nombre).not.toContain("pull_request");
    }
  });

  it("la subida de fotos (up media) despliega solo a staging, aunque se dispare con un push a main", () => {
    expect(disparos(upMedia)).toContain("push:");
    expect(upMedia).not.toContain("entorno: production");
    expect(trabajo(upMedia, "desplegar-staging")).toContain("entorno: staging");
  });
});
