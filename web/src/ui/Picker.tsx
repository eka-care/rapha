/** A CLOSED CHOICE, drawn the way shadcn draws one.
 *
 *  shadcn is Radix primitives plus styling you own, and that is exactly what
 *  this is: the components are Radix's, the anatomy is shadcn's, and every
 *  colour, radius and spacing below comes from this product's own tokens.
 *  There is no Tailwind here and no second design system to keep in step.
 *
 *  What the native `<select>` could not do, and why it mattered on a form a
 *  nurse uses: it opens an operating system menu this product cannot style,
 *  it truncates a long option to the width of the control, and it has no
 *  search, so picking "Glucose [Mass/volume] in Capillary blood by
 *  Glucometer" out of eleven similar phrases meant reading all eleven.
 *
 *  Two shapes, and ui/pick.ts decides which from the list itself. A short
 *  list of short words is a menu. A long list, or one of long names, gets a
 *  search box, which is shadcn's Combobox: a popover holding a filter and a
 *  list.
 *
 *  THE VALUE THAT IS STORED IS ALWAYS THE CODE. The display is what the
 *  terminology calls it and is never what is sent. Both shapes below pass
 *  `value` up and draw `display`, and nothing here invents either.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as RSelect from "@radix-ui/react-select";
import * as RPopover from "@radix-ui/react-popover";
import { Icon } from "../icons";
import { matches, needsSearch } from "./pick";
import "../style/ui.css";

export type Choice = { value: string; display: string };

export function Pick({
  id, value, options, placeholder = "Choose", disabled, autoFocus, onChange, invalid,
}: {
  id: string;
  value: string;
  options: Choice[];
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  invalid?: boolean;
  onChange: (value: string | undefined) => void;
}) {
  const search = useMemo(() => needsSearch(options.map((o) => o.display)), [options]);
  return search
    ? <Combo id={id} value={value} options={options} placeholder={placeholder}
             disabled={disabled} autoFocus={autoFocus} invalid={invalid} onChange={onChange} />
    : <Menu id={id} value={value} options={options} placeholder={placeholder}
            disabled={disabled} autoFocus={autoFocus} invalid={invalid} onChange={onChange} />;
}

type Props = Parameters<typeof Pick>[0];

/** The short list. Radix Select: a real listbox with typeahead, arrow keys,
 *  and a menu this product draws rather than the operating system. */
function Menu({ id, value, options, placeholder, disabled, autoFocus, invalid, onChange }: Props) {
  return (
    <RSelect.Root value={value || undefined} disabled={disabled}
                  onValueChange={(v) => onChange(v || undefined)}>
      <RSelect.Trigger id={id} className="pk" autoFocus={autoFocus}
                       aria-invalid={invalid || undefined}>
        <RSelect.Value placeholder={placeholder} />
        <RSelect.Icon className="pk-c"><Icon name="chev" className="i sm" /></RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        {/* `position="popper"` keeps the menu beside the control instead of
            over it. A menu that covers the field it belongs to hides the
            label of the thing being answered. */}
        <RSelect.Content className="pk-pop" position="popper" sideOffset={4}>
          <RSelect.Viewport className="pk-list">
            {options.map((o) => (
              <RSelect.Item key={o.value} value={o.value} className="pk-row">
                <RSelect.ItemText>{o.display}</RSelect.ItemText>
                <RSelect.ItemIndicator className="pk-tick">
                  <Icon name="check" className="i sm" />
                </RSelect.ItemIndicator>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

/** The long list. shadcn's Combobox: a popover holding a search box and the
 *  options that survive it. Written against Radix Popover and a plain input
 *  rather than a command-menu library, because the whole of what a command
 *  menu would add here is filtering, and the filter is ui/pick.ts, which is
 *  checked without a browser. */
function Combo({ id, value, options, placeholder, disabled, autoFocus, invalid, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  const shown = useMemo(() => matches(options, query), [options, query]);
  const chosen = options.find((o) => o.value === value);

  // Opening starts clean, with the cursor on the first thing that matches
  // nothing in particular: on everything.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const t = setTimeout(() => box.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);
  useEffect(() => { setCursor(0); }, [query]);

  const take = (o: Choice) => { onChange(o.value); setOpen(false); };

  return (
    <RPopover.Root open={open} onOpenChange={setOpen}>
      <RPopover.Trigger asChild>
        <button type="button" id={id} className="pk" disabled={disabled} autoFocus={autoFocus}
                aria-invalid={invalid || undefined}>
          <span className={chosen ? "pk-v" : "pk-v empty"}>
            {chosen ? chosen.display : placeholder}
          </span>
          <span className="pk-c"><Icon name="chev" className="i sm" /></span>
        </button>
      </RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content className="pk-pop" sideOffset={4} align="start"
                          /* The search box takes the cursor, not the popover. */
                          onOpenAutoFocus={(e) => e.preventDefault()}>
          <div className="pk-find">
            <Icon name="search" className="i sm" />
            <input
              ref={box} className="pk-q" value={query} placeholder="Type to narrow"
              aria-label="Type to narrow the list" autoComplete="off"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault(); setCursor((n) => Math.min(n + 1, shown.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault(); setCursor((n) => Math.max(n - 1, 0));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  const hit = shown[cursor];
                  if (hit) take(hit);
                }
              }}
            />
          </div>
          <div className="pk-list" role="listbox">
            {shown.map((o, i) => (
              <button
                type="button" key={o.value} role="option" aria-selected={o.value === value}
                className={`pk-row${i === cursor ? " on" : ""}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => take(o)}
              >
                <span>{o.display}</span>
                {o.value === value && (
                  <span className="pk-tick"><Icon name="check" className="i sm" /></span>
                )}
              </button>
            ))}
            {/* Said plainly, rather than an empty box that looks broken. */}
            {!shown.length && <div className="pk-none">Nothing matches “{query}”.</div>}
          </div>
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  );
}
