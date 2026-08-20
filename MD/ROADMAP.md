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
| D7 | **Las Fases 7+ se ordenan por un piloto en obra real** | El orden lo decide qué **bloquea el uso**, no qué falta del spec. Consecuencias: la administración de usuarios sube al primer lugar —hoy no se puede dar de alta a nadie y el Login ya lo promete—; presupuesto, procesos y tiempo real bajan; y el móvil se va al final, lo que hace que el piloto sea **web-only**. Eso último solo se sostiene si el residente captura con señal: `PATCH /actividades/{id}/avance` y la feature `avance` de la web ya lo permiten. **Si el residente resulta no tener señal en campo, el móvil deja de ser opcional y salta al frente de la fila** — es el supuesto que hay que confirmar antes de empezar el piloto, no durante. |
| D8 | **Endurecer no compite con el piloto: es su precondición** | Un piloto mete datos reales de un cliente en producción, así que la Fase 8 (operación segura) va **antes** que cualquier feature nueva. Sin restauración probada, sin poder revertir una migración y sin rastro de quién cambió qué, el riesgo no es técnico sino del cliente. El detonante fue encontrar que **nada se ha desplegado nunca**: las seis fases viven en una rama sin fusionar a `main`, mientras el §12.12 manda trunk-based con `main` siempre desplegable. El endurecimiento que **sostiene** el sistema cuando crece —virtualización, datasets golden, deuda de tipos— es otra cosa y va en la Fase 14. |

## Estado actual (Fase 8 en curso)

| Capa | Entregado | Pendiente |
|---|---|---|
| `database/` | 22 migraciones **con su `down` y bitácora de versión aplicada** · RLS por rol en toda tabla · semillas · generador de calendario · auth hook · agregación de `registro_avance` · lote de carga reversible · `periodo_bloqueado` · `idempotencia` · 5 archivos de pruebas de aislamiento · restauración de respaldo probada en CI | Publicar las sync rules auditadas en el PowerSync de producción · sellar la base de producción |
| `backend/` | Dominio completo (15 contextos) · 59 rutas del §11.2 · `adapters/excel` y `adapters/export` · jobs Arq + Redis con worker propio · notificaciones Resend · `problem+json` uniforme · id de petición + Sentry + sonda de dependencias · `Idempotency-Key` en 10 mutaciones · **547 pruebas** | `POST /reportes/{tipo}` genérico · procesos (§7.9) · tiempo real (`WS /ws`) |
| `frontend/` | Shell 3 columnas · navegación por rol · tokens/densidad · Login · cliente Supabase + HTTP · features `proyectos`, `catalogos`, `programacion`, `avance`, `cierres`, `estimacion`, `materiales`, `incidencias`, `evaluaciones` · **221 pruebas** + 4 E2E de humo | Features: cargas, expediente, reportes, revisión física · cablear `Idempotency-Key` · los 6 E2E de workflow |
| `mobile/` | `lib/` (auth, sesión, jwt, dispositivo, reglas de avance, tabs) · `sync/` (PowerSync + SQLite) · rutas por rol · sync-rules auditadas · config Play | Pantallas de captura y revisión · cola de evidencias a R2 · build de Play Store |
| CI | `.github/workflows/ci.yml`: backend con Postgres real (integración + RLS), ida y vuelta de las 22 migraciones, restauración de respaldo, web, humo en navegador, tipos de móvil, contrato al día · dependencias fijas en `constraints.txt` | Confirmar en verde con el job de backend restaurado |

---

## Lo inmediato

**Fase 8 en curso.** El primer frente ya cerró: la rama se fusionó a `main` por
el PR #18, así que el trunk-based del §12.12 dejó de ser una intención. El
segundo frente —migraciones reversibles y respaldo probado— está hecho y
probado; falta sellar la base de producción la primera vez que se despliegue
(`./scripts/migrar.sh --sellar`) y siguen abiertos los frentes 4 a 6.

**Y un hallazgo que hay que decir sin adornos: el CI llevaba dos commits sin
probar nada del backend.** El commit `4543909`, al sacar el paso del contrato a
un script, se llevó por delante ocho pasos del job `backend`: instalar
dependencias, aplicar migraciones, dar contraseña a `obractrl_api`, ruff,
`lint-imports`, `pytest` y el aislamiento RLS. El job quedó con un solo paso
—y sin el `pip install` que necesita—. Está restaurado, con los pasos nuevos de
la Fase 8 encima.

