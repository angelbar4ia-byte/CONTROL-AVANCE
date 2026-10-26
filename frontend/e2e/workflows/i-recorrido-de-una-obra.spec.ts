import {
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  solicitarApi,
  test,
} from '../infraestructura';

/**
 * El recorrido de **una** obra de punta a punta (cerebro WORKFLOWS.md §8.3, las
 * etapas 2 a 8 del App flow).
 *
 * Los otros specs prueban cada workflow aislado, sobre obras que la semilla ya
 * trae a medio camino. Este prueba lo que ellos no pueden: que las piezas
 * **encajan** — lo que sale de una etapa es justo lo que la siguiente necesita.
 *
 *   2-3  Control da de alta la obra y la genera desde su prototipo.
 *   4    Se programa: el CPM calcula la ruta crítica y reacciona a un vínculo.
 *   3    Se cuantifica sobre un plano: la medida se compara con la cantidad base,
 *        y la desviación que levanta se ve (con y sin causa) y se le captura causa.
 *   6    El residente captura avance: el avance y el estatus de la obra se derivan.
 *   8    Se cierran las actividades (residente → supervisor → control).
 *   7    El supervisor genera la estimación; control la valida.
 *   8    El cierre de obra no deja entregar con dinero sin resolver; con la
 *        estimación validada, las cuatro partes firman y la obra queda entregada.
 *
 * Es una obra nueva por corrida (clave con marca de tiempo): no consume obras
 * de la semilla ni depende de que nadie las haya tocado.
 */

const ROLES_I = ['residente', 'supervisor', 'control', 'superIntendente'] as const;

interface ActividadApi {
  id: string;
  concepto_clave: string;
  cant_base: string;
}

