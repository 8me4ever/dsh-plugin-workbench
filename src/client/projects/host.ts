/**
 * Renders one project slot.
 *
 * Two branches only: a filled slot hands control to the project, an empty slot
 * shows the reserved-slot page. The page is deliberately instructive — it names
 * the index, the file to edit, and the minimal shape of a project — because the
 * console lets you click a free card, and what you find behind it should tell
 * you how to fill it rather than just look empty.
 */
import { createElement as h, type ReactElement } from 'react'
import type { Translate } from '../i18n.ts'
import { CODE, HINT, T } from '../tokens.ts'
import { pad2, slotLabel } from '../views.ts'
import type { ProjectContext, ProjectSlot } from './types.ts'

/** The minimal project shape shown on an empty slot, kept in sync with the docs. */
const SNIPPET = [
  '{',
  "  id: 'my-project',",
  "  title: () => '我的项目',",
  "  render: (ctx) => h('div', null, '内容'),",
  '}',
].join('\n')

/**
 * Build the slot renderer.
 * @param projectCtx - the context every project receives.
 * @param t - bound translator.
 */
export function createProjectHost(projectCtx: ProjectContext, t: Translate) {
  return function ProjectHost(props: { slot: ProjectSlot; index: number }): ReactElement {
    const { slot, index } = props
    if (slot === null || slot === undefined) return placeholder(index, t)

    // A project is user-authored code running inside the host UI. Calling
    // `render` ourselves means a throw here is caught by us instead of
    // unmounting the workbench — one broken project should not cost you the
    // other three.
    let body: ReactElement | null
    try {
      body = slot.render(projectCtx)
    } catch (err) {
      body = failure(index, err, t)
    }
    return h('div', { style: { minHeight: '100%' } }, body)
  }
}

/** The reserved-slot card. */
function placeholder(index: number, t: Translate): ReactElement {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 12,
        maxWidth: 520,
        margin: '24px auto 0',
        padding: '20px 22px',
        border: `1px dashed ${T.border2}`,
        borderRadius: 12,
        background: T.bgLayer1,
      },
    },
    h(
      'div',
      { style: { display: 'flex', alignItems: 'baseline', gap: 10 } },
      h(
        'span',
        {
          style: {
            fontFamily: T.mono,
            fontSize: 26,
            fontWeight: 600,
            lineHeight: 1,
            color: T.textDim,
          },
        },
        pad2(index + 1),
      ),
      h('span', { style: { fontSize: 14, fontWeight: 500, color: T.text1 } }, slotLabel(index, t)),
      h(
        'span',
        {
          style: {
            fontSize: 11,
            color: T.text3,
            border: `1px solid ${T.border2}`,
            borderRadius: 4,
            padding: '1px 5px',
          },
        },
        t('slot.free'),
      ),
    ),
    h('div', { style: HINT }, t('slot.free.hint')),
    h(
      'div',
      { style: { display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 12 } },
      h('span', { style: { color: T.text3 } }, t('slot.free.file')),
      h('code', { style: { ...CODE, color: T.brand } }, 'src/client/projects/slots.ts'),
    ),
    h(
      'pre',
      {
        style: {
          ...CODE,
          margin: 0,
          width: '100%',
          boxSizing: 'border-box',
          padding: '10px 12px',
          borderRadius: 8,
          background: T.bgLayer2,
          border: `1px solid ${T.border1}`,
          whiteSpace: 'pre',
          overflowX: 'auto',
        },
      },
      SNIPPET,
    ),
  )
}

/** Shown in place of a project whose `render` threw. */
function failure(index: number, err: unknown, t: Translate): ReactElement {
  const message = err instanceof Error ? err.message : String(err)
  return h(
    'div',
    {
      style: {
        maxWidth: 560,
        padding: '14px 16px',
        border: `1px solid ${T.border2}`,
        borderLeft: `3px solid ${T.danger}`,
        borderRadius: 10,
        background: T.bgLayer1,
      },
    },
    h('div', { style: { fontSize: 13, fontWeight: 500, color: T.danger } },
      `${slotLabel(index, t)} · ${t('slot.error')}`),
    h('div', { style: { ...CODE, marginTop: 6, color: T.text2, wordBreak: 'break-word' } }, message),
  )
}
