import { delay, http, HttpResponse } from 'msw';
import type {
  AccuracyReport,
  CorrectionRequest,
  DocumentOut,
  Problem,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEndpointIn,
} from '@/api/types';
import { getField } from '@/lib/fields';
import { createMockDb, newDocument, recompute, type MockDb } from './db';

let db: MockDb = createMockDb();

export function resetMockDb(): MockDb {
  db = createMockDb();
  return db;
}

export function mockDb(): MockDb {
  return db;
}

const API = '*/api/v1';

function problem(status: number, detail: string, path: string): HttpResponse<Problem> {
  return HttpResponse.json<Problem>(
    { type: 'about:blank', title: 'Error', status, detail, instance: path },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

function withExtraction(doc: DocumentOut): DocumentOut {
  const ext = db.extractions.get(doc.id);
  if (!ext || doc.status === 'processing' || doc.status === 'queued') return doc;
  const d = ext.data;
  const all = [d.vendor_name, d.invoice_number, d.total, d.iban, d.payment_reference, d.currency];
  return {
    ...doc,
    vendor_name: d.vendor_name.value,
    invoice_number: d.invoice_number.value,
    total: d.total.value,
    currency: d.currency.value,
    needs_review: d.needs_review,
    min_confidence: Math.min(...all.map((f) => f.confidence)),
  };
}

function advance(doc: DocumentOut): DocumentOut {
  const left = db.pending.get(doc.id);
  if (left === undefined) return doc;
  if (left > 0) {
    db.pending.set(doc.id, left - 1);
    return doc;
  }
  db.pending.delete(doc.id);
  doc.status = db.extractions.get(doc.id)?.data.needs_review ? 'needs_review' : 'extracted';
  return doc;
}

export const handlers = [
  http.get(`${API}/health`, () =>
    HttpResponse.json({ status: 'ok', provider: 'mock', version: 'msw' }),
  ),

  http.get(`${API}/settings`, () => HttpResponse.json(db.settings)),
  http.put(`${API}/settings`, async ({ request }) => {
    const body = (await request.json()) as { confidence_threshold: number };
    db.settings = { ...db.settings, confidence_threshold: body.confidence_threshold };
    for (const ext of db.extractions.values()) recompute(ext, body.confidence_threshold);
    return HttpResponse.json(db.settings);
  }),

  http.get(`${API}/documents`, ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? 1);
    const size = Number(url.searchParams.get('page_size') ?? 20);
    const status = url.searchParams.get('status');
    const review = url.searchParams.get('needs_review');
    const q = url.searchParams.get('q')?.toLowerCase();
    let items = [...db.documents.values()].map((d) => withExtraction(advance(d)));
    if (status) items = items.filter((d) => d.status === status);
    if (review === 'true') items = items.filter((d) => d.needs_review === true);
    if (q)
      items = items.filter((d) =>
        `${d.filename} ${d.invoice_number ?? ''}`.toLowerCase().includes(q),
      );
    items.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return HttpResponse.json({
      items: items.slice((page - 1) * size, page * size),
      total: items.length,
      page,
      page_size: size,
    });
  }),

  http.post(`${API}/documents`, async ({ request }) => {
    const form = await request.formData();
    const file = form.get('file');
    // duck-typed: jsdom and Node each have their own File class
    if (typeof file !== 'object' || file === null || file.size === 0) {
      return problem(422, 'The uploaded file is empty', '/api/v1/documents');
    }
    const doc = newDocument(db, file.name || 'upload.pdf', file.size);
    return HttpResponse.json(
      { id: doc.id, status: 'queued', status_url: `/api/v1/documents/${doc.id}` },
      { status: 202 },
    );
  }),

  http.get(`${API}/documents/:id`, ({ params, request }) => {
    const doc = db.documents.get(String(params.id));
    if (!doc)
      return problem(
        404,
        `Document ${String(params.id)} was not found`,
        new URL(request.url).pathname,
      );
    return HttpResponse.json(withExtraction(advance(doc)));
  }),

  http.delete(`${API}/documents/:id`, ({ params }) => {
    db.documents.delete(String(params.id));
    db.extractions.delete(String(params.id));
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(`${API}/documents/:id/file`, async () => {
    try {
      const res = await fetch(new URL('/mock/sample-invoice.pdf', globalThis.location.origin));
      return new HttpResponse(await res.arrayBuffer(), {
        headers: { 'Content-Type': 'application/pdf' },
      });
    } catch {
      return new HttpResponse('%PDF-1.4 mock', { headers: { 'Content-Type': 'application/pdf' } });
    }
  }),

  http.get(`${API}/documents/:id/extraction`, ({ params, request }) => {
    const id = String(params.id);
    const doc = db.documents.get(id);
    const ext = db.extractions.get(id);
    if (!doc || !ext)
      return problem(404, `Document ${id} was not found`, new URL(request.url).pathname);
    if (doc.status === 'processing' || doc.status === 'queued') {
      return problem(
        409,
        `Document is ${doc.status}; no extraction yet`,
        new URL(request.url).pathname,
      );
    }
    return HttpResponse.json(ext);
  }),

  http.patch(`${API}/documents/:id/extraction`, async ({ params, request }) => {
    const id = String(params.id);
    const doc = db.documents.get(id);
    const ext = db.extractions.get(id);
    const path = new URL(request.url).pathname;
    if (!doc || !ext) return problem(404, `Document ${id} was not found`, path);
    if (doc.status === 'approved') return problem(409, 'Approved documents are locked', path);
    const body = (await request.json()) as CorrectionRequest;
    for (const c of body.corrections) {
      const field = getField(ext.data, c.field);
      if (!field) return problem(422, `Unknown field ${c.field}`, path);
      field.value = c.value;
      field.confidence = 1;
      if (!ext.corrected_fields.includes(c.field)) ext.corrected_fields.push(c.field);
    }
    recompute(ext, db.settings.confidence_threshold);
    doc.status = ext.data.needs_review ? 'needs_review' : 'extracted';
    ext.updated_at = new Date().toISOString();
    await delay(50);
    return HttpResponse.json(ext);
  }),

  http.post(`${API}/documents/:id/approve`, ({ params, request }) => {
    const doc = db.documents.get(String(params.id));
    const path = new URL(request.url).pathname;
    if (!doc) return problem(404, 'Document not found', path);
    if (doc.status === 'approved') return problem(409, 'Document is already approved', path);
    doc.status = 'approved';
    doc.approved_at = new Date().toISOString();
    for (const ep of db.webhooks.filter((w) => w.active)) {
      db.deliveries.push(delivery(ep.id, 'invoice.approved', doc.id));
    }
    return HttpResponse.json(withExtraction(doc));
  }),

  http.post(`${API}/documents/:id/reprocess`, ({ params }) => {
    const doc = db.documents.get(String(params.id));
    if (doc) {
      doc.status = 'processing';
      db.pending.set(doc.id, 3);
    }
    return HttpResponse.json(
      { id: String(params.id), status: 'queued', status_url: '' },
      { status: 202 },
    );
  }),

  http.get(`${API}/samples`, () => HttpResponse.json(db.samples)),
  http.post(`${API}/samples/:name`, ({ params, request }) => {
    const sample = db.samples.find((s) => s.name === params.name);
    if (!sample)
      return problem(
        404,
        `Sample ${String(params.name)} was not found`,
        new URL(request.url).pathname,
      );
    const doc = newDocument(db, sample.name, sample.size_bytes);
    return HttpResponse.json({ id: doc.id, status: 'queued', status_url: '' }, { status: 202 });
  }),

  http.get(`${API}/exports`, ({ request }) => {
    const url = new URL(request.url);
    const ids = url.searchParams.get('ids')?.split(',');
    const docs = [...db.documents.values()].filter((d) =>
      ids ? ids.includes(d.id) : d.status === 'approved',
    );
    const rows = docs.map((d) => {
      const x = withExtraction(d);
      return [x.id, x.filename, x.invoice_number ?? '', x.total ?? '', x.currency ?? ''].join(',');
    });
    const format = url.searchParams.get('format') ?? 'csv';
    return new HttpResponse(
      ['document_id,filename,invoice_number,total,currency', ...rows].join('\n'),
      {
        headers: {
          'Content-Type': format === 'csv' ? 'text/csv' : 'application/octet-stream',
          'Content-Disposition': `attachment; filename="invoicelens-mock.${format}"`,
        },
      },
    );
  }),

  http.get(`${API}/webhook-endpoints`, () => HttpResponse.json(db.webhooks)),
  http.post(`${API}/webhook-endpoints`, async ({ request }) => {
    const body = (await request.json()) as WebhookEndpointIn;
    const ep: WebhookEndpoint = {
      id: db.seq++,
      url: body.url,
      description: body.description ?? null,
      active: body.active,
      created_at: new Date().toISOString(),
      secret_hint: `••••${body.secret.slice(-4)}`,
    };
    db.webhooks.push(ep);
    return HttpResponse.json(ep, { status: 201 });
  }),
  http.patch(`${API}/webhook-endpoints/:id`, async ({ params, request }) => {
    const ep = db.webhooks.find((w) => w.id === Number(params.id));
    if (!ep) return problem(404, 'Webhook endpoint not found', '');
    const body = (await request.json()) as { active?: boolean };
    ep.active = body.active ?? ep.active;
    return HttpResponse.json(ep);
  }),
  http.delete(`${API}/webhook-endpoints/:id`, ({ params }) => {
    db.webhooks = db.webhooks.filter((w) => w.id !== Number(params.id));
    return new HttpResponse(null, { status: 204 });
  }),
  http.post(`${API}/webhook-endpoints/:id/test`, ({ params }) => {
    const d = delivery(Number(params.id), 'ping', null);
    db.deliveries.push(d);
    return HttpResponse.json(d);
  }),
  http.get(`${API}/webhook-endpoints/:id/deliveries`, ({ params }) =>
    HttpResponse.json(db.deliveries.filter((d) => d.endpoint_id === Number(params.id)).reverse()),
  ),

  http.get(`${API}/metrics/accuracy`, async () => {
    await delay(100);
    const report: AccuracyReport = {
      provider: 'mock',
      documents: 10,
      fields_total: 390,
      fields_correct: 385,
      accuracy: 0.9872,
      review_rate: 1,
      per_field: [
        { field: 'invoice_number', correct: 8, total: 10, accuracy: 0.8 },
        { field: 'total', correct: 10, total: 10, accuracy: 1 },
      ],
      per_document: [],
    };
    return HttpResponse.json(report);
  }),
];

function delivery(endpointId: number, event: string, documentId: string | null): WebhookDelivery {
  return {
    id: db.seq++,
    endpoint_id: endpointId,
    document_id: documentId,
    event,
    status: 'succeeded',
    attempts: 1,
    last_status_code: 200,
    last_error: null,
    created_at: new Date().toISOString(),
    delivered_at: new Date().toISOString(),
  };
}
