import { describe, expect, it } from 'vitest';
import { TIMELINE_DAYS, TIMELINE_MINUTES, TIMELINE_END, clampMinute, dayOf, isoDate, monthOf } from './time';

describe('шкала до конца 2027', () => {
  it('включает все 365 дней 2027 и ограничивает перемотку последней минутой', () => {
    expect(TIMELINE_DAYS).toBe(1095);
    expect(isoDate(TIMELINE_DAYS - 1)).toBe('2027-12-31');
    expect(dayOf(TIMELINE_END) - dayOf('2027-01-01') + 1).toBe(365);
    expect(clampMinute(dayOf('2028-01-01') * 1440)).toBe(TIMELINE_MINUTES - 1);
    expect(monthOf(dayOf('2027-12-31')).days).toBe(31);
  });
});
