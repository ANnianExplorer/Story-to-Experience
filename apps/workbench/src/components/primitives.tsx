/**
 * Shared presentational primitives for the workbench.
 *
 * These are layout-only: no business state, no API calls. Colours and spacing
 * come from the generated token CSS so a new page cannot invent its own theme.
 */
import React from 'react';

export function StatusPill({ tone, children }: { tone: 'neutral' | 'ok' | 'warn' | 'bad'; children: React.ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function Panel({
  title,
  headingId,
  children,
  className = '',
}: {
  title: string;
  headingId: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()} aria-labelledby={headingId}>
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
