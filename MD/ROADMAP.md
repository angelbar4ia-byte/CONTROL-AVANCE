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

## Estado actual (Fase 6 en curso)

| Capa | Entregado | Pendiente |
|---|---|---|
| `database/` | 22 migraciones · RLS por rol en toda tabla · semillas · generador de calendario · auth hook · agregación de `registro_avance` · lote de carga reversible · `periodo_bloqueado` · `idempotencia` · 5 archivos de pruebas de aislamiento | Publicar las sync rules auditadas en el PowerSync de producción |
| `backend/` | Dominio completo (15 contextos) · 59 rutas del §11.2 · `adapters/excel` y `adapters/export` · jobs Arq + Redis con worker propio · notificaciones Resend · `problem+json` uniforme · id de petición + Sentry + sonda de dependencias · `Idempotency-Key` en 10 mutaciones · **547 pruebas** | `POST /reportes/{tipo}` genérico · procesos (§7.9) · tiempo real (`WS /ws`) |
| `frontend/` | Shell 3 columnas · navegación por rol · tokens/densidad · Login · cliente Supabase + HTTP · features `proyectos`, `catalogos`, `programacion`, `avance`, `cierres`, `estimacion`, `materiales`, `incidencias`, `evaluaciones` · **221 pruebas** + 4 E2E de humo | Features: cargas, expediente, reportes, revisión física · cablear `Idempotency-Key` · los 6 E2E de workflow |
| `mobile/` | `lib/` (auth, sesión, jwt, dispositivo, reglas de avance, tabs) · `sync/` (PowerSync + SQLite) · rutas por rol · sync-rules auditadas · config Play | Pantallas de captura y revisión · cola de evidencias a R2 · build de Play Store |
| CI | `.github/workflows/ci.yml`: backend con Postgres real (integración + RLS), web, humo en navegador, tipos de móvil, contrato al día · dependencias fijas en `constraints.txt` | Confirmar en verde tras los arreglos de la primera corrida |

---

## Pendiente para la siguiente sesión

Ordenado por lo que desbloquea más con menos. Los tres primeros son la deuda de
la Fase 5 y la Fase 6; el resto ya es alcance nuevo.

### 1. Confirmar el CI en verde (minutos)

Ya corrió una vez y encontró dos cosas, las dos por diferencias entre una
máquina de desarrollo y un entorno limpio: el contrato no era reproducible
(`fastapi>=0.115` resolvía distinto en CI) y el humo de E2E no arrancaba sin el
`.env.local` no versionado. Ambas corregidas —`backend/constraints.txt` y
`--mode test`— y verificadas en local, la segunda reproduciendo las condiciones
de CI. **Falta ver la corrida en verde.**

Lo que sí funcionó a la primera: Postgres, migraciones, las ~150 pruebas de
integración y los 5 archivos de aislamiento RLS, que hasta entonces no corrían
en ninguna parte.

### 2. Las tres features web de la Fase 5

Consumen endpoints que **ya existen** y están en el contrato, con los hooks de
Orval generados. Es trabajo de UI, no de integración:

- **Cargas** — bandeja de pendientes del §10.3: subir archivo, ver el reporte de
  errores por fila (número, columna, valor, motivo), revertir el lote,
  descargar plantilla.
- **Expediente** — por obra: documentos, vista agregada y el PDF (§11.2).
- **Reportes** — encolar, consultar estado y descargar (§11.2 `GET /reportes/{id}`).

Con esto la Fase 5 cierra según D1, que pide el vertical hasta la UI.

### 3. Cablear `Idempotency-Key` en las pantallas

El backend está listo y protege 10 mutaciones. Falta que **cada pantalla fije
su clave**, una por operación: `claveDeIdempotencia()` al montar el formulario
y la misma en cada intento. Cuidado con el error fácil —generarla dentro de
`peticion` daría una cabecera nueva en cada intento y no desduplicaría nada—.
Hecho eso, se puede volver a encender `retry` en las mutaciones de
`queryClient.ts`, que hoy está en 0 justamente por esto.

### 4. Los seis E2E de workflow

Hoy marcados `test.fixme` en `frontend/e2e/workflows/`, con el arnés y el
`entrar()` ya resueltos. Necesitan un entorno con API + Postgres migrado y
sembrado + un usuario real del proveedor de auth (`E2E_API_URL`, `E2E_USUARIO`,
`E2E_PASSWORD`). Dos de los seis son móvil (§5.2) y van con Detox/Maestro, no
con Playwright.

### 5. Móvil

Pantallas reales de captura y revisión, y la cola de evidencias a R2. Es lo
único que queda sin empezar de una capa entera; el `lib/` y el `sync/` ya están.

### 6. Publicar las sync rules

La auditoría quedó escrita y el archivo corregido (`mobile/sync-rules.yaml`),
pero desplegarlo en el PowerSync de producción y verificar que el bucket del
residente sincroniza lo que debe es un paso que necesita el servicio arriba.

> **Dónde está el detalle.** El desglose de la Fase 6 —qué se entregó en cada
> frente, con su razón— vive en [`FASE-6.md`](FASE-6.md), incluidas las
> decisiones F6.1 a F6.11.

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

> **En curso.** Cuatro frentes cerrados (`problem+json`, observabilidad, sync
> rules auditadas, CI y despliegue) y dos a medias: `Idempotency-Key` con el
> backend hecho y sin cablear en las pantallas, y E2E con el humo corriendo y
> los seis workflows en `fixme`. El desglose con sus razones está en
> [`FASE-6.md`](FASE-6.md); lo que sigue, en
> [Pendiente para la siguiente sesión](#pendiente-para-la-siguiente-sesión).

---

## Invariantes que ninguna fase rompe

1. La dependencia apunta **hacia adentro**; `domain/` no conoce FastAPI, SQLModel, RLS ni React (§12.11).
2. Las reglas del §6 se definen **una vez** en el dominio; el front las refleja y la BD las repite como `CHECK`.
3. Las sync rules **espejean** RLS; si cambia el alcance de un rol, cambia en ambos lados.
4. Un módulo **nunca** lee tablas ni estado interno de otro: solo fachadas y eventos de dominio.
