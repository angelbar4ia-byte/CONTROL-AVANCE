import { defineConfig } from 'orval';

/**
 * Generación del cliente de API.
 *
 * Spec §12.2 — FastAPI emite `openapi.json` y Orval genera los hooks de
 * TanStack Query. Cero integración manual: el front programa **contra el
 * contrato**, no contra la implementación (AGENTS.md).
 *
 * `src/api/generado/` es artefacto: no se edita a mano y se regenera en CI
 * en cada cambio de contrato (§12.8).
 */
export default defineConfig({
  obractrl: {
    input: { target: '../openapi/openapi.json' },
    output: {
      mode: 'tags-split',
      target: 'src/api/generado/obractrl.ts',
      schemas: 'src/api/generado/modelo',
      client: 'react-query',
      prettier: true,
      override: {
        mutator: {
          path: 'src/api/cliente.ts',
          name: 'peticion',
        },
        query: {
          useQuery: true,
          useInfinite: true,
          signal: true,
        },
      },
    },
  },
});
