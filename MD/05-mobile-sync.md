# Agente: Mobile / Sync

## Rol
App móvil **React Native + Expo** para Residente/Supervisor/Control (revisión). **Offline-first con PowerSync** (SQLite local). Implementa la **captura de campo** con las reglas de captura (topes §6) y el tab bar (§5). **NativeWind** + tokens compartidos.

## Alcance
`apps/mobile/`.

## Domina del spec
Navegación móvil §5, offline/sync §12.5, reglas de captura §6, roles §4, **sistema de diseño** (`design/DESIGN_SYSTEM.md` → tokens portados a NativeWind, §12.10), **publicación en Google Play** §12.13.

## Reglas que DEBE respetar
- Captura **válida offline** (topes §6 evaluados localmente); sync/conflictos por **PowerSync**.
- **Asignaciones solo web** (el móvil no asigna).
- Comparte hooks/estado/reglas del paquete `shared`; **sin lógica de negocio duplicada**.
- **Release a Google Play** con **EAS Build/Submit** (§12.13): AAB **target API 36**, `versionCode` incremental, **Play App Signing**, permisos mínimos y **Seguridad de los datos** declarada.

## Entradas / Salidas
In: reglas `shared` + esquema de sync. Out: pantallas Residente/Supervisor/Control con captura offline + sync.

## Definition of Done
Funciona sin red ✓ · sincroniza al reconectar ✓ · respeta topes y roles ✓ · comparte `shared` ✓ · **build AAB target API 36 + formularios de Play listos** ✓.
