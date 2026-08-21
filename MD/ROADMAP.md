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

## Estado actual (Fases 7 a 16 cerradas)

| Capa | Entregado | Pendiente |
|---|---|---|
| `database/` | 28 migraciones **con su `down` y bitácora de versión aplicada** · RLS por rol en toda tabla · semillas · generador de calendario · auth hook · agregación de `registro_avance` · lote de carga reversible · `periodo_bloqueado` · `idempotencia` · **bitácora de negocio por trigger** · registro de respaldos · guardia de privilegios de `usuario` · orden de cambio del extra-catálogo · **dispositivos de push con su puerta `security definer`** · 7 archivos de pruebas de aislamiento · restauración de respaldo probada en CI | Publicar las sync rules auditadas en el PowerSync de producción · sellar la base de producción |
| `backend/` | Dominio completo (15 contextos) · 62 rutas del §11.2 · `adapters/excel` y `adapters/export` · jobs Arq + Redis con worker propio · notificaciones Resend · `problem+json` uniforme · id de petición + Sentry + sonda de dependencias · `Idempotency-Key` en 19 mutaciones · `/health` completo (base, cola, jobs, disco, respaldo) · `/usuarios` y alcance con proveedor de auth como puerto · `/torre` y actividades por obra · `POST /actividades` extra-catálogo · **cierre de obra (workflow D)** · presupuesto y rendimientos · **versión mínima del cliente (426) y Expo Push** · **procesos (§7.9), bitácora, `POST /reportes/{tipo}` por alcance y tiempo real por SSE** · **730 pruebas sin Postgres** (`pytest` en local) más las 246 de integración que corren en CI · 6 datasets golden | Nada del §11.2: la superficie de la API queda cubierta |
| `frontend/` | Shell 3 columnas · navegación por rol · tokens/densidad · Login · cliente Supabase + HTTP · features `proyectos`, `catalogos`, `programacion`, `avance`, `cierres`, `estimacion`, `materiales`, `incidencias`, `evaluaciones` · `equipo`, `cargas`, `expediente`, `reportes`, `torre` (virtualizada), `extras`, `revisiones`, `cierresObra`, `presupuesto` · virtualización compartida (`lib/tablaVirtual`) · `Idempotency-Key` cableada en las 12 mutaciones protegidas · **`bitacora`, `procesos` y `avance-total`: las tres entradas de sidebar que faltaban** · avisos en vivo por SSE con indicador propio · **365 pruebas** + 4 E2E de humo + 3 del alta | Los 6 E2E de workflow |
| `mobile/` | **Las 14 pantallas del §5.2, ninguna placeholder** · captura offline con las reglas del §6 · **cola de evidencias a R2** y **bandeja de salida a la API** · force/soft update y cabeceras de versión · registro de Expo Push · `sync/` (PowerSync + SQLite) con dos tablas local-only · sync-rules auditadas · **38 pruebas** + 3 flujos de Maestro | Assets de tienda · `projectId` real de EAS · correr Maestro contra un emulador · publicar en Play Console |
| CI | `.github/workflows/ci.yml`: backend con Postgres real (integración + RLS), mypy informativo, ida y vuelta de las 27 migraciones, restauración de respaldo, web, humo en navegador, **tipos y pruebas de móvil**, contrato al día **y compatible hacia atrás (§12.12)** · dependencias fijas en `constraints.txt` | Blueprint de staging aplicado en Render · E2E de móvil (necesitan emulador y API sembrada) |

---

## Lo inmediato

**Fases 7 a 16 cerradas.** El sistema se puede operar —desplegar, promover,
revertir, restaurar, con rastro de quién cambió qué—, ya se puede dar de alta a
alguien sin abrir `psql`, un Control de obra puede subir su catálogo real desde
Excel, el residente puede capturar en campo sin señal desde un teléfono, y
**la superficie del §11.2 quedó cubierta**: no hay endpoint del spec sin
implementar ni entrada de sidebar que caiga en "en construcción".

Lo que queda ya no es código: es poner el sistema enfrente de una obra real.
Ninguno de estos cabos bloquea eso, y casi todos son de operación:

1. **Sellar la base de producción** la primera vez que se despliegue este
   runner: `./database/scripts/migrar.sh --sellar`.
2. **Crear los servicios de staging en Render** desde el blueprint, con su
   proyecto de Supabase y su bucket de R2 propios.
3. **`SUPABASE_SERVICE_KEY` en el backend.** Sin ella el alta de usuarios
   responde 503 y el resto del sistema funciona igual — pero el piloto empieza
   por dar de alta gente, así que es de las primeras variables que hay que
   poner. Nunca llega al cliente (§10.7).
4. **Tags `vX.Y.Z` y changelog** (§12.12), y ejercitar una vez el rollback de un
   deploy real.
5. **Publicar la app.** El código está; falta la cuenta de Play, el
   `projectId` real de EAS y los assets de la ficha (§12.13). El detalle, en
   [`../mobile/README.md`](../mobile/README.md).

Lo que sigue **no es una fase, es el piloto**: meter datos de un cliente real
y ver qué se rompe. Los dos pendientes que sobreviven a v1 —los seis E2E de
workflow y la publicación en Play— necesitan las dos cosas que faltan del
mundo, no del repo: un staging sembrado y una cuenta de Google.

El detalle de la Fase 6 está en [`FASE-6.md`](FASE-6.md); el procedimiento de
operación, en [`OPERACION.md`](OPERACION.md).

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

> **Cerrada**, con `/orgs` fuera de alcance a propósito (ver abajo).

**Por qué fue primero.** No se podía dar de alta a nadie. La pantalla de
Login le promete al usuario que "el alta de usuarios la realiza Control de
obra" (§5.1) y esa pantalla no existe: los usuarios del piloto habría que
insertarlos a mano en SQL, junto con sus puentes de alcance
(`supervisor_cluster`, `control_proyecto`). Sin esto no hay piloto que empiece.

