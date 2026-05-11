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
                    <Alert variant="destructive" className="rounded-lg bg-destructive-alert text-destructive-alert-foreground border-none p-5">
                        <span className="material-symbols-rounded text-[20px] mr-3">error</span>
                        <AlertDescription className="text-[14px]">{error}</AlertDescription>
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
                                        <Badge variant={leadStatus.variant} className={`${leadStatus.className} text-[12px] px-3 py-1 rounded-full`}>
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
                        <div className="flex items-center gap-2">
                            {!isTerminal && (
                                <Button variant="outline" onClick={startEditingLead} className="gap-2 rounded-full h-10 px-5  text-[14px]">
                                    <span className="material-symbols-rounded text-[18px]">edit</span> Edit
                                </Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setShowDeleteModal(true)} className="text-muted-foreground hover:text-destructive-hover-foreground hover:bg-destructive-hover rounded-full h-10 w-10">
                                <span className="material-symbols-rounded text-[20px]">delete</span>
                            </Button>
                        </div>
                    )}
                </div>

                {/* ── Edit Panel ────────────────────────────────────── */}
                {editingLead && (
                    <div className="bg-card border rounded-lg p-6 space-y-5 ">
                        <div className="flex items-center justify-between">
                            <h2 className="text-[18px] font-semibold">Edit Lead</h2>
                            <div className="flex items-center gap-3">
                                <Button onClick={handleSaveLead} disabled={savingLead} className="gap-2 rounded-full h-10 px-5  text-[14px]">
                                    <span className="material-symbols-rounded text-[18px]">check</span> {savingLead ? "Saving..." : "Save"}
                                </Button>
                                <Button variant="ghost" onClick={() => setEditingLead(false)} className="gap-2 rounded-full h-10 px-5 text-[14px]">
                                    <span className="material-symbols-rounded text-[18px]">close</span> Cancel
                                </Button>
                            </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <label className="text-[13px] font-medium text-muted-foreground pl-2">First Name</label>
                                <Input value={leadForm.first_name} onChange={e => setLeadForm({ ...leadForm, first_name: e.target.value })} className="h-11 text-[14px] rounded-lg px-4" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[13px] font-medium text-muted-foreground pl-2">Last Name</label>
                                <Input value={leadForm.last_name} onChange={e => setLeadForm({ ...leadForm, last_name: e.target.value })} className="h-11 text-[14px] rounded-lg px-4" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[13px] font-medium text-muted-foreground pl-2">Email</label>
                                <Input value={leadForm.email} onChange={e => setLeadForm({ ...leadForm, email: e.target.value })} className="h-11 text-[14px] rounded-lg px-4" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[13px] font-medium text-muted-foreground pl-2">Company</label>
                                <Input value={leadForm.company} onChange={e => setLeadForm({ ...leadForm, company: e.target.value })} className="h-11 text-[14px] rounded-lg px-4" />
                            </div>
                            <div className="sm:col-span-2 space-y-1.5">
                                <label className="text-[13px] font-medium text-muted-foreground pl-2">Title</label>
                                <Input value={leadForm.title} onChange={e => setLeadForm({ ...leadForm, title: e.target.value })} className="h-11 text-[14px] rounded-lg px-4" />
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Info Grid ─────────────────────────────────────── */}
                {loading ? (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 rounded-lg" />)}
                    </div>
                ) : lead && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div className="bg-card border rounded-lg p-5 ">
                            <div className="flex items-center gap-2 text-muted-foreground mb-2">
                                <span className="material-symbols-rounded text-[16px]">domain</span>
                                <span className="text-[12px] font-semibold uppercase tracking-wider">Company</span>
                            </div>
                            <p className="text-[15px] font-medium truncate">{lead.company || "—"}</p>
                        </div>
                        <div className="bg-card border rounded-lg p-5 ">
                            <div className="flex items-center gap-2 text-muted-foreground mb-2">
                                <span className="material-symbols-rounded text-[16px]">work</span>
                                <span className="text-[12px] font-semibold uppercase tracking-wider">Title</span>
                            </div>
                            <p className="text-[15px] font-medium truncate">{lead.title || "—"}</p>
                        </div>
                        <div className="bg-card border rounded-lg p-5 ">
                            <div className="flex items-center gap-2 text-muted-foreground mb-2">
                                <span className="material-symbols-rounded text-[16px]">tag</span>
                                <span className="text-[12px] font-semibold uppercase tracking-wider">Sequence</span>
                            </div>
                            <p className="text-[15px] font-medium">{lead.current_sequence} / {lead.max_follow_ups}</p>
                        </div>
                        <div className="bg-card border rounded-lg p-5 ">
                            <div className="flex items-center gap-2 text-muted-foreground mb-2">
                                <span className="material-symbols-rounded text-[16px]">event_available</span>
                                <span className="text-[12px] font-semibold uppercase tracking-wider">Next Email</span>
                            </div>
                            <p className="text-[14px] font-medium">
                                {isTerminal ? "—" : formatDate(lead.next_email_at)}
                            </p>
                        </div>
                    </div>
                )}

                {/* ── Notes ─────────────────────────────────────────── */}
                {loading ? (
                    <Skeleton className="h-[160px] rounded-lg" />
                ) : lead && (
                    <div className="bg-card border rounded-lg p-6 space-y-4 ">
                        <p className="text-[12px] font-semibold uppercase tracking-wider text-muted-foreground">Notes</p>
                        <Textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            placeholder="Add notes about this lead..."
                            className="min-h-[100px] text-[14px] p-4 rounded-sm resize-none"
                            disabled={loading || saving}
                        />
                        <div className="flex items-center gap-3">
                            <Button onClick={handleSaveNotes} disabled={saving || loading} className="rounded-full h-10 px-5  text-[14px]">
                                {saving ? "Saving..." : "Save Notes"}
                            </Button>
                            {!lead.has_replied && (
                                <Button variant="secondary" onClick={handleMarkAsReplied} disabled={marking || loading} className="gap-2 rounded-full h-10 px-5  text-[14px]">
                                    <span className="material-symbols-rounded text-[18px]">check_circle</span>
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
