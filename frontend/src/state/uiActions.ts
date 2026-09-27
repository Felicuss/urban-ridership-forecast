import type { UiAction } from '../lib/agent';
import { TIMELINE_DAYS, dayOf } from '../lib/time';
import { useStore, type Flags } from './store';

// Команды агента интерфейсу (ui_show, ui_layers, ui_ride MCP-сервера) применяются к состоянию так же,
// как клики диспетчера. MCP-сервер уже проверил параметры; здесь вторая линия: неизвестное пропускается.

const LAYERS = new Set<keyof Flags>(['heat', 'lines', 'stops', 'trams', 'metro', 'buildings', 'weather', 'daylight',
  'labels', 'satellite']);

export function applyUiAction(action: UiAction): void {
  const s = useStore.getState();
  if (action.type === 'show') {
    const day = action.date ? dayOf(action.date) : -1;
    if (day >= 0 && day < TIMELINE_DAYS) s.setDay(day);
    if (action.hour != null) useStore.getState().setHour(action.hour);
    if (action.network) s.selectRoute(null);
    else if (action.route != null) s.selectRoute(action.route);
    if (!action.network && action.stop) useStore.getState().selectStop(action.stop);
    if (action.view) s.setViewMode(action.view);
    if (action.horizon) s.setHorizon(action.horizon);
    if (action.tab) s.setTab(action.tab);
    return;
  }
  if (action.type === 'layers') {
    for (const key of action.enable ?? []) if (LAYERS.has(key as keyof Flags)) s.setFlag(key as keyof Flags, true);
    for (const key of action.disable ?? []) if (LAYERS.has(key as keyof Flags)) s.setFlag(key as keyof Flags, false);
    if (action.hideRoutes) s.setHiddenRoutes(action.hideRoutes);
    return;
  }
  s.selectRoute(action.route);
  s.startRide(action.route, action.direction ?? 0);
}
