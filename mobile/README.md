# `mobile/` — App React Native + Expo (Google Play)

Spec §5.2 (móvil por rol) · §12.5 (offline) · §12.12 (actualización) ·
§12.13 (publicación en Google Play).

## Estructura

```
mobile/
├─ app/                  expo-router
│  ├─ (residente)/       Obras · Avances · Incidencias · Ruta · Más
│  ├─ (supervisor)/      Torre · Incidencias · Cierres · Ruta · Más
│  └─ (control)/         Obras · Revisión · Fotos · Calidad
├─ src/
│  ├─ sync/              esquema local, conector y estado de PowerSync
│  ├─ salida/            bandeja de operaciones que exigen API (§11.3 C, F)
│  ├─ evidencias/        captura de fotos y su cola hacia R2 (§12.5)
│  ├─ pantallas/         pantallas compartidas entre roles (§5.3)
│  ├─ lib/               sesión, auth, guardias por rol y por versión, reglas
│  └─ ui/                encabezado, formularios, indicador de sync
├─ tests/                pruebas unitarias (jest-expo)
├─ e2e/                  flujos de Maestro — necesitan dispositivo
├─ sync-rules.yaml       reglas de sincronización de PowerSync
├─ app.json              config de Expo (applicationId, permisos)
└─ eas.json              perfiles de build y submit
```

El **Super intendente es solo web** (§5.2): si abre la app, se le indica en
vez de mostrarle una app vacía.

Control de obra en móvil hace **solo revisión física** — fotos, comentarios y
calidad. Toda la configuración (catálogos, presupuesto, programas, cargas) es
solo web.

## Offline (§12.5)

PowerSync mantiene una réplica **SQLite** local. La captura de avances del
Residente y la revisión física de Control funcionan sin señal; al reconectar
se concilian contra Postgres.

### El requisito que no se puede fallar

> Las **sync rules deben reflejar exactamente el mismo `org_id` y alcance por
> rol que las políticas RLS** (§12.4). Si divergen, el offline expone datos de
> otra organización — y RLS no puede evitarlo, porque estas consultas corren
> del lado del servicio de sync, no del cliente.

`sync-rules.yaml` es el espejo de `app.obra_visible()`
(`database/migrations/0011`). **Si cambia el alcance de un rol allá, cambia
aquí.**

### Conexión y cola de subida

`src/sync/ProveedorSync.tsx` conecta la réplica local al servicio de PowerSync
**mientras haya sesión**; al cerrar sesión llama `disconnect()` y nunca
`disconnectAndClear()`, que borraría la cola de capturas sin subir.

