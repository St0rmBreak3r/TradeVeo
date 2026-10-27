import { describe, expect, it } from 'vitest';
import { addDecimal, compareDecimal, formatCurrencyDecimal } from './decimal';

describe('decimal text helpers', () => {
  it('adds decimal strings without floating-point drift', () => {
    expect(addDecimal('0.1', '0.2')).toBe('0.3');
    expect(addDecimal('-1.25', '0.3')).toBe('-0.95');
  });

  it('compares values at different scales exactly', () => {
    expect(compareDecimal('0.10000000000000001', '0.1')).toBe(1);
    expect(compareDecimal('-0.01', '0')).toBe(-1);
    expect(compareDecimal('10.00', '10')).toBe(0);
  });

  it('formats values with currency-specific symbols and decimal rounding', () => {
    expect(formatCurrencyDecimal('0.1', 'USD')).toContain('0.10');
    expect(formatCurrencyDecimal('-3', 'GBP')).toContain('3.00');
    expect(formatCurrencyDecimal('1.235', 'USD')).toContain('1.24');
  });
});
