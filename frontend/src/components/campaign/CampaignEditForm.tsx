import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Check, X } from "lucide-react"

interface CampaignEditFormProps {
    editForm: {
        name: string
        sender_name: string
        goal: string
        follow_up_delay_minutes: number
        max_follow_ups: number
        scheduled_start_at: string
    }
    setEditForm: (form: CampaignEditFormProps["editForm"] | ((prev: CampaignEditFormProps["editForm"]) => CampaignEditFormProps["editForm"])) => void
    saving: boolean
    onSave: () => void
    onCancel: () => void
}

export default function CampaignEditForm({ editForm, setEditForm, saving, onSave, onCancel }: CampaignEditFormProps) {
    return (
        <div className="bg-card border rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Edit Campaign</h2>
                <div className="flex items-center gap-2">
                    <Button size="sm" onClick={onSave} disabled={saving} className="gap-1.5"><Check size={14} />{saving ? "Saving..." : "Save"}</Button>
                    <Button size="sm" variant="ghost" onClick={onCancel} className="gap-1.5"><X size={14} /> Cancel</Button>
                </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Name</label>
                    <Input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} className="h-9 text-sm" />
                </div>
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Sender Name</label>
                    <Input value={editForm.sender_name} onChange={e => setEditForm({ ...editForm, sender_name: e.target.value })} className="h-9 text-sm" />
                </div>
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Follow-up Delay (minutes)</label>
                    <Input type="number" value={editForm.follow_up_delay_minutes} onChange={e => setEditForm({ ...editForm, follow_up_delay_minutes: parseInt(e.target.value) || 0 })} className="h-9 text-sm" />
                </div>
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Max Follow-ups</label>
                    <Input type="number" value={editForm.max_follow_ups} onChange={e => setEditForm({ ...editForm, max_follow_ups: parseInt(e.target.value) || 0 })} className="h-9 text-sm" />
                </div>
            </div>
            <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-muted-foreground">Goal</label>
                <Textarea value={editForm.goal} onChange={e => setEditForm({ ...editForm, goal: e.target.value })} className="text-sm min-h-[80px] resize-none" />
            </div>
            <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-muted-foreground">Scheduled Start (optional)</label>
                <Input type="datetime-local" value={editForm.scheduled_start_at} onChange={e => setEditForm({ ...editForm, scheduled_start_at: e.target.value })} className="h-9 text-sm" />
                <p className="text-[11px] text-muted-foreground">Leave empty to start manually</p>
            </div>
        </div>
    )
}
