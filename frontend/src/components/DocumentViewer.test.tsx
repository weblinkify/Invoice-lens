import { act, render, screen } from '@testing-library/react';
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

describe('DocumentViewer sizing', () => {
  it('ignores scrollbar-sized width changes so the page does not re-render in a loop', () => {
    let notify: ResizeObserverCallback = () => undefined;
    const original = globalThis.ResizeObserver;
    globalThis.ResizeObserver = class {
      constructor(cb: ResizeObserverCallback) {
        notify = cb;
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    };
    const resize = (width: number) => {
      act(() => {
        notify([{ contentRect: { width } } as ResizeObserverEntry], {} as ResizeObserver);
      });
    };
    try {
      render(
        <DocumentViewer
          url="/f.pdf"
          contentType="application/pdf"
          filename="a.pdf"
          highlight={null}
        />,
      );
      resize(832);
      expect(screen.getByTestId('pdf-page')).toHaveAttribute('data-width', '800');
      resize(817); // vertical scrollbar appeared
      expect(screen.getByTestId('pdf-page')).toHaveAttribute('data-width', '800');
      resize(632); // real resize
      expect(screen.getByTestId('pdf-page')).toHaveAttribute('data-width', '600');
    } finally {
      globalThis.ResizeObserver = original;
    }
  });
});
