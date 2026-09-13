import { QueryClient, useQuery } from '@tanstack/react-query'
import type { ClubNote, Match, Player, Stats } from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      credentials: 'include',
      headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    })
  } catch {
    throw new ApiError('Could not reach the club. Check your connection and try again.', 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = Array.isArray(body.detail)
      ? body.detail
          .map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join(' ')}: ${d.msg}`)
          .join('. ')
      : body.detail
    if (response.status === 401 && !path.startsWith('/auth/')) {
      queryClient.setQueryData(['me'], null)
    }
    throw new ApiError(
      typeof detail === 'string' ? detail : 'Something went wrong. Please try again.',
      response.status,
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
export function send<T>(path: string, data?: unknown, method = 'POST') {
  return api<T>(path, { method, ...(data === undefined ? {} : { body: JSON.stringify(data) }) })
}
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1,
      refetchOnWindowFocus: true,
    },
  },
})
export function refreshClub() {
  return queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'config' })
}
export function useClub() {
  const players = useQuery({ queryKey: ['players'], queryFn: () => api<Player[]>('/players') })
  const matches = useQuery({ queryKey: ['matches'], queryFn: () => api<Match[]>('/matches') })
  const stats = useQuery({
    queryKey: ['stats', 'active'],
    queryFn: () => api<Stats>('/stats?active_season=true'),
  })
  const notes = useQuery({ queryKey: ['notes'], queryFn: () => api<ClubNote[]>('/notes') })
  return {
    players: players.data ?? [],
    matches: matches.data ?? [],
    stats: stats.data,
    notes: notes.data ?? [],
    loading: players.isPending || matches.isPending || stats.isPending || notes.isPending,
    error: players.error || matches.error || stats.error || notes.error,
  }
}
