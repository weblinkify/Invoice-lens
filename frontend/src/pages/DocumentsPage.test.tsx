import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/utils';
import { DocumentsPage } from './DocumentsPage';

describe('DocumentsPage', () => {
  it('lists documents with status badges and totals', async () => {
    renderWithProviders(<DocumentsPage />, { path: '/' });
    expect(await screen.findByText('invoice_02_modern_se.pdf')).toBeInTheDocument();
    expect(screen.getByText('3 documents')).toBeInTheDocument();
    expect(screen.getAllByText('Needs review').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText('Hansson Tech AB')).toBeInTheDocument();
  });

  it('filters by search, status and needs-review', async () => {
    renderWithProviders(<DocumentsPage />, { path: '/' });
    await screen.findByText('invoice_02_modern_se.pdf');
    await userEvent.type(screen.getByLabelText('Search by file name or invoice number'), 'totals');
    await waitFor(() => {
      expect(screen.queryByText('invoice_02_modern_se.pdf')).not.toBeInTheDocument();
    });
    expect(screen.getByText('invoice_05_modern_de_totals_mismatch.pdf')).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText('Search by file name or invoice number'));
    await userEvent.selectOptions(screen.getByLabelText('Filter by status'), 'approved');
    expect(await screen.findByText('No documents match these filters.')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Filter by status'), '');
    await userEvent.click(screen.getByRole('switch', { name: 'Only documents that need review' }));
    expect(await screen.findByText('invoice_02_modern_se.pdf')).toBeInTheDocument();
  });

  it('selects rows and exports them', async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    let exportedIds: string | null = null;
    server.use(
      http.get('*/api/v1/exports', ({ request }) => {
        exportedIds = new URL(request.url).searchParams.get('ids');
        return new HttpResponse('a,b', {
          headers: { 'Content-Disposition': 'attachment; filename="x.csv"' },
        });
      }),
    );
    renderWithProviders(<DocumentsPage />, { path: '/' });
    await userEvent.click(await screen.findByLabelText('Select invoice_02_modern_se.pdf'));
    expect(screen.getByText(/1 selected/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /export selected csv/i }));
    await waitFor(() => {
      expect(click).toHaveBeenCalled();
    });
    expect(exportedIds).toBe('doc-1');
    expect(await screen.findByText('Exported x.csv')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Select all on this page'));
    expect(screen.getByText(/3 selected/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('Select all on this page'));
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
  });

  it('shows export and load errors', async () => {
    server.use(http.get('*/api/v1/exports', () => new HttpResponse('x', { status: 500 })));
    renderWithProviders(<DocumentsPage />, { path: '/' });
    await screen.findByText('invoice_02_modern_se.pdf');
    await userEvent.click(screen.getByRole('button', { name: /excel/i }));
    expect(await screen.findByText('Export failed')).toBeInTheDocument();

    server.use(
      http.get('*/api/v1/documents', () =>
        HttpResponse.json(
          { type: 't', title: 'x', status: 500, detail: 'Database down', instance: '/' },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<DocumentsPage />, { path: '/' });
    expect(await screen.findByText('Database down')).toBeInTheDocument();
  });

  it('paginates', async () => {
    server.use(
      http.get('*/api/v1/documents', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page'));
        return HttpResponse.json({ items: [], total: 45, page, page_size: 20 });
      }),
    );
    renderWithProviders(<DocumentsPage />, { path: '/' });
    const nav = await screen.findByRole('navigation', { name: 'Pagination' });
    expect(within(nav).getByText('Page 1 of 3')).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole('button', { name: 'Next' }));
    expect(await within(nav).findByText('Page 2 of 3')).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole('button', { name: 'Previous' }));
    expect(await within(nav).findByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('opens a document when its row is clicked', async () => {
    renderWithProviders(<DocumentsPage />, { path: '/' });
    await userEvent.click(await screen.findByText('Hansson Tech AB'));
    expect(await screen.findByTestId('other-route')).toBeInTheDocument();
  });
});