**Lo que ya está.** La base está lista y es más de lo que parece: `usuario`
tiene su política de escritura para Control de obra (`es_config()`), los
puentes de alcance existen con RLS, y el auth hook (migración 0015) ya copia
`org_id`, `rol` y `usuario_id` al nivel raíz del JWT.

**La decisión que se tomó: contraseña temporal.** Crear una fila en `usuario`
no crea una cuenta en el proveedor de auth, y de los tres caminos —invitación
por correo, contraseña temporal, vinculación al primer acceso— se eligió el
segundo. Conviene decirlo sin adorno: **también exige la service key en el
backend**, igual que la invitación; lo que cambia es quién elige la contraseña
inicial. A cambio no hace falta una plantilla de correo más ni depender de que
el correo llegue, que en obra no es un detalle menor.

La higiene que se pierde —alguien más conoce la contraseña inicial— se acota
donde se puede: `usuario.debe_cambiar_password` obliga a cambiarla, la pantalla
sugiere una legible de doce caracteres (se va a dictar por teléfono), y la
contraseña **nunca vuelve en una respuesta ni sale en un `repr()`**, que es
como acabaría en una traza de Sentry.

**Dos escaladas de privilegio que estaban abiertas.** Al ir a construir la
pantalla aparecieron dos huecos que llevaban ahí desde la migración 0012:

> `usuario_self_update` deja que cada quien edite su perfil, y **RLS filtra
> filas, no columnas**: la fila propia sigue siendo la fila propia después de
> `update usuario set rol = 'super_intendente' where id = <yo>`. Por la ruta
> directa a Supabase (§10.7) eso es una sentencia desde el navegador. Y la
> escritura de `usuario` es `app.es_config()`, que incluye a Control de obra
> —correcto— pero nada le impedía otorgar el rol de más privilegio.

Ninguno se arregla con una política: hacen falta reglas por columna y por
transición, y eso es el trigger de la migración 0025. Va en la base porque es la
única frontera que cubre también la ruta directa y el `UPDATE` a mano en el
dashboard.

| Agente | Entregable | DoD |
|---|---|---|
| **01 Arquitecto** | Contrato de `/usuarios` y `/orgs` (§11.2) y el puerto de invitación —el proveedor de auth entra como puerto, no como llamada suelta desde un caso de uso—. | Camino de alta decidido y escrito antes de codear. |
| **03 Datos** | Extender `usuarios_sql` (hoy solo tiene `correos_de`) y crear `asignaciones_sql` para los puentes de alcance. | Prueba de aislamiento por rol; un Control de obra no asigna fuera de sus proyectos. |
| **02 Backend** | `GET/POST /usuarios`, `PATCH /usuarios/{id}`, `GET/POST /orgs` y las rutas de asignación de alcance. Adaptador del proveedor de auth en `infrastructure/`. | Rol y alcance validados en el dominio, no solo en el router. |
| **04 Web** | Pantallas **Usuarios** (C) y **Asignaciones** (§5.1 "Equipo"): alta, edición, asignar clusters a un supervisor y proyectos a un control. | Sin lógica de negocio en componentes. |
| **07 QA** | Pruebas de dominio e integración; E2E del alta completa. | Verde en CI. |

**Lo que quedó fuera y no es deuda escondida: `GET/POST /orgs`.** Crear una
organización es dar de alta a un *cliente*, no a un usuario, y el piloto empieza
con la organización ya creada. Construir la pantalla ahora sería adivinar un
flujo de alta de tenant —facturación, quién crea al primer Super intendente, qué
semilla se le carga— que nadie ha pedido todavía. Se anota aquí para que su
ausencia sea una decisión y no un olvido; entra cuando haya un segundo cliente.

**Criterio de cierre:** un Control de obra da de alta a un residente, le asigna
sus obras, el residente entra con su propia contraseña y captura avance — sin
que nadie toque SQL. **Cerrado**, con una salvedad: el último tramo —que el
residente *entre*— se prueba en integración con un doble del proveedor y no
contra un Supabase real, porque una prueba que crea cuentas de verdad deja
basura en un proyecto compartido. Falta ejercitarlo una vez a mano contra
staging, con `SUPABASE_SERVICE_KEY` puesta.

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
4. ✅ **Bitácora de negocio (§11.7, §12.12).** La tabla `bitacora` existía con
   RLS y nadie la escribía. Ahora la escribe la base: un trigger
   (`app.bitacora_registrar`, migración 0023) sobre las 17 tablas que **alteran
   resultados** —configuración, unidades, precios, recetas, catálogos maestros—
   guarda quién, cuándo y el diff de lo que cambió.

   La alternativa era que cada caso de uso escribiera su renglón. No se
   descartó por el trabajo, sino porque **la auditoría que se puede olvidar no
   es auditoría**: un caso de uso nuevo que no llame al registro no rompe
   ninguna prueba. El trigger cubre además la ruta directa a Supabase (§10.7) y
   el `UPDATE` que alguien corra a mano en el dashboard, que son los cambios que
   más falta hace poder rastrear.

   > Y es append-only por construcción: `bitacora` **no tiene política de
   > `INSERT`, `UPDATE` ni `DELETE`** para nadie. La escribe una función
   > `SECURITY DEFINER`. Una bitácora que su propio sujeto puede escribir no
   > prueba nada. Está probado en `database/tests/test_bitacora.sql`.

   Encontró un bug de paso: el `on delete cascade` de `organizacion` borra la
   fila padre **antes** que los hijos, así que el trigger intentaba escribir con
   un `org_id` que ya no existía y **dar de baja una organización era
   imposible**. Ya tiene su guarda y su caso de prueba.

5. ✅ **`/health` completo (§11.7).** Cubría base y cola; ahora también
   **jobs**, **disco** y **último respaldo**. `jobs` es el que separa "Redis
   responde" de "hay quien atienda la cola": `SIN WORKER` con trabajos
   encolados es un worker caído, no una cola ocupada — y ese fallo no produce
   ningún error visible en la API.

   El último respaldo la sonda no lo puede adivinar: lo escriben
   `respaldar.sh` y `probar_respaldo.sh` en `app.respaldo` (migración 0024), y
   se reportan las **dos** fechas por separado. Un respaldo de anoche con una
   restauración probada de hace seis meses es la situación que hay que ver
   antes del incidente, no durante.

   `disco` y `ultimo_respaldo` **no** degradan `estatus`: hay que atenderlos,
   pero no son "la API no puede trabajar", y una sonda que grita por todo deja
   de leerse.

