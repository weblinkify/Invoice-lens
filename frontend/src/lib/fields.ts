import type { DateField, InvoiceData, LineItem, NumberField, StringField } from '@/api/types';

export type FieldKind = 'string' | 'number' | 'date';
export type AnyField = StringField | NumberField | DateField;

export interface FieldMeta {
  name: keyof Omit<InvoiceData, 'line_items' | 'validation_issues' | 'needs_review'>;
  label: string;
  kind: FieldKind;
  section: 'Vendor' | 'Invoice' | 'Amounts' | 'Payment';
  mono?: boolean;
}

export const HEADER_FIELDS: readonly FieldMeta[] = [
  { name: 'vendor_name', label: 'Vendor name', kind: 'string', section: 'Vendor' },
  { name: 'vendor_vat_id', label: 'VAT ID', kind: 'string', section: 'Vendor', mono: true },
  {
    name: 'invoice_number',
    label: 'Invoice number',
    kind: 'string',
    section: 'Invoice',
    mono: true,
  },
  { name: 'invoice_date', label: 'Invoice date', kind: 'date', section: 'Invoice' },
  { name: 'due_date', label: 'Due date', kind: 'date', section: 'Invoice' },
  { name: 'currency', label: 'Currency', kind: 'string', section: 'Invoice', mono: true },
  { name: 'subtotal', label: 'Subtotal', kind: 'number', section: 'Amounts' },
  { name: 'vat_total', label: 'VAT total', kind: 'number', section: 'Amounts' },
  { name: 'total', label: 'Total', kind: 'number', section: 'Amounts' },
  { name: 'iban', label: 'IBAN', kind: 'string', section: 'Payment', mono: true },
  {
    name: 'payment_reference',
    label: 'Payment reference',
    kind: 'string',
    section: 'Payment',
    mono: true,
  },
];

export const SECTIONS = ['Vendor', 'Invoice', 'Amounts', 'Payment'] as const;

export const LINE_ITEM_FIELDS: readonly { name: keyof LineItem; label: string; kind: FieldKind }[] =
  [
    { name: 'description', label: 'Description', kind: 'string' },
    { name: 'quantity', label: 'Qty', kind: 'number' },
    { name: 'unit_price', label: 'Unit price', kind: 'number' },
    { name: 'vat_rate', label: 'VAT %', kind: 'number' },
    { name: 'line_total', label: 'Line total', kind: 'number' },
  ];

export function getField(data: InvoiceData, path: string): AnyField | undefined {
  const parts = path.split('.');
  if (parts.length === 1) {
    const meta = HEADER_FIELDS.find((f) => f.name === parts[0]);
    return meta ? data[meta.name] : undefined;
  }
  if (parts.length === 3 && parts[0] === 'line_items') {
    const item = data.line_items[Number(parts[1])];
    const leaf = LINE_ITEM_FIELDS.find((f) => f.name === parts[2]);
    return item && leaf ? item[leaf.name] : undefined;
  }
  return undefined;
}

export function fieldKind(path: string): FieldKind {
  const leaf = path.split('.').at(-1) ?? path;
  return (
    HEADER_FIELDS.find((f) => f.name === leaf)?.kind ??
    LINE_ITEM_FIELDS.find((f) => f.name === leaf)?.kind ??
    'string'
  );
}

export function fieldLabel(path: string): string {
  const parts = path.split('.');
  if (parts.length === 3) {
    const leaf = LINE_ITEM_FIELDS.find((f) => f.name === parts[2]);
    return `Line ${Number(parts[1]) + 1} ${leaf?.label.toLowerCase() ?? parts[2]}`;
  }
  return HEADER_FIELDS.find((f) => f.name === path)?.label ?? path;
}

export function toInputValue(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

/** Convert form text into the JSON value the API expects (null for empty). */
export function fromInputValue(kind: FieldKind, raw: string): string | number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (kind === 'number') {
    const n = Number(trimmed.replace(/\s/g, '').replace(',', '.'));
    return Number.isFinite(n) ? n : trimmed;
  }
  return trimmed;
}

export function allFieldPaths(data: InvoiceData): string[] {
  return [
    ...HEADER_FIELDS.map((f) => f.name),
    ...data.line_items.flatMap((_, i) => LINE_ITEM_FIELDS.map((f) => `line_items.${i}.${f.name}`)),
  ];
}
