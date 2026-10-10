import { render, screen } from '@testing-library/react';
import { ConfidenceChip } from './ConfidenceChip';

describe('ConfidenceChip', () => {
  it.each([
    [0.95, 'high', 'Confidence 95%, high confidence'],
    [0.8, 'high', 'Confidence 80%, high confidence'],
    [0.62, 'medium', 'Confidence 62%, check this value'],
    [0.31, 'low', 'Confidence 31%, low confidence'],
  ])('renders %s as %s', (confidence, band, label) => {
    render(<ConfidenceChip confidence={confidence} threshold={0.8} />);
    const chip = screen.getByLabelText(label);
    expect(chip).toHaveAttribute('data-band', band);
    expect(chip).toHaveTextContent(`${Math.round(confidence * 100)}%`);
  });

  it('respects a custom threshold', () => {
    render(<ConfidenceChip confidence={0.7} threshold={0.6} />);
    expect(screen.getByText('70%').closest('[data-band]')).toHaveAttribute('data-band', 'high');
  });

  it('shows verified state for reviewer-confirmed fields', () => {
    render(<ConfidenceChip confidence={0.2} threshold={0.8} verified />);
    expect(screen.getByLabelText('Verified by reviewer')).toHaveTextContent('Verified');
  });
});
