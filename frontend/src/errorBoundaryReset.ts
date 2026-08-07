export type ErrorBoundaryResetKey = string | number | boolean | null | undefined

export function haveResetKeysChanged(
  previous: readonly ErrorBoundaryResetKey[] = [],
  next: readonly ErrorBoundaryResetKey[] = [],
) {
  return previous.length !== next.length || previous.some((key, index) => !Object.is(key, next[index]))
}
