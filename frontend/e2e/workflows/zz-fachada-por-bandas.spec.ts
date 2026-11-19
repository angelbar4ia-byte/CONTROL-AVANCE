import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La fachada por BANDAS de altura (F1): el panel de la pestaña Trazos reparte los m² de cara exterior de los muros reales en la banda baja
 * (0 a 3.00), la media («+3.00», de 3.00 a 4.20) y el resto, según las zonas de losa, los puntos de nivel exterior y la ubicación de cada muro.
 * Cada m² cae en una sola banda y lo que pinta la pantalla es lo que calcula el servidor (no hay selector ni cantidad aparte).
 *
 * Dos cuartos de 6 × 4 m: el de 3.00 de x 0 a 6 y el de 4.20 de x 6 a 12 (y de -4 a 0).
 */

const ROLES_F = ['control', 'costos'] as const;

type Api = Parameters<typeof llamarApi>[0];
interface Banda {
  banda: string;
  neto_m2: string;
}
interface Fachada {
  bandas: Banda[];
  neto_m2: string;
  muros: { trazo_id: string; origen_de_caras: string }[];
  muros_sin_cara_exterior: { trazo_id: string }[];
}

async function nuevaObra(request: Api, prefijo: string) {
  const sufijo = Date.now().toString(36).toUpperCase();
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'PB', archivo_url: `planos/${prefijo}.dwg` });
  const trazo = (wkt: string, extra: Record<string, unknown> = {}) =>
    llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, { version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [], ...extra });
  const muro = (wkt: string) => trazo(wkt, { grosor_m: '0.15', alineacion: 'centro' });
  const fachada = () => llamarApi<Fachada>(request, 'control', 'GET', `/planos/${plano.id}/fachada-por-bandas`);
  return { obra, plano, trazo, muro, fachada };
}

async function conDosCuartos(request: Api, prefijo: string) {
  const o = await nuevaObra(request, prefijo);
  for (const [nombre, altura, espesor, wkt] of [
    ['Entrepiso 3.00', '3.00', '0.12', 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'],
    ['Entrepiso 4.20', '4.20', '0.20', 'POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))'],
  ] as const) {
    const z = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${o.plano.id}/zonas-de-losa`, { nombre, altura_libre_m: altura, espesor_m: espesor });
    const losa = await o.trazo(wkt);
    await llamarApi(request, 'control', 'PUT', `/trazos/${losa.trazo_id}/losa`, { zona_id: z.id });
  }
  return o;
}

const netos = (f: Fachada) => Object.fromEntries(f.bandas.map((b) => [b.banda, Number(b.neto_m2)]));

test.describe('Cuantificador · fachada por bandas de altura', () => {
  test.skip(!hayRoles(...ROLES_F), motivoSinRoles(...ROLES_F));
  test.setTimeout(180_000);

  test('el panel reparte la cara exterior en bandas y sigue al punto de nivel exterior que se coloca en el plano', async ({ page, request }) => {
    const { obra, plano, muro, fachada } = await conDosCuartos(request, 'FB');
    // Borde de arriba del cuarto de 4.20: la cara A mira afuera (exterior), la B adentro. Zona de 4.20: 6 m × 3.00 y 6 m × 1.20.
    const exterior = await muro('LINESTRING(6 -4, 12 -4)');
    expect(netos(await fachada())).toEqual({ baja: 18, media: 7.2, resto: 0 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panel = page.locator('[data-fachada-por-bandas]');
    const neto = (banda: string) => panel.locator(`[data-fachada-banda="${banda}"] [data-neto]`);
    await expect(neto('baja')).toHaveText('18.00');
    await expect(neto('media')).toHaveText('7.20');
    await expect(neto('resto')).toHaveText('0.00');
    await expect(panel.locator('[data-fachada-total] [data-neto]')).toHaveText('25.20');
    await expect(panel).toContainText('zona de losa');

    // Un punto de nivel exterior de -0.30 m, colocado con un clic justo afuera del muro (a unos 30 px): la cara mide 4.50 m desde su suelo.
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);
    await expect(page.locator('svg.visor[data-encuadre="listo"]')).toBeVisible();
    const marca = (await page.locator(`[data-trazo-id="${exterior.trazo_id}"]`).boundingBox())!;
    const zonas = page.getByTestId('zonas-de-losa');
    await zonas.getByLabel('Cota del punto de nivel').fill('-0.30');
    await zonas.getByLabel('Rótulo del punto de nivel').fill('Banqueta');
    await zonas.getByRole('button', { name: 'Colocar punto de nivel exterior' }).click();
    await page.mouse.click(Math.min(Math.max(marca.x + marca.width / 2, c.x + 5), c.x + c.width - 5), Math.max(marca.y - 30, c.y + 5));
    await expect.poll(async () => (await fachada()).bandas.find((b) => b.banda === 'resto')?.neto_m2).toBe('1.80');
    await page.keyboard.press('Escape');
    // La pantalla repite lo que dice el servidor (se vuelve a pedir sola cuando cambian los trazos).
    await expect(neto('baja')).toHaveText('18.00');
    await expect(neto('media')).toHaveText('7.20');
    await expect(neto('resto')).toHaveText('1.80');
    await expect(panel.locator('[data-fachada-total] [data-neto]')).toHaveText('27.00');
    expect(netos(await fachada())).toEqual({ baja: 18, media: 7.2, resto: 1.8 });
  });

  test('sin zonas, la fachada sigue la ubicación y la altura del muro real; un muro sin caras definidas avisa y no se cuenta', async ({ page, request }) => {
    const { obra, plano, muro, fachada } = await nuevaObra(request, 'FU');
    const fachadaA = await muro('LINESTRING(0 10, 5 10)');
    await llamarApi(request, 'control', 'PUT', `/trazos/${fachadaA.trazo_id}/muro/clasificacion`, { tipo: 'confinado', ubicacion: 'fachada_a' });
    // La altura real del muro manda: 4.50 m × 5 m de largo = 15 + 6 + 1.5.
    await llamarApi(request, 'control', 'PUT', `/trazos/${fachadaA.trazo_id}/muro`, { altura_m: '4.5', caras: 2 });
    const sinCaras = await muro('LINESTRING(0 14, 4 14)');
    const interior = await muro('LINESTRING(0 16, 4 16)');
    await llamarApi(request, 'control', 'PUT', `/trazos/${interior.trazo_id}/muro/clasificacion`, { tipo: 'confinado', ubicacion: 'interior' });
    const f = await fachada();
    expect(netos(f)).toEqual({ baja: 15, media: 6, resto: 1.5 });
    expect(f.muros_sin_cara_exterior.map((m) => m.trazo_id).sort()).toEqual([sinCaras.trazo_id, interior.trazo_id].sort());

    await entrarComo(page, 'costos'); // todos los roles que ven el plano leen
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panel = page.locator('[data-fachada-por-bandas]');
    await expect(panel.locator('[data-fachada-banda="baja"] [data-neto]')).toHaveText('15.00');
    await expect(panel.locator('[data-fachada-banda="media"] [data-neto]')).toHaveText('6.00');
    await expect(panel.locator('[data-fachada-banda="resto"] [data-neto]')).toHaveText('1.50');
    await expect(panel.locator('[data-fachada-total] [data-neto]')).toHaveText('22.50');
    await expect(panel).toContainText('ubicación');
    await expect(panel.locator('[data-fachada-sin-cara]')).toContainText('2 muros sin cara exterior definida no se cuentan');
  });
});
