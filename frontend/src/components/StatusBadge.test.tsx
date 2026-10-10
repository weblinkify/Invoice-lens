import { render, screen } from '@testing-library/react';
import type { DocumentStatus } from '@/api/types';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it.each<[DocumentStatus, string]>([
    ['queued', 'Queued'],
    ['processing', 'Processing'],
    ['needs_review', 'Needs review'],
    ['extracted', 'Ready'],
    ['approved', 'Approved'],
    ['failed', 'Failed'],
  ])('shows %s', (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label).closest('[data-status]')).toHaveAttribute('data-status', status);
  });
});
