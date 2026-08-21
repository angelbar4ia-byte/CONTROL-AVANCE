# E2E del móvil — Maestro

> **Maestro y no Playwright** (§11.7, Fase 15 del ROADMAP). Playwright maneja
> un navegador; aquí no hay navegador. Y **Maestro y no Detox**: Detox exige
> compilar la app con su runner inyectado —o sea, probar un binario que no es
> el que se publica—, mientras que Maestro habla con el dispositivo por
> accesibilidad y corre contra el **APK de `preview`**, el mismo que se le
> instala a un probador (§12.13).

## Lo que estos flujos prueban, y lo que no

Prueban lo que solo se puede ver en un dispositivo real: que la captura
funcione **en modo avión** y que lo capturado siga ahí al recuperar la red.
Esa es la promesa entera del §12.5, y no hay prueba unitaria que la sostenga
—las reglas se prueban en `mobile/tests/`, pero la promesa es sobre SQLite,
el ciclo de vida de la app y la radio del teléfono—.

No prueban cálculo: el CPM, los montos y la explosión de insumos tienen sus
datasets golden en el backend (§11.7, Fase 14).

## Por qué no corren en CI

Necesitan un emulador de Android con la app instalada y una API alcanzable con
datos sembrados. El job `mobile` de `.github/workflows/ci.yml` corre tipos y
pruebas unitarias, que no necesitan nada de eso.

Levantar un emulador en CI es posible —`reactivecircus/android-emulator-runner`—
y **no se hizo a propósito**: sin un entorno de staging con Postgres sembrado
(pendiente #2 de "Lo inmediato" en el ROADMAP), el flujo se quedaría en la
pantalla de login. Un E2E que no puede pasar de la primera pantalla es un job
rojo permanente, y un job rojo permanente se ignora.

Se corren a mano antes de publicar:

```bash
# Una vez: https://maestro.mobile.dev
export MAESTRO_APP_ID=com.obractrl.app
eas build --profile preview --platform android   # o un APK ya descargado
adb install obractrl-preview.apk

maestro test mobile/e2e/01-login-y-captura-offline.yaml
```

## Credenciales

Los flujos leen `MAESTRO_USUARIO` y `MAESTRO_CONTRASENA` del entorno. No hay
credenciales en el repo, ni de prueba: la cuenta de revisión de Google Play
también se entrega por el Play Console, no por GitHub (§12.13, §12.4).
