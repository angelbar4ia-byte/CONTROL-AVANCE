import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * El visor encuadra el plano sobre su contenido cuando llega (y avisa con `data-encuadre="listo"`), pero no salta bajo las
 * manos de quien está colocando cosas: guardar su primer trazo en un plano vacío no cambia la vista (antes acercaba a ese único
 * punto —1.16 unidades de ancho— y el castillo siguiente caía en otra escala, con el primero fuera de la vista).
 */

const ROLES_EV = ['control'] as const;

test.describe('Cuantificador · encuadre del visor', () => {
  test.skip(!hayRoles(...ROLES_EV), motivoSinRoles(...ROLES_EV));
  test.setTimeout(120_000);

  test('un plano con trazos se encuadra y uno vacío no salta al colocar el primero', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ENC-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const conTrazos = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'Con trazos', archivo_url: 'planos/con.dwg' });
    await llamarApi(request, 'control', 'POST', `/planos/${conTrazos.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: 'LINESTRING(400 300, 460 300)',
      enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
    });
    const vacio = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'Vacío', archivo_url: 'planos/vacio.dwg' });
    const clave = `KE-${sufijo}`.slice(0, 20);
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo del encuadre', tipo: 'castillo', parametros: { alto: 6 + (Date.now() % 1_000_000) / 1e7 }, // rango propio (6.0 a 6.1): ningún otro spec lo usa
    });

    await entrarComo(page, 'control');
    const visor = page.locator('svg.visor');
    const vista = async () => (await visor.getAttribute('viewBox'))!;

    // 1. Con trazos: se encuadra sobre ellos (no se queda en la vista de partida) y lo dice.
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${conTrazos.id}`);
    await expect(page.locator('svg.visor[data-encuadre="listo"]')).toBeVisible();
    expect(await vista()).not.toBe('0 0 1000 700');
    const [x] = (await vista()).split(' ').map(Number);
    expect(x).toBeGreaterThan(300);

    // 2. Vacío: sigue «pendiente» y, al colocar el primer trazo, la vista no cambia.
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${vacio.id}`);
    await expect(visor).toHaveAttribute('data-encuadre', 'pendiente');
    const antes = await vista();
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Colocar ${clave} en el plano` }).click();
    const c = (await visor.boundingBox())!;
    await page.mouse.click(c.x + c.width * 0.7, c.y + c.height * 0.4);
    await expect(page.getByRole('status')).toContainText(`${clave} colocado`);
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
    expect(await vista()).toBe(antes);
  });
});
