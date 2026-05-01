const TOKEN_KEY = "auth_token"
const USER_KEY = "auth_user"

export type User = {
    id: string
    email: string
    name: string
    picture_url: string | null
}

export function getStoredToken(): string | null {
    return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken(): void {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
}

export function getStoredUser(): User | null {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try {
        return JSON.parse(raw) as User
    } catch {
        return null
    }
}

export function setStoredUser(user: User): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function isAuthenticated(): boolean {
    return getStoredToken() !== null
}
