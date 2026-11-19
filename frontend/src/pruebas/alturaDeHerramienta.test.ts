import { describe, expect, it } from 'vitest';

import { ALTURA_DE_HERRAMIENTA_M, alturaBaseDeLaPlantilla } from '@/cuantificador/alturaDeHerramienta';
import { opcionesDeMuroIniciales } from '@/cuantificador/trazoPeticion';
import { vanoPorDefecto } from '@/cuantificador/vanos';

describe('Altura del plano: la herramienta y la altura base del artefacto (sin el driver altura_estandar)', () => {
  it('la de la herramienta es 3.00 m, ya no 2.6', () => {
    expect(ALTURA_DE_HERRAMIENTA_M).toBe(3);
    expect(opcionesDeMuroIniciales().alt).toBe('3');
  });

  it('la altura base de una plantilla es la suya; sin altura o con un valor que no vale es null', () => {
    expect(alturaBaseDeLaPlantilla('2.800')).toBe(2.8);
    expect(alturaBaseDeLaPlantilla(3.2)).toBe(3.2);
    expect(alturaBaseDeLaPlantilla(null)).toBeNull();
    expect(alturaBaseDeLaPlantilla(undefined)).toBeNull();
    expect(alturaBaseDeLaPlantilla('0')).toBeNull();
    expect(alturaBaseDeLaPlantilla('x')).toBeNull();
  });

  it('el castillo se propone con la altura del muro; los demás vanos no cambian', () => {
    expect(vanoPorDefecto('castillo').alto).toBe(3);
    expect(vanoPorDefecto('castillo', 2.6).alto).toBe(2.6);
    expect(vanoPorDefecto('puerta', 2.6).alto).toBe(2.1);
  });
});

describe('La plantilla de muro viaja con el trazo para que su altura base cuente al nacer', () => {
  it('una línea con grosor manda muro_plantilla_id; sin grosor o sin plantilla no', async () => {
    const { trazoPeticion } = await import('@/cuantificador/trazoPeticion');
    const base = { versionPlano: 1, herramienta: 'linea' as const, puntos: [[0, 0], [10, 0]] as [number, number][], enlaces: [] };
    const conGrosor = { ...base, grosorM: 0.15, alineacion: 'centro' as const };
    expect(trazoPeticion({ ...conGrosor, muroPlantillaId: 'p-1' }).muro_plantilla_id).toBe('p-1');
    expect(trazoPeticion({ ...conGrosor, muroPlantillaId: null })).not.toHaveProperty('muro_plantilla_id');
    expect(trazoPeticion({ ...base, muroPlantillaId: 'p-1' })).not.toHaveProperty('muro_plantilla_id');
  });
});
