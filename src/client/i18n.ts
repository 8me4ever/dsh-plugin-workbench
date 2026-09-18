/**
 * The translation shape this plugin binds once and passes around.
 *
 * `ctx.locale.bind(namespace)` returns a function that resolves a key against
 * this plugin's dictionary and falls back to the key itself, so a missing
 * entry shows up as the key rather than as blank space.
 */
export type Translate = (key: string) => string
