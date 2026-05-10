import { useState, useEffect, useCallback } from "react"
import { useParams } from "react-router-dom"
import { get, patch } from "@/lib/api"
import { getLeadStatus } from "@/lib/status"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { type Lead } from "@/lib/types"
import EmailActivityTimeline, { type EmailActivity } from "@/components/lead/EmailActivityTimeline"
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
    AlertCircle,
    Trash2,
    Hash,
    CalendarClock,
    Pencil,
    Check,
    X
} from "lucide-react"
import DeleteLeadModal from "@/components/DeleteLeadModal"

function formatDate(dateString: string | null) {
    if (!dateString) return "Not scheduled"
    const date = new Date(dateString)
    const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    const timeStr = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    return `${dateStr}, ${timeStr}`
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

    const fetchData = useCallback(async () => {
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
    }, [campaignId, leadId])

    useEffect(() => {
        fetchData()
    }, [fetchData])

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
                            <p className="text-[14px] font-medium">{lead.current_sequence} / {lead.max_follow_ups}</p>
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
                {loading ? (
                    <Skeleton className="h-[140px] rounded-xl" />
                ) : lead && (
                    <div className="bg-card border rounded-xl p-5 space-y-3">
                        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
                        <Textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            placeholder="Add notes about this lead..."
                            className="min-h-[80px] text-[14px] resize-none"
                            disabled={loading || saving}
                        />
                        <div className="flex items-center gap-2">
                            <Button size="sm" onClick={handleSaveNotes} disabled={saving || loading}>
                                {saving ? "Saving..." : "Save Notes"}
                            </Button>
                            {!lead.has_replied && (
                                <Button variant="outline" size="sm" onClick={handleMarkAsReplied} disabled={marking || loading} className="gap-1.5">
                                    <CheckCircle2 size={13} />
                                    {marking ? "Marking..." : "Mark as Replied"}
                                </Button>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Email Activity ────────────────────────────────── */}
                <div className="space-y-3">
                    <h2 className="text-lg font-semibold">Email Activity</h2>
                    <EmailActivityTimeline
                        activity={activity}
                        loading={loading}
                        expandedIds={expandedIds}
                        toggleExpand={toggleExpand}
                    />
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
