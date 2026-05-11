import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"


export default function NotFound() {
    return (
        <div className="min-h-screen bg-background flex items-center justify-center p-8">
            <div className="max-w-md w-full text-center space-y-6">
                <div className="flex justify-center">
                    <div className="rounded-full bg-muted p-6 flex items-center justify-center">
                        <span className="material-symbols-rounded text-[64px] text-muted-foreground">help</span>
                    </div>
                </div>

                <div className="space-y-2">
                    <h1 className="text-4xl font-bold">404</h1>
                    <h2 className="text-2xl font-semibold">Page Not Found</h2>
                    <p className="text-muted-foreground">
                        The page you're looking for doesn't exist or has been moved.
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
