/**
 * Theme tokens and the handful of shared style atoms.
 *
 * The DSH web frontend exposes its design system as CSS custom properties in
 * the `--dsw-alias-*` family (the shipped client plugins style themselves with
 * exactly these names). We read the variables and keep a light-theme literal
 * as the fallback, so a missing variable degrades to something readable rather
 * than to `initial`.
 *
 * Never hardcode a colour here without also adding its variable: the panel has
 * to survive the host switching between light and dark.
 */
import type { CSSProperties } from 'react'

export const T = {
  font: 'var(--dsw-font-family, system-ui, -apple-system, "Segoe UI", sans-serif)',
  mono: 'var(--ds-font-family-code, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace)',

  /** Surfaces, from the page itself outwards to raised cards. */
  bgBase: 'var(--dsw-alias-bg-base, #FFFFFF)',
  bgLayer1: 'var(--dsw-alias-bg-layer-1, #FFFFFF)',
  bgLayer2: 'var(--dsw-alias-bg-layer-2, #F4F5F6)',
  bgHover: 'var(--dsw-alias-interactive-bg-hover, rgba(15, 17, 21, 0.06))',

  /** Hairlines. l1 is the faintest, l3 the most assertive. */
  border1: 'var(--dsw-alias-border-l1, rgba(15, 17, 21, 0.08))',
  border2: 'var(--dsw-alias-border-l2, rgba(15, 17, 21, 0.14))',
  border3: 'var(--dsw-alias-border-l3, rgba(15, 17, 21, 0.22))',

  /** Text ramp: primary → secondary → tertiary → dimmed. */
  text1: 'var(--dsw-alias-label-primary, #0F1115)',
  text2: 'var(--dsw-alias-label-secondary, #61666B)',
  text3: 'var(--dsw-alias-label-tertiary, #81858C)',
  textDim: 'var(--dsw-alias-label-dimmed, #ADB2B8)',

  /** Semantic accents. */
  brand: 'var(--dsw-alias-brand-primary, #4D6BFE)',
  info: 'var(--dsw-alias-state-business-primary, #185FA5)',
  ok: 'var(--dsw-alias-state-success-primary, #0F6E56)',
  warn: 'var(--dsw-alias-state-warn-label, #854F0B)',
  danger: 'var(--dsw-alias-state-error-primary, #E24B4A)',

  elevation: 'var(--dsw-elevation-prominent, 0 12px 32px rgba(15, 17, 21, 0.16))',
} as const

/** Scrolling containers: hide the bar unless it is actually needed. */
export const SCROLL: CSSProperties = {
  overflowY: 'auto',
  overflowX: 'hidden',
  scrollbarWidth: 'thin',
}

/** A borderless button that only shows a surface on hover/active. */
export function ghostButton(active = false): CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    border: '1px solid transparent',
    borderRadius: 6,
    background: active ? T.bgHover : 'transparent',
    color: 'inherit',
    font: 'inherit',
    fontSize: 12,
    padding: '2px 8px',
    cursor: 'pointer',
  }
}

/** A small outlined button, for the few explicit actions. */
export const OUTLINE_BUTTON: CSSProperties = {
  border: `1px solid ${T.border2}`,
  borderRadius: 6,
  background: 'transparent',
  color: 'inherit',
  font: 'inherit',
  fontSize: 12,
  padding: '2px 8px',
  cursor: 'pointer',
}

/** Muted, small explanatory text. */
export const HINT: CSSProperties = {
  color: T.text3,
  fontSize: 12,
  lineHeight: 1.6,
}

/** A block of code or a raw identifier. */
export const CODE: CSSProperties = {
  fontFamily: T.mono,
  fontSize: 11.5,
  lineHeight: 1.6,
  color: T.text2,
}

/** Section heading inside a scrolling view. */
export const SECTION_TITLE: CSSProperties = {
  fontSize: 11,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: T.text3,
  fontWeight: 500,
}

/**
 * Colour for a plugin loader phase, matching `store.ts#FiberPhase`.
 * Kept here so the trigger, the control room and any project agree.
 */
export function phaseColor(phase: string | null): string {
  switch (phase) {
    case 'active': return T.ok
    case 'loading': return T.info
    case 'pending': return T.warn
    case 'failed': return T.danger
    case 'unloading': return T.text3
    default: return T.textDim
  }
}
