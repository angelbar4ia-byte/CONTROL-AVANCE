/**
 * Feature Catálogos · APU (§3.3, §3.5, §7.3, §10.8, §11.2).
 *
 * Se fijan las cuatro piezas que no viven en los componentes (§12.11): los
 * permisos por rol que refleja el contrato (`reglas.ts`), la prioridad de
 * CLAVE en la búsqueda (`busqueda.ts`), el armado del árbol de la explosión
 * y la lectura del estado del CPU (`explosion.ts`), y la traducción
 * formulario ↔ DTO (`formulario.ts`).
 */

import { describe, expect, it } from 'vitest';

import type {
  ConceptoRespuesta,
  CPURespuesta,
  FamiliaRespuesta,
  InsumoRespuesta,
  LineaExplosionRespuesta,
  PrecioUnitarioRespuesta,
  VersionCPURespuesta,
} from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import { buscarPorClave, filtrarPorClave, soloPorDescripcion } from '@/catalogos/busqueda';
import {
  armarArbolExplosion,
  contarLineas,
  estadoCPU,
  variantesDelHistorial,
} from '@/catalogos/explosion';
import {
  ivaOpcional,
  parsearSinonimos,
  peticionInsumo,
  peticionMaterial,
  peticionVersionCPU,
  precioIncompleto,
  numeroOpcional,
  textoOpcional,
} from '@/catalogos/formulario';
import {
  etiquetaCategoria,
  etiquetaTipoConcepto,
  etiquetaTipoInsumo,
  ivaDelInsumo,
  puedeAdministrarCatalogos,
  puedeConsultarAPU,
  puedePublicarCPU,
  tonoEstatusCatalogo,
} from '@/catalogos/reglas';

const ROLES: readonly Rol[] = ['residente', 'supervisor', 'control_obra', 'super_intendente'];

function precio(total: string, destajo: string, materiales: string): PrecioUnitarioRespuesta {
  return { total, destajo, materiales };
}

function linea(
  ruta: readonly string[],
  referencia: string,
  extra: Partial<LineaExplosionRespuesta> = {},
): LineaExplosionRespuesta {
  return {
    ruta: [...ruta],
    nivel: ruta.length,
    tipo_hijo: 'insumo',
    referencia,
    categoria: 'material',
    cantidad_unitaria: '1',
    cantidad: '1',
    costo_unitario: '10',
    importe: '10',
    es_destajo: false,
    ...extra,
  };
}

function version(
  n: number,
  total: string,
  destajo: string,
  extra: Partial<VersionCPURespuesta> = {},
): VersionCPURespuesta {
  return {
    version: n,
    variante: null,
    vigente: false,
    precio: precio(total, destajo, '0'),
    ...extra,
  };
}

describe('permisos por rol (§11.2, bloque "Catálogos · APU")', () => {
  it('el alta y la lista de catálogos son solo de Control de obra', () => {
    expect(ROLES.filter(puedeAdministrarCatalogos)).toEqual(['control_obra']);
  });

  it('la consulta del APU (CPU y explosión) es de Control de obra y Super intendente', () => {
    expect(ROLES.filter(puedeConsultarAPU)).toEqual(['control_obra', 'super_intendente']);
  });

  it('publicar una versión de CPU es solo de Control de obra', () => {
    expect(ROLES.filter(puedePublicarCPU)).toEqual(['control_obra']);
  });

  it('el Super intendente lee el APU pero no lo publica ni edita catálogos', () => {
    expect(puedeConsultarAPU('super_intendente')).toBe(true);
    expect(puedePublicarCPU('super_intendente')).toBe(false);
    expect(puedeAdministrarCatalogos('super_intendente')).toBe(false);
  });
});

describe('etiquetas del diccionario (§8.2, invariantes del §8.7)', () => {
  it('traduce los tipos e insumos canónicos', () => {
    expect(etiquetaTipoInsumo('mano_obra')).toBe('Mano de obra');
    expect(etiquetaTipoConcepto('auxiliar')).toBe('Auxiliar');
    expect(etiquetaTipoConcepto('matriz')).toBe('Matriz');
    expect(etiquetaCategoria('subcontrato')).toBe('Subcontrato');
  });

  it('un valor desconocido no rompe la UI', () => {
    expect(etiquetaTipoInsumo('inventado')).toBe('inventado');
    expect(etiquetaCategoria('inventada')).toBe('inventada');
    expect(tonoEstatusCatalogo('inventado')).toBe('outline');
  });

  it('la baja lógica se distingue del alta (§8.7)', () => {
    expect(tonoEstatusCatalogo('activo')).toBe('ok');
    expect(tonoEstatusCatalogo('inactivo')).toBe('outline');
  });
});

