/**
 * Feature Proyecto · Cluster · Obra (§4, §7.2, §11.2, §11.3 A).
 *
 * Se fijan las tres piezas que no viven en los componentes (§12.11):
 * los permisos por rol que refleja el contrato (`reglas.ts`), el armado del
 * árbol (`arbol.ts`) y la traducción formulario ↔ DTO (`formulario.ts`).
 */

import { describe, expect, it } from 'vitest';

import type {
  ClusterRespuesta,
  ObraRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
} from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import {
  construirArbol,
  filtrarObrasPorTexto,
  proyectoDeCluster,
  prototiposDeProyecto,
} from '@/proyectos/arbol';
import {
  cambiosDeObra,
  formularioDeObra,
  hayCambios,
  numeroOpcional,
  obrasDelLote,
  parsearClavesLote,
  textoOpcional,
} from '@/proyectos/formulario';
import {
  etiquetaEstatusObra,
  impedimentoParaGenerar,
  obraCongelada,
  puedeAdministrarObras,
  puedeConfigurarEstructura,
  puedeDeclararJuntaDeArranque,
  puedeEditarObra,
  tonoEstatusObra,
} from '@/proyectos/reglas';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

function proyecto(id: string, clave: string): ProyectoRespuesta {
  return { id, clave, nombre: `Proyecto ${clave}` };
}

function cluster(id: string, proyectoId: string, clave: string): ClusterRespuesta {
  return { id, proyecto_id: proyectoId, clave, nombre: `Manzana ${clave}` };
}

function obra(id: string, clusterId: string, clave: string, extra: Partial<ObraRespuesta> = {}): ObraRespuesta {
  return {
    id,
    cluster_id: clusterId,
    prototipo_id: 'proto-1',
    clave,
    residente_id: null,
    estatus: 'pendiente',
    fecha_inicio: null,
    fecha_fin: null,
    avance_pct: '0',
    m2: null,
    es_urba: false,
    ...extra,
  };
}

describe('permisos por rol (§11.2, bloque "Proyecto · Obra")', () => {
  it('proyecto, cluster y prototipo son de Control de obra y Super intendente', () => {
    const pueden = ROLES.filter(puedeConfigurarEstructura);
    expect(pueden).toEqual(['control_obra', 'super_intendente']);
  });

  it('el alta y la edición de obras son solo del creador de obra (C)', () => {
    const pueden = ROLES.filter(puedeAdministrarObras);
    expect(pueden).toEqual(['control_obra']);
  });

  it('el Super intendente configura la estructura pero no crea obras', () => {
    expect(puedeConfigurarEstructura('super_intendente')).toBe(true);
    expect(puedeAdministrarObras('super_intendente')).toBe(false);
  });
});

describe('obra entregada = congelada (§11.3 D.3)', () => {
  it('una obra entregada ya no se edita ni se regenera', () => {
    const entregada = obra('o1', 'c1', 'FRESNO 01', { estatus: 'entregada' });
    expect(obraCongelada(entregada)).toBe(true);
    expect(puedeEditarObra('control_obra', entregada)).toBe(false);
    expect(impedimentoParaGenerar('control_obra', entregada)).toBe('congelada');
  });

  it('Control de obra edita una obra en proceso', () => {
    const enProceso = obra('o1', 'c1', 'FRESNO 01', { estatus: 'en_proceso' });
    expect(puedeEditarObra('control_obra', enProceso)).toBe(true);
    expect(puedeEditarObra('supervisor', enProceso)).toBe(false);
  });
});

describe('la junta de arranque (D-537)', () => {
  it('solo Control de obra la declara, y solo con la obra pendiente', () => {
    const pendiente = obra('o1', 'c1', 'FRESNO 01', { estatus: 'pendiente' });
    expect(ROLES.filter((rol) => puedeDeclararJuntaDeArranque(rol, pendiente))).toEqual([
      'control_obra',
    ]);
  });

  it('una obra que ya arrancó no ofrece la junta', () => {
    for (const estatus of ['iniciada', 'en_proceso', 'por_entregar', 'entregada']) {
      const ya = obra('o1', 'c1', 'FRESNO 01', { estatus });
      expect(puedeDeclararJuntaDeArranque('control_obra', ya)).toBe(false);
    }
  });
});

