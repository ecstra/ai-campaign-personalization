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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { del } from "@/lib/api"


type DeleteCampaignModalProps = {
    open: boolean
    onClose: () => void
    campaignId: string
    campaignName: string
}

export default function DeleteCampaignModal({
    open,
    onClose,
    campaignId,
    campaignName
}: DeleteCampaignModalProps) {
    const navigate = useNavigate()
    const [confirmName, setConfirmName] = useState("")
    const [deleting, setDeleting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const isValid = confirmName === campaignName

    const handleDelete = async () => {
        if (!isValid) return

        try {
            setDeleting(true)
            setError(null)
            await del(`/campaigns/${campaignId}`)
            navigate("/")
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to delete campaign")
        } finally {
            setDeleting(false)
        }
    }

    const handleClose = () => {
        if (!deleting) {
            setConfirmName("")
            setError(null)
            onClose()
        }
    }

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent showCloseButton={false} className="gap-6">
                <DialogHeader className="gap-3">
                    <DialogTitle>Delete Campaign</DialogTitle>
                    <DialogDescription>
                        This action cannot be undone. This will permanently delete the campaign and all associated leads and emails.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    <div className="space-y-1.5">
                        <Label htmlFor="confirm-name" className="text-[12px] pl-2">
                            Type <span className="font-medium">{campaignName}</span> to confirm
                        </Label>
                        <Input
                            id="confirm-name"
                            value={confirmName}
                            onChange={(e) => setConfirmName(e.target.value)}
                            placeholder="Campaign name"
                            disabled={deleting}
                            autoComplete="off"
                            className="h-11 text-[14px] rounded-full px-4"
                        />
                    </div>

                    {error && (
                        <div className="text-[13px] text-destructive-alert-foreground bg-destructive-alert p-3 rounded-xl">
                            {error}
                        </div>
                    )}
                </div>

                <DialogFooter className="sm:gap-2">
                    <Button variant="ghost" onClick={handleClose} disabled={deleting} className="rounded-full h-10 px-5">
                        Cancel
                    </Button>
                    <Button
                        variant="destructive"
                        onClick={handleDelete}
                        disabled={!isValid || deleting}
                        className="rounded-full h-10 px-5"
                    >
                        {deleting ? "Deleting..." : "Delete Campaign"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
