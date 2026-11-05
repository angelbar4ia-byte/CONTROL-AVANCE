import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';


/** La barra de funciones (deshacer, escala, lo que se muestra, la vista del plano): va aparte de la de trazo. */
const funciones = (page: import('@playwright/test').Page) => page.getByRole('toolbar', { name: 'Funciones' });

/**
 * Herramientas de takeoff del cuantificador (Fase 1):
 *
 *  1. Una línea con pendiente mide más que su planta: largo × √(1 + p²), y la cota lo dice.
 *  2. «Copiar en lote» repite una pieza (un castillo) con los mismos enlaces, sin abrir el cajón, y
 *     Ctrl+Z deshace la última copia.
 *  3. Las anotaciones: un texto suelto, una flecha y una llamada, además de la nota.
 *  4. Girar y voltear el plano: se guarda con el plano, no cambia ninguna cantidad, y dibujar o
 *     elegir sobre el plano girado cae donde se ve.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_V = ['control'] as const;

type Geo = { type: string; coordinates: unknown };
interface Feature {
  id: string;
  geometry: Geo;
  properties: { forma?: unknown; enlaces: { cantidad: string; medida: string; actividad_id?: string; nodo_id: string }[] };
}

async function obraNueva(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const clave = `${prefijo}-${Date.now().toString(36).toUpperCase()}`;
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
    clave,
  });
  const actividades = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  return { obra, actividades };
}

test.describe('Cuantificador · herramientas de takeoff', () => {
  test.skip(!hayRoles(...ROLES_V), motivoSinRoles(...ROLES_V));
  test.setTimeout(150_000);

  test('una línea con pendiente mide más que su planta', async ({ page, request }) => {
    const { obra } = await obraNueva(request, 'PEN');
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Cubierta',
      archivo_url: 'planos/cubierta.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo).toBeVisible();
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });

    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    const opciones = page.getByRole('region', { name: 'Opciones de la línea' });
    await opciones.getByRole('button', { name: '33 %' }).click();
    await expect(opciones.getByRole('button', { name: '33 %' })).toHaveAttribute('aria-pressed', 'true');

    // Las opciones se pliegan a su cabecera para dejar libre el plano, y se recuerda.
    const cabeza = opciones.getByRole('button', { name: 'Línea' });
    await cabeza.click();
    await expect(cabeza).toHaveAttribute('aria-expanded', 'false');
    await expect(opciones.getByRole('button', { name: '33 %' })).toHaveCount(0);

    const c = (await lienzo.boundingBox())!;
    await page.mouse.click(c.x + c.width * 0.3, c.y + c.height * 0.6);
    await page.mouse.click(c.x + c.width * 0.8, c.y + c.height * 0.6);

    const alta = page.getByRole('dialog', { name: 'Guardar línea' });
    await expect(alta.getByTestId('aviso-pendiente')).toContainText('33 %');
    const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByLabel('Medida').selectOption('longitud');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');

    const { features } = await llamarApi<{ features: (Feature & { properties: { pendiente_pct: string } })[] }>(
      request,
      'control',
      'GET',
      `/planos/${plano.id}/trazos`,
    );
    const coords = features[0]!.geometry.coordinates as [number, number][];
    const planta = Math.hypot(coords[1]![0] - coords[0]![0], coords[1]![1] - coords[0]![1]);
    expect(Number(features[0]!.properties.pendiente_pct)).toBe(33);
    expect(Number(features[0]!.properties.enlaces[0]!.cantidad)).toBeCloseTo(planta * Math.sqrt(1 + 0.33 ** 2), 3);

    // La cota (y la etiqueta) escriben el largo real, no el de la planta.
    await funciones(page).getByRole('button', { name: 'Cota', exact: true }).click();
    const cota = Number((await page.getByTestId('cotas').locator('text').first().textContent())!.replace(/[^\d.]/g, ''));
    expect(cota).toBeCloseTo(planta * Math.sqrt(1 + 0.33 ** 2), 1);
  });

  test('copiar en lote repite una pieza con sus enlaces y se deshace', async ({ page, request }) => {
    const { obra, actividades } = await obraNueva(request, 'COP');
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Castillos',
      archivo_url: 'planos/castillos.dwg',
    });
    // Un muro grande que da el encuadre y un castillo (forma estampada) enlazado a conteo.
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 200 0, 200 100, 0 100, 0 0))',
      enlaces: [],
    });
    const castillo = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((20 20, 30 20, 30 30, 20 30, 20 20))',
      forma: { tipo: 'cuadrado', ancho_m: '0.15', alto_m: '0.15', rotacion_grados: '0', nombre: 'Castillo' },
      enlaces: [{ actividad_id: actividades[0]!.id, medida: 'conteo', factor: '1' }],
    });
    const trazos = async () =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(page.locator('.visor__trazo')).toHaveCount(2);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });

    // Sin pieza elegida no se puede copiar.
    await expect(barra.getByRole('button', { name: 'Copiar en lote', exact: true })).toBeDisabled();

    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const caja = (await page.locator(`[data-trazo-id="${castillo.trazo_id}"]`).boundingBox())!;
    await page.mouse.click(caja.x + caja.width / 2, caja.y + caja.height / 2);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await expect(barra.getByRole('button', { name: 'Copiar en lote', exact: true })).toBeEnabled();
    await barra.getByRole('button', { name: 'Copiar en lote', exact: true }).click();

    const c = (await lienzo.boundingBox())!;
    for (const [i, fx] of [0.45, 0.6, 0.75].entries()) {
      await page.mouse.click(c.x + c.width * fx, c.y + c.height * 0.65);
      await expect(page.getByRole('status')).toContainText(`Copia ${i + 1} hecha`);
    }
    await expect.poll(async () => (await trazos()).length).toBe(5);
    const copias = (await trazos()).filter((f) => f.id !== castillo.trazo_id && f.properties.forma);
    expect(copias).toHaveLength(3);
    for (const k of copias) {
      expect(k.properties.enlaces).toHaveLength(1);
      expect(k.properties.enlaces[0]!.medida).toBe('conteo');
      expect(k.properties.enlaces[0]!.nodo_id).toBe(actividades[0]!.id);
    }

    // Ctrl+Z quita la última copia.
    await page.keyboard.press('Escape'); // termina el lote
    await page.keyboard.press('Control+z');
    await expect.poll(async () => (await trazos()).length).toBe(4);
  });

  test('anotaciones: texto, flecha y llamada', async ({ page, request }) => {
    const { obra } = await obraNueva(request, 'ANO');
    const plano = await llamarApi<{ id: string }>(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Anotado',
      archivo_url: 'planos/anotado.dwg',
    }).catch(() => null);
    test.skip(plano === null, 'El residente de la semilla no ve esta obra.');

    await entrarComo(page, 'residente');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano!.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo).toBeVisible();
    const c = (await lienzo.boundingBox())!;
    const en = (fx: number, fy: number) => ({ x: c.x + c.width * fx, y: c.y + c.height * fy });

    await page.getByRole('button', { name: 'Nota', exact: true }).click();
    const opciones = page.getByRole('region', { name: 'Opciones de la anotación' });

    // Texto suelto.
    await opciones.getByRole('button', { name: 'Texto' }).click();
    await page.mouse.click(en(0.5, 0.4).x, en(0.5, 0.4).y);
    let alta = page.getByRole('dialog', { name: /Anotar el plano/ });
    await alta.getByLabel('Texto', { exact: true }).fill('Eje A');
    await alta.getByRole('button', { name: 'Guardar texto' }).click();
    await expect(page.getByRole('status')).toContainText('Texto guardada');
    await expect(page.locator('.visor__anotacion[data-tipo="texto"] text')).toHaveText('Eje A');

    // Flecha: dos clics, texto opcional (se guarda vacía).
    await opciones.getByRole('button', { name: 'Flecha' }).click();
    await page.mouse.click(en(0.4, 0.6).x, en(0.4, 0.6).y);
    await page.mouse.click(en(0.6, 0.7).x, en(0.6, 0.7).y);
    alta = page.getByRole('dialog', { name: /Anotar el plano/ });
    await alta.getByRole('button', { name: 'Guardar flecha' }).click();
    await expect(page.locator('.visor__anotacion[data-tipo="flecha"] path')).toHaveCount(1);

    // Llamada: lo que señala y dónde va el texto.
    await opciones.getByRole('button', { name: 'Llamada' }).click();
    await page.mouse.click(en(0.7, 0.3).x, en(0.7, 0.3).y);
    await page.mouse.click(en(0.8, 0.5).x, en(0.8, 0.5).y);
    alta = page.getByRole('dialog', { name: /Anotar el plano/ });
    await alta.getByLabel('Llamada', { exact: true }).fill('Registro sanitario');
    await alta.getByRole('button', { name: 'Guardar llamada' }).click();
    await expect(page.locator('.visor__anotacion[data-tipo="llamada"] text')).toHaveText('Registro sanitario');

    const notas = await llamarApi<{ tipo: string; texto: string; destino: unknown }[]>(
      request,
      'residente',
      'GET',
      `/planos/${plano!.id}/notas`,
    );
    expect(notas.map((n) => n.tipo)).toEqual(['texto', 'flecha', 'llamada']);
    expect(notas[0]!.destino).toBeNull();
    expect(notas[1]!.destino).not.toBeNull();
    expect(notas[1]!.texto).toBe('');
    expect(notas[2]!.destino).not.toBeNull();
  });

  test('girar y voltear el plano se guarda y no cambia lo que se elige ni lo que se mide', async ({
    page,
    request,
  }) => {
    const { obra, actividades } = await obraNueva(request, 'VIS');
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Vista',
      archivo_url: 'planos/vista.dwg',
    });
    const sala = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 40 0, 40 20, 0 20, 0 0))',
      enlaces: [{ actividad_id: actividades[0]!.id, medida: 'area', factor: '1' }],
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((100 60, 140 60, 140 80, 100 80, 100 60))',
      enlaces: [],
    });
    const cantidad = async () =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features.find(
        (f) => f.id === sala.trazo_id,
      )!.properties.enlaces[0]!.cantidad;
    const antes = await cantidad();

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const girado = page.getByTestId('plano-girado');
    await expect(girado).toHaveAttribute('data-rotacion', '0');
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });

    await funciones(page).getByRole('button', { name: 'Girar el plano a la derecha' }).click();
    await expect(girado).toHaveAttribute('data-rotacion', '90');
    await funciones(page).getByRole('button', { name: 'Voltear el plano de izquierda a derecha' }).click();
    await expect(girado).toHaveAttribute('data-volteo', 'h');

    // Se guardó con el plano.
    await expect
      .poll(async () => {
        const planos = await llamarApi<{ id: string; rotacion_grados: number; volteo_horizontal: boolean }[]>(
          request,
          'control',
          'GET',
          `/obras/${obra.id}/planos`,
        );
        const p = planos.find((x) => x.id === plano.id)!;
        return [p.rotacion_grados, p.volteo_horizontal];
      })
      .toEqual([90, true]);
    expect(await cantidad()).toBe(antes);

    // Elegir un trazo sobre el plano girado: el clic cae en lo que se ve.
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const caja = (await page.locator(`[data-trazo-id="${sala.trazo_id}"]`).boundingBox())!;
    await page.mouse.click(caja.x + caja.width / 2, caja.y + caja.height / 2);
    await expect(page.getByText('Trazo elegido')).toBeVisible();

    // Un punto puesto en el centro de la sala, tal como se ve, cae dentro de la sala en el plano.
    await barra.getByRole('button', { name: 'Punto', exact: true }).click();
    const c = (await lienzo.boundingBox())!;
    expect(c.width).toBeGreaterThan(0);
    await page.mouse.click(caja.x + caja.width / 2, caja.y + caja.height / 2);
    const alta = page.getByRole('dialog', { name: 'Guardar punto' });
    const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    const puntos = (
      await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)
    ).features.filter((f) => f.geometry.type === 'Point');
    const [x, y] = puntos[0]!.geometry.coordinates as [number, number];
    expect(x).toBeGreaterThan(0);
    expect(x).toBeLessThan(40);
    expect(y).toBeGreaterThan(0);
    expect(y).toBeLessThan(20);

    // Se recuerda al recargar, y se puede regresar a como estaba.
    await page.reload();
    await expect(page.getByTestId('plano-girado')).toHaveAttribute('data-rotacion', '90');
    await funciones(page).getByRole('button', { name: 'Girar el plano a la izquierda' }).click();
    await funciones(page).getByRole('button', { name: 'Voltear el plano de izquierda a derecha' }).click();
    await expect(page.getByTestId('plano-girado')).toHaveAttribute('data-rotacion', '0');
    await expect(page.getByTestId('plano-girado')).toHaveAttribute('data-volteo', '');
  });
});
