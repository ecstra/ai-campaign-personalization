import { useState, useMemo, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { post } from "@/lib/api"
import { type Campaign } from "@/lib/types"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"


type FieldErrors = {
    name?: string
    sender_name?: string
    goal?: string
    max_follow_ups?: string
    delay_days?: string
    delay_hours?: string
    delay_minutes?: string
    delay_total?: string
}

const EMPTY_FORM = {
    name: "",
    sender_name: "",
    goal: "",
    max_follow_ups: 3,
}

// ── Section primitive ────────────────────────────────────────────────────

function SectionCard({
    icon,
    title,
    description,
    children,
}: {
    icon: React.ReactNode
    title: string
    description: string
    children: React.ReactNode
}) {
    return (
        <div className="bg-card border rounded-[24px] p-6 space-y-4 shadow-sm">
            <div className="flex items-start gap-4">
                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0 mt-0.5">
                    {icon}
                </div>
                <div className="min-w-0">
                    <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
                    <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{description}</p>
                </div>
            </div>
            <div className="space-y-4 pl-10">{children}</div>
        </div>
    )
}

// ── Page ─────────────────────────────────────────────────────────────────

export default function CampaignCreate() {
    const navigate = useNavigate()
    useBreadcrumbs([
        { label: "Campaigns", href: "/" },
        { label: "New Campaign" },
    ])

    const [loading, setLoading] = useState(false)
    const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
    const [form, setForm] = useState(EMPTY_FORM)

    const isDirty = form.name !== "" || form.sender_name !== "" || form.goal !== ""
    useEffect(() => {
        if (!isDirty) return
        const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
        window.addEventListener("beforeunload", handler)
        return () => window.removeEventListener("beforeunload", handler)
    }, [isDirty])

    const [delayDays, setDelayDays] = useState(2)
    const [delayHours, setDelayHours] = useState(0)
    const [delayMinutes, setDelayMinutes] = useState(0)

    const followUpDelayMinutes = useMemo(
        () => delayDays * 24 * 60 + delayHours * 60 + delayMinutes,
        [delayDays, delayHours, delayMinutes],
    )

    // ── Validation ──────────────────────────────────────────────────────

    const validateField = (name: keyof FieldErrors, value: string): boolean => {
        let error: string | undefined
        switch (name) {
            case "name": if (!value.trim()) error = "Campaign name is required"; break
            case "sender_name": if (!value.trim()) error = "Sender name is required"; break
            case "goal": if (!value.trim()) error = "Campaign goal is required"; break
        }
        setFieldErrors(prev => ({ ...prev, [name]: error }))
        return !error
    }

    const validateMaxFollowUps = (value: number): boolean => {
        const ok = value >= 1 && value <= 10
        setFieldErrors(prev => ({ ...prev, max_follow_ups: ok ? undefined : "Must be between 1 and 10" }))
        return ok
    }

    const validateDelay = (days: number, hours: number, minutes: number): boolean => {
        const errors: FieldErrors = {}
        if (days < 0 || days > 30) errors.delay_days = "0–30"
        if (hours < 0 || hours > 23) errors.delay_hours = "0–23"
        if (minutes < 0 || minutes > 59) errors.delay_minutes = "0–59"
        if (days * 24 * 60 + hours * 60 + minutes < 1) {
            errors.delay_total = "Total delay must be at least 1 minute"
        }
        setFieldErrors(prev => ({
            ...prev,
            delay_days: errors.delay_days,
            delay_hours: errors.delay_hours,
            delay_minutes: errors.delay_minutes,
            delay_total: errors.delay_total,
        }))
        return !errors.delay_days && !errors.delay_hours && !errors.delay_minutes && !errors.delay_total
    }

    // ── Handlers ────────────────────────────────────────────────────────

    const handleText = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { id, value } = e.target
        setForm(prev => ({ ...prev, [id]: value }))
        validateField(id as keyof FieldErrors, value)
    }

    const handleIntFromEvent = (
        e: React.ChangeEvent<HTMLInputElement>,
        setter: (n: number) => void,
        validate: (n: number) => void,
    ) => {
        const raw = e.target.value
        const parsed = raw === "" ? 0 : parseInt(raw, 10)
        const n = isNaN(parsed) ? 0 : parsed
        setter(n)
        validate(n)
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        const checks = [
            validateField("name", form.name),
            validateField("sender_name", form.sender_name),
            validateField("goal", form.goal),
            validateMaxFollowUps(form.max_follow_ups),
            validateDelay(delayDays, delayHours, delayMinutes),
        ]
        if (!checks.every(Boolean)) return

        setLoading(true)
        try {
            const created = await post<Campaign>("/campaigns", {
                ...form,
                follow_up_delay_minutes: followUpDelayMinutes,
            })
            toast.success("Campaign created")
            navigate(`/campaigns/${created.id}`)
        } catch (err) {
            toast.error(parseApiError(err))
        } finally {
            setLoading(false)
        }
    }

    const hasFieldErrors = Object.values(fieldErrors).some(Boolean)
    const hasEmptyFields = !form.name.trim() || !form.sender_name.trim() || !form.goal.trim()

    // Live summary for the side panel
    const delaySummary = useMemo(() => {
        const parts: string[] = []
        if (delayDays) parts.push(`${delayDays}d`)
        if (delayHours) parts.push(`${delayHours}h`)
        if (delayMinutes) parts.push(`${delayMinutes}m`)
        return parts.length ? parts.join(" ") : "—"
    }, [delayDays, delayHours, delayMinutes])

    // ── Render ──────────────────────────────────────────────────────────

    return (
        <div className="p-6">
            <div className="max-w-5xl mx-auto space-y-5">
                {/* Header */}
                <div>
                    <h1 className="text-[28px] font-bold tracking-tight">New campaign</h1>
                    <p className="text-muted-foreground text-[14px] mt-1">
                        Configure the outreach. Add leads after it's created.
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
                    {/* LEFT: form sections */}
                    <div className="space-y-5 min-w-0">
                        {/* Basics */}
                        <SectionCard
                            icon={<span className="material-symbols-rounded text-[18px]">mail</span>}
                            title="Basics"
                            description="Name is internal. Sender name appears in the 'From' field of every email."
                        >
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="space-y-1.5">
                                    <Label htmlFor="name" className="text-[12px]">Campaign name</Label>
                                    <Input
                                        id="name"
                                        value={form.name}
                                        onChange={handleText}
                                        placeholder="Q1 Outreach"
                                        aria-invalid={!!fieldErrors.name}
                                        aria-describedby={fieldErrors.name ? "name-error" : undefined}
                                        className={`h-11 text-[14px] rounded-[24px] ${fieldErrors.name ? "border-destructive" : ""}`}
                                    />
                                    {fieldErrors.name && <p id="name-error" className="text-[12px] text-destructive">{fieldErrors.name}</p>}
                                </div>
                                <div className="space-y-1.5">
                                    <Label htmlFor="sender_name" className="text-[12px]">Sender name</Label>
                                    <Input
                                        id="sender_name"
                                        value={form.sender_name}
                                        onChange={handleText}
                                        placeholder="John Doe"
                                        aria-invalid={!!fieldErrors.sender_name}
                                        aria-describedby={fieldErrors.sender_name ? "sender_name-error" : undefined}
                                        className={`h-11 text-[14px] rounded-[24px] ${fieldErrors.sender_name ? "border-destructive" : ""}`}
                                    />
                                    {fieldErrors.sender_name && <p id="sender_name-error" className="text-[12px] text-destructive">{fieldErrors.sender_name}</p>}
                                </div>
                            </div>
                        </SectionCard>

                        {/* Sequence */}
                        <SectionCard
                            icon={<span className="material-symbols-rounded text-[18px]">timer</span>}
                            title="Sequence"
                            description="How long to wait between follow-ups, and how many to send before stopping."
                        >
                            <div className="space-y-1.5">
                                <Label className="text-[12px]">Follow-up delay</Label>
                                <div className="grid grid-cols-3 gap-2 max-w-md">
                                    <div className="relative">
                                        <Input
                                            type="number" min={0} max={30} placeholder="0"
                                            value={delayDays || ""}
                                            onChange={e => handleIntFromEvent(e, setDelayDays, n => validateDelay(n, delayHours, delayMinutes))}
                                            className={`h-11 text-[14px] pr-12 rounded-[24px] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_days ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-muted-foreground">Day</span>
                                    </div>
                                    <div className="relative">
                                        <Input
                                            type="number" min={0} max={23} placeholder="0"
                                            value={delayHours || ""}
                                            onChange={e => handleIntFromEvent(e, setDelayHours, n => validateDelay(delayDays, n, delayMinutes))}
                                            className={`h-11 text-[14px] pr-12 rounded-[24px] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_hours ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-muted-foreground">Hr</span>
                                    </div>
                                    <div className="relative">
                                        <Input
                                            type="number" min={0} max={59} placeholder="0"
                                            value={delayMinutes || ""}
                                            onChange={e => handleIntFromEvent(e, setDelayMinutes, n => validateDelay(delayDays, delayHours, n))}
                                            className={`h-11 text-[14px] pr-12 rounded-[24px] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_minutes ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-muted-foreground">Min</span>
                                    </div>
                                </div>
                                {fieldErrors.delay_total && (
                                    <p className="text-[11px] text-destructive">{fieldErrors.delay_total}</p>
                                )}
                            </div>

                            <div className="space-y-1.5 max-w-xs">
                                <Label htmlFor="max_follow_ups" className="text-[12px]">Max follow-ups</Label>
                                <Input
                                    id="max_follow_ups"
                                    type="number" min={1} max={10}
                                    value={form.max_follow_ups || ""}
                                    onChange={e => {
                                        const n = parseInt(e.target.value, 10) || 0
                                        setForm(prev => ({ ...prev, max_follow_ups: n }))
                                        validateMaxFollowUps(n)
                                    }}
                                    aria-invalid={!!fieldErrors.max_follow_ups}
                                    aria-describedby={fieldErrors.max_follow_ups ? "max_follow_ups-error" : undefined}
                                    className={`h-11 text-[14px] rounded-[24px] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.max_follow_ups ? "border-destructive" : ""}`}
                                />
                                {fieldErrors.max_follow_ups ? (
                                    <p id="max_follow_ups-error" className="text-[12px] text-destructive">{fieldErrors.max_follow_ups}</p>
                                ) : (
                                    <p className="text-[12px] text-muted-foreground">Between 1 and 10.</p>
                                )}
                            </div>
                        </SectionCard>

                        {/* Goal */}
                        <SectionCard
                            icon={<span className="material-symbols-rounded text-[18px]">track_changes</span>}
                            title="Campaign goal"
                            description="Everything the LLM uses to personalize each email. Specifics beat templates."
                        >
                            <Textarea
                                id="goal"
                                value={form.goal}
                                onChange={handleText}
                                aria-invalid={!!fieldErrors.goal}
                                aria-describedby={fieldErrors.goal ? "goal-error" : undefined}
                                placeholder={`We help [who] solve [their problem] by [your solution].\n\nProof points:\n- …\n- …\n\nGoal: get them to [specific action, e.g. book a 20-min call].`}
                                className="min-h-[220px] text-[14px] p-4 rounded-[20px] leading-relaxed font-mono"
                            />
                            {fieldErrors.goal && <p id="goal-error" className="text-[12px] text-destructive">{fieldErrors.goal}</p>}
                            <p className="text-[12px] text-muted-foreground flex items-start gap-2">
                                <span className="material-symbols-rounded text-[14px] mt-0.5 shrink-0">info</span>
                                Include proof points, audience description, and the exact action you want. The quality of this text drives the quality of every email.
                            </p>
                        </SectionCard>
                    </div>

                    {/* RIGHT: live summary */}
                    <aside className="lg:sticky lg:top-6 lg:self-start space-y-5">
                        <div className="bg-card border rounded-[24px] p-6 space-y-4 shadow-sm">
                            <div>
                                <p className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">Summary</p>
                            </div>
                            <dl className="space-y-3 text-[14px]">
                                <div className="flex justify-between gap-3">
                                    <dt className="text-muted-foreground">Name</dt>
                                    <dd className="font-medium truncate max-w-[60%] text-right">{form.name || "—"}</dd>
                                </div>
                                <div className="flex justify-between gap-3">
                                    <dt className="text-muted-foreground">Sender</dt>
                                    <dd className="font-medium truncate max-w-[60%] text-right">{form.sender_name || "—"}</dd>
                                </div>
                                <div className="flex justify-between gap-3">
                                    <dt className="text-muted-foreground">Delay</dt>
                                    <dd className="font-medium">{delaySummary}</dd>
                                </div>
                                <div className="flex justify-between gap-3">
                                    <dt className="text-muted-foreground">Follow-ups</dt>
                                    <dd className="font-medium">{form.max_follow_ups || 0}</dd>
                                </div>
                            </dl>
                        </div>

                        <div className="bg-muted/40 border rounded-[24px] p-5 space-y-2">
                            <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">
                                <span className="material-symbols-rounded text-[14px]">info</span>
                                Next steps
                            </div>
                            <p className="text-[13px] text-muted-foreground leading-relaxed">
                                After creating, you'll land on the campaign page. Add leads (manually or via CSV) and start the campaign.
                            </p>
                        </div>

                        <div className="flex flex-col gap-2">
                            <Button
                                type="submit"
                                size="lg"
                                disabled={loading || hasFieldErrors || hasEmptyFields}
                                className="w-full h-12 rounded-full text-[15px] font-medium"
                            >
                                {loading ? "Creating..." : "Create campaign"}
                            </Button>
                            <Button
                                type="button"
                                variant="ghost"
                                size="lg"
                                onClick={() => navigate("/")}
                                className="w-full h-12 rounded-full text-[15px] font-medium"
                            >
                                Cancel
                            </Button>
                        </div>
                    </aside>
                </form>
            </div>
        </div>
    )
}