6. ✅ **Staging (§12.12).** `render.yaml` define ahora dos entornos: cada push
   a `main` despliega **staging**, y producción tiene `autoDeploy: false` — se
   promueve a mano eligiendo el commit que ya corrió en staging. Ese clic es la
   aprobación.

   **Sin rama `staging`**: una segunda rama de larga vida es lo contrario del
   trunk-based, porque invita a que los dos entornos diverjan y entonces lo que
   se probó ya no es lo que se promueve. Cada entorno lleva su Redis, su
   proyecto de Supabase y su bucket de R2 — un staging apuntando a la base de
   prod es prod con otro nombre y sin cuidado. Staging va sin llaves de Resend a
   propósito: un correo de staging llega a una persona real.

   El procedimiento completo —desplegar, promover, revertir, respaldar,
   restaurar, y qué mirar cuando algo va mal— está en
   [`OPERACION.md`](OPERACION.md).

**Criterio de cierre:** se puede desplegar a producción, revertir el deploy,
revertir una migración y restaurar un respaldo — y las tres cosas se probaron,
no se supusieron. **Cerrado**, con una salvedad honesta: la reversión de
migraciones y la restauración de respaldo se prueban en cada corrida de CI, y el
rollback de un deploy es un procedimiento escrito que todavía no se ha
ejercitado contra Render.

---

## Fase 9 — Cerrar la Fase 5 en web

> **Cerrada.** Reportes quedó resuelto dentro de Expediente y Estimación, no
> como pantalla aparte (ver abajo).

Deuda de D1: el vertical de cargas, expediente y reportes llegó hasta la API y
se detuvo. Los endpoints existían, estaban en el contrato y los hooks de Orval
ya estaban generados, así que era trabajo de UI y no de integración.

- ✅ **Cargas** — bandeja del §10.3: plantillas por tipo, subida con **vista
  previa obligatoria** antes de aplicar (§10.2), reporte de errores por fila
  —número, columna, valor, motivo— y reversa del lote como unidad (§10.8).
- ✅ **Expediente** — por obra: documentos, evidencias, cierres, estimaciones y
  las dos sumas de montos validados. El documento se sube **directo a R2** con
  presigned URL; no pasa por la API (§12.2).
- ✅ **Reportes** — encolar, seguir y descargar. No como pantalla propia: los
  dos reportes del sistema salen de un contexto —el XLSX desde una estimación,
  el PDF desde un expediente— y una bandeja separada obligaría a ir a otro lado
  a buscar lo que se acaba de pedir. `SeguimientoDeReporte` es un componente que
  vive donde se encola, sondea mientras el trabajo está vivo y se apaga solo.

**Tres bugs del transporte que bloqueaban todo esto**, y que ninguna prueba veía
porque las de web ejercitaban reglas puras y ninguna salía por la red:

1. `peticion` anteponía `/api/v1` a rutas que ya lo traían: toda llamada iba a
   `/api/v1/api/v1/...` (corregido en la Fase 7, al mandar la primera cabecera).
2. Un `FormData` se serializaba con `JSON.stringify` y se le fijaba
   `multipart/form-data` **sin boundary** — un multipart que ningún servidor
   puede separar. Sin esto, subir una carga era imposible.
3. Las descargas binarias pasaban por `respuesta.json()`, que sobre un `.xlsx`
   truena con un error de sintaxis que no dice nada. Ahora vuelven como archivo
   con su nombre, tomado del `Content-Disposition`.

`src/pruebas/cliente.test.ts` cubre los tres, que es lo que faltaba: una suite
que mire **lo que se manda**, no solo lo que se calcula.

**Y la regla 1 queda cumplida.** Las doce mutaciones que el backend protege ya
mandan su `Idempotency-Key`. Los formularios usan una clave fija por montaje;
las pantallas de lista, una por (método, ruta) —`lib/idempotencia.ts`—, porque
el mismo hook autoriza el cierre 1 y después el 2, y una clave fija haría que el
segundo llegara con la del primero y el backend respondiera 422.

> Lo que **no** se enciende es `retry` global en `queryClient`, y la razón
> cambió: ya no depende de las pantallas sino de que solo doce rutas del
> contrato son idempotentes. Un `retry` global reintentaría también el alta de
> un concepto, que no está protegida y se duplicaría. Queda en 0, y quien
> necesite reintento lo pide en su propio `mutation: { retry }`, donde sí se
> sabe si la ruta lo aguanta.

De paso, dos cosas que estaban a medias: la pantalla de Estimación pedía el UUID
de la obra escrito a mano —su docstring decía que `GET /obras` no existía, y
existe desde la Fase 1— y no tenía forma de exportar el XLSX que el backend ya
sabía generar.

**Criterio de cierre:** la Fase 5 queda cerrada según D1 y un Control de obra
carga su catálogo real desde Excel. **Cumplido**, con la salvedad de que
resolver los pendientes de la bandeja (§10.3) desde la UI no está: el contrato
no publica la ruta que los cierra. La pantalla los muestra y lo dice.

---

## Fase 10 — Torre de control

> **Cerrada.**

Es la pantalla donde **aterrizan tres de los cuatro roles** (§5.1: Supervisor,
Control de obra y Super intendente la tienen como primera entrada). Caían en
Cierres como sustituto, con un comentario en `App.tsx` que lo decía.

- ✅ **Backend**: `GET /obras/{id}/actividades` y `GET /actividades/{id}`, que
  no existían. Y uno que el roadmap no había previsto: **`GET /torre`**.
- ✅ **Web**: estado por obra —avance, ruta crítica, incidencias abiertas,
  cierres pendientes— filtrado por el alcance del rol. **Virtualizada** pasado
  el umbral (regla 4, §12.9).
