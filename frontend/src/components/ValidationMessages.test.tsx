import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ValidationMessages } from './ValidationMessages';

describe('ValidationMessages', () => {
  it('renders nothing without issues', () => {
    const { container } = render(<ValidationMessages issues={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('lists issues and lets the reviewer jump to a field', async () => {
    const onSelect = vi.fn();
    const many = Array.from({ length: 8 }, (_, i) => `line_items.${i}.line_total`);
    render(
      <ValidationMessages
        onSelectField={onSelect}
        issues={[
          {
            code: 'totals_mismatch',
            message: 'Subtotal + VAT ≠ total',
            fields: ['subtotal', 'total'],
          },
          { code: 'line_items_sum_mismatch', message: 'Lines do not add up', fields: many },
        ]}
      />,
    );
    expect(screen.getByRole('heading', { name: '2 validation issues' })).toBeInTheDocument();
    expect(screen.getByText('+2 more')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Total' }));
    expect(onSelect).toHaveBeenCalledWith('total');
    await userEvent.click(screen.getByRole('button', { name: 'Line 1 line total' }));
    expect(onSelect).toHaveBeenCalledWith('line_items.0.line_total');
  });

  it('uses singular wording for one issue', () => {
    render(<ValidationMessages issues={[{ code: 'x', message: 'Bad', fields: [] }]} />);
    expect(screen.getByRole('heading', { name: '1 validation issue' })).toBeInTheDocument();
  });
});
