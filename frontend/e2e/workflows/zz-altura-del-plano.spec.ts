import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Ola 4C · el plano propone la altura estándar del driver al trazar un muro, no 2.6 m fijos (Q1: lo guardado la conserva).
 * La obra tiene su propio ajuste del driver `altura_estandar`; el panel «Muro · medir por» lo muestra, el trazo nace con esa
 * altura en su conversión y, si el driver cambia después, ese trazo NO se recalcula.
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · altura del driver en el plano', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('un muro trazado nace con la altura del driver de la obra y no se recalcula si el driver cambia', async ({ page, request }) => {
    const clave = `ALT-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Altura del driver',
      archivo_url: 'planos/altura.dwg',
    });
    // El ajuste de ESTA obra para la altura estándar (el global no se toca: otros specs de la misma organización lo leen).
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '2.8' });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    // El panel «Muro · medir por» propone la altura del driver de la obra; sin concepto en m² no se ofrece.
    await expect(page.getByLabel('Altura (m)')).toHaveValue('2.8');
    // El panel de opciones de la línea tapa la izquierda del lienzo: los clics van a la derecha.
    await clic(0.68, 0.85);
    await clic(0.9, 0.85);
    await expect(page.getByRole('status')).toContainText('2.8 m de altura');

    type Trazos = { features: { geometry: { type: string }; properties: { enlaces: { enlace_id: string; cantidad: string; vigente: boolean }[] } }[] };
    const leer = async () => {
      const trazos = await llamarApi<Trazos>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
      const linea = trazos.features.find((f) => f.geometry.type === 'LineString')!;
      const enlace = linea.properties.enlaces.find((e) => e.vigente)!;
      const conv = await llamarApi<{ conversion: { alt: number } }>(request, 'control', 'GET', `/enlaces/${enlace.enlace_id}/conversion`);
      return { alt: conv.conversion.alt, cantidad: Number(enlace.cantidad) };
    };
    const guardado = await leer();
    expect(guardado.alt).toBeCloseTo(2.8, 6);
    expect(guardado.cantidad).toBeGreaterThan(0);

    // Q1: el driver cambia después y lo ya guardado conserva su altura y su cantidad.
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '3.5' });
    const despues = await leer();
    expect(despues.alt).toBeCloseTo(2.8, 6);
    expect(despues.cantidad).toBeCloseTo(guardado.cantidad, 6);
  });
});
