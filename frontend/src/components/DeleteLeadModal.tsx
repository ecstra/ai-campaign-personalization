import { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { del } from "@/lib/api"


type DeleteLeadModalProps = {
    open: boolean
    onClose: () => void
    campaignId: string
    leadId: string
    leadName: string
}

export default function DeleteLeadModal({
    open,
    onClose,
    campaignId,
    leadId,
    leadName
}: DeleteLeadModalProps) {
    const navigate = useNavigate()
    const [deleting, setDeleting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const handleDelete = async () => {
        try {
            setDeleting(true)
            setError(null)
            await del(`/campaigns/${campaignId}/leads/${leadId}`)
            navigate(`/campaigns/${campaignId}`)
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to delete lead")
        } finally {
            setDeleting(false)
        }
    }

    const handleClose = () => {
        if (!deleting) {
            setError(null)
            onClose()
        }
    }

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent>
                <DialogHeader>
                    <div className="size-12 rounded-full bg-destructive-container flex items-center justify-center mx-auto mb-2">
                        <span className="material-symbols-rounded text-[24px] text-destructive-container-foreground">delete_forever</span>
                    </div>
                    <DialogTitle className="text-center text-[20px]">Delete Lead</DialogTitle>
                    <DialogDescription className="text-center text-[14px]">
                        Are you sure you want to delete <span className="font-semibold">{leadName}</span>? This will permanently remove this lead and all their email activity from the campaign.
                    </DialogDescription>
                </DialogHeader>

                {error && (
                    <div className="text-[13px] text-destructive-alert-foreground bg-destructive-alert p-3 rounded-xs">
                        {error}
                    </div>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose} disabled={deleting} className="rounded-full h-10 px-5">
                        Cancel
                    </Button>
                    <Button
                        variant="destructive"
                        onClick={handleDelete}
                        disabled={deleting}
                        className="rounded-full h-10 px-5"
                    >
                        {deleting ? "Deleting..." : "Delete Lead"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
