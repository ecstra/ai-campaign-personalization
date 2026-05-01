import { createContext, useContext, useEffect, useState, useCallback } from "react"
import { get, post } from "@/lib/api"
import {
    type User,
    getStoredToken,
    setStoredToken,
    clearStoredToken,
    getStoredUser,
    setStoredUser,
} from "@/lib/auth"

type AuthContextType = {
    user: User | null
    token: string | null
    isLoading: boolean
    isAuthenticated: boolean
    login: () => Promise<void>
    handleCallback: (code: string, state: string) => Promise<void>
    logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(getStoredUser)
    const [token, setToken] = useState<string | null>(getStoredToken)
    const [isLoading, setIsLoading] = useState(true)

    // Validate stored token on mount
    useEffect(() => {
        const storedToken = getStoredToken()
        if (!storedToken) {
            setIsLoading(false)
            return
        }

        get<User>("/auth/me")
            .then((userData) => {
                setUser(userData)
                setStoredUser(userData)
            })
            .catch(() => {
                // Token is invalid or expired
                clearStoredToken()
                setToken(null)
                setUser(null)
            })
            .finally(() => setIsLoading(false))
    }, [])

    const login = useCallback(async () => {
        const { url, state } = await get<{ url: string; state: string }>("/auth/google/login")
        // Store state in sessionStorage for CSRF validation on callback
        sessionStorage.setItem("oauth_state", state)
        window.location.href = url
    }, [])

    const handleCallback = useCallback(async (code: string, state: string) => {
        // Validate state matches what we stored (CSRF protection)
        const storedState = sessionStorage.getItem("oauth_state")
        if (storedState && storedState !== state) {
            throw new Error("OAuth state mismatch. Possible CSRF attack.")
        }
        sessionStorage.removeItem("oauth_state")

        const response = await post<{ token: string; user: User }>(
            "/auth/google/callback",
            { code, state },
        )

        setStoredToken(response.token)
        setStoredUser(response.user)
        setToken(response.token)
        setUser(response.user)
    }, [])

    const logout = useCallback(() => {
        clearStoredToken()
        setToken(null)
        setUser(null)
    }, [])

    return (
        <AuthContext.Provider
            value={{
                user,
                token,
                isLoading,
                isAuthenticated: !!token && !!user,
                login,
                handleCallback,
                logout,
            }}
        >
            {children}
        </AuthContext.Provider>
    )
}

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext)
    if (!context) {
        throw new Error("useAuth must be used within an AuthProvider")
    }
    return context
}
