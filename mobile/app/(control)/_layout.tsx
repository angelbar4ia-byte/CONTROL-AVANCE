/**
 * Tabs de Control de obra — revisión física en campo (§5.2).
 *
 * SOLO revisión: fotos, comentarios y calidad de los trabajos. Toda la
 * configuración (catálogos, presupuesto, programas, cargas) es solo web.
 */

import { Tabs } from 'expo-router';
import { Camera, Home, ShieldCheck, ClipboardCheck } from 'lucide-react-native';

import { opcionesTabs } from '@/lib/tabs';

export default function TabsControl() {
  return (
    <Tabs screenOptions={opcionesTabs}>
      <Tabs.Screen
        name="obras"
        options={{ title: 'Obras', tabBarIcon: ({ color }) => <Home size={22} color={color} strokeWidth={1.6} /> }}
      />
      <Tabs.Screen
        name="revision"
        options={{ title: 'Revisión', tabBarIcon: ({ color }) => <ClipboardCheck size={22} color={color} strokeWidth={1.6} /> }}
      />
      <Tabs.Screen
        name="fotos"
        options={{ title: 'Fotos', tabBarIcon: ({ color }) => <Camera size={22} color={color} strokeWidth={1.6} /> }}
      />
      <Tabs.Screen
        name="calidad"
        options={{ title: 'Calidad', tabBarIcon: ({ color }) => <ShieldCheck size={22} color={color} strokeWidth={1.6} /> }}
      />
    </Tabs>
  );
}
