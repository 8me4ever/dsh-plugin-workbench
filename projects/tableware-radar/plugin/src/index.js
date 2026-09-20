/**
 * dsh-tableware-radar — host half (the data face).
 *
 * Reads the pipeline's single source of truth `data/analysis.json` and exposes it to the
 * browser as the `tablewareRadar` service (`ctx.remote.tablewareRadar`), via the hand-written
 * TYPERT manifest in `./typert.host.js` (auto-registered by the typert loader).
 *
 * Both methods are 0-parameter (ARCHITECTURE §3.4) — the gateway strictly validates
 * `parameters.length`.
 *
 * It declares NO `inject`: the host half wants nothing from the host, so the entry can never
 * be stuck waiting for a service a profile does not compose.
 */
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

/** Cordis plugin name — also the client bundle id and the patch row id. */
export const name = 'dsh-tableware-radar'

/** No host-side service dependencies. */
export const inject = []

/**
 * Default data directory. Overridable via plugin config `dataDir` or the
 * `TABLEWARE_DATA_DIR` env var, so the plugin is not pinned to one checkout.
 */
export const DEFAULT_DATA_DIR =
  process.env.TABLEWARE_DATA_DIR || 'F:/Samuel/dsh-plugins/dsh-tableware-radar/data'

/** Reads `analysis.json` and answers status probes. */
export class TablewareRadarService {
  /** @param {string} dataDir absolute directory holding `analysis.json`. */
  constructor(dataDir) {
    this.dataDir = dataDir
    this.analysisPath = join(dataDir, 'analysis.json')
  }

  /**
   * Report whether the pipeline has ever produced `analysis.json`.
   * @returns {{present: boolean, path: string, mtimeMs: number, bytes: number, generatedAt: (string|null)}}
   */
  getStatus() {
    try {
      const stat = statSync(this.analysisPath)
      return {
        present: true,
        path: this.analysisPath,
        mtimeMs: stat.mtimeMs,
        bytes: stat.size,
        generatedAt: this._generatedAt(),
      }
    } catch {
      return {
        present: false,
        path: this.analysisPath,
        mtimeMs: 0,
        bytes: 0,
        generatedAt: null,
      }
    }
  }

  /**
   * Read and parse `analysis.json`.
   * @returns {object|null} the analysis, or `null` when the file is missing/unreadable.
   */
  getAnalysis() {
    try {
      return JSON.parse(readFileSync(this.analysisPath, 'utf8'))
    } catch {
      return null
    }
  }

  /** @returns {string|null} the file's `generated_at`, or null. */
  _generatedAt() {
    try {
      const parsed = JSON.parse(readFileSync(this.analysisPath, 'utf8'))
      return typeof parsed?.generated_at === 'string' ? parsed.generated_at : null
    } catch {
      return null
    }
  }
}

/**
 * Mount the host half.
 * @param {object} ctx host cordis context.
 * @param {object} [config] plugin config (`{ dataDir?: string }`).
 */
export function apply(ctx, config = {}) {
  const dataDir = (config && config.dataDir) || DEFAULT_DATA_DIR
  const service = new TablewareRadarService(dataDir)
  ctx.provide('tablewareRadar', service)
  if (ctx.logger && typeof ctx.logger.info === 'function') {
    ctx.logger.info(`[dsh-tableware-radar] data face mounted; analysis=${service.analysisPath}`)
  }
}

export default { name, inject, apply }
