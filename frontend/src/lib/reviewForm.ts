import type { InvoiceData } from '@/api/types';
import { HEADER_FIELDS, LINE_ITEM_FIELDS, toInputValue } from './fields';

export type LineValues = Record<(typeof LINE_ITEM_FIELDS)[number]['name'], string>;
export type ReviewValues = Record<(typeof HEADER_FIELDS)[number]['name'], string> & {
  line_items: LineValues[];
};

export function toFormValues(data: InvoiceData): ReviewValues {
  const header = Object.fromEntries(
    HEADER_FIELDS.map((f) => [f.name, toInputValue(data[f.name].value)]),
  ) as Record<(typeof HEADER_FIELDS)[number]['name'], string>;
  return {
    ...header,
    line_items: data.line_items.map(
      (item) =>
        Object.fromEntries(
          LINE_ITEM_FIELDS.map((f) => [f.name, toInputValue(item[f.name].value)]),
        ) as LineValues,
    ),
  };
}
