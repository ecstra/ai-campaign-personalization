import { useState, useEffect } from "react"
import { useParams } from "react-router-dom"
import DOMPurify from "dompurify"
import { get, patch } from "@/lib/api"
import { formatTime } from "@/lib/utils"
import { getLeadStatus, getEmailStatus } from "@/lib/status"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import {
    Building2,
    Briefcase,
    CheckCircle2,
    Clock,
    Send,
    AlertCircle,
    Trash2,
    Reply,
    Hash,
    CalendarClock,
    Pencil,
    Check,
    X
} from "lucide-react"
import DeleteLeadModal from "@/components/DeleteLeadModal"

type Lead = {
    id: string
    campaign_id: string
    email: string
    first_name: string
    last_name: string
    company: string | null
    title: string | null
    notes: string | null
    status: string
    has_replied: boolean
    current_sequence: number
    next_email_at: string | null
    created_at: string
    updated_at: string
    campaign_name: string
}

type EmailActivity = {
    id: string
    sequence_number: number
    subject: string
    body: string
    status: string
    sent_at: string | null
    created_at: string
}

function formatDate(dateString: string | null) {
    if (!dateString) return "Not scheduled"
    const date = new Date(dateString)
    const formatted = formatTime(dateString)
    const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    return formatted ? `${dateStr}, ${formatted.time} ${formatted.timezone}` : date.toLocaleString()
}

