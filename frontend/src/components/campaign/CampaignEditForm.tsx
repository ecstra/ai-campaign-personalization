import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"


interface EditFormValues {
    name: string
    sender_name: string
    goal: string
    follow_up_delay_minutes: number
    max_follow_ups: number
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

    return (
        <div className="bg-card border border-border rounded-2xl p-6 space-y-5 ">
            <div className="flex items-center justify-between">
                <h2 className="text-title-l">Edit Campaign</h2>
                <div className="flex items-center gap-3">
                    <Button onClick={handleSave} disabled={saving} className="gap-2 rounded-full h-10 px-5  text-[14px]">
                        <span className="material-symbols-rounded text-[18px]">check</span>{saving ? "Saving..." : "Save"}
                    </Button>
                    <Button variant="ghost" onClick={onCancel} className="gap-2 rounded-full h-10 px-5 text-[14px]">
                        <span className="material-symbols-rounded text-[18px]">close</span> Cancel
                    </Button>
                </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                    <label className="text-[13px] font-medium text-muted-foreground pl-2">Name</label>
                    <Input value={editForm.name} onChange={e => { setEditForm({ ...editForm, name: e.target.value }); setErrors(prev => ({ ...prev, name: undefined })) }} className={`h-11 text-[14px] rounded-full px-4 ${errors.name ? "border-destructive" : ""}`} />
                    {errors.name && <p className="text-[12px] text-destructive pl-2">{errors.name}</p>}
                </div>
                <div className="space-y-1.5">
                    <label className="text-[13px] font-medium text-muted-foreground pl-2">Sender Name</label>
                    <Input value={editForm.sender_name} onChange={e => { setEditForm({ ...editForm, sender_name: e.target.value }); setErrors(prev => ({ ...prev, sender_name: undefined })) }} className={`h-11 text-[14px] rounded-full px-4 ${errors.sender_name ? "border-destructive" : ""}`} />
                    {errors.sender_name && <p className="text-[12px] text-destructive pl-2">{errors.sender_name}</p>}
                </div>
                <div className="space-y-1.5">
                    <label className="text-[13px] font-medium text-muted-foreground pl-2">Follow-up Delay (minutes)</label>
                    <Input type="number" value={editForm.follow_up_delay_minutes} onChange={e => setEditForm({ ...editForm, follow_up_delay_minutes: parseInt(e.target.value) || 0 })} className="h-11 text-[14px] rounded-full px-4 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
                </div>
                <div className="space-y-1.5">
                    <label className="text-[13px] font-medium text-muted-foreground pl-2">Max Follow-ups</label>
                    <Input type="number" value={editForm.max_follow_ups} onChange={e => setEditForm({ ...editForm, max_follow_ups: parseInt(e.target.value) || 0 })} className="h-11 text-[14px] rounded-full px-4 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
                </div>
            </div>
            <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-muted-foreground pl-2">Goal</label>
                <Textarea value={editForm.goal} onChange={e => { setEditForm({ ...editForm, goal: e.target.value }); setErrors(prev => ({ ...prev, goal: undefined })) }} className={`text-[14px] p-4 rounded-sm min-h-[100px] resize-none ${errors.goal ? "border-destructive" : ""}`} />
                {errors.goal && <p className="text-[12px] text-destructive pl-2">{errors.goal}</p>}
            </div>
        </div>
    )
}
