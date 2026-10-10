/** In-memory state behind the MSW handlers (used by Vitest and `npm run dev:mock`). */
import type {
  AppSettings,
  DocumentOut,
  Extraction,
  InvoiceData,
  Sample,
  WebhookDelivery,
  WebhookEndpoint,
} from '@/api/types';
import fixtures from './fixtures.json';

interface Fixture {
  document: DocumentOut;
  extraction: Extraction;
}

const FIXTURES = fixtures as unknown as Record<string, Fixture>;
export const TEMPLATE = FIXTURES.invoice_02!;

export interface MockDb {
  documents: Map<string, DocumentOut>;
  extractions: Map<string, Extraction>;
  /** Number of status polls left before a queued document finishes processing. */
  pending: Map<string, number>;
  settings: AppSettings;
  webhooks: WebhookEndpoint[];
  deliveries: WebhookDelivery[];
  samples: Sample[];
  seq: number;
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

export function createMockDb(): MockDb {
  const db: MockDb = {
    documents: new Map(),
    extractions: new Map(),
    pending: new Map(),
    settings: {
      confidence_threshold: 0.8,
      llm_provider: 'mock',
      demo_mode: true,
      max_upload_bytes: 10 * 1024 * 1024,
    },
    webhooks: [],
    deliveries: [],
    samples: [
      { name: 'invoice_02_modern_se.pdf', template: 'modern', edge_cases: [], size_bytes: 2560 },
      {
        name: 'invoice_05_modern_de_totals_mismatch.pdf',
        template: 'modern',
        edge_cases: ['totals_mismatch'],
        size_bytes: 2703,
      },
    ],
    seq: 1,
  };
  for (const [i, f] of Object.values(FIXTURES).entries()) {
    const id = `doc-${i + 1}`;
    db.documents.set(id, { ...clone(f.document), id });
    db.extractions.set(id, { ...clone(f.extraction), document_id: id });
  }
  return db;
}

export function newDocument(db: MockDb, filename: string, size: number): DocumentOut {
  const id = `new-${db.seq++}`;
  const now = new Date().toISOString();
  const doc: DocumentOut = {
    ...clone(TEMPLATE.document),
    id,
    filename,
    size_bytes: size,
    status: 'processing',
    created_at: now,
    updated_at: now,
    approved_at: null,
  };
  db.documents.set(id, doc);
  db.extractions.set(id, { ...clone(TEMPLATE.extraction), document_id: id, corrected_fields: [] });
  db.pending.set(id, 1);
  return doc;
}

export function recompute(extraction: Extraction, threshold: number): void {
  const data: InvoiceData = extraction.data;
  const corrected = new Set(extraction.corrected_fields);
  data.validation_issues = data.validation_issues.filter(
    (i) => !i.fields.every((f) => corrected.has(f)),
  );
  const fields = [
    data.vendor_name,
    data.vendor_vat_id,
    data.invoice_number,
    data.invoice_date,
    data.due_date,
    data.currency,
    data.subtotal,
    data.vat_total,
    data.total,
    data.iban,
    data.payment_reference,
    ...data.line_items.flatMap((li) => [
      li.description,
      li.quantity,
      li.unit_price,
      li.vat_rate,
      li.line_total,
    ]),
  ];
  data.needs_review =
    data.validation_issues.length > 0 || fields.some((f) => f.confidence < threshold);
  extraction.threshold = threshold;
}