describe('prioridad de CLAVE en la búsqueda (§3.3)', () => {
  const insumos = [
    { clave: 'MAT-CEMENTO', descripcion: 'Cemento gris' },
    { clave: 'MAT-002', descripcion: 'Cemento blanco' },
    { clave: 'CEM', descripcion: 'Aglutinante' },
    { clave: 'CEM-01', descripcion: 'Otro' },
  ];

  const descripcionDe = (item: { descripcion: string }) => item.descripcion;

  it('la clave manda: exacta, luego por inicio, luego parcial y al final descripción', () => {
    const resultados = buscarPorClave(insumos, 'cem', descripcionDe);
    expect(resultados.map((r) => r.item.clave)).toEqual([
      'CEM',
      'CEM-01',
      'MAT-CEMENTO',
      'MAT-002',
    ]);
    expect(resultados.map((r) => r.coincidencia)).toEqual([
      'clave_exacta',
      'clave_inicio',
      'clave_parcial',
      'descripcion',
    ]);
  });

  it('marca lo que entró solo por descripción, para que se note (§3.3)', () => {
    const resultados = buscarPorClave(insumos, 'blanco', descripcionDe);
    expect(resultados).toHaveLength(1);
    expect(resultados[0]?.item.clave).toBe('MAT-002');
    expect(soloPorDescripcion(resultados[0]!.coincidencia)).toBe(true);
  });

  it('sin aguja no filtra ni reordena: manda el orden del servidor', () => {
    const resultados = buscarPorClave(insumos, '   ', descripcionDe);
    expect(resultados.map((r) => r.item.clave)).toEqual(insumos.map((i) => i.clave));
  });

  it('ignora mayúsculas y acentos del texto de UI', () => {
    const conceptos = [{ clave: 'EST-01', descripcion: 'Cimentación corrida' }];
    expect(filtrarPorClave(conceptos, 'CIMENTACION', descripcionDe)).toHaveLength(1);
    expect(filtrarPorClave(conceptos, 'est-01', descripcionDe)).toHaveLength(1);
  });

  it('lo que no casa por ningún lado se queda fuera', () => {
    expect(filtrarPorClave(insumos, 'varilla', descripcionDe)).toEqual([]);
  });
});

describe('IVA por familia con override por insumo (§3.5)', () => {
  const familiaGravada: Pick<FamiliaRespuesta, 'iva_aplica'> = { iva_aplica: true };
  const familiaExenta: Pick<FamiliaRespuesta, 'iva_aplica'> = { iva_aplica: false };

  it('sin override, hereda de la familia', () => {
    expect(ivaDelInsumo({ iva_aplica: null }, familiaGravada)).toEqual({
      aplica: true,
      origen: 'familia',
    });
    expect(ivaDelInsumo({ iva_aplica: null }, familiaExenta)).toEqual({
      aplica: false,
      origen: 'familia',
    });
  });

  it('el override del insumo gana sobre su familia, en los dos sentidos', () => {
    expect(ivaDelInsumo({ iva_aplica: false }, familiaGravada)).toEqual({
      aplica: false,
      origen: 'insumo',
    });
    expect(ivaDelInsumo({ iva_aplica: true }, familiaExenta)).toEqual({
      aplica: true,
      origen: 'insumo',
    });
  });

  it('un override en `false` no se confunde con "sin override"', () => {
    // El bug clásico: `iva_aplica ?? familia` está bien, `|| familia` no.
    expect(ivaDelInsumo({ iva_aplica: false }, familiaGravada).origen).toBe('insumo');
  });

  it('sin familia y sin override no inventa un valor', () => {
    expect(ivaDelInsumo({ iva_aplica: null }, undefined)).toEqual({
      aplica: null,
      origen: 'sin_definir',
    });
    // La familia puede venir sin el campo (`iva_aplica` es opcional en el
    // contrato); eso tampoco define nada.
    expect(ivaDelInsumo({ iva_aplica: null }, { iva_aplica: undefined })).toEqual({
      aplica: null,
      origen: 'sin_definir',
    });
  });
});