describe('impedimentoParaGenerar (Workflow A, §11.3 A.2)', () => {
  it('sin prototipo no hay árbol que recorrer (urbanización, §7.2)', () => {
    const urba = obra('o1', 'c1', 'URBA 01', { prototipo_id: null, es_urba: true });
    expect(impedimentoParaGenerar('control_obra', urba)).toBe('sin_prototipo');
  });

  it('solo Control de obra genera', () => {
    const lista = obra('o1', 'c1', 'FRESNO 01');
    expect(impedimentoParaGenerar('control_obra', lista)).toBeNull();
    expect(impedimentoParaGenerar('super_intendente', lista)).toBe('rol');
    expect(impedimentoParaGenerar('residente', lista)).toBe('rol');
  });
});

describe('estatus de obra (§8.2)', () => {
  it('mapea los 5 estatus canónicos a un tono y una etiqueta', () => {
    expect(tonoEstatusObra('pendiente')).toBe('outline');
    expect(tonoEstatusObra('iniciada')).toBe('info');
    expect(tonoEstatusObra('en_proceso')).toBe('accent');
    expect(tonoEstatusObra('por_entregar')).toBe('warn');
    expect(tonoEstatusObra('entregada')).toBe('ok');
    expect(etiquetaEstatusObra('por_entregar')).toBe('Por entregar');
  });

  it('un estatus desconocido no rompe la UI', () => {
    expect(tonoEstatusObra('inventado')).toBe('outline');
    expect(etiquetaEstatusObra('inventado')).toBe('inventado');
  });
});

describe('construirArbol (§7.2)', () => {
  const proyectos = [proyecto('p1', 'ALAMOS'), proyecto('p2', 'ROBLES')];
  const clusters = [cluster('c1', 'p1', 'FRESNO'), cluster('c2', 'p1', 'OLMO'), cluster('c3', 'p2', 'CEDRO')];
  const obras = [
    obra('o1', 'c1', 'FRESNO 01'),
    obra('o2', 'c1', 'FRESNO 02'),
    obra('o3', 'c3', 'CEDRO 01'),
  ];

  it('anida clusters y obras bajo su proyecto y cuenta las obras', () => {
    const arbol = construirArbol(proyectos, clusters, obras);

    expect(arbol.proyectos).toHaveLength(2);
    expect(arbol.proyectos[0]?.proyecto.clave).toBe('ALAMOS');
    expect(arbol.proyectos[0]?.nObras).toBe(2);
    expect(arbol.proyectos[0]?.clusters).toHaveLength(2);
    expect(arbol.proyectos[0]?.clusters[0]?.obras.map((o) => o.clave)).toEqual([
      'FRESNO 01',
      'FRESNO 02',
    ]);
    expect(arbol.proyectos[1]?.nObras).toBe(1);
  });

  it('no inventa un avance agregado: solo cuenta nodos (§6)', () => {
    const arbol = construirArbol(proyectos, clusters, obras);
    expect(Object.keys(arbol.proyectos[0] ?? {})).toEqual(['proyecto', 'clusters', 'nObras']);
  });

  it('las obras sin cluster conocido no se pierden', () => {
    const arbol = construirArbol(proyectos, [cluster('c1', 'p1', 'FRESNO')], obras);
    expect(arbol.sinCluster.map((o) => o.clave)).toEqual(['CEDRO 01']);
  });

  it('con ocultarVacios descarta ramas sin obras (al filtrar)', () => {
    const arbol = construirArbol(proyectos, clusters, [obra('o1', 'c1', 'FRESNO 01')], {
      ocultarVacios: true,
    });
    expect(arbol.proyectos).toHaveLength(1);
    expect(arbol.proyectos[0]?.clusters.map((c) => c.cluster.clave)).toEqual(['FRESNO']);
  });

  it('sin ocultarVacios conserva proyectos y clusters vacíos', () => {
    const arbol = construirArbol(proyectos, clusters, []);
    expect(arbol.proyectos).toHaveLength(2);
    expect(arbol.proyectos[0]?.clusters).toHaveLength(2);
  });
});

