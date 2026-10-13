import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      // `cloudflare:workers` solo existe dentro de workerd; en Node se usa un doble mínimo.
      "cloudflare:workers": fileURLToPath(new URL("./test/helpers/cloudflare-workers.ts", import.meta.url)),
    },
  },
  test: { include: ["test/**/*.test.ts"], environment: "node" },
});