- Sin tiempo real *entonces*: recarga de TanStack Query. La **Fase 16** le puso
  avisos en vivo por SSE, y la Torre es la primera pantalla que recarga sola.

**Por qué `GET /torre` y no cinco llamadas del cliente.** La Torre necesita seis
números por obra. Resolverlo desde el navegador serían cinco peticiones por
obra, y el §12.1 habla de 60–80 obras activas: cuatrocientas peticiones para
pintar una pantalla, cada una con su ida y vuelta de RLS. Es una consulta con
`count(*) filter` y `lateral`, y **no filtra por `org_id` a mano**: los conteos
pasan por las mismas políticas que la tabla, así que un supervisor cuenta sobre
lo que ve y nada más. Eso es exactamente lo que prueba
`test_torre_endtoend.py`.

**Tres estados, no cinco.** *Detenida* (algo impide trabajar), *pendiente* (algo
espera a una persona) y *al corriente*. El avance **no** entra en la
clasificación: una obra al 5 % puede ir en tiempo, y teñirla de rojo por el
número enseña a ignorar los rojos. El orden de la lista sale de lo mismo —
primero lo que estorba, después lo que espera—, resuelto en SQL para no traer
ochenta filas y filtrarlas en el cliente.

Dos errores de esquema que la prueba de integración atrapó y que un mock no
habría visto: `estatus_actividad` no tiene `'cerrada'` sino `'concluida'`, y
`contratista` no tiene `nombre` sino `razon_social`. También que
`estatus <> 'cerrada'` contaba las incidencias **rechazadas** como trabajo
pendiente.

**Criterio de cierre:** un supervisor abre la app y ve, en una pantalla, dónde
está cada obra suya y qué le toca hacer hoy. **Cumplido** — con la salvedad de
que las acciones se hacen en sus pantallas (Cierres, Incidencias): la Torre
lleva a ellas y no las duplica, porque dos copias de las mismas reglas de
transición se desincronizan.

---

## Fase 11 — Los huecos de una obra real

> **Cerrada.**

Lo que aparece en cuanto una obra de verdad se mueve, y que no tenía a dónde ir.

- ✅ **`POST /actividades`** — alta extra-catálogo con OC (§11.2, rol R), con su
  pantalla *Extra-catálogo* (§5.1), que el Residente traía en su sidebar desde
  la Fase 1 sin que llevara a ninguna parte.
- ✅ **Revisión física en web** (C). El endpoint existía desde la Fase 4 y
  ninguna pantalla lo usaba. El §11.2 la marca «móvil», pero el móvil es la
  Fase 15: sin esta pantalla el expediente llega al cierre de obra sin evidencia
  de calidad (§11.3 D).
- ✅ **`POST /actividades/{id}/registros`: decidido, y la decisión es no.**

**Qué es «OC», dicho porque el spec no lo dice.** El §11.2 la nombra una sola
vez y no la define. Se interpreta como **orden de cambio**, y de ahí sale la
regla entera de esta ruta: *no hay trabajo extra sin orden que lo autorice*.
Vive como `CHECK` en la migración 0026 —para que la cubra también la ruta
directa a Supabase (§10.7)— y como regla de dominio, que es la que da el
mensaje en español. La interpretación está escrita en la propia migración: si
resulta equivocada, lo que hay que cambiar es la columna, y conviene que el
razonamiento esté donde está el dato.

La segunda regla es menos obvia y más cara: **un extra sin precio del modo de
pago elegido no se puede estimar** (§11.3 E), o sea que es trabajo real que
nadie va a cobrar. Se exige el precio del modo elegido y solo ese.

**Sobre `/registros`: la ruta no se implementa.** El §11.2 la nombraba como
«registro diario (R)», y después de D5 no queda nada que hiciera que
`PATCH /actividades/{id}/avance` no haga ya: el PATCH escribe su delta en
`registro_avance`, que es la única fuente de `cant_ejecutada` (D6). Una segunda
ruta que escriba lo mismo son dos caminos que mantener sincronizados.

> **Pero la pregunta destapó un bug de verdad.** El PATCH recibe un **absoluto**
> y deriva el delta restando lo que ya había. Desde D5 hay **otro escritor** —el
> móvil, por PowerSync, sin pasar por la API— y eso convierte el
> lee-modifica-escribe en una carrera concreta: la actividad va en 10, la web
> lee 10 y el residente quiere dejarla en 12; entre la lectura y la escritura el
> móvil sincroniza un +5. La web calcula delta = +2 sobre el 10 que leyó y el
> total queda en 17. Ni 12 ni 15: un número que nadie capturó.
>
> Resuelto con `select … for update` en la lectura de captura
> (`obtener_para_captura`), que serializa a los dos escritores — el trigger de
> agregación actualiza `actividad`, así que la transacción del móvil espera. Con
> prueba que reproduce el intercalado.

**Criterio de cierre:** no lo tenía escrito; el de facto era que el trabajo que
aparece en obra tenga dónde registrarse y que lo ejecutado tenga cómo
documentarse. **Cumplido.**

---

## Fase 12 — Cierre de obra · Workflow D

> **Cerrada.** Con esto, **los seis workflows del §11.3 tienen backend**.

Era el único de los seis sin nada: las tablas existían con RLS desde la
migración 0009 y no había ruta que las tocara. Es la culminación natural del
piloto —se cierra la obra con la que se empezó— y el expediente técnico de la
Fase 5 se construyó justamente para sostenerlo.

- ✅ `POST /obras/{id}/cierre-obra` (SI) y `POST /cierres-obra/{id}/participar`
  (los cuatro roles), más la bandeja y el detalle del acta.
- ✅ Dominio: qué exige un cierre antes de dejar firmar.
- ✅ Web: *Cierres de obra*, compartida aunque solo el SI la abra.

**La decisión que hace útil esta ruta: qué bloquea y qué no.** No todo pendiente
impide entregar, y confundirlos la rompe por los dos lados — si todo bloquea, el
cierre es imposible y la gente aprende a saltárselo; si nada bloquea, se firma
una entrega con dinero sin resolver.

