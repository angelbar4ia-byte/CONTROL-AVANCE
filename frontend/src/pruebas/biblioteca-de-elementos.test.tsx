/**
 * La biblioteca de elementos del Cuantificador: plegable por categoría y subcategoría, con «Expandir todo» y
 * «Contraer todo», y abierta por defecto en la categoría del elemento elegido.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { CategoriaDeBiblioteca } from '@/api/generado/modelo';
import { BibliotecaDeElementos } from '@/cuantificador/elementos/BibliotecaDeElementos';

const MCT = {
  clave: 'MCT-01010',
  nombre: 'Muro de piedra',
  tipo: 'muro_de_contencion_de_piedra',
  se_mide_por: 'metro lineal de trazo',
  concepto: { clave: 'MCT-01011', descripcion: 'MURO DE MAMPOSTERÍA DE PIEDRA DE CERRO', unidad: 'm3' },
};
const CATEGORIAS: CategoriaDeBiblioteca[] = [
  {
    clave: 'contencion',
    nombre: 'Muros de contención',
    prefijo: 'MCT',
    subcategorias: [{ clave: 'mamposteria', nombre: 'Mampostería', prefijo: 'MCT', elementos: [MCT] }],
  },
  {
    clave: 'otra',
    nombre: 'Otra categoría',
    prefijo: 'OT',
    subcategorias: [{ clave: 'sub', nombre: 'Subcategoría', prefijo: 'OT', elementos: [] }],
  },
];

describe('BibliotecaDeElementos', () => {
  it('abre por defecto la categoría del elemento elegido y deja cerrada la otra', () => {
    render(<BibliotecaDeElementos categorias={CATEGORIAS} elegida="MCT-01010" onElegir={vi.fn()} />);
    expect(screen.getByRole('button', { name: /MCT-01010/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Muros de contención/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Otra categoría/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Subcategoría')).not.toBeInTheDocument();
  });

  it('Expandir todo abre todo y Contraer todo lo cierra', () => {
    render(<BibliotecaDeElementos categorias={CATEGORIAS} elegida="MCT-01010" onElegir={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Expandir todo' }));
    expect(screen.getByText('Subcategoría')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Contraer todo' }));
    expect(screen.queryByRole('button', { name: /MCT-01010/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Muros de contención/ })).toHaveAttribute('aria-expanded', 'false');
  });

  it('elegir un elemento avisa su clave', () => {
    const onElegir = vi.fn();
    render(<BibliotecaDeElementos categorias={CATEGORIAS} elegida={null} onElegir={onElegir} />);
    fireEvent.click(screen.getByRole('button', { name: /Muros de contención/ }));
    fireEvent.click(screen.getByRole('button', { name: /Mampostería/ }));
    fireEvent.click(screen.getByRole('button', { name: /MCT-01010/ }));
    expect(onElegir).toHaveBeenCalledWith('MCT-01010');
  });
});
