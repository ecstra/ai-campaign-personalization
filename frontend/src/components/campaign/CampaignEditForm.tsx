import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Check, X } from "lucide-react"

interface EditFormValues {
    name: string
    sender_name: string
    goal: string
    follow_up_delay_minutes: number
    max_follow_ups: number
    scheduled_start_at: string
}

interface CampaignEditFormProps {
    editForm: EditFormValues
    setEditForm: (form: EditFormValues | ((prev: EditFormValues) => EditFormValues)) => void
    saving: boolean
    onSave: () => void
    onCancel: () => void
}

export default function CampaignEditForm({ editForm, setEditForm, saving, onSave, onCancel }: CampaignEditFormProps) {
    const [errors, setErrors] = useState<{ name?: string; sender_name?: string; goal?: string }>({})

    const handleSave = () => {
        const e: typeof errors = {}
        if (!editForm.name.trim()) e.name = "Name is required"
        if (!editForm.sender_name.trim()) e.sender_name = "Sender name is required"
        if (!editForm.goal.trim()) e.goal = "Goal is required"
        if (Object.keys(e).length > 0) {
            setErrors(e)
            return
        }
        setErrors({})
        onSave()
    }

    const fieldClass = (key: keyof typeof errors) =>
        `h-9 text-sm ${errors[key] ? "border-destructive" : ""}`

    return (
        <div className="bg-card border rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Edit Campaign</h2>
                <div className="flex items-center gap-2">
                    <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1.5"><Check size={14} />{saving ? "Saving..." : "Save"}</Button>
                    <Button size="sm" variant="ghost" onClick={onCancel} className="gap-1.5"><X size={14} /> Cancel</Button>
                </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Name</label>
                    <Input value={editForm.name} onChange={e => { setEditForm({ ...editForm, name: e.target.value }); setErrors(prev => ({ ...prev, name: undefined })) }} className={fieldClass("name")} />
                    {errors.name && <p className="text-[11px] text-destructive">{errors.name}</p>}
                </div>
                <div className="space-y-1.5">
                    <label className="text-[12px] font-medium text-muted-foreground">Sender Name</label>
                    <Input value={editForm.sender_name} onChange={e => { setEditForm({ ...editForm, sender_name: e.target.value }); setErrors(prev => ({ ...prev, sender_name: undefined })) }} className={fieldClass("sender_name")} />
                    {errors.sender_name && <p className="text-[11px] text-destructive">{errors.sender_name}</p>}
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
                <Textarea value={editForm.goal} onChange={e => { setEditForm({ ...editForm, goal: e.target.value }); setErrors(prev => ({ ...prev, goal: undefined })) }} className={`text-sm min-h-[80px] resize-none ${errors.goal ? "border-destructive" : ""}`} />
                {errors.goal && <p className="text-[11px] text-destructive">{errors.goal}</p>}
            </div>
            <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-muted-foreground">Scheduled Start (optional)</label>
                <Input type="datetime-local" value={editForm.scheduled_start_at} onChange={e => setEditForm({ ...editForm, scheduled_start_at: e.target.value })} className="h-9 text-sm" />
                <p className="text-[11px] text-muted-foreground">Leave empty to start manually</p>
            </div>
        </div>
    )
}