| Bloquean | Solo se informan |
|---|---|
| Avance incompleto · actividades sin concluir · cierres de actividad esperando · estimaciones sin validar · incidencias que **detienen** | Incidencias abiertas de impacto menor · expediente sin documentos · evaluación final ausente |

Los primeros describen trabajo o dinero sin resolver; los segundos son cosas que
deberían estar y cuya falta hay que ver, pero que no impiden que la obra esté
terminada.

**Abrir con pendientes está permitido y es el punto** (§11.3 D.1): convocar al
equipo es lo que hace que se resuelvan. Lo que no se puede es firmar con ellos.
Y la cuarta firma **se valida antes de escribir nada**: registrarla y después
descubrir que faltaba resolver dejaría un acta completa sobre una obra que no se
puede entregar.

> **La obra se congela dentro de la transacción, no por evento.** El §11.3 D.3
> dice «evento `CierreObra` → obra `entregada`», y la tentación es publicarlo
> por el bus. No se hace, por lo mismo que `IncidenciaDetiene` ya documentaba
> para el bloqueo: `BusEnProceso` **se traga los fallos de sus manejadores a
> propósito**, y `entregada` no es un dato derivado que se pueda recalcular —es
> una frontera de permisos—. Una obra cerrada sin congelar admitiría capturas
> sobre un acta ya firmada, y nadie se enteraría.

El acta y el estado de la obra salen de **una** consulta con `lateral` sobre
siete contextos. En viajes separados, además de costar siete, dejarían una
ventana en la que el estado cambia: se contaría el avance de antes con las
incidencias de después.

**Criterio de cierre:** los seis workflows del §11.3 tienen backend y el de
cierre de obra corre de punta a punta. **Cumplido.** Falta su E2E, que va con la
regla 2 cuando haya un entorno con API y Postgres sembrado.

---

## Fase 13 — Presupuesto y rendimientos

> **Cerrada.**

Tablas con RLS (`presupuesto`, `partida_presupuesto`) desde la migración 0006 y
**ni un repositorio ni un endpoint**. Un área entera del §5.1 que aparece en el
sidebar de Control de obra y de Super intendente.

- ✅ Endpoints de presupuesto por obra y su historial de versiones.
- ✅ Rendimientos: lo ejecutado contra lo presupuestado, por concepto y por
  cuadrilla.
- ✅ Web: *Presupuesto de obras* y *Rendimientos* — una sola pantalla en las
  tres rutas que los sidebars ya traían (§5.3), **virtualizada** (regla 4).

**El presupuesto es del prototipo, no de la obra.** `presupuesto` cuelga de
`prototipo`, y tiene sentido: describe el modelo de vivienda, y todas las obras
que lo instancian comparten el mismo. Consecuencia que la pantalla dice en vez
de esconder: una obra **URBA** —sin prototipo (§7.2)— no tiene presupuesto, y eso
no es un error.

**Solo lectura, y no por falta de tiempo.** El presupuesto entra por carga de
Excel y se versiona ahí (§10.8). Un `POST` que dejara capturarlo a mano abriría
un segundo camino de alta con otro versionado y otra reversa para el mismo dato.

**Las dos caras que faltan son el punto.** El comparativo incluye lo
presupuestado y **no ejecutado** —trabajo que no se hizo— y lo ejecutado **sin
presupuestar** —los extra-catálogo de la Fase 11—. Son justo los dos que
explican por qué una obra costó lo que costó, y los dos que un `left join` desde
el presupuesto habría dejado fuera.

Tres decisiones del dominio que ninguna consulta puede tomar:

1. **Un porcentaje alto sobre un monto chico no es noticia.** Sin un piso de
   monto, un concepto de cien pesos con 20 % encabezaría la lista y empujaría
   fuera de vista uno de un millón con 3 %.
2. **`no_ejecutado` no es `bajo_costo`.** Gastar de menos porque el trabajo no
   se hizo no es un ahorro, y la acción que abre es otra: ahí se revisa el
   precio, aquí se pregunta por qué no se hizo. La pantalla tampoco lo pinta de
   verde.
3. **Sin presupuesto no hay porcentaje.** Un extra no se desvió «infinito por
   ciento»: la pregunta no aplica, y escribir un cero diría lo contrario.

El umbral es el del §3.6 y es **configurable por organización**: la constante del
dominio es el default, y el endpoint acepta el valor de la org.

De paso, un límite de Postgres que apareció al escribirlo: **`FULL JOIN` no
admite `is not distinct from`** —la condición tiene que ser hash o merge
joinable— y esa condición hacía falta, porque las actividades extra no tienen
concepto y su clave es `null`. Se resuelve con el conjunto de claves (`union`) y
dos `left join`.

**Criterio de cierre:** no lo tenía escrito; el de facto era que Control de obra
y Super intendente puedan ver en qué se fue el dinero. **Cumplido.**

---

## Fase 14 — Rendimiento y calidad

> **Cerrada**, salvo los seis E2E de workflow, que siguen esperando un entorno
> con API y Postgres sembrado.

El segundo bloque de endurecimiento: no habilita el piloto, lo sostiene cuando
crece.

- ✅ **La prueba intermitente.** `test_flujo_completo_deja_la_incidencia_cerrada`
  afirmaba el orden de los eventos con `order by fecha`, y cuatro eventos del
  mismo tick del reloj comparten `fecha`: Postgres devolvía el orden que le
  convenía. La migración 0027 le da a `incidencia_evento` una columna `orden`
  —una secuencia, no un reloj—. `fecha` responde *cuándo pasó*, que es lo que se
  muestra; `orden` responde *en qué secuencia*, que es lo que se ordena.
  Confundirlas fue el bug.
- ✅ **Virtualización (§12.9).** El patrón vivía copiado en dos pantallas; ahora
  está en `lib/tablaVirtual.tsx` y cubre además el **catálogo de conceptos y de
  insumos**, que es la vista de miles de renglones que el §12.9 nombra primero.
  Unidades, familias y contratistas se quedan sin virtualizar a propósito: son
  decenas, y acotarles el viewport costaría un `Ctrl+F` que deja de encontrar a
  cambio de nada.