`src/sync/conector.ts` sube la cola. Sigue el workflow B del §11.3 —
*"PowerSync concilia contra Postgres (respetando RLS); **en web**: `PATCH
/actividades/{id}/avance`"*—: la ruta móvil escribe con el cliente de Supabase
autenticado con el JWT del usuario, así que las mismas políticas RLS y los
`CHECK`/triggers del §6 que viven en la BD siguen aplicando.

`actividad` **no se sube**: es *servidor-manda*. La pantalla de captura la
actualiza local solo como reflejo optimista; subirla pisaría el total
canónico.

El estado se ve siempre en el encabezado (`src/ui/IndicadorSync.tsx`):
*sincronizado · sincronizando · N por subir · sin red · solo local*.

### Conflictos

Default: last-write-wins. Pero el avance **no** puede resolverse así: dos
capturas del mismo día desde dispositivos distintos deben sumar, no pisarse.
Por eso `registro_avance` guarda `delta_ejecutado` y no un total — los deltas
se acumulan sin conflicto y `actividad.cant_ejecutada` se deriva de su suma en
el servidor.

### Tres colas, un solo indicador

Lo que sale del teléfono viaja por tres caminos distintos, y la razón de cada
uno está en qué pasa si se elige mal:

| Cola | Qué lleva | Por qué esa y no otra |
|---|---|---|
| `ps_crud` (PowerSync) | Avance y revisión física | Escriben directo a Postgres con RLS de frontera (D5); no hay efecto de dominio que perder. |
| `evidencia_pendiente` | Fotos hacia R2 | Una foto de 3 MB no puede bloquear una captura de 200 bytes. Local-only: la ruta del archivo no significa nada en otro teléfono. |
| `operacion_pendiente` | `POST` a la API | Abrir una incidencia con `impacto=detiene` **bloquea actividades y replanea el CPM** (§11.3 F.5), y eso vive en el caso de uso. Un `INSERT` directo dejaría la obra viéndose libre estando detenida. |

Para quien está en la obra son una sola pregunta —¿ya salió lo que capturé?— y
por eso el indicador del encabezado las suma. Un "sincronizado" con tres fotos
sin subir estaría mintiendo con precisión técnica.

Lo que hace segura la tercera es el **`Idempotency-Key` (§11.2)**, generado al
capturar y no al enviar: si la red se cae después de que el servidor escribió,
el reintento manda la misma clave, el backend contesta 409 y la app lo lee
como éxito — porque lo es.

### Fotos

No viajan por PowerSync ni por la API: se guardan en `documentDirectory` —no
en el caché, que el sistema vacía cuando falta espacio— y suben directo a R2
con una presigned URL que emite `POST /evidencias/presigned`. Lo que se
comparte es la **clave** del objeto, que se cose sobre
`registro_avance.evidencias`, `revision_fisica.fotos` o
`incidencia.evidencias` cuando la subida termina.

La pantalla *Fotos* de Control de obra es esa cola, visible: sin ella, una
foto rechazada por el servidor moría en un `console.warn` y nadie se enteraba
hasta que faltaba en el cierre.

## Publicación en Google Play (§12.13)

| Dato | Valor |
|---|---|
| `applicationId` | `com.obractrl.app` — **permanente** una vez publicado |
| Firma | **Play App Signing**: EAS gestiona la *upload key*, Google la *app signing key* |
| Formato | Android App Bundle (`.aab`) desde el perfil `production` |
| `versionCode` | Autoincremental (`autoIncrement: true` en `eas.json`) |

```bash
npm run build:preview    # APK interno de prueba
npm run build:prod       # AAB de producción
npm run submit           # sube a Play Console (track interno, borrador)
npm run update           # OTA con EAS Update, sin pasar por tienda
```

### Antes de la primera subida

1. Cuenta de desarrollador de Google Play (**pago único $25 USD**).
2. Crear la app en Play Console con `com.obractrl.app`.
3. **Service account** de Google Cloud con permiso en Play Console; su JSON va
   en `play-service-account.json` — está en `.gitignore` y **no se commitea**.
4. Sustituir los `projectId` placeholder de `app.json` por los reales de EAS.
5. Assets: icono **512×512**, gráfico destacado **1024×500**, mínimo 2
   capturas de teléfono.
6. **URL de política de privacidad** (obligatoria: la app maneja cuenta,
   fotos/evidencias y datos de obra).
7. Formularios: Seguridad de los datos, Clasificación de contenido (IARC),
   Público objetivo (no dirigido a menores), Anuncios (**sin anuncios**).
8. **Credenciales de prueba** para el equipo de revisión — la app exige login.

### Target API level

Desde el **31-ago-2026**, apps nuevas y actualizaciones deben apuntar a
**Android 16 (API 36)** o mayor (prórroga posible al 1-nov-2026). Un Expo SDK
reciente ya lo soporta; verificar antes de compilar para producción.

### Permisos

Mínimos y justificados (§12.13). `app.json` declara **cámara** (evidencias),
**medios** (fotos) y red; y **bloquea explícitamente** ubicación y micrófono,
que la app no usa. Declarar de más complica la revisión y el formulario de
Seguridad de los datos.

Al llenar **Seguridad de los datos** hay que declarar que existen **datos en
el dispositivo** (SQLite/PowerSync, §12.5).

## Actualización (§12.12)

Dos canales:

| Canal | Para qué | Latencia |
|---|---|---|
| **EAS Update (OTA)** | Cambios de JS y assets | Instantáneo |
| **Build nativo a tienda** | SDK, permisos, módulos nativos | Días (revisión) |

La API **no rompe clientes viejos**: cambios aditivos y deprecación con
ventana. El cliente manda su versión en tres cabeceras —`X-Cliente-Version`,
`X-Cliente-Plataforma`, `X-Cliente-Runtime` (`src/lib/version.ts`)— y el
servidor decide:

- `GET /api/v1/cliente/version` devuelve la **mínima** y la **recomendada**;
  la app bloquea, sugiere o calla (`src/lib/actualizacion.ts`).
- El middleware del backend responde **426** a quien esté por debajo de la
  mínima, con `X-Version-Minima` en la respuesta.

Se cambia sin desplegar: `MOVIL_VERSION_MINIMA` es una variable de entorno del
backend. Un build nuevo tardaría días en llegar por Play, y llegaría tarde
justo a quien ya no puede usar la app.

**Si no se puede preguntar, no se bloquea.** Sin señal o con la API caída el
estado es `ok`, nunca `obligatoria`: bloquear la app porque no hubo respuesta
dejaría al residente sin capturar en el único escenario donde el offline es
todo el punto.

`comparar()` en `src/lib/version.ts` y `version_es_menor()` en
`backend/.../middleware.py` **tienen que dar lo mismo**, y por eso sus casos
están duplicados en `mobile/tests/version.test.ts` y
`backend/tests/api/test_version_de_cliente.py`. Si divergen, el servidor
responde 426 a una app que se cree al día — que por lo tanto no muestra la
pantalla que lo explicaría.

Los cambios de esquema de PowerSync deben ser compatibles con clientes que
aún tienen datos locales viejos y **cola de cambios sin sincronizar**. Las dos
tablas nuevas de la Fase 15 (`evidencia_pendiente`, `operacion_pendiente`) son
`localOnly`, así que agregarlas no tocó nada de lo que estaba en tránsito.

## Notificaciones (§12.2)

`src/lib/push.ts` registra el `ExponentPushToken` en
`POST /api/v1/dispositivos/push` al entrar y lo da de baja al salir. Lo
segundo es lo que se olvida y lo que importa: sin la baja, el teléfono que un
residente devuelve a la empresa sigue recibiendo los avisos de sus antiguas
obras.

Todo falla hacia adentro: sin permiso, sin `projectId` de EAS o sin red, se
registra en consola y ya. El push es un extra; la app existe para capturar sin
señal.

## Diseño (§12.10)

El móvil comparte los **mismos tokens** que la web, pero no puede compartir el
CSS: React Native no usa DOM ni variables CSS (§12.9). Por eso los valores
OKLCH están escritos como literales en `tailwind.config.js`.

> Si cambia un token en `frontend/src/estilos/obractrl-design.css`, hay que
> reflejarlo aquí. Son dos copias del mismo lenguaje visual.

El tab bar sustituye al sidebar; el layout de 3 columnas no aplica. La altura
de fila sube a 44px: en móvil manda el objetivo táctil, no la densidad.

## Estado

| Listo | Falta |
|---|---|
| Las 14 pantallas del §5.2, ninguna placeholder | Assets de tienda (icono, gráfico destacado, capturas) |
| Captura offline de avance con las reglas del §6 | `projectId` real de EAS en `app.json` |
| Cola de evidencias a R2 y bandeja de salida a la API | Correr los flujos de Maestro contra un emulador |
| Force/soft update y cabeceras de versión (§12.12) | Publicar en Play Console |
| Registro de Expo Push (§12.2) | |
| 38 pruebas unitarias · 3 flujos de Maestro | |

La suma de deltas del lado servidor —que este README anotaba como pendiente—
la resolvió la **migración 0017**: `actividad.cant_ejecutada` se deriva de la
suma de los deltas de `registro_avance`, así que un registro llegado por
PowerSync mueve el avance y el auto-estatus igual que uno llegado por la web.

## Desarrollo

```bash
npm install
npx expo start
npm run typecheck
```

### Configuración

Se leen de `app.json → expo.extra` y, si no están, de variables de entorno
(`src/lib/entorno.ts`):

| Variable | Para qué |
|---|---|
| `EXPO_PUBLIC_SUPABASE_URL` | Auth administrado (§12.4) |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | Auth administrado (§12.4) |
| `EXPO_PUBLIC_POWERSYNC_URL` | Servicio de sync. Sin ella la app corre **solo local** |
| `EXPO_PUBLIC_API_URL` | API de FastAPI: firma de evidencias, bandeja de cierres, push y versión mínima. Sin ella esas pantallas lo dicen, no lo fingen |

```bash
npm test                 # unitarias (jest-expo)
npx tsc --noEmit         # tipos
```

Los flujos de `e2e/` necesitan emulador y una API sembrada; no corren en CI y
su `README.md` explica por qué.
