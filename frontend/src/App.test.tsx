import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from './App';

describe('App shell', () => {
  it('renders navigation, provider badge and toggles dark mode', async () => {
    window.history.pushState({}, '', '/');
    render(<App />);
    expect(screen.getByRole('link', { name: 'Skip to content' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(await screen.findByText(/LLM: mock · demo/)).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: 'Switch to dark mode' });
    await userEvent.click(toggle);
    expect(document.documentElement).toHaveClass('dark');
    expect(localStorage.getItem('invoicelens-theme')).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
    expect(document.documentElement).not.toHaveClass('dark');
  });

  it('routes between pages', async () => {
    window.history.pushState({}, '', '/');
    render(<App />);
    await userEvent.click(screen.getByRole('link', { name: 'Documents' }));
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Settings' }));
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    window.history.pushState({}, '', '/documents/doc-1');
    render(<App />);
    expect(
      await screen.findByLabelText('Payment reference', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
  });

  it('shows a 404 page', async () => {
    window.history.pushState({}, '', '/nope');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('honours a stored theme', () => {
    localStorage.setItem('invoicelens-theme', 'dark');
    window.history.pushState({}, '', '/nope');
    render(<App />);
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument();
  });
});