describe('filtros y selects encadenados', () => {
  it('filtra obras por clave sin distinguir mayúsculas', () => {
    const obras = [obra('o1', 'c1', 'FRESNO 01'), obra('o2', 'c3', 'CEDRO 01')];
    expect(filtrarObrasPorTexto(obras, 'fresno').map((o) => o.clave)).toEqual(['FRESNO 01']);
    expect(filtrarObrasPorTexto(obras, '  ')).toHaveLength(2);
  });

  it('resuelve el proyecto de un cluster', () => {
    const clusters = [cluster('c1', 'p1', 'FRESNO')];
    expect(proyectoDeCluster(clusters, 'c1')).toBe('p1');
    expect(proyectoDeCluster(clusters, 'desconocido')).toBeNull();
  });

  it('los prototipos se acotan al proyecto; sin proyecto no ofrece ninguno', () => {
    const prototipos: readonly PrototipoRespuesta[] = [
      { id: 'pr1', proyecto_id: 'p1', clave: 'CAS-A', nombre: 'Modelo A' },
      { id: 'pr2', proyecto_id: 'p2', clave: 'CAS-B', nombre: 'Modelo B' },
    ];
    expect(prototiposDeProyecto(prototipos, 'p1').map((p) => p.clave)).toEqual(['CAS-A']);
    expect(prototiposDeProyecto(prototipos, null)).toEqual([]);
  });
});

describe('formulario ↔ DTO (§11.2)', () => {
  it('normaliza vacíos a null', () => {
    expect(textoOpcional('  ')).toBeNull();
    expect(textoOpcional(' FRESNO 01 ')).toBe('FRESNO 01');
    expect(numeroOpcional('')).toBeNull();
    expect(numeroOpcional('no-es-numero')).toBeNull();
    expect(numeroOpcional('72.5')).toBe(72.5);
  });

  it('el PATCH solo lleva lo que cambió', () => {
    const original = obra('o1', 'c1', 'FRESNO 01', { m2: '72.50', fecha_inicio: '2026-03-09' });
    const formulario = formularioDeObra(original);

    expect(hayCambios(cambiosDeObra(original, formulario))).toBe(false);
    expect(cambiosDeObra(original, { ...formulario, clave: 'FRESNO 02' })).toEqual({
      clave: 'FRESNO 02',
    });
  });

  it('vaciar el residente manda null explícito (libera la obra)', () => {
    const original = obra('o1', 'c1', 'FRESNO 01', { residente_id: 'u1' });
    const cambios = cambiosDeObra(original, { ...formularioDeObra(original), residenteId: '' });
    expect(cambios).toEqual({ residente_id: null });
    expect('residente_id' in cambios).toBe(true);
  });

  it('m2 se compara como número, no como texto ("72.50" === 72.5)', () => {
    const original = obra('o1', 'c1', 'FRESNO 01', { m2: '72.50' });
    const formulario = formularioDeObra(original);
    expect(cambiosDeObra(original, formulario)).toEqual({});
    expect(cambiosDeObra(original, { ...formulario, m2: '80' })).toEqual({ m2: 80 });
  });

  it('una clave vacía no borra la clave: el PATCH la omite', () => {
    const original = obra('o1', 'c1', 'FRESNO 01');
    expect(cambiosDeObra(original, { ...formularioDeObra(original), clave: '   ' })).toEqual({});
  });
});

describe('alta masiva (§11.2 POST /obras/bulk)', () => {
  it('una clave por línea, sin vacíos, avisando repetidas', () => {
    const { claves, duplicadas } = parsearClavesLote(
      'FRESNO 01\n  FRESNO 02  \n\nFRESNO 01\nFRESNO 03\n',
    );
    expect(claves).toEqual(['FRESNO 01', 'FRESNO 02', 'FRESNO 03']);
    expect(duplicadas).toEqual(['FRESNO 01']);
  });

  it('texto vacío no arma lote', () => {
    expect(parsearClavesLote('\n  \n').claves).toEqual([]);
  });

  it('repite los datos comunes en cada obra del lote', () => {
    const lote = obrasDelLote(
      { cluster_id: 'c1', prototipo_id: 'pr1', es_urba: false },
      ['FRESNO 01', 'FRESNO 02'],
    );
    expect(lote).toEqual([
      { cluster_id: 'c1', prototipo_id: 'pr1', es_urba: false, clave: 'FRESNO 01' },
      { cluster_id: 'c1', prototipo_id: 'pr1', es_urba: false, clave: 'FRESNO 02' },
    ]);
  });
});
