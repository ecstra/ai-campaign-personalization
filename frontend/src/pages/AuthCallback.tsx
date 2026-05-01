import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export default function AuthCallback() {
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()
    const { handleCallback } = useAuth()
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const code = searchParams.get("code")
        const state = searchParams.get("state")
        const errorParam = searchParams.get("error")

        if (errorParam) {
            setError(`Google authentication failed: ${errorParam}`)
            return
        }

        if (!code || !state) {
            setError("Missing authorization code or state parameter.")
            return
        }

        handleCallback(code, state)
            .then(() => navigate("/", { replace: true }))
            .catch((err) => setError(err?.message || "Authentication failed. Please try again."))
    }, [searchParams, handleCallback, navigate])

    if (error) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-muted/30">
                <Card className="w-full max-w-md mx-4">
                    <CardHeader className="text-center">
                        <CardTitle className="text-destructive">Authentication Error</CardTitle>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex justify-center">
                        <Button onClick={() => navigate("/login", { replace: true })}>
                            Back to Login
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-center space-y-4">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
                <p className="text-muted-foreground">Completing sign in...</p>
            </div>
        </div>
    )
}
