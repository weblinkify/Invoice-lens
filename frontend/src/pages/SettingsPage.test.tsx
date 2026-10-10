import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { mockDb } from '@/mocks/handlers';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/utils';
import { SettingsPage } from './SettingsPage';

describe('SettingsPage', () => {
  it('saves the confidence threshold', async () => {
    renderWithProviders(<SettingsPage />, { path: '/' });
    const save = screen.getByRole('button', { name: 'Save' });
    await waitFor(() => {
      expect(save).toBeEnabled();
    });
    const slider = screen.getByLabelText(/confidence threshold: 80%/i);
    fireEvent.change(slider, { target: { value: '0.6' } });
    expect(screen.getByLabelText(/confidence threshold: 60%/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Threshold set to 60%')).toBeInTheDocument();
    expect(mockDb().settings.confidence_threshold).toBe(0.6);
  });

  it('validates and adds a webhook endpoint, then tests and removes it', async () => {
    renderWithProviders(<SettingsPage />, { path: '/' });
    expect(await screen.findByText(/no endpoints yet/i)).toBeInTheDocument();
    const form = screen.getByRole('form', { name: 'Add webhook endpoint' });
    await userEvent.type(within(form).getByLabelText('Endpoint URL'), 'not-a-url');
    await userEvent.type(within(form).getByLabelText('Signing secret'), 'short');
    await userEvent.click(within(form).getByRole('button', { name: /add/i }));
    expect(await screen.findByText(/enter a full url/i)).toBeInTheDocument();
    expect(screen.getByText('Use at least 8 characters')).toBeInTheDocument();

    await userEvent.clear(within(form).getByLabelText('Endpoint URL'));
    await userEvent.type(
      within(form).getByLabelText('Endpoint URL'),
      'https://erp.example.com/hooks',
    );
    await userEvent.click(within(form).getByRole('button', { name: 'Generate secret' }));
    expect(within(form).getByLabelText<HTMLInputElement>('Signing secret').value).toMatch(
      /^whsec_[0-9a-f]{48}$/,
    );
    await userEvent.type(within(form).getByLabelText('Description'), 'ERP');
    await userEvent.click(within(form).getByRole('button', { name: /add/i }));

    const row = await screen.findByTestId('webhook-row');
    expect(within(row).getByText('https://erp.example.com/hooks')).toBeInTheDocument();

    await userEvent.click(within(row).getByRole('button', { name: /send test/i }));
    expect(await screen.findByText('Ping delivered (HTTP 200)')).toBeInTheDocument();
    expect(await within(row).findByText('ping')).toBeInTheDocument();

    await userEvent.click(within(row).getByRole('switch'));
    await waitFor(() => {
      expect(mockDb().webhooks[0]?.active).toBe(false);
    });
    await userEvent.click(within(row).getByRole('button', { name: 'Log' }));
    await userEvent.click(within(row).getByRole('button', { name: /delete webhook/i }));
    expect(await screen.findByText(/no endpoints yet/i)).toBeInTheDocument();
  });

  it('shows failed test deliveries', async () => {
    server.use(
      http.post('*/api/v1/webhook-endpoints/:id/test', () =>
        HttpResponse.json({
          id: 1,
          endpoint_id: 1,
          document_id: null,
          event: 'ping',
          status: 'failed',
          attempts: 5,
          last_status_code: 500,
          last_error: 'simulated outage',
          created_at: new Date().toISOString(),
          delivered_at: null,
        }),
      ),
    );
    mockDb().webhooks.push({
      id: 1,
      url: 'https://x.test/h',
      description: null,
      active: true,
      created_at: new Date().toISOString(),
      secret_hint: '••••abcd',
    });
    renderWithProviders(<SettingsPage />, { path: '/' });
    await userEvent.click(await screen.findByRole('button', { name: /send test/i }));
    expect(await screen.findByText('Ping failed: simulated outage')).toBeInTheDocument();
  });

  it('runs the accuracy report', async () => {
    renderWithProviders(<SettingsPage />, { path: '/' });
    await userEvent.click(screen.getByRole('button', { name: /run accuracy check/i }));
    expect(await screen.findByText('99%')).toBeInTheDocument();
    expect(screen.getByText('invoice_number')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /run accuracy check/i }));
  });
});
