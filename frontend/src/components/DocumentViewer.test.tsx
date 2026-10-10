import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DocumentViewer } from './DocumentViewer';

describe('DocumentViewer', () => {
  it('navigates pages and zooms', async () => {
    render(
      <DocumentViewer
        url="/f.pdf"
        contentType="application/pdf"
        filename="a.pdf"
        highlight={null}
      />,
    );
    expect(screen.getByRole('region', { name: 'Document viewer: a.pdf' })).toBeInTheDocument();
    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');

    await userEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(screen.getByText('125%')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Zoom out' }));
    await userEvent.click(screen.getByRole('button', { name: 'Zoom out' }));
    expect(screen.getByText('75%')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Fit to width' }));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('jumps to the highlighted page and draws the bounding box', async () => {
    const { rerender } = render(
      <DocumentViewer
        url="/f.pdf"
        contentType="application/pdf"
        filename="a.pdf"
        highlight={null}
      />,
    );
    expect(screen.queryByTestId('bbox-highlight')).not.toBeInTheDocument();
    rerender(
      <DocumentViewer
        url="/f.pdf"
        contentType="application/pdf"
        filename="a.pdf"
        highlight={{ page: 2, bbox: [0.1, 0.2, 0.3, 0.25], label: 'Total' }}
      />,
    );
    expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument();
    const box = screen.getByTestId('bbox-highlight');
    expect(box.style.left).toContain('10%');
    expect(box.style.top).toContain('20%');
    expect(screen.getByText('Highlighting Total on page 2')).toBeInTheDocument();
  });

  it('renders images with an accessible description', () => {
    render(
      <DocumentViewer
        url="/f.png"
        contentType="image/png"
        filename="scan.png"
        highlight={{ page: 1, bbox: [0, 0, 0.5, 0.5], label: 'IBAN' }}
      />,
    );
    expect(screen.getByAltText('Scanned invoice scan.png')).toBeInTheDocument();
    expect(screen.getByTestId('bbox-highlight')).toBeInTheDocument();
  });
});
