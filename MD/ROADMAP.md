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

## Estado actual (Fase 6 en curso)

| Capa | Entregado | Pendiente |
|---|---|---|
| `database/` | 22 migraciones · RLS por rol en toda tabla · semillas · generador de calendario · auth hook · agregación de `registro_avance` · lote de carga reversible · `periodo_bloqueado` · `idempotencia` · 5 archivos de pruebas de aislamiento | Publicar las sync rules auditadas en el PowerSync de producción |
| `backend/` | Dominio completo (15 contextos) · 59 rutas del §11.2 · `adapters/excel` y `adapters/export` · jobs Arq + Redis con worker propio · notificaciones Resend · `problem+json` uniforme · id de petición + Sentry + sonda de dependencias · `Idempotency-Key` en 10 mutaciones · **547 pruebas** | `POST /reportes/{tipo}` genérico · procesos (§7.9) · tiempo real (`WS /ws`) |
| `frontend/` | Shell 3 columnas · navegación por rol · tokens/densidad · Login · cliente Supabase + HTTP · features `proyectos`, `catalogos`, `programacion`, `avance`, `cierres`, `estimacion`, `materiales`, `incidencias`, `evaluaciones` · **221 pruebas** + 4 E2E de humo | Features: cargas, expediente, reportes, revisión física · cablear `Idempotency-Key` · los 6 E2E de workflow |
| `mobile/` | `lib/` (auth, sesión, jwt, dispositivo, reglas de avance, tabs) · `sync/` (PowerSync + SQLite) · rutas por rol · sync-rules auditadas · config Play | Pantallas de captura y revisión · cola de evidencias a R2 · build de Play Store |
| CI | `.github/workflows/ci.yml`: backend con Postgres real (integración + RLS), web, humo en navegador, tipos de móvil, contrato al día · dependencias fijas en `constraints.txt` | Confirmar en verde tras los arreglos de la primera corrida |

---

## Lo inmediato

**Confirmar el CI en verde.** Ya corrió una vez y encontró dos cosas, las dos
por diferencias entre una máquina de desarrollo y un entorno limpio: el
contrato no era reproducible (`fastapi>=0.115` resolvía distinto en CI) y el
humo de E2E no arrancaba sin el `.env.local` no versionado. Ambas corregidas
—`backend/constraints.txt` y `--mode test`— y verificadas en local, la segunda
reproduciendo las condiciones de CI. Falta ver la corrida en verde.

Lo que sí funcionó a la primera: Postgres, migraciones, las ~150 pruebas de
integración y los 5 archivos de aislamiento RLS, que hasta entonces no corrían
en ninguna parte.

Después de eso, **Fase 7**. El detalle de la Fase 6 —qué se entregó en cada
frente y por qué— está en [`FASE-6.md`](FASE-6.md), decisiones F6.1 a F6.13.

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
| **03 Datos** | Repos `usuarios_sql` (extender: hoy solo tiene `correos_de`), `asignaciones_sql` para los puentes de alcance. | Prueba de aislamiento por rol; un Control de obra no asigna fuera de sus proyectos. |
| **02 Backend** | `GET/POST /usuarios`, `PATCH /usuarios/{id}`, `GET/POST /orgs`, y las rutas de asignación de alcance. Adaptador del proveedor de auth en `infrastructure/`. | Rol y alcance validados en el dominio, no solo en el router. |
| **04 Web** | Pantalla **Usuarios** (C) y **Asignaciones** (§5.1 "Equipo"): alta, edición, asignar clusters a un supervisor y proyectos a un control. | Sin lógica de negocio en componentes. |
| **07 QA** | Pruebas de dominio e integración; E2E del alta completa. | Verde en CI. |

**Criterio de cierre:** un Control de obra da de alta a un residente, le asigna
sus obras, el residente entra con su propia contraseña y captura avance — sin
que nadie toque SQL.

---

## Fase 8 — Cerrar la Fase 5 en web

**Por qué aquí.** Es deuda de D1: el vertical de cargas, expediente y reportes
llegó hasta la API y se detuvo. Los endpoints existen, están en el contrato y
los hooks de Orval ya están generados, así que es trabajo de UI y no de
integración. Para un piloto con datos reales, la bandeja de cargas es además lo
que permite subir los catálogos del cliente sin que un operador corra scripts.

- **Cargas** — bandeja de pendientes del §10.3: subir archivo, ver el reporte
  de errores **por fila** (número, columna, valor, motivo), revertir el lote
  como unidad, descargar plantilla.
- **Expediente** — por obra: documentos, la vista agregada y el PDF.
- **Reportes** — encolar, consultar estado y descargar el archivo.

Al cerrar cada pantalla se le cablea su `Idempotency-Key` y se le escribe su
E2E (reglas 1 y 2 de arriba), incluido el rezago de las pantallas que ya
existían.

