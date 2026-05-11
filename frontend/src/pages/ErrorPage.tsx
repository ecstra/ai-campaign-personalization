import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"


type ErrorPageProps = {
    title?: string
    message?: string
    statusCode?: number
}

export default function ErrorPage({
    title = "Something went wrong",
    message = "An unexpected error occurred. Please try again later.",
    statusCode = 500
}: ErrorPageProps) {
    return (
        <div className="min-h-screen bg-background flex items-center justify-center p-8">
            <div className="max-w-md w-full text-center space-y-6">
                <div className="flex justify-center">
                    <div className="rounded-full bg-destructive/10 p-6 flex items-center justify-center">
                        <span className="material-symbols-rounded text-[64px] text-destructive">warning</span>
                    </div>
                </div>

                <div className="space-y-2">
                    <h1 className="text-4xl font-bold">{statusCode}</h1>
                    <h2 className="text-2xl font-semibold">{title}</h2>
                    <p className="text-muted-foreground">
                        {message}
                    </p>
                </div>

                <Link to="/">
                    <Button className="gap-2 rounded-full h-12 px-8 text-[15px]">
                        <span className="material-symbols-rounded text-[20px]">home</span>
                        Go to Home
                    </Button>
                </Link>
            </div>
        </div>
    )
}
