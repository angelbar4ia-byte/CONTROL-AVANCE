import {
  cerrarPorApi,
  entrarComo,
  expect,
  hayRoles,
  motivoSinRoles,
  test,
} from '../infraestructura';

/**
 * §11.3 E · Estimación semanal: generar → enviar → validar.
 *
 * Parte de trabajo ya validado: las dos actividades de `OBRA-E` se llevan por
 * el cierre completo con la API (eso se prueba en el workflow C) para que haya
 * algo que estimar. Lo que se ejercita aquí, con la web, es lo propio de la
 * estimación:
 *
 *  1. Supervisor genera la estimación en modo destajo → `borrador`.
 *  2. Supervisor la envía → `enviada`.
 *  3. Control de obra la valida → `validada`.
 *  4. El periodo queda bloqueado: un segundo intento de generar sobre la misma
 *     semana es rechazado (§11.3 E.5).
 *
 * Usa `OBRA-E` de `e2e/soporte/semilla.sql`; es de un solo uso (hay que volver
 * a sembrar para repetirlo).
 */

const ROLES_E = ['residente', 'supervisor', 'control'] as const;

test.describe('§11.3 E · Estimación semanal', () => {
  test.skip(!hayRoles(...ROLES_E), motivoSinRoles(...ROLES_E));
  test.setTimeout(60_000);

  test('el supervisor genera y envía, control valida y el periodo queda bloqueado', async ({ browser, request }) => {
    await cerrarPorApi(request, 'OBRA-E', 'E2E-EXC', 10);
    await cerrarPorApi(request, 'OBRA-E', 'E2E-PLA', 10);

    // --- 1. Supervisor: genera --------------------------------------
    const supervisor = await (await browser.newContext()).newPage();
    await entrarComo(supervisor, 'supervisor');
    await supervisor.goto('/estimacion');
    await supervisor.getByLabel('Obra').selectOption({ label: 'OBRA-E' });
    await supervisor.getByLabel('Modo de la estimación a generar').selectOption({ label: 'Destajo' });
    await supervisor.getByRole('button', { name: 'Generar estimación' }).click();

    // Una fila nueva en borrador. El monto es Σ cantidad validada × precio de
    // destajo de la semilla: 10 × 90 (excavación) + 10 × 150 (plantilla).
    const fila = supervisor.getByRole('row').filter({ hasText: 'borrador' });
    await expect(fila).toHaveCount(1);
    await expect(fila).toContainText('Destajo');
    await expect(fila).toContainText('2,400');

    // --- 2. Supervisor: envía ---------------------------------------
    await fila.getByRole('button', { name: 'Enviar' }).click();
    await expect(supervisor.getByRole('row').filter({ hasText: 'enviada' })).toHaveCount(1);

    // --- 3. Control de obra: valida ---------------------------------
    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto('/estimacion');
    await control.getByLabel('Obra').selectOption({ label: 'OBRA-E' });
    const filaControl = control.getByRole('row').filter({ hasText: 'enviada' });
    await expect(filaControl).toHaveCount(1);
    await filaControl.getByRole('button', { name: 'Validar' }).click();
    await expect(control.getByRole('row').filter({ hasText: 'validada' })).toHaveCount(1);

    // --- 4. Validada, el periodo queda bloqueado (§11.3 E.5) --------
    // Un segundo intento de generar sobre la misma semana es rechazado: es la
    // regla de la Fase 5 que solo se ve de punta a punta.
    await supervisor.reload();
    await supervisor.getByLabel('Obra').selectOption({ label: 'OBRA-E' });
    await supervisor.getByRole('button', { name: 'Generar estimación' }).click();
    await expect(supervisor.getByText(/El periodo \d+\/\d{4} de esta obra ya está bloqueado por una estimación validada/)).toBeVisible();

    // Y no se creó una segunda: sigue habiendo una sola, la validada. El número
    // de semana no se fija porque sale de la fecha de hoy (el ancla de la semilla).
    await expect(supervisor.getByRole('row').filter({ hasText: 'Destajo' })).toHaveCount(1);
    await expect(supervisor.getByRole('row').filter({ hasText: 'validada' })).toHaveCount(1);
  });
});
