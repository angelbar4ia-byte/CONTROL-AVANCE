# ObraCtrl — Roadmap de desarrollo

> **Fuente de verdad:** [`ObraCtrl-especificacion-tecnica.md`](ObraCtrl-especificacion-tecnica.md).
> **Contrato de equipo:** [`AGENTS.md`](AGENTS.md). Ningún agente inventa reglas.

## Decisiones del Arquitecto (acordadas)

| # | Decisión | Implicación |
|---|---|---|
| D1 | **Corte vertical por dominio** | Cada dominio se entrega de punta a punta (BD → dominio → casos de uso → API → web → QA) antes de abrir el siguiente. Nada de módulos a medias. |
| D2 | **Móvil en paralelo desde la Fase 1** | El agente Mobile/Sync no espera al backend completo: trabaja sobre el contrato ya publicado (`avance`, `cierres`) y sobre PowerSync. |
| D3 | **Contrato primero** | Arquitecto + Backend fijan OpenAPI y puertos antes de codear. Web/Mobile consumen hooks generados por Orval, nunca la implementación. |
| D4 | **RLS = frontera real** | Toda tabla nueva entra con política RLS + prueba de aislamiento en el mismo PR. Las sync rules de PowerSync espejean RLS. |
| D5 | **La conciliación offline va directo a Postgres** | Gana el spec §11.3 workflow B: el móvil escribe vía PowerSync → Postgres, con RLS como única frontera; **no** pasa por `PATCH /actividades/{id}/avance`, que queda como ruta exclusivamente web. Resuelve la contradicción que tenía el docstring de `adapters/api/v1/avance.py`. |
| D6 | **`registro_avance` es la única fuente de `cant_ejecutada`** | Corolario obligado de D5: si el móvil escribe deltas y la web escribía un absoluto, la primera captura offline pisaba el total. Ahora `cant_ejecutada` se **deriva** de Σ deltas en el trigger `app.registro_avance_agregar` (migración 0017), igual que `avance_pct` se deriva de ella desde 0007. Consecuencias aplicadas: `actualizar_avance` dejó de escribir `cant_ejecutada`/`avance_pct`; el caso de uso web solo aporta su delta; las semillas emiten un `registro_avance` de línea base. Exceder `cant_programada` **rechaza** la captura en vez de recortarla — recortar rompería la identidad `Σ deltas = total` que el expediente técnico necesita auditar. |

## Estado actual (al cierre de la Fase 5)

| Capa | Entregado | Pendiente |
|---|---|---|
| `database/` | 20 migraciones · RLS por rol en toda tabla · semillas · generador de calendario · auth hook · agregación de `registro_avance` · lote de carga reversible · `periodo_bloqueado` · 4 archivos de pruebas de aislamiento | Sync rules de PowerSync en producción (Fase 6) |
| `backend/` | Dominio completo: `avance`, `cierres`, `estimacion`, `programacion/cpm`, `catalogos`, `materiales`, `incidencias`, `evaluaciones`, `revisiones`, `proyectos`, `obras`, `cargadores`, `expediente`, `reportes`, `shared` · Routers v1: los 58 endpoints del §11.2 salvo los de la Fase 6 · `adapters/excel` (cargadores del §10.6) y `adapters/export` (XLSX de estimación, PDF de expediente) · jobs Arq + Redis con worker propio · notificaciones Resend · 491 pruebas de dominio + integración contra Postgres real | `POST /reportes/{tipo}` genérico · procesos (§7.9) · tiempo real (`WS /ws`) · `Idempotency-Key` (Fase 6) |
| `frontend/` | Shell 3 columnas · navegación por rol · tokens/densidad · Login · cliente Supabase + HTTP · features `proyectos`, `catalogos`, `programacion`, `avance`, `cierres`, `estimacion`, `materiales`, `incidencias`, `evaluaciones` · 221 pruebas | Features: cargas (bandeja de pendientes), expediente, reportes, revisión física |
| `mobile/` | `lib/` (auth, sesión, jwt, dispositivo, reglas de avance, tabs) · `sync/` (PowerSync + SQLite) · rutas por rol · sync-rules · config Play | Cola de evidencias a R2 · revisión física en campo · build de Play Store (Fase 6) |

> La Fase 5 cerró el backend de cargas, expediente y reportes. Lo que queda de
> esas tres verticales es **web**: la bandeja de pendientes del §10.3, el
> expediente por obra y la descarga de reportes consumen endpoints que ya
> existen y están en el contrato (`openapi/openapi.json`, 58 rutas).

---

## Fase 1 — Proyectos · Clusters · Obras  ·  Móvil: login + captura offline

**Objetivo:** el árbol Proyecto → Cluster → Obra existe end-to-end y el residente captura avance desde campo sin red.

**Trazabilidad:** §4 (roles/alcance) · §11.2 (Proyecto · Obra) · §12.4 (RLS) · Workflow A y B.

