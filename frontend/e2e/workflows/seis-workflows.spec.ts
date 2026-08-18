import { test } from '../infraestructura';

/**
 * Los seis workflows del §11.3, de punta a punta.
 *
 * ## Estado: pendientes, y marcados como tales a propósito
 *
 * Cada uno está declarado con `test.fixme`, que Playwright reporta como
 * "no implementado" y **nunca** como verde. Es deliberado: escribir seis
 * specs contra una UI que no se ha podido ejecutar produciría selectores
 * inventados y una suite que parece cubrir y no cubre. Un rojo honesto o un
 * "pendiente" visible valen más que un verde falso.
 *
 * Lo que sí queda listo es lo caro de acertar: el arnés
 * (`../infraestructura.ts`) con el salto por falta de backend y el `entrar()`
 * que pasa por el login real. Cada `fixme` lleva escritos los pasos y los
 * datos que necesita, que es lo que hace falta para implementarlo de corrido
 * cuando haya un entorno con API + Postgres sembrado.
 *
 * Dos de los seis (B y parte de D) **no son de web**: la captura offline y la
 * revisión física son móvil (§5.2). Se dejan anotados aquí para que el mapa de
 * los seis esté completo, pero su prueba va con Detox/Maestro sobre Expo, no
 * con Playwright.
 */

test.describe('§11.3 · Workflows de punta a punta', () => {
  test.fixme('A · Control de obra genera una obra desde su prototipo', async () => {
    // 1. Entrar como control_obra.
    // 2. Proyectos → alta de obra sobre un cluster de su proyecto.
    // 3. `POST /obras/{id}/generar` desde la UI.
    // 4. Verificar que la obra queda con actividades y programa instanciado.
    // Datos: un prototipo con árbol WBS y un programa base (semilla).
  });

  test.fixme('C · Cierre de actividad: solicitar → autorizar → validar', async () => {
    // Tres sesiones distintas (§11.3 C): residente solicita, supervisor
    // autoriza, control valida. Es el workflow que más justifica un E2E,
    // porque el rol cambia entre pasos y ninguna prueba unitaria lo cruza.
    // Verificar al final que la actividad quedó `cerrada` y estimable.
  });

  test.fixme('D · Cierre de obra con su expediente', async () => {
    // El expediente sostiene el cierre (§11.3 D). Parte de la evidencia entra
    // por móvil (revisión física), así que en web se verifica que el
    // expediente agregue lo que ya existe y que el cierre lo exija.
  });

  test.fixme('E · Estimación: generar → enviar → validar → periodo bloqueado', async () => {
    // El más completo: toca folio (§3.2), semana activa (§3.1) y termina
    // bloqueando el periodo (§11.3 E.5). Verificar que un segundo intento de
    // generar sobre la misma semana sea rechazado — es la regla que la Fase 5
    // agregó y que solo se ve de punta a punta.
  });

  test.fixme('F · Incidencia que detiene: abrir → bloquea actividades → cerrar', async () => {
    // `IncidenciaCreada(impacto=detiene)` bloquea actividades y dispara el
    // recálculo de ruta (§11.3 F). Verificar que la actividad bloqueada
    // rechace captura de avance y que al cerrar la incidencia se libere.
  });

  test.fixme('B · Captura offline del residente — es móvil, no web', async () => {
    // §5.2 y §12.5: la captura sin señal es de la app de Expo con PowerSync.
    // Queda anotado para que el mapa de los seis esté completo; su prueba va
    // con Detox/Maestro, no aquí.
  });
});
