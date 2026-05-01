export const API_URL = import.meta.env.VITE_API_URL || "/api"

type RequestOptions = {
    method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH"
    body?: unknown
    headers?: Record<string, string>
}

export class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
        super(message)
        this.status = status
        this.name = "ApiError"
    }
}

export async function api<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    const token = localStorage.getItem("auth_token")

    const config: RequestInit = {
        method: options?.method || "GET",
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options?.headers,
        },
    }

    if (options?.body) {
        config.body = JSON.stringify(options.body)
    }

    const res = await fetch(`${API_URL}${endpoint}`, config)

    if (res.status === 401) {
        // Token expired or invalid, clear auth state and redirect to login
        localStorage.removeItem("auth_token")
        localStorage.removeItem("auth_user")
        window.location.href = "/login"
        throw new ApiError("Session expired", 401)
    }

    if (!res.ok) {
        const errorText = await res.text().catch(() => "Unknown error")
        throw new ApiError(errorText || `HTTP ${res.status}`, res.status)
    }

    return res.json()
}

// Convenience methods
export const get = <T>(endpoint: string) => api<T>(endpoint)

export const post = <T>(endpoint: string, body: unknown) =>
    api<T>(endpoint, { method: "POST", body })

export const put = <T>(endpoint: string, body: unknown) =>
    api<T>(endpoint, { method: "PUT", body })

export const patch = <T>(endpoint: string, body: unknown) =>
    api<T>(endpoint, { method: "PATCH", body })

export const del = <T>(endpoint: string) =>
    api<T>(endpoint, { method: "DELETE" })
