import { describe, expect, it } from 'vitest';
import { useStore } from './store';
import { applyUiAction } from './uiActions';
import { dayIndex, isoDate } from '../lib/time';

describe('команды агента для даты и объекта', () => {
  it('переключает выбранный маршрут и остановку на всю сеть за 2027', () => {
    useStore.getState().selectRoute(17);
    useStore.getState().selectStop('g2594');
    applyUiAction({ type: 'show', network: true, date: '2027-01-01', horizon: 'year' });
    const state = useStore.getState();
    expect(state.route).toBeNull();
    expect(state.stop).toBeNull();
    expect(state.horizon).toBe('year');
    expect(isoDate(dayIndex(state.minute))).toBe('2027-01-01');
  });
  it('показывает сутки вместо ранее выбранного месяца', () => {
    useStore.getState().setHorizon('month');
    applyUiAction({ type: 'show', route: 1, date: '2027-10-08', horizon: 'day' });
    expect(useStore.getState().horizon).toBe('day');
    expect(useStore.getState().route).toBe(1);
    expect(isoDate(dayIndex(useStore.getState().minute))).toBe('2027-10-08');
  });
});
