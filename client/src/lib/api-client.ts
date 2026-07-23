const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  public readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new ApiError(payload?.detail ?? `Request failed (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

export function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`
}
