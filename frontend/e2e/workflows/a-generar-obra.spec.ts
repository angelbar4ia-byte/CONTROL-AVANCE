import { entrarComo, expect, hayRoles, MOTIVO_SALTO, motivoSinRoles, test } from '../infraestructura';

/**
 * §11.3 A · Generación de obra desde prototipo.
 *
 * Control de obra da de alta una obra sobre un cluster de su proyecto y la
 * genera desde su prototipo: el servicio recorre el árbol, crea las
 * actividades con el CPU vigente e instancia el programa de obra.
 *
 * Los datos salen de `e2e/soporte/semilla.sql`: un prototipo `CAS-E2E` con tres
 * conceptos, cada uno con CPU vigente, y un residente al que asignar la obra.
 * La clave de la obra lleva la hora para que dos corridas seguidas no choquen
 * (la clave es única por cluster).
 *
 * Al final, la junta de arranque (D-537): Control de obra marca la obra
 * `iniciada` y la fecha de la junta queda como arranque del cronograma.
 */

test.describe('§11.3 A · Generación de obra desde prototipo', () => {
  test.skip(!hayRoles('control'), motivoSinRoles('control'));
  test.setTimeout(60_000);

  test('Control de obra da de alta la obra y la genera desde su prototipo', async ({
    page,
  }) => {
    const clave = `A-${Date.now().toString(36).toUpperCase()}`;

    await entrarComo(page, 'control');
    await page.goto('/obras');
    await expect(page.getByRole('heading', { name: 'Creador de obra' })).toBeVisible();

    // 1. Alta de la obra (A.1).
    await page.getByRole('button', { name: 'Nueva obra' }).click();
    const alta = page.getByRole('dialog');
    await alta.getByLabel('Cluster').selectOption({ label: 'PROY-E2E · CLU-E2E — Cluster E2E' });

    // Los prototipos son del proyecto del cluster: hasta elegirlo, el select
    // está vacío y deshabilitado.
    await expect(alta.getByLabel('Prototipo')).toBeEnabled();
    await alta.getByLabel('Clave').fill(clave);
    await alta.getByLabel('Prototipo').selectOption({ label: 'CAS-E2E · Casa E2E' });
    await alta.getByLabel('Residente').selectOption({ label: 'Rosa Residente' });
    await alta.getByRole('button', { name: 'Crear obra' }).click();

    await expect(page.getByRole('status')).toHaveText('Obra creada');

    // 2. Abrir la obra desde el árbol y generar (A.2).
    await page.getByRole('button', { name: /CLU-E2E Cluster E2E/ }).click();
    await page.getByRole('button', { name: new RegExp(`^${clave} Pendiente`) }).click();

    const panel = page.getByRole('dialog', { name: clave });
    await expect(panel.getByRole('heading', { name: 'Generar desde prototipo' })).toBeVisible();
    await panel.getByRole('button', { name: 'Generar actividades' }).click();

    // 3. El resultado dice cuántas actividades salieron y sobre qué programa.
    //    El prototipo sembrado tiene tres conceptos hoja.
    await expect(panel.getByRole('status')).toContainText(/Generada 3 actividades · programa [0-9a-f]{8}/);

    // Generada la obra, el botón de generar da paso a «Deshacer»: generar dos
    // veces duplicaría las actividades.
    await expect(panel.getByRole('button', { name: 'Deshacer' })).toBeVisible();

    // 4. La junta de arranque: la obra pasa de «Pendiente» a «Iniciada» y su
    //    fecha es el arranque del cronograma. Es una marca de una sola vez: la
    //    tarjeta desaparece.
    await expect(panel.getByRole('heading', { name: 'Junta de arranque' })).toBeVisible();
    await panel.getByLabel('Fecha de la junta').fill('2031-03-03');
    await panel.getByRole('button', { name: 'Declarar junta de arranque' }).click();
    await expect(panel.getByText('Iniciada', { exact: true })).toBeVisible();
    await expect(panel.getByText(/03 mar 31/i)).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Junta de arranque' })).toHaveCount(0);
  });
});