export default function LeadDetail() {
    const { campaignId, leadId } = useParams<{ campaignId: string; leadId: string }>()
    const [lead, setLead] = useState<Lead | null>(null)
    const [activity, setActivity] = useState<EmailActivity[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [notes, setNotes] = useState("")
    const [saving, setSaving] = useState(false)
    const [marking, setMarking] = useState(false)
    const [showDeleteModal, setShowDeleteModal] = useState(false)
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
    const [editingLead, setEditingLead] = useState(false)
    const [leadForm, setLeadForm] = useState({ email: "", first_name: "", last_name: "", company: "", title: "" })
    const [savingLead, setSavingLead] = useState(false)

    useBreadcrumbs([
        { label: "Campaigns", href: "/" },
        { label: lead?.campaign_name || "Campaign", href: campaignId ? `/campaigns/${campaignId}` : "/" },
        { label: lead ? `${lead.first_name} ${lead.last_name}` : "Loading..." },
    ])

    const fetchData = async () => {
        if (!leadId || !campaignId) return
        try {
            setLoading(true)
            const [leadData, activityData] = await Promise.all([
                get<Lead>(`/leads/${leadId}`),
                get<EmailActivity[]>(`/leads/${leadId}/activity?campaign_id=${campaignId}`)
            ])
            setLead(leadData)
            setNotes(leadData.notes || "")
            setActivity(activityData)
            setError(null)
        } catch (err) {
            setError(parseApiError(err))
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
    }, [leadId, campaignId])

    const handleSaveNotes = async () => {
        if (!leadId || !lead) return
        const previousNotes = lead.notes
        setLead({ ...lead, notes })
        setSaving(true)
        try {
            await patch(`/leads/${leadId}`, { notes })
            toast.success("Notes saved")
        } catch (err) {
            setLead({ ...lead, notes: previousNotes })
            setNotes(previousNotes || "")
            toast.error(parseApiError(err))
        } finally {
            setSaving(false)
        }
    }

    const handleMarkAsReplied = async () => {
        if (!leadId || !lead) return
        const previousStatus = lead.status
        const previousReplied = lead.has_replied
        setLead({ ...lead, has_replied: true, status: "replied" })
        setMarking(true)
        try {
            await patch(`/leads/${leadId}`, { has_replied: true, status: "replied" })
            toast.success("Lead marked as replied")
        } catch (err) {
            setLead({ ...lead, has_replied: previousReplied, status: previousStatus })
            toast.error(parseApiError(err))
        } finally {
            setMarking(false)
        }
    }

    const toggleExpand = (id: string) => {
        setExpandedIds(prev => {
            const next = new Set(prev)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
        })
    }

    const startEditingLead = () => {
        if (!lead) return
        setLeadForm({
            email: lead.email,
            first_name: lead.first_name,
            last_name: lead.last_name,
            company: lead.company || "",
            title: lead.title || "",
        })
        setEditingLead(true)
    }

    const handleSaveLead = async () => {
        if (!leadId) return
        setSavingLead(true)
        try {
            await patch(`/leads/${leadId}`, leadForm)
            await fetchData()
            setEditingLead(false)
            toast.success("Lead updated")
        } catch (err) {
            toast.error(parseApiError(err))
        } finally {
            setSavingLead(false)
        }
    }

    if (error) {
        return (
            <div className="p-6">
                <div className="w-full">
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                </div>
            </div>
        )
    }

    const leadStatus = lead ? getLeadStatus(lead.status) : null
    const isTerminal = lead?.status === "completed" || lead?.status === "replied" || lead?.status === "failed"

    return (
        <div className="p-6">
            <div className="w-full space-y-6">

                {/* ── Header ───────────────────────────────────────── */}
                <div className="flex items-start justify-between">
                    <div>
                        {loading ? (
                            <>
                                <Skeleton className="h-9 w-52 mb-2" />
                                <Skeleton className="h-4 w-40" />
                            </>
                        ) : lead && (
                            <>
                                <div className="flex items-center gap-3 mb-1">
                                    <h1 className="text-2xl font-semibold tracking-tight">
                                        {lead.first_name} {lead.last_name}
                                    </h1>
                                    {leadStatus && (
                                        <Badge variant={leadStatus.variant} className={leadStatus.className}>
                                            {leadStatus.label}
                                        </Badge>
                                    )}
                                </div>
                                <a href={`mailto:${lead.email}`} className="text-sm text-muted-foreground hover:text-primary transition-colors">
                                    {lead.email}
                                </a>
                            </>
                        )}
                    </div>
                    {!loading && lead && (
                        <div className="flex items-center gap-1">
                            {!isTerminal && (
                                <Button variant="outline" size="sm" onClick={startEditingLead} className="gap-1.5">
                                    <Pencil size={13} /> Edit
                                </Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setShowDeleteModal(true)} className="text-muted-foreground hover:text-destructive">
                                <Trash2 size={14} />
                            </Button>
                        </div>
                    )}
                </div>

                {/* ── Edit Panel ────────────────────────────────────── */}
                {editingLead && (
                    <div className="bg-card border rounded-xl p-5 space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold">Edit Lead</h2>
                            <div className="flex items-center gap-2">
                                <Button size="sm" onClick={handleSaveLead} disabled={savingLead} className="gap-1.5">
                                    <Check size={14} /> {savingLead ? "Saving..." : "Save"}
                                </Button>
                                <Button size="sm" variant="ghost" onClick={() => setEditingLead(false)} className="gap-1.5">
                                    <X size={14} /> Cancel
                                </Button>
                            </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <label className="text-[12px] font-medium text-muted-foreground">First Name</label>
                                <Input value={leadForm.first_name} onChange={e => setLeadForm({ ...leadForm, first_name: e.target.value })} className="h-9 text-sm" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[12px] font-medium text-muted-foreground">Last Name</label>
                                <Input value={leadForm.last_name} onChange={e => setLeadForm({ ...leadForm, last_name: e.target.value })} className="h-9 text-sm" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[12px] font-medium text-muted-foreground">Email</label>
                                <Input value={leadForm.email} onChange={e => setLeadForm({ ...leadForm, email: e.target.value })} className="h-9 text-sm" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[12px] font-medium text-muted-foreground">Company</label>
                                <Input value={leadForm.company} onChange={e => setLeadForm({ ...leadForm, company: e.target.value })} className="h-9 text-sm" />
                            </div>
                            <div className="sm:col-span-2 space-y-1.5">
                                <label className="text-[12px] font-medium text-muted-foreground">Title</label>
                                <Input value={leadForm.title} onChange={e => setLeadForm({ ...leadForm, title: e.target.value })} className="h-9 text-sm" />
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Info Grid ─────────────────────────────────────── */}
                {loading ? (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
                    </div>
                ) : lead && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="bg-card border rounded-xl p-3.5">
                            <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5">
                                <Building2 size={12} />
                                <span className="text-[11px] font-medium uppercase tracking-wide">Company</span>
                            </div>
                            <p className="text-[14px] font-medium truncate">{lead.company || "—"}</p>
                        </div>
                        <div className="bg-card border rounded-xl p-3.5">
                            <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5">
                                <Briefcase size={12} />
                                <span className="text-[11px] font-medium uppercase tracking-wide">Title</span>
                            </div>
                            <p className="text-[14px] font-medium truncate">{lead.title || "—"}</p>
                        </div>
                        <div className="bg-card border rounded-xl p-3.5">
                            <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5">
                                <Hash size={12} />
                                <span className="text-[11px] font-medium uppercase tracking-wide">Sequence</span>
                            </div>
                            <p className="text-[14px] font-medium">{lead.current_sequence} / {3}</p>
                        </div>
                        <div className="bg-card border rounded-xl p-3.5">
                            <div className="flex items-center gap-1.5 text-muted-foreground mb-1.5">
                                <CalendarClock size={12} />
                                <span className="text-[11px] font-medium uppercase tracking-wide">Next Email</span>
                            </div>
                            <p className="text-[13px] font-medium">
                                {isTerminal ? "—" : formatDate(lead.next_email_at)}
                            </p>
                        </div>
                    </div>
                )}

                {/* ── Notes ─────────────────────────────────────────── */}
                <div className="bg-card border rounded-xl p-5 space-y-3">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
                    <Textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Add notes about this lead..."
                        className="min-h-[80px] text-[14px] resize-none"
                        disabled={loading}
                    />
                    <div className="flex items-center gap-2">
                        <Button size="sm" onClick={handleSaveNotes} disabled={saving || loading}>
                            {saving ? "Saving..." : "Save Notes"}
                        </Button>
                        {lead && !lead.has_replied && (
                            <Button variant="outline" size="sm" onClick={handleMarkAsReplied} disabled={marking || loading} className="gap-1.5">
                                <CheckCircle2 size={13} />
                                {marking ? "Marking..." : "Mark as Replied"}
                            </Button>
                        )}
                    </div>
                </div>

                {/* ── Email Activity ────────────────────────────────── */}
                <div className="space-y-3">
                    <h2 className="text-lg font-semibold">Email Activity</h2>

                    {loading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
                        </div>
                    ) : activity.length === 0 ? (
                        <div className="text-center py-12 border border-dashed rounded-xl">
                            <p className="text-sm text-muted-foreground">No emails sent yet</p>
                        </div>
                    ) : (
                        <div className="relative pl-6">
                            {/* Timeline line */}
                            <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

                            <div className="space-y-3">
                                {activity.map(email => {
                                    const isExpanded = expandedIds.has(email.id)
                                    const s = getEmailStatus(email.status)
                                    const dotColor = email.status === "sent" ? "bg-emerald-500"
                                        : email.status === "received" ? "bg-blue-500"
                                        : email.status === "failed" ? "bg-red-500"
                                        : "bg-yellow-500"

                                    return (
                                        <div key={email.id} className="relative">
                                            {/* Dot */}
                                            <div className={`absolute -left-6 top-4 w-3.5 h-3.5 rounded-full border-2 border-background ${dotColor} ring-2 ring-background`} />

                                            <div
                                                className={`bg-card border rounded-xl p-4 cursor-pointer transition-colors hover:bg-accent/50 ${isExpanded ? "bg-accent/30" : ""}`}
                                                onClick={() => toggleExpand(email.id)}
                                            >
                                                <div className="flex items-start justify-between gap-2">
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        {email.status === "sent" ? <Send size={13} className="text-emerald-600 flex-shrink-0" />
                                                            : email.status === "received" ? <Reply size={13} className="text-blue-600 flex-shrink-0" />
                                                            : email.status === "failed" ? <AlertCircle size={13} className="text-red-600 flex-shrink-0" />
                                                            : <Clock size={13} className="text-yellow-600 flex-shrink-0" />}
                                                        <span className="font-medium text-[13px]">
                                                            {email.status === "received" || email.sequence_number <= 0
                                                                ? "Reply Received"
                                                                : `Email #${email.sequence_number}`}
                                                        </span>
                                                        <span className="text-[11px] text-muted-foreground hidden sm:inline">
                                                            {formatDate(email.sent_at || email.created_at)}
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <Badge variant={s.variant} className={`${s.className} text-[10px]`}>{s.label}</Badge>
                                                        <svg className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                                        </svg>
                                                    </div>
                                                </div>

                                                <p className={`text-[13px] mt-2 ${isExpanded ? "" : "line-clamp-1"} text-muted-foreground`}>
                                                    {email.subject}
                                                </p>

                                                <div
                                                    className={`grid transition-[grid-template-rows,opacity,margin-top] duration-300 ease-out ${
                                                        isExpanded ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0 mt-0"
                                                    }`}
                                                >
                                                    <div className="overflow-hidden">
                                                        <div className="pt-3 border-t">
                                                        <div
                                                            className="text-[13px] leading-relaxed [&>p]:mb-2.5 [&>p:last-child]:mb-0"
                                                            dangerouslySetInnerHTML={{
                                                                __html: email.status === "failed"
                                                                    ? "We couldn't send this email. Please check if the email address is valid."
                                                                    : DOMPurify.sanitize(email.body, {
                                                                        // Strip all scripts, event handlers, and dangerous tags.
                                                                        // Allow only the basic formatting Gmail and our LLM produce.
                                                                        ALLOWED_TAGS: ["p", "br", "strong", "b", "em", "i", "u", "a", "ul", "ol", "li", "blockquote", "span", "div"],
                                                                        ALLOWED_ATTR: ["href", "target", "rel"],
                                                                        ALLOW_DATA_ATTR: false,
                                                                    })
                                                            }}
                                                        />
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Delete Modal ──────────────────────────────────── */}
                {lead && campaignId && (
                    <DeleteLeadModal
                        open={showDeleteModal}
                        onClose={() => setShowDeleteModal(false)}
                        campaignId={campaignId}
                        leadId={lead.id}
                        leadName={`${lead.first_name} ${lead.last_name}`}
                    />
                )}
            </div>
        </div>
    )
}
