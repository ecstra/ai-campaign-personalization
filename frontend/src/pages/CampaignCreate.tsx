import { useState, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { format } from "date-fns"
import { post } from "@/lib/api"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
    CalendarIcon, X, Info, Mail, Timer, Target, Clock,
} from "lucide-react"

type Campaign = { id: string; name: string }

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
    scheduled_start_at: "", // datetime-local string: "YYYY-MM-DDTHH:mm"
}

// ── Datetime helpers ─────────────────────────────────────────────────────
// scheduled_start_at is stored as a "YYYY-MM-DDTHH:mm" datetime-local string
// so the backend gets what it already expects. We split it into {date, time}
// for the Calendar + time Input UI, then recombine on change.

function parseScheduled(value: string): { date: Date | undefined; time: string } {
    if (!value) return { date: undefined, time: "09:00" }
    const [datePart, timePart = "09:00"] = value.split("T")
    const [y, m, d] = datePart.split("-").map(Number)
    if (!y || !m || !d) return { date: undefined, time: timePart.slice(0, 5) }
    return { date: new Date(y, m - 1, d), time: timePart.slice(0, 5) }
}

function composeScheduled(date: Date | undefined, time: string): string {
    if (!date) return ""
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, "0")
    const d = String(date.getDate()).padStart(2, "0")
    return `${y}-${m}-${d}T${time}`
}

// ── Section primitive ────────────────────────────────────────────────────
// Each major config area is its own card, matching the CampaignDetail theme
// (`bg-card border rounded-xl p-5`). Eyebrow icon + title + description
// header sits above the fields.

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
        <div className="bg-card border rounded-xl p-5 space-y-4">
            <div className="flex items-start gap-3">
                <div className="h-7 w-7 rounded-md bg-muted flex items-center justify-center text-muted-foreground shrink-0 mt-0.5">
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

// ── Datetime Picker built from shadcn Popover + Calendar + time Input ────

