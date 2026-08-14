# ObraCtrl — Equipo de agentes de desarrollo (`/agents`)

> ObraCtrl se construye en solitario: estos **agentes de IA especializados** (sub-agentes de Claude Code) son el equipo. Este archivo es el **contrato de coordinación**; cada agente tiene su propio archivo con alcance y reglas.

## Fuente de verdad
El documento `ObraCtrl-especificacion-tecnica.md`. **Ningún agente inventa reglas:** si falta una, se resuelve primero en el spec. Toda entrega se **traza a su sección**.

## Arquitectura (no negociable) — §12.11
- **Clean Architecture:** la dependencia apunta **hacia adentro**. El `domain/` (reglas deterministas: topes §6, avance %, CPM, valuación §10.5, folios §3.2, IVA §3.5) **no** conoce FastAPI, SQLModel, RLS ni React.
- **Screaming Architecture:** las carpetas **gritan el dominio** (`obras`, `avance`, `estimacion`, `materiales`, `incidencias`, `evaluaciones`, `catalogos`, `cargadores`, `reportes`), no la tecnología.
- **Anti-spaghetti:** comunicación entre módulos **solo por puertos/casos de uso**; **cero lógica de negocio** en controladores FastAPI o componentes React; **DTOs en el borde**.

Estructura de `services/api/`: `domain/ · application/ · adapters/{api,repos,excel,export} · infrastructure/`. Monorepo Turborepo con `apps/web`, `apps/mobile`, `services/api`, `packages/shared` (§12.6).

## Fronteras compartidas (lo que nadie rompe)
- **Contrato OpenAPI** → Orval genera los hooks de TanStack Query. El front programa **contra el contrato**, no contra la implementación.
- **Diccionario canónico** (§8): invariantes en código, **semilla editable** en BD (§8.7).
- **Capa de catálogos y cargadores** (§10), compartida con el producto de Auditoría; cabeceras reales en §10.6.
- **Fachadas modulares** + **RLS multi-tenant** (`org_id`, §12.4).

## Reglas de coordinación
1. **Contratos primero:** Arquitecto + Backend acuerdan OpenAPI y puertos antes de codear.
2. **Fronteras de módulo:** un módulo nunca lee las tablas ni el estado interno de otro.
3. **DTOs en el borde:** las entidades de dominio no cruzan crudas a la API ni a React.
4. **Inversión de dependencias:** los puertos se declaran en dominio/aplicación y se implementan en el borde.
5. **Revisión del Arquitecto** en cada entrega: regla de dependencia, screaming, sin lógica duplicada, contrato respetado.

## Roster
| # | Agente | Alcance | Archivo |
|---|---|---|---|
| 1 | Arquitecto / Orquestador | contratos, fronteras, diccionario, revisión | `01-arquitecto.md` |
| 2 | Backend | dominio + módulos FastAPI + RLS | `02-backend.md` |
| 3 | Datos / CPM | esquema, repos, CPM, cargadores, sync | `03-datos-cpm.md` |
| 4 | Web | React/Vite, shadcn, hooks Orval | `04-web.md` |
| 5 | Mobile / Sync | RN/Expo, offline PowerSync, captura | `05-mobile-sync.md` |
| 6 | Reportes / Docs | Excel + PDF | `06-reportes.md` |
| 7 | QA / Tests | Pytest, Vitest/Playwright | `07-qa.md` |

## Flujo de una funcionalidad
Arquitecto define contrato/puertos → **Datos** prepara esquema/migración/repos → **Backend** implementa dominio + casos de uso + endpoints → **Web/Mobile** consumen los hooks generados → **QA** prueba (dominio + integración + e2e) → **Arquitecto** revisa.

## Definition of Done (global)
Lista cuando: tiene **tests de dominio**, respeta el **contrato OpenAPI**, **no** tiene lógica en controladores/React, respeta **RLS** y el **diccionario canónico**, y está **trazada** a su sección del spec.