- ✅ **Datasets golden (§11.7).** CPM y explosión de insumos, congelados en
  `tests/golden/`. Un golden no comprueba que el cálculo sea correcto —eso lo
  hacen las pruebas de dominio— sino que **no cambie sin que alguien lo decida**,
  y su valor está en el diff: cuando una holgura pasa de 2 a 0, lo que aparece
  en la revisión es esa línea.
- ✅ **Idempotencia de reprocesos (§11.7).** Correr el recálculo de CPM 2× —y
  3×— da el mismo resultado. Importa porque el recálculo viaja como job y un job
  **se reintenta**: si reintentarlo moviera las fechas, un fallo transitorio de
  red se convertiría en un cronograma distinto.
- ✅ **Deuda de tipos: decidida.** De 294 hallazgos, 198 eran `dict` sin
  parametrizar. Se aceptan como convención (`disallow_any_generics = false`)
  porque `dict[str, Any]` **no detecta nada** que `dict` no dijera ya, y lo que
  sí hacían esos 198 era enterrar los otros 96. Con eso mypy entra a CI como
  paso informativo: no bloquea, pero la cuenta se ve, y si sube alguien agregó
  deuda.
- ⏳ **Los seis E2E de workflow.** El arnés está listo desde la Fase 6 y el del
  alta de usuario se escribió en la Fase 7. Los seis siguen en `fixme` por la
  misma razón de entonces: escribirlos contra una UI que no se ha podido
  ejecutar produce selectores inventados.
- ⏳ **Reprocesos acotados (§11.7)** — tope de iteraciones y detector «sin
  progreso». No se hizo: hoy ningún reproceso itera. El CPM es una pasada sobre
  un grafo acíclico —`CicloEnGrafoError` corta antes— y las cargas recorren un
  archivo una vez. Se anota para cuando exista un job que pueda no converger, no
  antes: un tope sobre algo que no itera es código que nadie ejecuta.

> **Y un bug real que encontró mypy en cuanto dejó de ser ruido.**
> `ColaDeTrabajos.estado` —de la Fase 8— leía `RedisSettings.health_check_key`,
> que **no existe**: el atributo vive en el `Worker`, no en los ajustes de
> conexión. `/health` habría reportado `error: AttributeError` en el campo
> `jobs`, o sea una sonda diciendo «no sé» justo sobre lo que existe para
> vigilar. Es exactamente el tipo de hallazgo que los 198 de `dict` estaban
> tapando.

**Criterio de cierre:** no lo tenía escrito; el de facto era que los cálculos
que importan queden congelados y que las vistas grandes no crezcan el DOM con la
obra. **Cumplido.**

---

## Fase 15 — Móvil

> **Cerrada**, salvo lo que necesita una cuenta de Google Play o un emulador.

Entraba con `lib/` y `sync/` listos desde la Fase 1 y **once pantallas de
quince líneas**. Sale con las catorce del §5.2 funcionando y con la pregunta
que de verdad tenía que responderse: *qué se puede escribir desde un teléfono
sin señal y qué no*.

### Las tres colas, que son la decisión de la fase

D5 zanjó que el **avance** concilia directo contra Postgres vía PowerSync. Lo
que no estaba zanjado es que eso **no generaliza**, y descubrirlo fue el
trabajo:

| Cola | Qué lleva | Por qué esa |
|---|---|---|
| `ps_crud` de PowerSync | Avance y revisión física | Escriben directo a Postgres con RLS de frontera. No hay efecto de dominio que perder: `revision_fisica` es una entidad propia (§7.8) que no dispara nada. |
| `evidencia_pendiente` (local-only) | Fotos hacia R2 | Una foto de 3 MB no puede bloquear una captura de 200 bytes. Y la ruta `file:///…` de *este* teléfono no significa nada en otro, así que no sincroniza: lo que viaja es la **clave** del objeto. |
| `operacion_pendiente` (local-only) | `POST` a la API | Abrir una incidencia con `impacto=detiene` **bloquea actividades y replanea el CPM** (§11.3 F.5), y eso vive en el caso de uso, no en un trigger. |

Ese tercer renglón es el hallazgo. Un `INSERT` directo de `incidencia` desde
el móvil habría creado la fila y **no habría bloqueado nada**: el resultado no
sería un error visible sino algo peor —una obra que se ve libre estando
detenida—. La bandeja de salida guarda el `POST` con su `Idempotency-Key`
generada **al capturar**, y por eso el reintento es seguro: si la red se cae
después de que el servidor escribió, la misma clave devuelve 409 y la app lo
lee como éxito, que es lo que es.

Para el residente las tres son una sola pregunta —*¿ya salió lo que capturé?*—
y por eso el indicador del encabezado las suma. Un "sincronizado" con tres
fotos sin subir sería una mentira técnicamente precisa.

- ✅ **Las catorce pantallas (§5.2).** Residente, Supervisor y Control de
  obra. Las compartidas se implementaron **una vez** y cambian por rol (§5.3):
  Obras, Incidencias y Ruta crítica viven en `src/pantallas/` con una prop
  `papel`, no duplicadas por grupo de tabs.
- ✅ **Captura offline con evidencia** (§11.3 B) y **revisión física** (§7.8),
  las dos cosas que el §12.5 nombra por su nombre.
- ✅ **Cola de evidencias a R2** con `POST /evidencias/presigned`. Tres etapas
  —encolar, subir, coser— y la separación importa: si la app muere entre subir
  y coser, la clave ya está persistida y el siguiente intento no vuelve a
  mandar los 3 MB. La foto se copia a `documentDirectory` y no al caché, que
  el sistema vacía cuando falta espacio: sin eso, una evidencia se sacaba y
  nunca llegaba.
