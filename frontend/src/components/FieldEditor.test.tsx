import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FieldEditor } from './FieldEditor';

const issue = { code: 'invalid_iban', message: 'IBAN checksum is invalid', fields: ['iban'] };

describe('FieldEditor', () => {
  it('labels the input and shows its confidence', () => {
    render(
      <FieldEditor
        path="total"
        label="Total"
        kind="number"
        confidence={0.95}
        threshold={0.8}
        defaultValue="12.5"
      />,
    );
    const input = screen.getByLabelText('Total');
    expect(input).toHaveValue('12.5');
    expect(input).toHaveAttribute('data-attention', 'false');
    expect(input).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByText('95%')).toBeInTheDocument();
  });

  it('flags low confidence fields for attention', () => {
    render(
      <FieldEditor path="iban" label="IBAN" kind="string" mono confidence={0.3} threshold={0.8} />,
    );
    const input = screen.getByLabelText('IBAN');
    expect(input).toHaveAttribute('data-attention', 'true');
    expect(input).toHaveAttribute('data-band', 'low');
    expect(input.className).toContain('font-mono');
  });

  it('renders validation issues and errors inline and links them for screen readers', () => {
    render(
      <FieldEditor
        path="iban"
        label="IBAN"
        kind="string"
        confidence={0.9}
        threshold={0.8}
        issues={[issue]}
        error="IBAN should look like FI21…"
      />,
    );
    const input = screen.getByLabelText('IBAN');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('data-attention', 'true');
    const describedBy = input.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent('IBAN checksum is invalid');
    expect(screen.getByText('IBAN should look like FI21…')).toBeInTheDocument();
  });

  it('treats verified fields as done', () => {
    render(
      <FieldEditor
        path="iban"
        label="IBAN"
        kind="string"
        confidence={0.2}
        threshold={0.8}
        verified
      />,
    );
    expect(screen.getByLabelText('IBAN')).toHaveAttribute('data-attention', 'false');
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('forwards events and supports compact mode with date placeholder', async () => {
    const onChange = vi.fn();
    render(
      <FieldEditor
        path="due_date"
        label="Due date"
        kind="date"
        confidence={0.6}
        threshold={0.8}
        compact
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText('Due date');
    expect(input).toHaveAttribute('placeholder', 'YYYY-MM-DD');
    await userEvent.type(input, '2');
    expect(onChange).toHaveBeenCalled();
  });
});