describe('árbol de la explosión (§7.3)', () => {
  it('anida los componentes de un auxiliar bajo su concepto', () => {
    const arbol = armarArbolExplosion([
      linea(['EST-01'], 'MAT-01'),
      linea(['EST-01'], 'AUX-01', { tipo_hijo: 'concepto', categoria: 'auxiliar' }),
      linea(['EST-01', 'AUX-01'], 'MAT-02'),
      linea(['EST-01', 'AUX-01'], 'MOA-01', { categoria: 'mano_obra', es_destajo: true }),
      linea(['EST-01'], 'MOA-02', { categoria: 'mano_obra', es_destajo: true }),
    ]);

    expect(arbol.map((n) => n.linea.referencia)).toEqual(['MAT-01', 'AUX-01', 'MOA-02']);
    expect(arbol[1]?.hijos.map((n) => n.linea.referencia)).toEqual(['MAT-02', 'MOA-01']);
    expect(arbol[0]?.hijos).toEqual([]);
    expect(contarLineas(arbol)).toBe(5);
  });

  it('anida en profundidad: matriz dentro de auxiliar', () => {
    const arbol = armarArbolExplosion([
      linea(['EST-01'], 'AUX-01', { tipo_hijo: 'concepto', categoria: 'auxiliar' }),
      linea(['EST-01', 'AUX-01'], 'MTZ-01', { tipo_hijo: 'concepto', categoria: 'matriz' }),
      linea(['EST-01', 'AUX-01', 'MTZ-01'], 'MAT-09'),
    ]);

    expect(arbol).toHaveLength(1);
    expect(arbol[0]?.hijos[0]?.hijos[0]?.linea.referencia).toBe('MAT-09');
    expect(contarLineas(arbol)).toBe(3);
  });

  it('un concepto sin composición da un árbol vacío', () => {
    expect(armarArbolExplosion([])).toEqual([]);
    expect(contarLineas([])).toBe(0);
  });

  it('una línea con nivel imposible no se pierde: cuelga de la raíz', () => {
    const arbol = armarArbolExplosion([
      linea(['EST-01'], 'MAT-01'),
      { ...linea(['EST-01', 'AUX-01', 'MTZ-01'], 'MAT-09'), nivel: 3 },
    ]);
    expect(arbol.map((n) => n.linea.referencia)).toEqual(['MAT-01', 'MAT-09']);
  });

  it('no recompone importes: la línea llega tal cual del backend', () => {
    const original = linea(['EST-01'], 'MOA-01', {
      categoria: 'mano_obra',
      es_destajo: true,
      cantidad_unitaria: '0.5',
      cantidad: '1.5',
      costo_unitario: '250.0000',
      importe: '375.0000',
    });
    const [nodo] = armarArbolExplosion([original]);
    expect(nodo?.linea).toBe(original);
  });
});

describe('estado del CPU vigente (§10.8)', () => {
  function cpu(
    vigente: VersionCPURespuesta | null,
    calculado: PrecioUnitarioRespuesta,
    historial: readonly VersionCPURespuesta[] = [],
  ): CPURespuesta {
    return {
      concepto_id: 'c1',
      clave: 'EST-01',
      variante: null,
      vigente,
      historial: [...historial],
      calculado,
    };
  }

  it('sin versión publicada lo dice, no finge que está al día', () => {
    expect(estadoCPU(cpu(null, precio('120', '40', '80')))).toBe('sin_vigente');
  });

  it('vigente igual al calculado = al día', () => {
    const v = version(3, '120', '40', { vigente: true });
    expect(estadoCPU(cpu(v, precio('120', '40', '80')))).toBe('al_dia');
  });

  it('la escala decimal no crea un falso desfase ("120.0000" === "120")', () => {
    const v = version(3, '120.0000', '40.0000', { vigente: true });
    expect(estadoCPU(cpu(v, precio('120', '40', '80')))).toBe('al_dia');
  });

  it('si cambió el catálogo el precio calculado difiere: desfasado', () => {
    const v = version(3, '120', '40', { vigente: true });
    expect(estadoCPU(cpu(v, precio('135', '40', '95')))).toBe('desfasado');
  });

  it('un destajo distinto también es desfase, aunque el total coincida', () => {
    const v = version(3, '120', '40', { vigente: true });
    expect(estadoCPU(cpu(v, precio('120', '55', '65')))).toBe('desfasado');
  });

  it('lista las variantes del historial sin repetir y sin la receta base', () => {
    const historial = [
      version(1, '100', '30'),
      version(2, '110', '35', { variante: 'ALTA' }),
      version(3, '115', '35', { variante: 'ALTA' }),
      version(4, '118', '36', { variante: 'BAJA' }),
    ];
    expect(variantesDelHistorial(cpu(null, precio('0', '0', '0'), historial))).toEqual([
      'ALTA',
      'BAJA',
    ]);
  });
});

