import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { CorrectionRequest } from '@/api/types';
import { mockDb } from '@/mocks/handlers';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/utils';
import { ReviewPage } from './ReviewPage';

function capturePatches(): CorrectionRequest[] {
  const bodies: CorrectionRequest[] = [];
  server.events.on('request:start', ({ request }) => {
    if (request.method === 'PATCH') {
      void request
        .clone()
        .json()
        .then((b) => bodies.push(b as CorrectionRequest));
    }
  });
  return bodies;
}

const renderReview = (id = 'doc-1') =>
  renderWithProviders(<ReviewPage />, { route: `/documents/${id}`, path: '/documents/:id' });

afterEach(() => {
  server.events.removeAllListeners();
});

describe('ReviewPage', () => {
  it('shows the document, fields and confidence', async () => {
    renderReview();
    expect(await screen.findByLabelText('Payment reference')).toHaveValue('RF633601G105500875');
    expect(screen.getByRole('heading', { name: /invoice_02_modern_se\.pdf/ })).toBeInTheDocument();
    expect(
      screen.getByRole('region', { name: 'Document viewer: invoice_02_modern_se.pdf' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('review-status')).toHaveTextContent('2 fields to check');
    expect(screen.getByLabelText('Payment reference')).toHaveAttribute('data-band', 'medium');
    expect(screen.getByLabelText('Vendor name')).toHaveAttribute('data-attention', 'true');
    expect(screen.getByLabelText('Total')).toHaveAttribute('data-attention', 'false');
    expect(screen.getByText('Line items (3)')).toBeInTheDocument();
  });

  it('editing a field sends the correct PATCH and marks it verified', async () => {
    const patches = capturePatches();
    renderReview();
    const input = await screen.findByLabelText('Payment reference');
    await userEvent.clear(input);
    await userEvent.type(input, 'RF6336016105500875');
    await userEvent.click(screen.getByLabelText('Total')); // blur saves
    await waitFor(() => {
      expect(patches).toEqual([
        { corrections: [{ field: 'payment_reference', value: 'RF6336016105500875' }] },
      ]);
    });
    await waitFor(() => {
      expect(screen.getByTestId('review-status')).toHaveTextContent('1 field to check');
    });
    expect(screen.getAllByText('Verified')).toHaveLength(1);
  });

  it('sends numbers for numeric fields and skips unchanged values', async () => {
    const patches = capturePatches();
    renderReview();
    const qty = await screen.findByLabelText('Line 1 Qty');
    await userEvent.click(qty);
    await userEvent.click(screen.getByLabelText('Total')); // unchanged → no request
    await userEvent.clear(qty);
    await userEvent.type(qty, '5');
    await userEvent.click(screen.getByLabelText('Total'));
    await waitFor(() => {
      expect(patches).toEqual([{ corrections: [{ field: 'line_items.0.quantity', value: 5 }] }]);
    });
  });

  it('blocks invalid values with inline errors', async () => {
    const patches = capturePatches();
    renderReview();
    const due = await screen.findByLabelText('Due date');
    await userEvent.clear(due);
    await userEvent.type(due, '31/04/2026');
    await userEvent.tab();
    expect(await screen.findByText('Use the format YYYY-MM-DD')).toBeInTheDocument();
    expect(due).toHaveAttribute('aria-invalid', 'true');
    expect(patches).toEqual([]);
  });

  it('Enter confirms a low-confidence value and Tab jumps between fields to check', async () => {
    const patches = capturePatches();
    renderReview();
    const vendor = await screen.findByLabelText('Vendor name');
    await userEvent.click(screen.getByRole('button', { name: /next to check/i }));
    expect(vendor).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText('Payment reference')).toHaveFocus();
    await userEvent.click(vendor);
    await userEvent.keyboard('{Enter}');
    await waitFor(() => {
      expect(patches).toEqual([
        { corrections: [{ field: 'vendor_name', value: 'Hansson Tech AB' }] },
      ]);
    });
  });

  it('highlights the bounding box of the focused field', async () => {
    renderReview();
    await userEvent.click(await screen.findByLabelText('Payment reference'));
    const box = await screen.findByTestId('bbox-highlight');
    expect(box.style.left).toContain('28.56%');
    expect(screen.getByText('Highlighting Payment reference on page 1')).toBeInTheDocument();
  });

  it('approves with Ctrl+Enter, saving pending edits first', async () => {
    const patches = capturePatches();
    renderReview();
    const ref = await screen.findByLabelText('Payment reference');
    await userEvent.clear(ref);
    await userEvent.type(ref, 'RF6336016105500875');
    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true });
    expect(await screen.findByText('Approved — fields are locked.')).toBeInTheDocument();
    expect(patches[0]?.corrections).toEqual([
      { field: 'payment_reference', value: 'RF6336016105500875' },
    ]);
    expect(mockDb().documents.get('doc-1')?.status).toBe('approved');
    expect(screen.getByLabelText('Payment reference')).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: /export csv/i })).toBeInTheDocument();
  });

  it('approves via the button and shows validation issues', async () => {
    renderReview('doc-2');
    expect(await screen.findByRole('heading', { name: '2 validation issues' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'IBAN' }));
    expect(screen.getByLabelText('IBAN')).toHaveFocus();
    await userEvent.click(screen.getByRole('button', { name: /^approve/i }));
    expect(
      (await screen.findAllByText('Invoice approved and sent to connected systems')).length,
    ).toBeGreaterThan(0);
  });

  it('shows processing and failure states', async () => {
    mockDb().documents.get('doc-3')!.status = 'failed';
    mockDb().documents.get('doc-3')!.error = 'LLM is down';
    renderReview('doc-3');
    expect(await screen.findByText('LLM is down')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Reading the invoice…')).toBeInTheDocument();
  });

  it('shows an error for unknown documents', async () => {
    renderReview('nope');
    expect(await screen.findByText('Document nope was not found')).toBeInTheDocument();
  });

  it('reports save errors', async () => {
    server.use(
      http.patch('*/api/v1/documents/:id/extraction', () =>
        HttpResponse.json(
          { type: 't', title: 'x', status: 422, detail: 'total: not valid', instance: '/' },
          { status: 422 },
        ),
      ),
    );
    renderReview();
    const total = await screen.findByLabelText('Total');
    await userEvent.clear(total);
    await userEvent.type(total, '1');
    await userEvent.tab();
    expect(await screen.findByText('total: not valid')).toBeInTheDocument();
  });
});
