/**
 * Punto de entrada de la SPA.
 *
 * Spec §12.2 (React + Vite) · §12.9 (render en cliente, sin SSR).
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from '@/app/App';
import '@/estilos/obractrl-design.css';

const contenedor = document.getElementById('root');
if (!contenedor) throw new Error('Falta #root en index.html');

createRoot(contenedor).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