describe('formulario ↔ DTO (§11.2, DTOs en el borde)', () => {
  it('normaliza vacíos a null', () => {
    expect(textoOpcional('  ')).toBeNull();
    expect(textoOpcional('  EST-01 ')).toBe('EST-01');
    expect(numeroOpcional('')).toBeNull();
    expect(numeroOpcional('no-es-numero')).toBeNull();
    expect(numeroOpcional('120.5')).toBe(120.5);
  });

  it('el IVA vacío es "hereda de la familia" (null), no "no aplica" (§3.5)', () => {
    expect(ivaOpcional('')).toBeNull();
    expect(ivaOpcional('si')).toBe(true);
    expect(ivaOpcional('no')).toBe(false);
  });

  it('los sinónimos aceptan líneas o comas y se deduplican (§3.5, §10.3)', () => {
    expect(parsearSinonimos('m2\n mts2 ,m2, \n M2')).toEqual(['m2', 'mts2', 'M2']);
    expect(parsearSinonimos('  \n , ')).toEqual([]);
  });

  it('el insumo lleva su tipo; el material no (§7.3: material = insumo tipo material)', () => {
    const formulario = {
      clave: ' MAT-01 ',
      descripcion: ' Cemento ',
      tipo: 'material' as const,
      unidadId: 'u1',
      familiaId: '',
      costoBase: '250',
      iva: 'no' as const,
      factorConversion: '',
    };

    const insumo = peticionInsumo(formulario);
    expect(insumo).toEqual({
      clave: 'MAT-01',
      descripcion: 'Cemento',
      tipo: 'material',
      unidad_id: 'u1',
      familia_id: null,
      costo_base: 250,
      iva_aplica: false,
      factor_conversion: undefined,
    });

    expect('tipo' in peticionMaterial(formulario)).toBe(false);
  });

  it('publicar sin precio deja que el backend lo calcule de la explosión (§7.3)', () => {
    expect(peticionVersionCPU({ variante: '', precioUnitario: '', precioDestajo: '' })).toEqual({
      variante: null,
      precio_unitario: null,
      precio_destajo: null,
    });
  });

  it('un precio explícito viaja completo: total y destajo', () => {
    const formulario = { variante: ' ALTA ', precioUnitario: '120', precioDestajo: '40' };
    expect(peticionVersionCPU(formulario)).toEqual({
      variante: 'ALTA',
      precio_unitario: 120,
      precio_destajo: 40,
    });
    expect(precioIncompleto(formulario)).toBe(false);
  });

  it('capturar solo uno de los dos precios se avisa antes de enviar (§7.3)', () => {
    expect(precioIncompleto({ variante: '', precioUnitario: '120', precioDestajo: '' })).toBe(
      true,
    );
    expect(precioIncompleto({ variante: '', precioUnitario: '', precioDestajo: '40' })).toBe(
      true,
    );
    expect(precioIncompleto({ variante: '', precioUnitario: '', precioDestajo: '' })).toBe(false);
  });
});

describe('tipos del contrato que la UI consume tal cual', () => {
  it('un concepto y un insumo se buscan por su clave, no por su id', () => {
    const concepto: ConceptoRespuesta = {
      id: 'c1',
      tipo: 'auxiliar',
      clave: 'AUX-01',
      descripcion: 'Mortero',
    };
    const insumo: InsumoRespuesta = {
      id: 'i1',
      tipo: 'material',
      clave: 'MAT-01',
      descripcion: 'Cemento',
    };

    expect(filtrarPorClave([concepto], 'AUX', (c) => c.descripcion)).toHaveLength(1);
    expect(filtrarPorClave([insumo], 'c1', (i) => i.descripcion)).toHaveLength(0);
  });
});
