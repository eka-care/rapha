/** A tick box, Radix's, styled from this product's tokens.
 *
 *  The hand-rolled one worked and reported itself wrongly: it was an
 *  `<input>` with its appearance taken away, so a screen reader was given a
 *  control the browser had stopped drawing and the label was attached by
 *  wrapping rather than by name. Radix's keeps a real checked state, real
 *  keyboard behaviour and a real association with its label.
 */
import * as RCheckbox from "@radix-ui/react-checkbox";
import "../style/ui.css";

/** The box on its own, for the two places that already draw their own label
 *  around a row of other things: the second-stage confirm, and the role
 *  editor's switch with a capability id under its name. */
export function Box({ id, checked, disabled, autoFocus, onChange, label }: {
  id?: string;
  checked: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  onChange: (next: boolean) => void;
  /** Only where nothing else names it. Inside a <label> this stays unset,
   *  because the label already does the naming and two names is worse than
   *  one. */
  label?: string;
}) {
  return (
    <RCheckbox.Root id={id} className="cb" checked={checked} disabled={disabled}
                    autoFocus={autoFocus} aria-label={label}
                    onCheckedChange={(v) => onChange(v === true)}>
      <RCheckbox.Indicator className="cb-i" />
    </RCheckbox.Root>
  );
}

export function Check({ id, checked, disabled, autoFocus, onChange, children }: {
  id?: string;
  checked: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  onChange: (next: boolean) => void;
  /** The words beside it. A tick with no sentence is a tick nobody can
   *  answer, so this is not optional. */
  children: React.ReactNode;
}) {
  return (
    <label className="f-check">
      <Box id={id} checked={checked} disabled={disabled} autoFocus={autoFocus}
           onChange={onChange} />
      <span>{children}</span>
    </label>
  );
}
