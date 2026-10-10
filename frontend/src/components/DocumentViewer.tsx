import { ChevronLeft, ChevronRight, Maximize, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

export interface Highlight {
  page: number;
  bbox: number[];
  label: string;
}

interface Props {
  url: string;
  contentType: string;
  filename: string;
  highlight: Highlight | null;
}

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

export function DocumentViewer({ url, contentType, filename, highlight }: Props) {
  const [numPages, setNumPages] = useState(1);
  const [page, setPage] = useState(1);
  const [zoomIndex, setZoomIndex] = useState(2);
  const [width, setWidth] = useState(600);
  const containerRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLDivElement>(null);
  const isPdf = contentType === 'application/pdf';
  const zoom = ZOOM_STEPS[zoomIndex] ?? 1;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(280, entry.contentRect.width - 32));
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, []);

  // Jump to the highlighted field's page when the highlight changes (derived state, no effect).
  const [shownHighlight, setShownHighlight] = useState(highlight);
  if (highlight !== shownHighlight) {
    setShownHighlight(highlight);
    if (highlight && highlight.page !== page) setPage(highlight.page);
  }

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [highlight, page]);

  const showMark = highlight && highlight.page === page && highlight.bbox.length === 4;
  const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = highlight?.bbox ?? [];

  const overlay = showMark ? (
    <div
      ref={markRef}
      data-testid="bbox-highlight"
      aria-hidden
      className="pointer-events-none absolute rounded-sm bg-yellow-300/30 ring-2 ring-yellow-500 transition-all duration-200"
      style={{
        left: `calc(${x0 * 100}% - 3px)`,
        top: `calc(${y0 * 100}% - 3px)`,
        width: `calc(${(x1 - x0) * 100}% + 6px)`,
        height: `calc(${(y1 - y0) * 100}% + 6px)`,
      }}
    />
  ) : null;

  return (
    <section
      aria-label={`Document viewer: ${filename}`}
      className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-lg border bg-muted/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-card px-3 py-2">
        <div className="flex items-center gap-1" role="group" aria-label="Page navigation">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => {
              setPage((p) => p - 1);
            }}
          >
            <ChevronLeft />
          </Button>
          <span className="min-w-[5.5rem] text-center text-sm tabular-nums" aria-live="polite">
            Page {page} of {numPages}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Next page"
            disabled={page >= numPages}
            onClick={() => {
              setPage((p) => p + 1);
            }}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="Zoom">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Zoom out"
            disabled={zoomIndex === 0}
            onClick={() => {
              setZoomIndex((z) => z - 1);
            }}
          >
            <ZoomOut />
          </Button>
          <span className="w-12 text-center text-sm tabular-nums" aria-live="polite">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Zoom in"
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            onClick={() => {
              setZoomIndex((z) => z + 1);
            }}
          >
            <ZoomIn />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Fit to width"
            onClick={() => {
              setZoomIndex(2);
            }}
          >
            <Maximize />
          </Button>
        </div>
      </div>
      <div
        ref={containerRef}
        className="flex-1 overflow-auto p-4"
        tabIndex={0}
        aria-label="Document page"
      >
        <div className="mx-auto w-fit">
          {isPdf ? (
            <Document
              file={url}
              onLoadSuccess={({ numPages: n }) => {
                setNumPages(n);
              }}
              loading={<Skeleton className="aspect-[1/1.414] w-[min(600px,100%)]" />}
              error={<p className="p-6 text-sm text-destructive">Could not load the PDF.</p>}
            >
              <div className="relative bg-white shadow-md">
                <Page
                  pageNumber={page}
                  width={width * zoom}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                />
                {overlay}
              </div>
            </Document>
          ) : (
            <div className="relative bg-white shadow-md" style={{ width: width * zoom }}>
              <img src={url} alt={`Scanned invoice ${filename}`} className="block w-full" />
              {overlay}
            </div>
          )}
        </div>
      </div>
      {highlight && (
        <p className="sr-only" aria-live="polite">
          Highlighting {highlight.label} on page {highlight.page}
        </p>
      )}
    </section>
  );
}