**Criterio de cierre:** la Fase 5 queda cerrada según D1 —el vertical llega a
la UI— y un Control de obra carga su catálogo real desde Excel.

---

## Fase 9 — Torre de control

**Por qué aquí.** Es la pantalla donde **aterrizan tres de los cuatro roles**
(§5.1: Supervisor, Control de obra y Super intendente la tienen como primera
entrada). Hoy caen en Cierres como sustituto, con un comentario en `App.tsx`
que lo dice. Es la pantalla compartida por excelencia del §5.3: una sola
implementación que cambia por rol y alcance.

- Backend: `GET /obras/{id}/actividades` y `GET /actividades/{id}`, que hoy no
  existen y la Torre necesita.
- Web: Torre de control con el estado por obra —avance, ruta crítica,
  incidencias abiertas, cierres pendientes, semana activa— filtrada por el
  alcance del rol.
- Sin tiempo real todavía: primero con recarga de TanStack Query. El `WS /ws`
  del §11.2 entra en la Fase 14, cuando haya algo que valga la pena empujar.

**Criterio de cierre:** un supervisor abre la app y ve, en una pantalla, dónde
está cada obra suya y qué le toca hacer hoy.

---

## Fase 10 — Los huecos de una obra real

**Por qué aquí.** Son las cosas que aparecen en cuanto una obra de verdad se
mueve, y que hoy no tienen a dónde ir.

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

## Fase 11 — Cierre de obra · Workflow D

**Por qué aquí.** Es el **único de los seis workflows del §11.3 sin nada de
backend**, y es la culminación natural del piloto: se cierra la obra con la que
se empezó. El expediente técnico de la Fase 5 se construyó justamente para
sostenerlo (§11.3 D).

- Las tablas `cierre_obra` y `cierre_obra_participacion` **ya existen con RLS**
  desde la migración 0009; falta todo lo demás.
- `POST /obras/{id}/cierre-obra` (SI) y `POST /cierres-obra/{id}/participar`
  (todos los roles).
- Dominio: qué exige un cierre de obra —avance, cierres validados, expediente,
  evaluación— antes de dejar cerrar.
- Web: *Cierres de obra* (SI).

---

## Fase 12 — Presupuesto y rendimientos

Tablas con RLS (`presupuesto`, `partida_presupuesto`) y **ni un repositorio ni
un endpoint**. Es un área entera del §5.1 que aparece en el sidebar de Control
de obra y de Super intendente.

- Repos y endpoints de presupuesto por obra y por partida.
- Rendimientos: lo ejecutado contra lo presupuestado, por concepto y por
  cuadrilla.
- Web: *Presupuesto de obras* y *Rendimientos*, pantallas compartidas (§5.3).

---

## Fase 13 — Móvil

Una app entera sin pantallas: `lib/` (auth, sesión, jwt, dispositivo, reglas de
avance) y `sync/` (PowerSync + SQLite) están listos, y las sync rules quedaron
auditadas en la Fase 6.

- Captura offline del residente (§11.3 B) y revisión física de Control de obra.
- Cola de evidencias a R2 con presigned URL: las fotos no viajan por la API.
- Expo Push (§12.2), lo único de notificaciones que falta —Resend ya está—.
- E2E con Detox o Maestro; **no** con Playwright.
- Build y publicación (§12.13): `eas.json` ya tiene los tres perfiles.

> Si el piloto revela que el residente no tiene señal en campo, esta fase deja
> de ser la última (D7).

---

## Fase 14 — Lo que queda del spec

Lo que no bloquea el piloto pero cierra la superficie del §11.2:

- **Tiempo real** `WS /ws` (o SSE): Torre, bandejas y notificaciones en vivo.
- **Procesos** (§7.9, mejora continua): `GET/POST /procesos` — (SI).
- **Bitácora de eventos** (SI): la tabla existe con RLS y nadie la escribe.
- **`POST /reportes/{tipo}`** genérico: hoy los dos reportes se encolan desde
  su propia ruta; el spec pide además una genérica por alcance.
- Revisar la deuda de tipos: mypy tiene ~258 hallazgos, casi todos del patrón
  `list[dict]` sin parametrizar. Decidir si se adopta o se corrige, pero
  decidirlo.

---

## Invariantes que ninguna fase rompe

1. La dependencia apunta **hacia adentro**; `domain/` no conoce FastAPI, SQLModel, RLS ni React (§12.11).
2. Las reglas del §6 se definen **una vez** en el dominio; el front las refleja y la BD las repite como `CHECK`.
3. Las sync rules **espejean** RLS; si cambia el alcance de un rol, cambia en ambos lados.
4. Un módulo **nunca** lee tablas ni estado interno de otro: solo fachadas y eventos de dominio.