test.describe('§8.3 · El recorrido de una obra', () => {
  test.skip(!hayRoles(...ROLES_I), motivoSinRoles(...ROLES_I));
  test.setTimeout(120_000);

  test('de dar de alta la obra a entregarla', async ({ page, request }) => {
    const clave = `REC-${Date.now().toString(36).toUpperCase()}`;

    // --- Etapas 2 y 3: dar de alta el lugar y generar la obra ---------------
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string; rol: string }[]>(request, 'control', 'GET', '/usuarios');
    const residente = usuarios.find((u) => u.nombre === 'Rosa Residente');
    expect(residente, 'el residente de la semilla existe').toBeDefined();

    const obra = await llamarApi<{ id: string; estatus: string; avance_pct: string }>(
      request,
      'control',
      'POST',
      '/obras',
      {
        cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
        prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
        residente_id: residente!.id,
        clave,
      },
    );
    expect(obra.estatus).toBe('pendiente');
    expect(Number(obra.avance_pct)).toBe(0);

    const generada = await llamarApi<{ n_actividades: number }>(
      request,
      'control',
      'POST',
      `/obras/${obra.id}/generar`,
      { modo_pago: 'destajo' },
    );
    expect(generada.n_actividades).toBe(3);

    const actividades = await llamarApi<ActividadApi[]>(request, 'residente', 'GET', `/obras/${obra.id}/actividades`);
    const por = (clave: string) => actividades.find((a) => a.concepto_clave === clave)!;
    const excavacion = por('E2E-EXC');
    const plantilla = por('E2E-PLA');
    const cimiento = por('E2E-CIM');

    // --- Etapa 4: programar -------------------------------------------------
    const antes = await llamarApi<{ fin_programado: string }>(
      request,
      'control',
      'POST',
      `/obras/${obra.id}/ruta-critica/recalcular`,
    );
    await llamarApi(request, 'control', 'PATCH', `/actividades/${plantilla.id}/programacion`, {
      duracion_dias: '3',
      dependencias: [{ ref: excavacion.id, tipo: 'FS', lag_dias: '0' }],
    });
    const ruta = await llamarApi<{
      fin_programado: string;
      actividades: { actividad_id: string; es_critica: boolean; inicio_temprano: string; holgura: number }[];
    }>(request, 'control', 'POST', `/obras/${obra.id}/ruta-critica/recalcular`);

    // Un vínculo fin-inicio alarga la obra y pone a las dos actividades en la ruta crítica.
    expect(ruta.fin_programado > antes.fin_programado).toBe(true);
    const enRuta = (id: string) => ruta.actividades.find((a) => a.actividad_id === id)!;
    expect(enRuta(excavacion.id).es_critica).toBe(true);
    expect(enRuta(plantilla.id).es_critica).toBe(true);
    expect(enRuta(plantilla.id).inicio_temprano > enRuta(excavacion.id).inicio_temprano).toBe(true);
    // El cimiento no depende de nadie: tiene holgura y no es crítico.
    expect(enRuta(cimiento.id).es_critica).toBe(false);
    expect(enRuta(cimiento.id).holgura).toBeGreaterThan(0);

    // --- Etapa 3: cuantificar sobre el plano --------------------------------
    const plano = await llamarApi<{ id: string }>(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta del recorrido',
      archivo_url: 'e2e/recorrido.dwg',
    });
    const trazo = await llamarApi<{
      trazo_id: string;
      recalculos: { cantidad_total: string; desviacion_id: string | null }[];
    }>(request, 'residente', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'POLYGON((0 0, 10 0, 10 12, 0 12, 0 0))',
      enlaces: [{ medida: 'area', factor: '1', actividad_id: excavacion.id }],
    });
    // 10 × 12 = 120 contra una base de 100: la medida se compara y levanta una
    // desviación candidata; nunca reemplaza la cantidad base (MODELO.md §1b).
    expect(Number(trazo.recalculos[0]!.cantidad_total)).toBe(120);
    expect(trazo.recalculos[0]!.desviacion_id).not.toBeNull();
    await llamarApi(request, 'control', 'POST', `/trazos/${trazo.trazo_id}/aprobar`);
    const estado = await llamarApi<{ nodo_id: string; cant_base: string; cantidad_medida: string; diferencia: string }[]>(
      request,
      'residente',
      'GET',
      `/obras/${obra.id}/cuantificacion`,
    );
    const nodo = estado.find((n) => n.nodo_id === excavacion.id)!;
    expect(Number(nodo.cant_base)).toBe(100);
    expect(Number(nodo.cantidad_medida)).toBe(120);
    expect(Number(nodo.diferencia)).toBe(20);
    const sigueBase = (await llamarApi<ActividadApi>(request, 'residente', 'GET', `/actividades/${excavacion.id}`)).cant_base;
    expect(Number(sigueBase)).toBe(100);

    // --- Etapa 6: el avance de la obra se deriva ----------------------------
    await llamarApi(request, 'residente', 'PATCH', `/actividades/${excavacion.id}/avance`, { cant_ejecutada: '50' });
    const enProceso = await llamarApi<{ estatus: string; avance_pct: string }>(request, 'residente', 'GET', `/obras/${obra.id}`);
    expect(enProceso.estatus).toBe('en_proceso');
    expect(Number(enProceso.avance_pct)).toBeGreaterThan(0);
    expect(Number(enProceso.avance_pct)).toBeLessThan(90);

    // La desviación que levantó la medida se ve —sin causa, que es un estado
    // válido— y el residente le captura su causa; solo caben las de su factor.
    await entrarComo(page, 'residente');
    await page.goto('/desviaciones');
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    const causa = page.getByRole('combobox', { name: /^Causa de E2E-EXC/ });
    await expect(causa).toHaveValue('');
    await expect(causa.getByRole('option', { name: 'Retrabajo' })).toHaveCount(1);
    await expect(causa.getByRole('option', { name: 'Mercado' })).toHaveCount(0); // esa es de precio
    await causa.selectOption('retrabajo');
    await expect(causa).toHaveValue('retrabajo');
    await expect(page.getByText(/Rosa Residente ·/)).toBeVisible();

    // La web lo refleja: el residente ve la obra y sus actividades, con el botón de medir.
    await page.goto('/avances');
    await page.getByLabel('Obra', { exact: true }).selectOption({ label: clave });
    await page.getByRole('tab', { name: /^Todas/ }).click();
    await expect(page.getByRole('row', { name: /^E2E-EXC Excavación de cepas/ }).getByRole('button', { name: 'Medir' })).toBeVisible();

    // --- Etapa 8: cerrar las actividades ------------------------------------
    for (const [actividad, cantidad] of [
      [excavacion, 100],
      [plantilla, 80],
      [cimiento, 60],
    ] as const) {
      await llamarApi(request, 'residente', 'PATCH', `/actividades/${actividad.id}/avance`, { cant_ejecutada: cantidad });
      const cierre = await llamarApi<{ id: string }>(request, 'residente', 'POST', `/actividades/${actividad.id}/cierre`, {
        cantidad,
        checklist: [{ item: 'Recorrido', ok: true }],
        adjuntos: ['r2://evidencias/recorrido.jpg'],
      });
      await llamarApi(request, 'supervisor', 'POST', `/cierres/${cierre.id}/autorizar`);
      await llamarApi(request, 'control', 'POST', `/cierres/${cierre.id}/validar`, { comentario: 'Recorrido' });
    }
    const porEntregar = await llamarApi<{ estatus: string; avance_pct: string }>(request, 'residente', 'GET', `/obras/${obra.id}`);
    expect(porEntregar.estatus).toBe('por_entregar');
    expect(Number(porEntregar.avance_pct)).toBe(100);

    // --- Etapa 7: estimar ---------------------------------------------------
    const estimacion = await llamarApi<{ id: string; estatus: string; monto_total: string }>(
      request,
      'supervisor',
      'POST',
      `/obras/${obra.id}/estimaciones`,
      { modo: 'destajo' },
    );
    expect(estimacion.estatus).toBe('borrador');
    expect(Number(estimacion.monto_total)).toBeGreaterThan(0);

    // --- Etapa 8: entregar --------------------------------------------------
    const acta = await llamarApi<{ id: string }>(request, 'superIntendente', 'POST', `/obras/${obra.id}/cierre-obra`);
    for (const rol of ['residente', 'supervisor', 'control'] as const) {
      await llamarApi(request, rol, 'POST', `/cierres-obra/${acta.id}/participar`, { comentario: 'Conforme' });
    }
    // Con una estimación sin validar hay dinero sin resolver: la firma final se rechaza.
    const bloqueada = await solicitarApi(request, 'superIntendente', 'POST', `/cierres-obra/${acta.id}/participar`, {
      comentario: 'Entrego',
    });
    expect(bloqueada.status()).toBe(422);
    expect(await bloqueada.text()).toContain('estimación(es) sin validar');
    expect((await llamarApi<{ estatus: string }>(request, 'superIntendente', 'GET', `/obras/${obra.id}`)).estatus).toBe(
      'por_entregar',
    );

    await llamarApi(request, 'supervisor', 'PATCH', `/estimaciones/${estimacion.id}`, { estatus: 'enviada' });
    await llamarApi(request, 'control', 'POST', `/estimaciones/${estimacion.id}/validar`);

    await llamarApi(request, 'superIntendente', 'POST', `/cierres-obra/${acta.id}/participar`, { comentario: 'Entrego' });
    const entregada = await llamarApi<{ estatus: string; avance_pct: string }>(request, 'superIntendente', 'GET', `/obras/${obra.id}`);
    expect(entregada.estatus).toBe('entregada');
    expect(Number(entregada.avance_pct)).toBe(100);

    // Una obra entregada queda congelada: ya no se puede editar (§11.3 D).
    const congelada = await solicitarApi(request, 'control', 'PATCH', `/obras/${obra.id}`, { m2: 1 });
    expect(congelada.status()).toBe(409);
  });
});
