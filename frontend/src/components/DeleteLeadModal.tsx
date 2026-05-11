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
                    <DialogTitle className="flex items-center gap-2 text-destructive">
                        <span className="material-symbols-rounded text-[28px]">warning</span>
                        Delete Lead
                    </DialogTitle>
                    <DialogDescription>
                        Are you sure you want to delete <span className="font-semibold">{leadName}</span>? This will permanently remove this lead and all their email activity from the campaign.
                    </DialogDescription>
                </DialogHeader>

                {error && (
                    <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
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