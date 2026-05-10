import { Navigate } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import AppLayout from "@/components/AppLayout"
import { Skeleton } from "@/components/ui/skeleton"

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { isAuthenticated, isLoading } = useAuth()

    if (isLoading) {
        return (
            <AppLayout>
                <div className="p-6">
                    <div className="max-w-5xl mx-auto space-y-6">
                        <Skeleton className="h-8 w-64" />
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <Skeleton className="h-[200px] w-full rounded-xl" />
                            <Skeleton className="h-[200px] w-full rounded-xl" />
                        </div>
                        <Skeleton className="h-[400px] w-full rounded-xl" />
                    </div>
                </div>
            </AppLayout>
        )
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />
    }

    return <>{children}</>
}