La lección no es el descuido: es que **un CI verde no dice qué corrió**. Un job
al que se le borran los pasos no se pone rojo, se pone verde más rápido. Vale
la pena mirar la duración de la corrida además del color.

Después de la Fase 8, **Fase 7**. El detalle de la Fase 6 —qué se entregó en
cada frente y por qué— está en [`FASE-6.md`](FASE-6.md), decisiones F6.1 a
F6.13.

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
> [`FASE-6.md`](FASE-6.md); lo que sigue, en [Lo inmediato](#lo-inmediato).
>
> Lo que **no** cubrió esta fase y sí pide el §12.12 —trunk-based, migraciones
> reversibles, respaldo probado, bitácora de negocio— va en la Fase 8, que por
> eso sube antes de cualquier feature nueva (D8).

---

## Reglas que aplican a toda fase de aquí en adelante

Absorben la deuda que dejó la Fase 6 sin convertirla en una fase aparte,
porque no es trabajo suelto: es algo que cada pantalla nueva trae consigo.

1. **Cada pantalla que dispare una mutación sensible fija su
   `Idempotency-Key`.** El backend ya protege 10 mutaciones; la clave la crea
   quien llama, **una por operación** (`claveDeIdempotencia()` al montar el
   formulario, la misma en cada intento). Generarla dentro de `peticion` no
   desduplica nada. Cuando todas las pantallas la manden, se vuelve a encender
   `retry` en `queryClient.ts`.
2. **Cada workflow que llegue a la UI se lleva su spec de E2E.** Los seis del
   §11.3 están hoy en `frontend/e2e/workflows/` como `test.fixme`, con el arnés
   resuelto. El de C (cierres) ya se puede escribir: su UI existe.
3. **Toda tabla nueva entra con RLS + prueba de aislamiento** (D4), y todo
   cambio de contrato se commitea con `openapi.json` y el cliente de Orval
   regenerados — CI lo verifica.
4. **Toda vista que pueda pasar de unos cientos de renglones nace
   virtualizada** (§12.9). Hoy solo el Gantt lo está.
5. **Todo cambio de configuración o de catálogo deja rastro en `bitacora`**
   (§11.7, §12.12): quién, cuándo y qué. Es la bitácora *de negocio*, distinta
   del log técnico.

---

## Fase 7 — Onboarding: usuarios, alcance y organización

**Por qué va primero.** Hoy no se puede dar de alta a nadie. La pantalla de
Login le promete al usuario que "el alta de usuarios la realiza Control de
obra" (§5.1) y esa pantalla no existe: los usuarios del piloto habría que
insertarlos a mano en SQL, junto con sus puentes de alcance
(`supervisor_cluster`, `control_proyecto`). Sin esto no hay piloto que empiece.

**Lo que ya está.** La base está lista y es más de lo que parece: `usuario`
tiene su política de escritura para Control de obra (`es_config()`), los
puentes de alcance existen con RLS, y el auth hook (migración 0015) ya copia
`org_id`, `rol` y `usuario_id` al nivel raíz del JWT.

**La decisión que hay que tomar antes de codear.** Crear una fila en `usuario`
**no** crea una cuenta en el proveedor de auth: la persona no puede entrar
hasta que exista un `auth.users` ligado por `usuario.auth_user_id`. Tres
caminos, y no son equivalentes:

| Camino | A favor | En contra |
|---|---|---|
| **Invitación por correo** (Supabase Admin API) | El usuario fija su propia contraseña; es lo que corresponde al §12.4 | Mete la *service key* en el backend —nunca en el cliente (§10.7)— y una plantilla de correo más (Resend ya está) |
| **Alta con contraseña temporal** | El más simple de construir | Peor higiene: alguien más conoce la contraseña inicial |
| **Vinculación al primer acceso** | Cero superficie nueva | Deja una ventana con una cuenta sin org ni rol, que es justo lo que el §12.4 no quiere |

La invitación es la recomendada; conviene decidirlo en la primera media hora
de la fase y no a medio camino.

| Agente | Entregable | DoD |
|---|---|---|
| **01 Arquitecto** | Contrato de `/usuarios` y `/orgs` (§11.2) y el puerto de invitación —el proveedor de auth entra como puerto, no como llamada suelta desde un caso de uso—. | Camino de alta decidido y escrito antes de codear. |
| **03 Datos** | Extender `usuarios_sql` (hoy solo tiene `correos_de`) y crear `asignaciones_sql` para los puentes de alcance. | Prueba de aislamiento por rol; un Control de obra no asigna fuera de sus proyectos. |
| **02 Backend** | `GET/POST /usuarios`, `PATCH /usuarios/{id}`, `GET/POST /orgs` y las rutas de asignación de alcance. Adaptador del proveedor de auth en `infrastructure/`. | Rol y alcance validados en el dominio, no solo en el router. |
| **04 Web** | Pantallas **Usuarios** (C) y **Asignaciones** (§5.1 "Equipo"): alta, edición, asignar clusters a un supervisor y proyectos a un control. | Sin lógica de negocio en componentes. |
| **07 QA** | Pruebas de dominio e integración; E2E del alta completa. | Verde en CI. |

**Criterio de cierre:** un Control de obra da de alta a un residente, le asigna
sus obras, el residente entra con su propia contraseña y captura avance — sin
que nadie toque SQL.

---

## Fase 8 — Operación segura · el endurecimiento que habilita el piloto

**Por qué sube hasta aquí.** Un piloto mete **datos reales de un cliente** en
producción. Hacer eso sin camino de restauración probado, sin poder revertir
una migración y sin rastro de quién cambió qué no es un riesgo técnico: es un
riesgo para el cliente. Endurecer no compite con el piloto — es su
precondición.

El hallazgo que lo volvió urgente —que **nada se había desplegado nunca**, con
las seis fases en una rama sin fusionar— ya está resuelto: el PR #18 llevó las
seis a `main`, que es de donde despliega `render.yaml` con `autoDeploy: true`.

**Frentes.**

1. ✅ **Trunk-based de verdad (§12.12).** La rama se fusionó a `main` por PR.
   Falta la parte que se sostiene con disciplina y no con un merge: ramas
   cortas, `main` siempre desplegable, tags `vX.Y.Z` y changelog.
2. ✅ **Migraciones reversibles y respaldo probado (§12.12).** Se descartó
   Alembic —estaba declarado en `pyproject.toml` sin que nadie lo usara, y salió
   de ahí— y se formalizó el esquema que ya existía: `app.schema_migrations` con
   el `sha256` de cada archivo, cada `up` en la misma transacción que su
   renglón, `migrations/down/` completo para las 22, y `revertir.sh` /
   `probar_respaldo.sh`. El CI aplica, revierte las 22, vuelve a aplicar,
   respalda, restaura en una base vacía y compara 1 763 objetos de esquema.

   > Un `down` que nunca corrió no es un `down`, es un archivo. Y hay tres que
   > no son simétricos —el valor de enum de la 0019, la reconciliación de la
   > 0017, el vínculo con el prototipo de la 0018—: cada uno lo dice en su
   > encabezado, porque descubrirlo durante un rollback sería tarde.

   Queda un paso operativo: **sellar producción** (`migrar.sh --sellar`) la
   primera vez que se despliegue, o el runner intentaría reaplicar las 22.
3. ✅ **Expand → contract.** Escrita en `database/README.md` como una de las
   tres reglas del versionado: primero agregar (nullable + backfill), desplegar
   código que tolera ambos esquemas, contraer en un release posterior. Así el
   rollback del código no arrastra a la base.
4. **Bitácora de negocio (§11.7, §12.12).** La tabla `bitacora` existe con RLS
   y **nadie la escribe**. Los cambios de configuración y de catálogo —umbral
   §3.6, IVA, mapeos, motivos— tienen que dejar quién/cuándo/qué, y los
   sensibles versionarse para no alterar resultados pasados.
5. **`/health` completo (§11.7).** Hoy cubre BD y cola; el spec pide además
   disco, jobs y **último respaldo**.
6. **Staging.** El §12.12 pide promoción `main` → staging → prod con
   aprobación. Hoy `render.yaml` define un solo entorno.

**Criterio de cierre:** se puede desplegar a producción, revertir el deploy,
revertir una migración y restaurar un respaldo — y las tres cosas se probaron,
no se supusieron. Las dos últimas ya se prueban en cada corrida de CI; falta
ejercitar el rollback de un deploy real.

---

## Fase 9 — Cerrar la Fase 5 en web

Deuda de D1: el vertical de cargas, expediente y reportes llegó hasta la API y
se detuvo. Los endpoints existen, están en el contrato y los hooks de Orval ya
están generados, así que es trabajo de UI y no de integración. Para un piloto
con datos reales, la bandeja de cargas es además lo que permite subir los
catálogos del cliente sin que un operador corra scripts.

- **Cargas** — bandeja de pendientes del §10.3: subir archivo, ver el reporte
  de errores **por fila** (número, columna, valor, motivo), revertir el lote
  como unidad, descargar plantilla.
- **Expediente** — por obra: documentos, la vista agregada y el PDF.
- **Reportes** — encolar, consultar estado y descargar el archivo.

Al cerrar cada pantalla se le cablea su `Idempotency-Key` y se le escribe su
E2E (reglas 1 y 2), incluido el rezago de las pantallas que ya existían.

**Criterio de cierre:** la Fase 5 queda cerrada según D1 y un Control de obra
carga su catálogo real desde Excel.

---

## Fase 10 — Torre de control

Es la pantalla donde **aterrizan tres de los cuatro roles** (§5.1: Supervisor,
Control de obra y Super intendente la tienen como primera entrada). Hoy caen en
Cierres como sustituto, con un comentario en `App.tsx` que lo dice. Es la
pantalla compartida por excelencia del §5.3: una sola implementación que cambia
por rol y alcance.

- Backend: `GET /obras/{id}/actividades` y `GET /actividades/{id}`, que hoy no
  existen y la Torre necesita.
- Web: estado por obra —avance, ruta crítica, incidencias abiertas, cierres
  pendientes, semana activa— filtrado por el alcance del rol. Virtualizada
  desde el día uno (regla 4).
- Sin tiempo real todavía: primero con recarga de TanStack Query. El `WS /ws`
  entra en la Fase 16, cuando haya algo que valga la pena empujar.

**Criterio de cierre:** un supervisor abre la app y ve, en una pantalla, dónde
está cada obra suya y qué le toca hacer hoy.

---

## Fase 11 — Los huecos de una obra real

Lo que aparece en cuanto una obra de verdad se mueve, y que hoy no tiene a
dónde ir.

- `POST /actividades` — **alta extra-catálogo con OC** (§11.2, rol R). En una
  obra real siempre hay trabajo que no estaba en el prototipo; hoy no hay forma
  de registrarlo. Web: pantalla *Extra-catálogo* del §5.1.
- **Revisión física en web** (C): el endpoint existe desde la Fase 4 y ninguna
  pantalla lo usa. Mientras el móvil no esté, es la única manera de registrar
  fotos, comentario y calidad.
- Revisar si `POST /actividades/{id}/registros` (§11.2) sigue teniendo sentido
  o si D5 lo dejó sin objeto: el móvil escribe `registro_avance` directo por
  PowerSync y la web aporta su delta por `PATCH .../avance`. **Puede que la
  conclusión sea borrarlo del contrato**, y eso también es una entrega.

---

## Fase 12 — Cierre de obra · Workflow D

Es el **único de los seis workflows del §11.3 sin nada de backend**, y la
culminación natural del piloto: se cierra la obra con la que se empezó. El
expediente técnico de la Fase 5 se construyó justamente para sostenerlo
(§11.3 D).

- Las tablas `cierre_obra` y `cierre_obra_participacion` **ya existen con RLS**
  desde la migración 0009; falta todo lo demás.
- `POST /obras/{id}/cierre-obra` (SI) y `POST /cierres-obra/{id}/participar`
  (todos los roles).
- Dominio: qué exige un cierre de obra —avance, cierres validados, expediente,
  evaluación— antes de dejar cerrar.
- Web: *Cierres de obra* (SI).

---

## Fase 13 — Presupuesto y rendimientos

Tablas con RLS (`presupuesto`, `partida_presupuesto`) y **ni un repositorio ni
un endpoint**. Es un área entera del §5.1 que aparece en el sidebar de Control
de obra y de Super intendente.

- Repos y endpoints de presupuesto por obra y por partida.
- Rendimientos: lo ejecutado contra lo presupuestado, por concepto y por
  cuadrilla.
- Web: *Presupuesto de obras* y *Rendimientos*, pantallas compartidas (§5.3),
  virtualizadas (regla 4).

---

## Fase 14 — Rendimiento y calidad

El segundo bloque de endurecimiento: no habilita el piloto, lo sostiene cuando
crece.

- **Virtualización (§12.9).** Hoy solo el Gantt usa `@tanstack/react-virtual`.
  El spec nombra catálogo de conceptos/CPU, histórico, presupuesto y ruta
  crítica como vistas de miles de renglones. Canvas si la densidad del Gantt
  crece.
- **Datasets golden (§11.7).** Congelar resultados esperados de CPM, explosión
  de insumos y valuación de materiales, para que una regresión se vea como un
  diff y no como un número raro en pantalla.
- **Idempotencia de reprocesos (§11.7).** Probar que correr una carga 2× da el
  mismo resultado, en modo Actualizar.
- **Reprocesos acotados (§11.7).** Tope de iteraciones, detector "sin progreso"
  y backoff, para que un job no entre en bucle.
- **Los seis E2E de workflow**, si la regla 2 no los fue absorbiendo antes.
- **Deuda de tipos.** mypy tiene ~258 hallazgos, casi todos del patrón
  `list[dict]` sin parametrizar. Decidir si se adopta como convención o se
  corrige — pero decidirlo, no dejarlo flotando.

---

## Fase 15 — Móvil

Una app entera sin pantallas: `lib/` (auth, sesión, jwt, dispositivo, reglas de
avance) y `sync/` (PowerSync + SQLite) están listos, y las sync rules quedaron
auditadas en la Fase 6.

- Captura offline del residente (§11.3 B) y revisión física de Control de obra.
- Cola de evidencias a R2 con presigned URL: las fotos no viajan por la API.
- Expo Push (§12.2), lo único de notificaciones que falta —Resend ya está—.
- **Actualización (§12.12):** canal OTA de EAS vs build nativo, header de
  versión del cliente, y pantalla de force/soft update. El esquema local de
  PowerSync debe migrar sin romper la cola de cambios sin sincronizar.
- E2E con Detox o Maestro; **no** con Playwright.
- Build y publicación (§12.13): `eas.json` ya tiene los tres perfiles.

> Si el piloto revela que el residente no tiene señal en campo, esta fase deja
> de ser la penúltima (D7).

---

## Fase 16 — Lo que queda del spec

Lo que no bloquea el piloto pero cierra la superficie del §11.2:

- **Tiempo real** `WS /ws` (o SSE): Torre, bandejas y notificaciones en vivo.
- **Procesos** (§7.9, mejora continua): `GET/POST /procesos` — (SI).
- **`POST /reportes/{tipo}`** genérico: hoy los dos reportes se encolan desde
  su propia ruta; el spec pide además una genérica por alcance.
- **Contrato aditivo con ventana de deprecación (§12.12)**, ahora que hay un
  cliente móvil viejo al que no romper.

---

## Definición de cerrado (v1)

"Cerrar" no es agotar el spec: es llegar a un sistema que una organización real
pueda usar y que se pueda operar sin heroísmos. v1 está cerrado cuando:

**Funciona de punta a punta**
- [ ] Los **seis workflows del §11.3** corren completos, con su E2E verde.
- [ ] Los **cuatro roles** del §4 tienen su sidebar del §5.1 sin huecos.
- [ ] Un cliente se da de alta, carga sus catálogos, corre un mes de obra y
      cierra una obra — sin que nadie toque SQL.

**Se puede operar**
- [ ] `main` desplegable, promoción a staging y prod, rollback probado.
- [ ] Migración `down` probada y **restauración de respaldo probada**.
- [ ] `/health` completo y Sentry recibiendo de API y worker.
- [ ] Bitácora de negocio separada del log técnico.

**Aguanta la escala del §12.1**
- [ ] 3–10 organizaciones, 60–80 obras activas, 20–30 usuarios concurrentes.
- [ ] Vistas de miles de renglones virtualizadas.
- [ ] RLS verificado por prueba en toda tabla (ya se cumple; mantenerlo).

**Se puede cambiar sin romper**
- [ ] Contrato aditivo con ventana de deprecación.
- [ ] Móvil con force/soft update y esquema PowerSync migrable.
- [ ] Datasets golden congelando los cálculos que importan.

Lo que queda **fuera de v1** y se anota para no confundirlo con deuda: SSO
(§12.1 "activable a futuro"), microservicios (§12.1 "futuro"), App Store —el
§12.13 solo cubre Google Play— y cualquier segundo idioma.

---

## Invariantes que ninguna fase rompe

1. La dependencia apunta **hacia adentro**; `domain/` no conoce FastAPI, SQLModel, RLS ni React (§12.11).
2. Las reglas del §6 se definen **una vez** en el dominio; el front las refleja y la BD las repite como `CHECK`.
3. Las sync rules **espejean** RLS; si cambia el alcance de un rol, cambia en ambos lados.
4. Un módulo **nunca** lee tablas ni estado interno de otro: solo fachadas y eventos de dominio.
