# `frontend/` — Web React + Vite (Vercel)

SPA estática. Spec §12.2 (stack) · §12.9 (render) · §12.10 (diseño y layout) ·
§5.1 (navegación por rol).

## Estructura

```
src/
├─ app/          providers, rutas y sesión
├─ shell/        layout de 3 columnas, sidebar por rol, motor de densidad
├─ features/     una carpeta por dominio (§5.3)
├─ lib/          supabase, formato es-MX, utilidades
├─ api/          cliente HTTP + hooks generados por Orval (artefacto)
└─ estilos/      obractrl-design.css — fuente de verdad del diseño
```

## Dos rutas de datos que no se mezclan (§10.7)

| Qué | Cómo |
|---|---|
| **Catálogos** — selects, tablas, filtros | Directo a Supabase con `supabase-js` + RLS |
| **Lógica de dominio** — cargas/ETL, CPM, estimaciones, cierres | API FastAPI vía hooks de Orval |

La lista blanca de tablas consultables directo está en `src/lib/supabase.ts`.
Si una pantalla necesita algo que no está ahí, casi siempre significa que
debía pasar por un caso de uso del backend.

> **Seguridad:** el front usa la **anon key**. La *service key* nunca llega al
> navegador — saltaría RLS y expondría toda la base. `src/lib/supabase.ts`
> falla al arrancar si detecta una service key.

## Diseño (§12.10, DESIGN_SYSTEM.md)

`src/estilos/obractrl-design.css` es la **fuente de verdad**: tokens OKLCH,
tipografía Geist, motor de densidad y componentes del prototipo aprobado.
`tailwind.config.ts` solo los **expone** a Tailwind; los valores viven en el
CSS, una sola vez.

La paleta de Tailwind se **reemplaza**, no se extiende: si `bg-red-500`
siguiera existiendo, acabaría usándose y aparecería un segundo lenguaje
visual. Reglas:

1. **Cero colores crudos** — todo por token `--c-*`.
2. Números **siempre** con `--f-mono` + `tabular-nums`.
3. Respetar `body[data-density]`; no hardcodear alturas ni paddings de fila.
4. Mantener el shell y sus patrones: `Sheet` para drill-down, edición en línea
   en tablas.

### Rendimiento (§12.9)

Las vistas con miles de renglones —catálogo de conceptos/CPU, presupuesto,
ruta crítica, histórico— usan **virtualización** con `@tanstack/react-virtual`:
solo se montan las filas visibles. Gráficas y Gantt en **SVG**; si la densidad
del timeline crece mucho, Canvas.

## Navegación por rol (§5.1, §5.3)

`src/shell/navegacion.ts` mapea rol → secciones del sidebar. Las pantallas
compartidas (Torre, Incidencias, Ruta crítica, Cierres, Estimación,
Evaluación, Expediente, Presupuesto, Rendimientos, Avance) se implementan
**una sola vez** y cambian comportamiento por rol y alcance — no se duplican.

`rutaPermitida()` es una guarda de **UX**, no de seguridad: las fronteras
reales son el RBAC del backend y RLS (§12.4).

## Contrato de API

FastAPI genera `openapi.json`; Orval genera los hooks de TanStack Query.
`src/api/generado/` es artefacto y está en `.gitignore`: se regenera en CI en
cada cambio de contrato (§12.8).

```bash
npm run api:generar
```

## Estado

| Listo | Falta |
|---|---|
| Shell de 3 columnas y navegación por rol | Las features de `src/features/` |
| Tokens y motor de densidad | Tabla virtualizada reutilizable |
| Cliente Supabase con guarda de service key | Gantt / ruta crítica |
| Cliente HTTP con `problem+json` | Paleta de comandos (Ctrl+K) |
| Formato es-MX (13 pruebas) | Edición de celda en línea |

## Desarrollo

```bash
npm install
cp .env.example .env    # y llenar

npm run dev             # http://localhost:5173
npm run typecheck
npm test
npm run build
```

En dev, `vite.config.ts` proxea `/api` al backend local para no lidiar con
CORS (§12.8).

## Despliegue

`vercel.json` configura el build, el rewrite de SPA y las cabeceras. El deploy
es por Git. Las variables (`VITE_*`) se definen por entorno en Vercel; solo
las que empiezan con `VITE_` llegan al cliente.
