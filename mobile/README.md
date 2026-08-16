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
│  ├─ lib/               sesión, auth, guardia por rol, reglas de avance
│  └─ ui/                encabezado, indicador de sync, chip de perfil
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

### Fotos

No viajan por PowerSync ni por la API: se guardan local y suben directo a R2
en segundo plano con una presigned URL.

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
ventana. El cliente manda su versión en un header y el servidor puede exigir
actualización mínima (force-update).

Los cambios de esquema de PowerSync deben ser compatibles con clientes que
aún tienen datos locales viejos y **cola de cambios sin sincronizar**.

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
| Login real + sesión persistida en `expo-secure-store` | Pantallas de Supervisor y Control (hoy son placeholders) |
| Tabs por rol (§5.2) con guardia de sesión/rol | Cola de evidencias (fotos) a R2 |
| Captura offline de avance con las reglas del §6 | Extra-catálogo, incidencias, cierres, ruta crítica |
| Conector de PowerSync + indicador de sincronización | Suma de deltas en el servidor (ver abajo) |
| Sync rules espejo de RLS · tokens NativeWind | Assets de tienda |

> **Pendiente del lado servidor:** `registro_avance` guarda deltas, pero hoy
> nada en Postgres los acumula en `actividad.cant_ejecutada` — el trigger
> `app.actividad_recalcular` deriva `avance_pct`/estatus *a partir de*
> `cant_ejecutada`, que solo escribe el caso de uso `capturar_avance`. Cuando
> el móvil suba sus registros, hace falta que backend/datos cierren ese paso
> (trigger de agregación o job de conciliación).

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
