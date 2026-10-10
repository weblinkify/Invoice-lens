import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/utils';
import { UploadPage } from './UploadPage';

const pdf = (name: string) => new File(['%PDF-1.4 test'], name, { type: 'application/pdf' });

describe('UploadPage', () => {
  it('uploads files, polls status and links to review', async () => {
    renderWithProviders(<UploadPage />, { path: '/' });
    await userEvent.upload(screen.getByLabelText('Upload invoice files'), [pdf('march.pdf')]);
    const row = await screen.findByTestId('upload-row');
    expect(within(row).getByText('march.pdf')).toBeInTheDocument();
    const link = await within(row).findByRole('link', { name: /review/i }, { timeout: 4000 });
    expect(link.getAttribute('href')).toMatch(/^\/documents\/new-/);
  });

  it('shows rejected files with a reason', async () => {
    renderWithProviders(<UploadPage />, { path: '/' });
    const input = screen.getByLabelText('Upload invoice files');
    await userEvent.upload(input, [new File(['x'], 'notes.txt', { type: 'text/plain' })], {
      applyAccept: false,
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported file type');
  });

  it('shows server-side upload errors', async () => {
    server.use(
      http.post('*/api/v1/documents', () =>
        HttpResponse.json(
          {
            type: 't',
            title: 'Too large',
            status: 413,
            detail: 'File is too large',
            instance: '/',
          },
          { status: 413 },
        ),
      ),
    );
    renderWithProviders(<UploadPage />, { path: '/' });
    await userEvent.upload(screen.getByLabelText('Upload invoice files'), [pdf('big.pdf')]);
    expect(await screen.findByRole('alert')).toHaveTextContent('File is too large');
  });

  it('loads a sample invoice and navigates to review', async () => {
    renderWithProviders(<UploadPage />, { path: '/' });
    const button = screen.getByRole('button', { name: /try with sample invoice/i });
    await userEvent.click(button);
    expect(await screen.findByTestId('other-route')).toBeInTheDocument();
  });

  it('reports when no samples exist', async () => {
    server.use(http.get('*/api/v1/samples', () => HttpResponse.json([])));
    renderWithProviders(<UploadPage />, { path: '/' });
    await screen.findByRole('button', { name: /try with sample invoice/i });
    await new Promise((r) => setTimeout(r, 50));
    await userEvent.click(screen.getByRole('button', { name: /try with sample invoice/i }));
    expect(await screen.findByText('No sample invoices are available')).toBeInTheDocument();
  });
});
