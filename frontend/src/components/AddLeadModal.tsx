import { useState } from "react"
import { post } from "@/lib/api"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"

const EMPTY_FORM = {
    email: "",
    first_name: "",
    last_name: "",
    company: "",
    title: "",
    notes: "",
}

export default function AddLeadModal({
    open,
    onClose,
    onSuccess,
    campaignId
}: {
    open: boolean
    onClose: () => void
    onSuccess: () => void
    campaignId: string
}) {
    const [loading, setLoading] = useState(false)
    const [fieldErrors, setFieldErrors] = useState<{
        email?: string
        first_name?: string
        last_name?: string
    }>({})
    const [form, setForm] = useState(EMPTY_FORM)

    const resetAndClose = () => {
        setForm(EMPTY_FORM)
        setFieldErrors({})
        onClose()
    }

    const validateField = (name: string, value: string) => {
        let error: string | undefined

        switch (name) {
            case "first_name":
                if (!value.trim()) error = "First name is required"
                break
            case "last_name":
                if (!value.trim()) error = "Last name is required"
                break
            case "email":
                if (!value.trim()) {
                    error = "Email is required"
                } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
                    error = "Invalid email address"
                }
                break
        }

        setFieldErrors(prev => ({ ...prev, [name]: error }))
        return !error
    }

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { id, value } = e.target
        setForm(prev => ({ ...prev, [id]: value }))
        // Only validate if it's one of the required fields we track errors for
        if (["first_name", "last_name", "email"].includes(id)) {
            validateField(id, value)
        }
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()

        const isFirstNameValid = validateField("first_name", form.first_name)
        const isLastNameValid = validateField("last_name", form.last_name)
        const isEmailValid = validateField("email", form.email)

        if (!isFirstNameValid || !isLastNameValid || !isEmailValid) {
            return
        }

        setLoading(true)

        try {
            await post(`/campaigns/${campaignId}/leads`, form)
            setForm(EMPTY_FORM)
            setFieldErrors({})
            onSuccess()
            toast.success("Lead added successfully")
        } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to add lead"
            toast.error(message)
        } finally {
            setLoading(false)
        }
    }

    const hasFieldErrors = Object.values(fieldErrors).some(Boolean)
    const hasEmptyFields = !form.first_name.trim() || !form.last_name.trim() || !form.email.trim()

    return (
        <Dialog open={open} onOpenChange={(isOpen) => !isOpen && resetAndClose()}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Add Lead</DialogTitle>
                    <DialogDescription>
                        Add a new lead to this campaign
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="first_name">First Name *</Label>
                            <Input
                                id="first_name"
                                value={form.first_name}
                                onChange={handleInputChange}
                                placeholder="John"
                                aria-invalid={!!fieldErrors.first_name}
                                aria-describedby={fieldErrors.first_name ? "first_name-error" : undefined}
                                className={fieldErrors.first_name ? "border-destructive" : ""}
                            />
                            {fieldErrors.first_name && (
                                <p id="first_name-error" className="text-xs text-destructive">{fieldErrors.first_name}</p>
                            )}
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="last_name">Last Name *</Label>
                            <Input
                                id="last_name"
                                value={form.last_name}
                                onChange={handleInputChange}
                                placeholder="Doe"
                                aria-invalid={!!fieldErrors.last_name}
                                aria-describedby={fieldErrors.last_name ? "last_name-error" : undefined}
                                className={fieldErrors.last_name ? "border-destructive" : ""}
                            />
                            {fieldErrors.last_name && (
                                <p id="last_name-error" className="text-xs text-destructive">{fieldErrors.last_name}</p>
                            )}
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="email">Email *</Label>
                        <Input
                            id="email"
                            type="email"
                            value={form.email}
                            onChange={handleInputChange}
                            placeholder="john@company.com"
                            aria-invalid={!!fieldErrors.email}
                            aria-describedby={fieldErrors.email ? "email-error" : undefined}
                            className={fieldErrors.email ? "border-destructive" : ""}
                        />
                        {fieldErrors.email && (
                            <p id="email-error" className="text-xs text-destructive">{fieldErrors.email}</p>
                        )}
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="company">Company</Label>
                            <Input
                                id="company"
                                value={form.company}
                                onChange={handleInputChange}
                                placeholder="Acme Inc"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="title">Title</Label>
                            <Input
                                id="title"
                                value={form.title}
                                onChange={handleInputChange}
                                placeholder="CTO"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="notes">Notes (for personalization)</Label>
                        <textarea
                            id="notes"
                            value={form.notes}
                            onChange={handleInputChange}
                            className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            placeholder="Met at conference, interested in AI..."
                        />
                    </div>

                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={resetAndClose}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={loading || hasFieldErrors || hasEmptyFields}>
                            {loading ? "Adding..." : "Add Lead"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}