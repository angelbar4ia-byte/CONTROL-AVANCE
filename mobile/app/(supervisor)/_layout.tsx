/**
 * Tabs del Supervisor — inspección (§5.2).
 *
 * Autoriza cierres de actividad (§4). Asignaciones NO aparece: es solo web.
 */

import { Tabs } from 'expo-router';
import {
  Building2,
  ClipboardCheck,
  ClipboardList,
  GitBranch,
  MoreHorizontal,
} from 'lucide-react-native';

import { opcionesTabs } from '@/lib/tabs';

export default function TabsSupervisor() {
  return (
    <Tabs screenOptions={opcionesTabs}>
      <Tabs.Screen
        name="torre"
        options={{ title: 'Torre', tabBarIcon: ({ color }) => <Building2 size={22} color={color} strokeWidth={1.6} /> }}
      />
      <Tabs.Screen
        name="incidencias"
        options={{ title: 'Incidencias', tabBarIcon: ({ color }) => <ClipboardList size={22} color={color} strokeWidth={1.6} /> }}
      />
      <Tabs.Screen
        name="cierres"
        options={{ title: 'Cierres', tabBarIcon: ({ color }) => <ClipboardCheck size={22} color={color} strokeWidth={1.6} /> }}
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
  );
}
