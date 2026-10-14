export async function collectHistory<T>(
  readPage: (cursor?: string, signal?: AbortSignal) => Promise<{ items: T[]; nextCursor: string | null }>,
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = []
  const seen = new Set<string>()
  let cursor: string | undefined
  do {
    signal?.throwIfAborted()
    const page = await readPage(cursor, signal)
    signal?.throwIfAborted()
    items.push(...page.items)
    cursor = page.nextCursor ?? undefined
    if (cursor) {
      if (seen.has(cursor) || page.items.length === 0) {
        throw new Error('历史分页异常，请刷新后重试。')
      }
      seen.add(cursor)
    }
  } while (cursor)
  return items
}