| Agente | Entregable | DoD |
|---|---|---|
| **01 Arquitecto** | Contrato OpenAPI de `/proyectos`, `/clusters`, `/prototipos`, `/obras`, `/frentes`, `/obras/{id}/generar`, `/obras/bulk`. Puertos en `application/puertos/repositorios.py`. | Contrato revisado antes de codear; DTOs en el borde. |
| **03 Datos/CPM** | Repos `proyectos_sql.py`, `clusters_sql.py`, `prototipos_sql.py`, `frentes_sql.py`; extender `obras_sql.py`. Verificar RLS de las tablas del §4. | Prueba de aislamiento por rol para cada repo nuevo. |
| **02 Backend** | `domain/proyectos/`, `domain/obras/` (hoy vacíos) con entidades + invariantes. Caso de uso `generar_obra_desde_prototipo` (Workflow A). Routers `v1/proyectos.py`, `v1/obras.py`. | Cero lógica en el controlador; `lint-imports` verde. |
| **04 Web** | Feature `frontend/src/proyectos/`: árbol Proyecto→Cluster→Obra, alta/edición por rol, alta masiva. Hooks Orval regenerados. | Sin lógica de negocio en componentes; tokens del design system. |
| **05 Mobile** | Pantalla de login real (`lib/auth.ts` ya existe) + tabs por rol + captura offline de avance contra PowerSync, con `reglasAvance.ts` como reflejo del §6. | Funciona en avión; la cola sincroniza al recuperar red. |
| **07 QA** | Pytest de dominio + integración de los endpoints nuevos; Vitest de la feature web; prueba de sync offline. | Verde en CI. |

**Criterio de cierre de fase:** un Control de obra crea un proyecto, cluster y obra; genera actividades desde prototipo; un Residente captura avance offline en el móvil y sincroniza.

---

## Fase 2 — Catálogos · APU/CPU

**Trazabilidad:** §10 (catálogos y cargadores), §10.6 (cabeceras reales), §11.2 (Catálogos · APU).

- Repos y RLS de `unidades`, `familias`, `insumos`, `conceptos`, `materiales`, `contratistas`.
- Dominio `catalogos/` con `PrecioUnitario` (CPU con desglose de destajo) y explosión de insumos.
- Routers de catálogo + `GET /conceptos/{id}/cpu` y `/explosion`; versionado de CPU.
- **Ruta directa a Supabase** para lectura de catálogos en el front (§10.7) — la escritura siempre por API.
- `adapters/excel/`: primeros cargadores con las cabeceras del §10.6.
- Web: tablas de catálogo con filtros y editor de APU.

---

## Fase 3 — Programación · CPM

**Trazabilidad:** §11.2 (Programación · CPM), `domain/programacion/cpm.py` ya existe.

- Programas base, instanciación y versionado por obra.
- Endpoints `GET /obras/{id}/programa`, `POST` instanciar, `GET /ruta-critica`, `POST /recalcular`, `PATCH /actividades/{id}/programacion`.
- Job Arq + Redis para recálculo asíncrono; evento `ActividadCerrada` → recalcular CPM.
- Web: Gantt con ruta crítica resaltada y edición de dependencias.

---

## Fase 4 — Materiales · Incidencias · Evaluación (completar)

Los casos de uso existen; falta cerrar el vertical.

- Materiales: consumo vs presupuesto, salidas de almacén, web + reporte.
- Incidencias: Workflow F completo, evento `IncidenciaCreada(impacto=detiene)` → actividades bloqueadas + recálculo de ruta.
- Evaluación: Workflow H (auto R · control C · final SI), criterios y respuestas, UI web.
- Revisión física en móvil (Control de obra): fotos + comentario + calidad, evidencias a R2 vía presigned URL.

---

## Fase 5 — Cargas · Expediente · Reportes

- Cargadores Excel del §10 con validación y reporte de errores por fila.
- Expediente técnico por obra: agregación de evidencias, cierres y estimaciones.
- `adapters/export/`: export de estimación a XLSX (job), PDF de expediente.
- Notificaciones (Resend) en `EstimacionValidada`.

---

## Fase 6 — Endurecimiento y despliegue

- Sync rules de PowerSync en producción, espejeando RLS (§12.4).
- Observabilidad, `Idempotency-Key` en mutaciones sensibles, `problem+json` uniforme.
- E2E Playwright de los seis workflows; build de Play Store y Vercel/Render.

> **En curso.** El desglose real —seis frentes, qué se entregó en cada uno y
> qué falta— vive en [`FASE-6.md`](FASE-6.md). Resumen: `problem+json`,
> observabilidad, sync rules auditadas, CI e idempotencia están hechos; queda
> cablear `Idempotency-Key` en las pantallas y escribir los seis E2E de
> workflow (hoy marcados `fixme`, con el arnés listo).

---

## Invariantes que ninguna fase rompe

1. La dependencia apunta **hacia adentro**; `domain/` no conoce FastAPI, SQLModel, RLS ni React (§12.11).
2. Las reglas del §6 se definen **una vez** en el dominio; el front las refleja y la BD las repite como `CHECK`.
3. Las sync rules **espejean** RLS; si cambia el alcance de un rol, cambia en ambos lados.
4. Un módulo **nunca** lee tablas ni estado interno de otro: solo fachadas y eventos de dominio.
