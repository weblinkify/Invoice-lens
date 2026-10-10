import { z } from 'zod';
import type { FieldKind } from './fields';

const numberText = z
  .string()
  .trim()
  .refine((v) => v === '' || Number.isFinite(Number(v.replace(/\s/g, '').replace(',', '.'))), {
    message: 'Enter a number, e.g. 1234.50',
  });

const dateText = z
  .string()
  .trim()
  .refine((v) => v === '' || (/^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v))), {
    message: 'Use the format YYYY-MM-DD',
  });

const kindSchemas: Record<FieldKind, z.ZodType<string>> = {
  string: z.string().max(255, 'Keep it under 255 characters'),
  number: numberText,
  date: dateText,
};

const fieldSchemas: Record<string, z.ZodType<string>> = {
  currency: z
    .string()
    .trim()
    .refine((v) => v === '' || /^[A-Za-z]{3}$/.test(v), {
      message: 'Use a 3-letter ISO code (EUR)',
    }),
  iban: z
    .string()
    .trim()
    .refine((v) => v === '' || /^[A-Za-z]{2}\d{2}[A-Za-z0-9 ]{8,40}$/.test(v), {
      message: 'IBAN should look like FI21 1234 5600 0007 85',
    }),
};

/** Validate a reviewer's input for a field; returns true or an error message (RHF `validate`). */
export function validateField(path: string, kind: FieldKind, value: string): true | string {
  const schema = fieldSchemas[path] ?? kindSchemas[kind];
  const result = schema.safeParse(value);
  return result.success ? true : (result.error.issues[0]?.message ?? 'Invalid value');
}

export const webhookSchema = z.object({
  url: z.url({ message: 'Enter a full URL, e.g. https://erp.example.com/hooks' }),
  secret: z.string().min(8, 'Use at least 8 characters').max(255),
  description: z.string().max(255).optional(),
});
export type WebhookFormValues = z.infer<typeof webhookSchema>;

export const thresholdSchema = z.object({
  threshold: z
    .number({ message: 'Enter a number' })
    .min(0.05, 'Minimum is 0.05')
    .max(1, 'Maximum is 1'),
});
export type ThresholdFormValues = z.infer<typeof thresholdSchema>;
