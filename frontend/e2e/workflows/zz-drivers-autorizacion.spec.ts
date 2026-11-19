import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * Los cambios a drivers pasan por Control de obra (F3): Costos propone (queda pendiente y el valor vigente no cambia), solo Control de obra
 * autoriza (queda quién y cuándo) y lo que propone Control de obra se aplica de inmediato. El escarpio y la corona siguen fijos (F4).
 */

const ROLES_D = ['control', 'costos', 'residente'] as const;
const DRIVER = 'desperdicio_acero';

interface Propuesta {
  id: string;
  estado: string;
  clave: string;
  propuso_rol: string;
  decidio_rol: string | null;
  valor: string | null;
}
interface Driver {
  clave: string;
  valor_global: string;
  valor_vigente: string;
  inmutable: boolean;
  propuestas_pendientes: Propuesta[];
}

test.describe('Cuantificador · autorización de cambios a drivers', () => {
  test.skip(!hayRoles(...ROLES_D), motivoSinRoles(...ROLES_D));
  test.setTimeout(150_000);

  test('Costos propone, Control de obra autoriza y queda quién y cuándo; el escarpio y la corona no se cambian', async ({ page, browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `DA-${sufijo}`,
    });
    const drivers = async () =>
      Object.fromEntries((await llamarApi<Driver[]>(request, 'control', 'GET', `/obras/${obra.id}/drivers`)).map((d) => [d.clave, d]));
    const pendientes = () => llamarApi<Propuesta[]>(request, 'control', 'GET', `/drivers-propuestas?estado=pendiente&clave=${DRIVER}`);
    const limpiar = async () => {
      for (const p of await pendientes()) await llamarApi(request, 'control', 'POST', `/drivers-propuestas/${p.id}/rechazar`, {});
    };
    await limpiar();
    const antes = (await drivers())[DRIVER]!.valor_global;
    const nuevo = String(Number(antes) + 3);

    try {
      // --- Costos propone desde la pantalla --------------------------------------------------------------------------------
      await entrarComo(page, 'costos');
      await page.goto(`/cuantificador?obra=${obra.id}`);
      await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Paramétrico/ }).click();
      const tabla = page.locator('#area-parametrico').getByRole('table', { name: 'Drivers del Paramétrico' });
      const fila = tabla.locator(`tr[data-driver="${DRIVER}"]`);
      await fila.getByLabel(/^Valor global de/).fill(nuevo);
      await fila.getByLabel(/^Valor global de/).press('Enter');
      await expect(page.locator('[data-aviso-propuesta]')).toContainText('queda pendiente hasta que Control de obra lo autorice');
      await expect(fila.locator('[data-propuesta]')).toContainText(`valor ${nuevo}`);
      // Pendiente: el driver NO cambió y Costos no ve el botón de autorizar.
      expect((await drivers())[DRIVER]!.valor_global).toBe(antes);
      await expect(fila.locator('[data-vigente]')).toHaveText(antes);
      await expect(fila.getByRole('button', { name: /^Autorizar el cambio/ })).toHaveCount(0);
      const [p] = await pendientes();
      expect([p!.propuso_rol, p!.estado, p!.valor]).toEqual(['costos', 'pendiente', expect.stringContaining(nuevo)]);
      // Costos tampoco autoriza por la API (403) y no se acumulan dos propuestas del mismo driver (422).
      expect((await solicitarApi(request, 'costos', 'POST', `/drivers-propuestas/${p!.id}/autorizar`)).status()).toBe(403);
      expect((await solicitarApi(request, 'costos', 'PUT', `/drivers/${DRIVER}`, { valor: '9' })).status()).toBe(422);

      // --- Control de obra autoriza desde su pantalla ----------------------------------------------------------------------
      const control = await browser.newContext();
      const paginaControl = await control.newPage();
      try {
        await entrarComo(paginaControl, 'control');
        await paginaControl.goto(`/cuantificador?obra=${obra.id}`);
        await paginaControl.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Paramétrico/ }).click();
        const filaControl = paginaControl.locator(`#area-parametrico tr[data-driver="${DRIVER}"]`);
        await expect(filaControl.locator('[data-propuesta]')).toContainText('propuso');
        await filaControl.getByRole('button', { name: /^Autorizar el cambio/ }).click();
        await expect(filaControl.locator('[data-vigente]')).toHaveText(nuevo);
        await expect(filaControl.locator('[data-propuesta]')).toHaveCount(0);
        // La bitácora: quién propuso, quién decidió y cuándo.
        await paginaControl.locator('[data-bitacora-de-drivers] summary').click();
        const registro = paginaControl.locator('[data-bitacora-de-drivers]').locator(`[data-bitacora-propuesta="${p!.id}"]`);
        await expect(registro).toContainText('autorizada');
      } finally {
        await control.close();
      }
      expect((await drivers())[DRIVER]!.valor_global).toBe(nuevo);
      const hist = await llamarApi<Propuesta[]>(request, 'control', 'GET', `/drivers-propuestas?clave=${DRIVER}`);
      expect(hist.find((h) => h.id === p!.id)).toMatchObject({ estado: 'autorizada', propuso_rol: 'costos', decidio_rol: 'control_obra' });

      // --- Lo que propone Control de obra se aplica al instante (200) ---------------------------------------------------------
      const r = await solicitarApi(request, 'control', 'PUT', `/drivers/${DRIVER}`, { valor: antes });
      expect(r.status()).toBe(200);
      expect((await drivers())[DRIVER]!.valor_global).toBe(antes);

      // --- F4: el escarpio y la corona siguen fijos, aun para Control de obra ------------------------------------------------
      for (const clave of ['escarpio_minimo', 'corona_cimiento_cm']) {
        expect((await drivers())[clave]!.inmutable).toBe(true);
        expect((await solicitarApi(request, 'control', 'PUT', `/drivers/${clave}`, { modo: 'ajustable' })).status()).toBe(422);
        expect((await solicitarApi(request, 'control', 'PUT', `/drivers/${clave}`, { valor: '2' })).status()).toBe(422);
      }
      const escarpio = tabla.locator('tr[data-driver="escarpio_minimo"]');
      await expect(escarpio.locator('[data-inmutable]')).toBeVisible();
      await expect(escarpio.getByLabel(/^Valor global de/)).toBeDisabled();
      await expect(escarpio.getByLabel(/^Modo de/)).toBeDisabled();
      // El residente no propone ni autoriza.
      expect((await solicitarApi(request, 'residente', 'PUT', `/drivers/${DRIVER}`, { valor: '2' })).status()).toBe(403);
    } finally {
      await limpiar();
      await llamarApi(request, 'control', 'PUT', `/drivers/${DRIVER}`, { valor: antes });
    }
  });
});
