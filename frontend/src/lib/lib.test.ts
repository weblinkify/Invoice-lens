import fixtures from '@/mocks/fixtures.json';
import type { InvoiceData } from '@/api/types';
import { confidenceBand } from './confidence';
import {
  allFieldPaths,
  fieldKind,
  fieldLabel,
  fromInputValue,
  getField,
  toInputValue,
} from './fields';
import { formatBytes, formatDate, formatDateTime, formatMoney, pct } from './utils';
import { thresholdSchema, validateField, webhookSchema } from './validation';

const data = (fixtures as unknown as Record<string, { extraction: { data: InvoiceData } }>)
  .invoice_02!.extraction.data;

describe('fields', () => {
  it('reads header and line item fields', () => {
    expect(getField(data, 'currency')?.value).toBe('SEK');
    expect(getField(data, 'line_items.0.quantity')?.value).toBe(4);
    expect(getField(data, 'line_items.99.quantity')).toBeUndefined();
    expect(getField(data, 'nope')).toBeUndefined();
    expect(getField(data, 'a.b')).toBeUndefined();
  });

  it('describes fields', () => {
    expect(fieldKind('line_items.1.unit_price')).toBe('number');
    expect(fieldKind('due_date')).toBe('date');
    expect(fieldKind('unknown')).toBe('string');
    expect(fieldLabel('iban')).toBe('IBAN');
    expect(fieldLabel('line_items.2.vat_rate')).toBe('Line 3 vat %');
    expect(fieldLabel('mystery')).toBe('mystery');
    expect(allFieldPaths(data)).toHaveLength(11 + data.line_items.length * 5);
  });

  it('converts form values', () => {
    expect(toInputValue(null)).toBe('');
    expect(toInputValue(12.5)).toBe('12.5');
    expect(fromInputValue('number', ' 1 234,50 ')).toBe(1234.5);
    expect(fromInputValue('number', 'abc')).toBe('abc');
    expect(fromInputValue('string', '  ')).toBeNull();
    expect(fromInputValue('date', '2026-01-02')).toBe('2026-01-02');
  });
});

describe('validation', () => {
  it.each([
    ['total', 'number', '12,50', true],
    ['total', 'number', 'twelve', 'Enter a number, e.g. 1234.50'],
    ['due_date', 'date', '2026-13-45', 'Use the format YYYY-MM-DD'],
    ['due_date', 'date', '', true],
    ['currency', 'string', 'EURO', 'Use a 3-letter ISO code (EUR)'],
    ['iban', 'string', 'FI21 1234 5600 0007 85', true],
    ['iban', 'string', '12345', 'IBAN should look like FI21 1234 5600 0007 85'],
    ['vendor_name', 'string', 'x'.repeat(300), 'Keep it under 255 characters'],
  ] as const)('%s=%s', (path, kind, value, expected) => {
    expect(validateField(path, kind, value)).toBe(expected);
  });

  it('validates forms', () => {
    expect(webhookSchema.safeParse({ url: 'nope', secret: 'short' }).success).toBe(false);
    expect(webhookSchema.safeParse({ url: 'https://x.io/h', secret: 'long-enough' }).success).toBe(
      true,
    );
    expect(thresholdSchema.safeParse({ threshold: 2 }).success).toBe(false);
  });
});

describe('utils', () => {
  it('formats values', () => {
    expect(formatMoney(1234.5, 'EUR')).toBe('€1,234.50');
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(5, 'NOT')).toMatch(/^NOT\s5\.00$/);
    expect(formatMoney(5, 'bad code')).toBe('5.00 bad code');
    expect(formatDate('2026-03-05')).toBe('5 Mar 2026');
    expect(formatDate(null)).toBe('—');
    expect(formatDate('garbage')).toBe('garbage');
    expect(formatDateTime('garbage')).toBe('garbage');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('2026-03-05T10:00:00Z')).toContain('2026');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB');
    expect(pct(0.756)).toBe('76%');
    expect(confidenceBand(0.5, 0.8)).toBe('medium');
  });
});