function DateTimePicker({
    value,
    onChange,
}: {
    value: string
    onChange: (next: string) => void
}) {
    const { date, time } = parseScheduled(value)
    const [open, setOpen] = useState(false)

    const handleDateSelect = (next: Date | undefined) => {
        onChange(composeScheduled(next, time))
        if (next) setOpen(false)
    }

    const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange(composeScheduled(date, e.target.value || "09:00"))
    }

    const handleClear = (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        onChange("")
    }

    const label = date
        ? `${format(date, "EEE, MMM d, yyyy")} at ${format(
            new Date(`1970-01-01T${time}:00`), "h:mm a")}`
        : "Pick a date and time"

    return (
        <div className="flex items-center gap-2">
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        type="button"
                        variant="outline"
                        className="w-[320px] justify-start gap-2 h-9 text-[13px] font-normal"
                    >
                        <CalendarIcon size={14} className="text-muted-foreground" />
                        <span className={date ? "" : "text-muted-foreground"}>{label}</span>
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                        mode="single"
                        selected={date}
                        onSelect={handleDateSelect}
                        disabled={(d) => d < new Date(new Date().setHours(0, 0, 0, 0))}
                        autoFocus
                    />
                    <div className="border-t p-3 flex items-center gap-2">
                        <Clock size={14} className="text-muted-foreground shrink-0" />
                        <Input
                            type="time"
                            value={time}
                            onChange={handleTimeChange}
                            className="h-8 text-[13px]"
                        />
                    </div>
                </PopoverContent>
            </Popover>
            {date && (
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleClear}
                    className="h-9 px-2 text-muted-foreground"
                    aria-label="Clear scheduled start"
                >
                    <X size={14} />
                </Button>
            )}
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

    const scheduledSummary = useMemo(() => {
        if (!form.scheduled_start_at) return "Manual start"
        const { date, time } = parseScheduled(form.scheduled_start_at)
        if (!date) return "Manual start"
        return `${format(date, "MMM d")} at ${format(new Date(`1970-01-01T${time}:00`), "h:mm a")}`
    }, [form.scheduled_start_at])

    // ── Render ──────────────────────────────────────────────────────────

    return (
        <div className="p-6">
            <div className="max-w-5xl mx-auto space-y-5">
                {/* Header */}
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">New campaign</h1>
                    <p className="text-muted-foreground text-[13px] mt-1">
                        Configure the outreach. Add leads after it's created.
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
                    {/* LEFT: form sections */}
                    <div className="space-y-5 min-w-0">
                        {/* Basics */}
                        <SectionCard
                            icon={<Mail size={14} />}
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
                                        className={`h-9 text-[13px] ${fieldErrors.name ? "border-destructive" : ""}`}
                                    />
                                    {fieldErrors.name && <p id="name-error" className="text-[11px] text-destructive">{fieldErrors.name}</p>}
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
                                        className={`h-9 text-[13px] ${fieldErrors.sender_name ? "border-destructive" : ""}`}
                                    />
                                    {fieldErrors.sender_name && <p id="sender_name-error" className="text-[11px] text-destructive">{fieldErrors.sender_name}</p>}
                                </div>
                            </div>
                        </SectionCard>

                        {/* Sequence */}
                        <SectionCard
                            icon={<Timer size={14} />}
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
                                            className={`h-9 text-[13px] pr-12 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_days ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">Day</span>
                                    </div>
                                    <div className="relative">
                                        <Input
                                            type="number" min={0} max={23} placeholder="0"
                                            value={delayHours || ""}
                                            onChange={e => handleIntFromEvent(e, setDelayHours, n => validateDelay(delayDays, n, delayMinutes))}
                                            className={`h-9 text-[13px] pr-12 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_hours ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">Hr</span>
                                    </div>
                                    <div className="relative">
                                        <Input
                                            type="number" min={0} max={59} placeholder="0"
                                            value={delayMinutes || ""}
                                            onChange={e => handleIntFromEvent(e, setDelayMinutes, n => validateDelay(delayDays, delayHours, n))}
                                            className={`h-9 text-[13px] pr-12 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.delay_minutes ? "border-destructive" : ""}`}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">Min</span>
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
                                    className={`h-9 text-[13px] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${fieldErrors.max_follow_ups ? "border-destructive" : ""}`}
                                />
                                {fieldErrors.max_follow_ups ? (
                                    <p id="max_follow_ups-error" className="text-[11px] text-destructive">{fieldErrors.max_follow_ups}</p>
                                ) : (
                                    <p className="text-[11px] text-muted-foreground">Between 1 and 10.</p>
                                )}
                            </div>
                        </SectionCard>

                        {/* Goal */}
                        <SectionCard
                            icon={<Target size={14} />}
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
                                className="min-h-[220px] text-[13px] leading-relaxed font-mono"
                            />
                            {fieldErrors.goal && <p id="goal-error" className="text-[11px] text-destructive">{fieldErrors.goal}</p>}
                            <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <Info size={11} className="mt-0.5 shrink-0" />
                                Include proof points, audience description, and the exact action you want. The quality of this text drives the quality of every email.
                            </p>
                        </SectionCard>

                        {/* Scheduling */}
                        <SectionCard
                            icon={<CalendarIcon size={14} />}
                            title="Schedule start"
                            description="Optional. Leave empty to start manually after adding leads."
                        >
                            <DateTimePicker
                                value={form.scheduled_start_at}
                                onChange={v => setForm(prev => ({ ...prev, scheduled_start_at: v }))}
                            />
                            <p className="text-[11px] text-muted-foreground">
                                If set, the campaign auto-activates at this time, provided it has leads.
                            </p>
                        </SectionCard>
                    </div>

                    {/* RIGHT: live summary */}
                    <aside className="lg:sticky lg:top-6 lg:self-start space-y-5">
                        <div className="bg-card border rounded-xl p-5 space-y-3">
                            <div>
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Summary</p>
                            </div>
                            <dl className="space-y-2.5 text-[13px]">
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
                                <div className="flex justify-between gap-3">
                                    <dt className="text-muted-foreground">Start</dt>
                                    <dd className="font-medium">{scheduledSummary}</dd>
                                </div>
                            </dl>
                        </div>

                        <div className="bg-muted/40 border rounded-xl p-4 space-y-1.5">
                            <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                                <Info size={11} />
                                Next steps
                            </div>
                            <p className="text-[12px] text-muted-foreground leading-relaxed">
                                After creating, you'll land on the campaign page. Add leads (manually or via CSV), preview a generated email, then start the campaign.
                            </p>
                        </div>

                        <div className="flex flex-col gap-2">
                            <Button
                                type="submit"
                                disabled={loading || hasFieldErrors || hasEmptyFields}
                                className="w-full"
                            >
                                {loading ? "Creating..." : "Create campaign"}
                            </Button>
                            <Button
                                type="button"
                                variant="ghost"
                                onClick={() => navigate("/")}
                                className="w-full"
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
