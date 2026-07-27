const configuredApiBaseUrl = import.meta.env.VITE_API_URL?.trim()
const API_BASE_URL = (configuredApiBaseUrl || "http://localhost:8000").replace(/\/+$/, "")

export class ApiError extends Error {
  public readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

function errorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string" && payload.trim()) return payload
  if (!payload || typeof payload !== "object") return fallback

  const record = payload as Record<string, unknown>
  if (typeof record.detail === "string" && record.detail.trim()) return record.detail
  if (typeof record.message === "string" && record.message.trim()) return record.message

  if (Array.isArray(record.detail)) {
    const validationMessages = record.detail.flatMap((entry) => {
      if (!entry || typeof entry !== "object") return []
      const message = (entry as Record<string, unknown>).msg
      return typeof message === "string" && message.trim() ? [message] : []
    })
    if (validationMessages.length > 0) return validationMessages.join(". ")
  }

  return fallback
}

async function responseErrorMessage(response: Response) {
  const fallback = `Request failed (${response.status})`
  const contentType = response.headers.get("content-type") ?? ""

  if (contentType.includes("application/json")) {
    return errorMessage(await response.json().catch(() => null), fallback)
  }

  const body = await response.text().catch(() => "")
  return body.trim() || fallback
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(apiUrl(path), init)
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error
    throw new ApiError("Unable to reach the ReelProof API. Check that the server is running and VITE_API_URL is correct.", 0)
  }

  if (!response.ok) {
    throw new ApiError(await responseErrorMessage(response), response.status)
  }

  return response.json() as Promise<T>
}

export function apiUrl(path: string) {
  return `${API_BASE_URL}/${path.replace(/^\/+/, "")}`
}
