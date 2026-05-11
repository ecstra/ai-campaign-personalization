import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

type ConfirmDialogProps = {
    open: boolean
    onClose: () => void
    onConfirm: () => void
    title: string
    description: string
    confirmLabel?: string
    loading?: boolean
    variant?: "destructive" | "default"
}

export default function ConfirmDialog({
    open,
    onClose,
    onConfirm,
    title,
    description,
    confirmLabel = "Delete",
    loading = false,
    variant = "destructive",
}: ConfirmDialogProps) {
    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent>
                <DialogHeader>
                    <div className="size-12 rounded-full bg-destructive-container flex items-center justify-center mx-auto mb-2">
                        <span className="material-symbols-rounded text-[24px] text-destructive-container-foreground">delete_forever</span>
                    </div>
                    <DialogTitle className="text-center text-[20px]">{title}</DialogTitle>
                    <DialogDescription className="text-center text-[14px]">
                        {description}
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} disabled={loading} className="rounded-full h-10 px-5">
                        Cancel
                    </Button>
                    <Button
                        variant={variant}
                        onClick={onConfirm}
                        disabled={loading}
                        className="rounded-full h-10 px-5"
                    >
                        {loading ? "Deleting..." : confirmLabel}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
