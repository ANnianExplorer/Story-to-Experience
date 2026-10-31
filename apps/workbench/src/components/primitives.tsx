/**
 * Shared presentational primitives for the workbench.
 *
 * Layout-only: no business state, no API calls. Colours and spacing come from
 * the generated token CSS plus the shared classical layer, so a new page cannot
 * invent its own palette.
 */
import React from 'react';

export function StatusPill({ tone, children }: { tone: 'neutral' | 'ok' | 'warn' | 'bad'; children: React.ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

/**
 * A numbered section, in the manner of a book chapter: an index numeral, a
 * hairline, then the title. The number is decorative for layout, but the
 * heading itself stays a real `<h2>` so screen readers keep the outline.
 */
export function Panel({
  title,
  headingId,
  index,
  children,
  className = '',
}: {
  title: string;
  headingId: string;
  index?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()} aria-labelledby={headingId}>
      {index && (
        // The numeral and the hairline are a chapter mark; repeating the title
        // here would duplicate the heading immediately below it.
        <p className="xj-index" aria-hidden="true">
          <span className="xj-index-no">{index}</span>
        </p>
      )}
      <h2 id={headingId}>{title}</h2>
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      {label}
      {children}
    </label>
  );
}

export function Count({ value }: { value: number }) {
  return <span className="count">{value}</span>;
}

/** A vermilion seal used as a mark, never as a control. */
export function Seal({ children, filled = false, press = false }: { children: React.ReactNode; filled?: boolean; press?: boolean }) {
  const classes = ['xj-seal'];
  if (filled) classes.push('xj-seal--filled');
  if (press) classes.push('xj-seal--press');
  return (
    <span className={classes.join(' ')} aria-hidden="true">
      {children}
    </span>
  );
}
