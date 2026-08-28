/**
 * dsh-job-radar client: registers a "Job Radar" settings section rendering
 * the job dashboard panel. Reads data through the jobRadar Remote mounted
 * by the host half of this same bundle.
 *
 * Built by esbuild into the __ModuleLoader__ factory bundle at
 * client/client.js; the only externals are react and the loader module
 * table's client-runtime entries.
 */
import { createElement as h } from 'react'
import { RadarPanel } from './RadarPanel.ts'

const NS = 'dsh-job-radar'

/** The subset of the slots service this plugin touches (structural). */
interface SlotsService {
  inject(slot: string, register: () => unknown): void
  register(meta: Record<string, unknown>, component: () => unknown): unknown
}

/** The client cordis context shape this plugin relies on (structural). */
interface RadarClientContext {
  effect(callback: () => unknown, label?: string): void
  locale: {
    register(namespace: string, dicts: { zh: Record<string, string>; en: Record<string, string> }): unknown
    bind(namespace: string): (key: string) => string
  }
  slots: SlotsService
}

export const name = 'dsh-job-radar'
export const inject = ['slots', 'locale']

/** The remote namespace handle; resolved after mount via ctx.reflect. */
interface ReflectHost {
  reflect: { get(name: string): unknown }
}

export function apply(ctx: RadarClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh: DICT_ZH, en: DICT_EN }), 'dsh-job-radar: dictionaries')
  const t = ctx.locale.bind(NS)

  const reflectCtx = ctx as unknown as ReflectHost
  const remote = (): any =>
    (reflectCtx.reflect as unknown as { get(name: string): unknown }).get('remote.jobRadar')

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'job-radar',
    order: 30,
    label: () => t('nav'),
    locale: NS,
    inject: () => ({ hooks: { remote } }),
  }, () => h(RadarPanel, { hooks: { remote } })))
}

const DICT_ZH = { nav: 'Job Radar 岗位看板' }
const DICT_EN = { nav: 'Job Radar Dashboard' }
