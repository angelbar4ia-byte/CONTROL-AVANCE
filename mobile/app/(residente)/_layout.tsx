/**
 * Tabs del Residente — captura en campo, offline (§5.2, §12.5).
 *
 * "Más" agrupa Frentes, Extra-catálogo, Control de materiales (lectura),
 * Autoevaluación, Guía de estimación y Expediente.
 */

import { Tabs } from 'expo-router';
import {
  ClipboardList,
  GitBranch,
  Home,
  LineChart,
  MoreHorizontal,
} from 'lucide-react-native';

import { GuardiaRol } from '@/lib/guardia';
import { opcionesTabs } from '@/lib/tabs';

export default function TabsResidente() {
  return (
    <GuardiaRol rol="residente">
      <Tabs screenOptions={opcionesTabs}>
        <Tabs.Screen
          name="obras"
          options={{ title: 'Obras', tabBarIcon: ({ color }) => <Home size={22} color={color} strokeWidth={1.6} /> }}
        />
        <Tabs.Screen
          name="avances"
          options={{ title: 'Avances', tabBarIcon: ({ color }) => <LineChart size={22} color={color} strokeWidth={1.6} /> }}
        />
        <Tabs.Screen
          name="incidencias"
          options={{ title: 'Incidencias', tabBarIcon: ({ color }) => <ClipboardList size={22} color={color} strokeWidth={1.6} /> }}
        />
        <Tabs.Screen
          name="ruta"
          options={{ title: 'Ruta', tabBarIcon: ({ color }) => <GitBranch size={22} color={color} strokeWidth={1.6} /> }}
        />
        <Tabs.Screen
          name="mas"
          options={{ title: 'Más', tabBarIcon: ({ color }) => <MoreHorizontal size={22} color={color} strokeWidth={1.6} /> }}
        />
      </Tabs>
    </GuardiaRol>
  );
}