- ✅ **Actualización (§12.12).** `GET /cliente/version` publica la mínima y la
  recomendada; el middleware responde **426** a quien esté por debajo; la app
  bloquea, sugiere o calla. Se mueve con una variable de entorno, sin
  desplegar y sin pasar por la tienda — que es el punto, porque un build nuevo
  llegaría tarde justo a quien ya no puede usar la app. **Si no se puede
  preguntar, no se bloquea:** sin señal el estado es `ok`, nunca
  `obligatoria`.
- ✅ **Expo Push (§12.2).** Migración 0028, registro y baja del token, y el
  aviso de `EstimacionValidada` saliendo ya por los dos canales. El push **no
  lleva el monto**: aparece en la pantalla de bloqueo y pasa por servidores de
  Expo y de Google (§12.4).
- ✅ **38 pruebas de móvil en CI** y **3 flujos de Maestro** con `testID`
  reales en los componentes.
- ⏳ **Publicar en Play.** Falta lo que no es código: cuenta de desarrollador,
  `projectId` de EAS, assets de la ficha y los formularios de la consola
  (§12.13). Está enumerado en `mobile/README.md`.
- ⏳ **Correr Maestro contra un emulador.** Los flujos están escritos contra
  componentes reales, pero necesitan un APK instalado y una API con datos
  sembrados — el mismo pendiente de staging que tienen los seis E2E de web.

> **La política RLS más estrecha del esquema.** `dispositivo_push` no se
> cuelga de `app.obra_visible()`: cada quien ve **solo sus** dispositivos, ni
> siquiera el Super intendente los ajenos. Un token de push no es un dato, es
> una capacidad de escritura sobre la pantalla de alguien. Y como el envío sí
> necesita el token del destinatario, la excepción es **una** función
> `security definer` con nombre propio (`app.tokens_push_de`) que devuelve
> tokens y nada más, filtrando por organización — en vez de aflojar la
> política y volver legibles todos los tokens desde cualquier `select`.

> **Y dos bugs que estaban esperando.**
> 1. **La app no compilaba sus pruebas, y nadie lo sabía.** `nativewind`
>    estaba como `^4.1.23` y resolvía a 4.2.6, cuyo `react-native-css-interop`
>    exige `react-native-worklets/plugin` — de Reanimated **4**, y aquí hay 3.
>    Todo el pipeline de Babel se caía. El job de móvil solo corría `tsc`, que
>    no pasa por Babel, así que el rojo no existía. Se fijó la versión exacta,
>    con el mismo criterio de `constraints.txt` en el backend.
> 2. **La ida y vuelta de migraciones probaba 22 de 27.** El paso de CI tenía
>    `--pasos 22` escrito a mano desde la Fase 6. Las cinco más nuevas —las
>    que más probable es que tengan un `down` malo— nunca se revertían. Ahora
>    el número se cuenta.

**Criterio de cierre:** un residente puede trabajar una jornada completa sin
señal —ver sus obras, capturar avance con foto, levantar una incidencia— y al
volver la cobertura todo sale solo, sin que nadie toque nada y sin duplicados.
**Cumplido**, salvo la publicación en la tienda, que no es código.

> Si el piloto revela que el residente no tiene señal en campo, esta fase deja
> de ser la penúltima (D7). Ya no aplica: se adelantó.

---

## Fase 16 — Lo que queda del spec

> **Cerrada.** Con esto no queda ningún endpoint del §11.2 sin implementar, ni
> ninguna entrada de sidebar del §5.1 que lleve a "en construcción".

Cuatro cabos sueltos que no bloqueaban el piloto pero dejaban el spec a medias.
Tres eran superficie faltante; el cuarto era una promesa que el sistema hacía y
no podía cumplir.

### Tiempo real: SSE, no WebSocket

El §11.2 ofrece las dos —`WS /ws` **o** `GET /events`— y se tomó SSE. El
tráfico es de una sola dirección: la Torre y las bandejas necesitan enterarse
de que algo cambió, no mandar nada. Un WebSocket da un canal bidireccional del
que se usaría la mitad, y con él un protocolo de mensajes, un ping propio y una
máquina de reconexión que hay que escribir. SSE es HTTP: pasa por el proxy de
Render y por las VPN corporativas sin negociar un `Upgrade` —justo donde los
WebSockets fallan en obra—, y la reconexión es del protocolo.

Tres decisiones que valen más que el transporte:

- **El aviso lleva ids, nunca contenido.** Un canal en vivo es el lugar más
  fácil para filtrar datos sin querer: basta un manejador que serialice el
  agregado completo para que quien esté suscrito reciba campos que su rol no
  podría pedir por HTTP. Quien recibe `{"tipo": "actividad_cerrada", …}` vuelve
  a consultar con su token, y la frontera sigue siendo RLS (§12.4). Por eso la
  traducción de evento a aviso es **una tabla explícita** —`adapters/api/
  avisos.py`— y no un `__dict__`: agregar un campo al canal es una decisión, no
  un descuido.
- **El cliente invalida, no aplica.** Escribir el cambio en la caché a partir
  del aviso sería inventar el estado en el navegador, que **no puede saber** qué
  le permite ver RLS. Invalidando, el dato lo trae la API con las reglas de
  siempre.
- **El token va en la cabecera.** `EventSource` no deja poner cabeceras, así
  que el JWT acabaría en la query string —logs de Render, historial, proxies—.
  El cliente lee el flujo con `fetch` + streams para mandar `Authorization`,
  como todo lo demás.

El canal reparte en memoria dentro del proceso y por **Redis pub/sub** entre
procesos, con el mismo `REDIS_URL` que ya usa Arq. Sin Redis se degrada, no se
rompe: en un despliegue de una instancia —el del piloto— funciona completo. Y
la cola de cada suscriptor es acotada: una pestaña dormida pierde avisos en vez
de tumbar el proceso, que es el intercambio correcto cuando el dato de verdad
está a una petición de distancia.

### `POST /reportes/{tipo}`: el catálogo es la tabla

Los tipos, sus roles y sus parámetros viven en `adapters/export/catalogo.py`.
Con un `if/elif` en el router, agregar un reporte serían tres cosas que tocar y
el olvidado siempre es el rol — por eso hay una prueba de que el genérico **no
es un rodeo**: pedir `estimacion` como residente da 403, igual que en la ruta
específica. El orden de las validaciones también se prueba: *existe → puedes →
está completo*, porque al revés un 422 por parámetro faltante le confirmaría a
alguien sin permiso que ese reporte existe.

El tercer tipo, `avance`, es el que justifica el endpoint: **no cuelga de
ninguna entidad**. Su sujeto es el alcance del que pregunta, y sale bien porque
el contexto RLS viaja al worker. Reusa la consulta de la Torre en vez de
escribir una propia: si el reporte contara las obras detenidas con otro
criterio, la junta donde se miran los dos números discutiría cuál está mal.

Sus **dos avances** se llaman distinto porque son distintos —`por_actividades`
es un conteo, `promedio_simple` es una media— y con obras de distinto tamaño
difieren muchísimo. El **ponderado por dinero** no está, aquí ni en la
pantalla: exige decidir contra qué se pondera y el spec no lo fija. Esa
decisión ya tiene su lugar en Presupuesto.

### Procesos y bitácora: la tabla existía, faltaba la puerta

`proceso` está en la migración 0010 con su RLS de catálogo desde la Fase 1, y
`bitacora` se escribe sola por trigger desde la Fase 8. Las dos entradas del
sidebar del SI llevaban a "en construcción" — una auditoría que solo se lee con
`psql` no cumple lo que el §12.12 pide, porque quien necesita saber quién movió
el IVA es justamente quien no tiene ese acceso.

- **Procesos**: todos leen, el SI escribe. La asimetría es del §11.2 y es
  correcta: un proceso de mejora que solo ve quien lo escribió no mejora nada.
  Se agregó `PATCH` —que el spec no pide— porque sin mover el estatus el
  tablero se queda en `propuesto` para siempre; y **sin máquina de estados**,
  porque imponer un orden sería inventar una regla que el §7.9 no da.
- **`EstatusProceso` se decidió aquí** y **no** como enum de Postgres: cambiar
  un tipo de la base es una migración con `down` probado, y estos cuatro
  valores son convención de tablero —semilla editable del §8.7—, no invariante.
- **Bitácora**: solo lectura, y no por elección de la ruta —la tabla no tiene
  política de INSERT, UPDATE ni DELETE—. La pantalla pinta el **diff campo por
  campo**, que es lo que se viene a ver: un volcado del `jsonb` escondería el
  cambio entre treinta campos iguales.

### Contrato aditivo: la ventana ahora se verifica sola

Desde la Fase 15 hay un cliente que no se puede actualizar a voluntad. Que el
contrato "no rompa" era una intención escrita en el §12.12 y nada la
comprobaba: se puede regenerar `openapi.json` correctamente y romper a todos
los clientes viejos a la vez.

Ahora hay una **línea base** —`openapi/publicado.json`, el contrato que está en
producción— y un script que compara contra ella en CI. Quitar una operación,
volver obligatorio un campo, sacar uno de una respuesta o achicar un enum ponen
el build en rojo; agregar, no. Y la ventana es parte de la regla: una ruta
deprecada declara su `x-sunset`, quitarla antes de esa fecha falla, y una
deprecación **sin** fecha también —porque nunca vencería—. El ayudante
(`adapters/api/deprecacion.py`) marca la ruta y manda `Deprecation`/`Sunset`
del RFC 8594 en cada respuesta. Hoy no hay ninguna ruta deprecada, que es lo
correcto: esta fase agrega, no quita. Lo que existe es el mecanismo, listo
antes de que haga falta improvisarlo bajo presión.

> **Un bug que encontró la suite.** `canal_de_avisos` es una instancia de
> módulo —tiene que sobrevivir a la petición que abrió la conexión SSE— y su
> puente con Redis es una tarea de fondo. Al apagar la app, cancelar esa tarea
> desde un event loop distinto al que la creó levanta `RuntimeError`, y eso
> tiraba el `lifespan`. Se vio porque cada prueba abre su propio loop; en
> producción habría aparecido el día que alguien levantara la app dos veces en
> el mismo proceso, o en un apagado con mala suerte. Cerrar ahora tolera un
> loop muerto: que el apagado truene por un detalle de limpieza convertiría un
> deploy normal en un incidente.

**Criterio de cierre:** que no quede endpoint del §11.2 sin implementar, que
ninguna entrada del §5.1 lleve a una pantalla vacía, y que romper el contrato
sea imposible sin que CI lo diga. **Cumplido.**

---

## Definición de cerrado (v1)

"Cerrar" no es agotar el spec: es llegar a un sistema que una organización real
pueda usar y que se pueda operar sin heroísmos. v1 está cerrado cuando:

**Funciona de punta a punta**
- [ ] Los **seis workflows del §11.3** corren completos, con su E2E verde.
      *(El código está; los E2E esperan un staging sembrado.)*
- [x] Los **cuatro roles** del §4 tienen su sidebar del §5.1 sin huecos
      (Fase 16: procesos, bitácora y avance total eran los tres que faltaban).
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
- [x] Contrato aditivo con ventana de deprecación — verificado en CI contra
      `openapi/publicado.json` (Fase 16).
- [x] Móvil con force/soft update y esquema PowerSync migrable (Fase 15).
- [x] Datasets golden congelando los cálculos que importan (Fase 14).

Lo que queda **fuera de v1** y se anota para no confundirlo con deuda: SSO
(§12.1 "activable a futuro"), microservicios (§12.1 "futuro"), App Store —el
§12.13 solo cubre Google Play— y cualquier segundo idioma.

---

## Invariantes que ninguna fase rompe

1. La dependencia apunta **hacia adentro**; `domain/` no conoce FastAPI, SQLModel, RLS ni React (§12.11).
2. Las reglas del §6 se definen **una vez** en el dominio; el front las refleja y la BD las repite como `CHECK`.
3. Las sync rules **espejean** RLS; si cambia el alcance de un rol, cambia en ambos lados.
4. Un módulo **nunca** lee tablas ni estado interno de otro: solo fachadas y eventos de dominio.
