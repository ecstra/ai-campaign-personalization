import { useState, useEffect, useMemo } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { get, post, patch } from "@/lib/api"
import { getCampaignStatus, getLeadStatus } from "@/lib/status"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import ErrorPage from "./ErrorPage"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
    Upload, UserPlus, Search, Play, Pause, Trash2,
    ArrowUpRight, Eye, Pencil, Check, X, Copy, CalendarClock, AlertTriangle,
} from "lucide-react"
import AddLeadModal from "@/components/AddLeadModal"
import ImportCSVModal from "@/components/ImportCSVModal"
import DeleteCampaignModal from "@/components/DeleteCampaignModal"
import PreviewEmailModal from "@/components/PreviewEmailModal"
import AttachedDocumentsCard from "@/components/AttachedDocumentsCard"

type AttachedDoc = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string | null
    updated_at: string | null
}

type Campaign = {
    id: string
    name: string
    sender_name: string
    sender_email: string
    goal: string | null
    follow_up_delay_minutes: number
    max_follow_ups: number
    status: string
    scheduled_start_at: string | null
    documents: AttachedDoc[]
}

type CampaignStats = {
    emails_sent: number
    emails_target: number
    emails_in_window: number
    rate_limit: number
    rate_limit_window_minutes: number
    rate_limit_remaining: number
    rate_limit_resets_at: string | null
    total_leads: number
    reply_count: number
    reply_rate: number
    leads_by_status: Record<string, number>
    avg_sequence_at_reply: number | null
}

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
}

function formatDelay(minutes: number): string {
    const days = Math.floor(minutes / (24 * 60))
    const hours = Math.floor((minutes % (24 * 60)) / 60)
    const mins = minutes % 60
    const parts = []
    if (days > 0) parts.push(`${days}d`)
    if (hours > 0) parts.push(`${hours}h`)
    if (mins > 0 || parts.length === 0) parts.push(`${mins}m`)
    return parts.join(" ")
}

export default function CampaignDetail() {
    const { id } = useParams<{ id: string }>()
    const [campaign, setCampaign] = useState<Campaign | null>(null)
    const [leads, setLeads] = useState<Lead[]>([])
    const [stats, setStats] = useState<CampaignStats | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [showAddLead, setShowAddLead] = useState(false)
    const [showImportCSV, setShowImportCSV] = useState(false)
    const [searchQuery, setSearchQuery] = useState("")
    const [toggling, setToggling] = useState(false)
    const [showDelete, setShowDelete] = useState(false)
    const [showPreview, setShowPreview] = useState(false)
    const [editing, setEditing] = useState(false)
    const [editForm, setEditForm] = useState({ name: "", sender_name: "", goal: "", follow_up_delay_minutes: 0, max_follow_ups: 0, scheduled_start_at: "" })
    const [saving, setSaving] = useState(false)
    const [selectedLeads, setSelectedLeads] = useState<Set<string>>(new Set())
    const [bulkDeleting, setBulkDeleting] = useState(false)
    const navigate = useNavigate()

    useBreadcrumbs([
        { label: "Campaigns", href: "/" },
        { label: campaign?.name || "Loading..." },
    ])

    const filteredLeads = useMemo(() => {
        if (!searchQuery.trim()) return leads
        const query = searchQuery.toLowerCase()
        return leads.filter(lead =>
            lead.first_name.toLowerCase().includes(query) ||
            lead.last_name.toLowerCase().includes(query) ||
            `${lead.first_name} ${lead.last_name}`.toLowerCase().includes(query) ||
            lead.email.toLowerCase().includes(query) ||
            (lead.company && lead.company.toLowerCase().includes(query)) ||
            (lead.title && lead.title.toLowerCase().includes(query)) ||
            lead.status.toLowerCase().includes(query)
        )
    }, [leads, searchQuery])

    const fetchData = async () => {
        try {
            setLoading(true)
            const [campaignData, leadsData, statsData] = await Promise.all([
                get<Campaign>(`/campaigns/${id}`),
                get<Lead[]>(`/campaigns/${id}/leads`),
                get<CampaignStats>(`/campaigns/${id}/stats`)
            ])
            setCampaign(campaignData)
            setLeads(leadsData)
            setStats(statsData)
            setError(null)
        } catch (err) {
            setError(parseApiError(err))
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { if (id) fetchData() }, [id])

    const handleLeadsAdded = () => { setShowAddLead(false); setShowImportCSV(false); fetchData() }

    const handleToggleStatus = async () => {
        if (!id || !campaign || toggling) return
        const action = campaign.status === "active" ? "stop" : "start"
        setToggling(true)
        try {
            const result = await patch<Campaign>(`/campaigns/${id}/status?action=${action}`, {})
            setCampaign(result)
            toast.success(`Campaign ${action === "start" ? "started" : "paused"}`)
        } catch (err) { toast.error(parseApiError(err)) }
        finally { setToggling(false) }
    }

    const startEditing = () => {
        if (!campaign) return
        setEditForm({
            name: campaign.name, sender_name: campaign.sender_name, goal: campaign.goal || "",
            follow_up_delay_minutes: campaign.follow_up_delay_minutes, max_follow_ups: campaign.max_follow_ups,
            scheduled_start_at: campaign.scheduled_start_at ? new Date(campaign.scheduled_start_at).toISOString().slice(0, 16) : "",
        })
        setEditing(true)
    }

    const handleSaveEdit = async () => {
        if (!id) return
        setSaving(true)
        try {
            const result = await patch<Campaign>(`/campaigns/${id}`, editForm)
            setCampaign(result); setEditing(false); toast.success("Campaign updated")
        } catch (err) { toast.error(parseApiError(err)) }
        finally { setSaving(false) }
    }

    const handleDuplicate = async () => {
        if (!id) return
        try {
            const result = await post<Campaign>(`/campaigns/${id}/duplicate`, {})
            toast.success("Campaign duplicated"); navigate(`/campaigns/${result.id}`)
        } catch (err) { toast.error(parseApiError(err)) }
    }

    const handleBulkDelete = async () => {
        if (!id || selectedLeads.size === 0) return
        setBulkDeleting(true)
        try {
            await post(`/campaigns/${id}/leads/bulk-delete`, { lead_ids: Array.from(selectedLeads) })
            toast.success(`${selectedLeads.size} lead(s) deleted`); setSelectedLeads(new Set()); fetchData()
        } catch (err) { toast.error(parseApiError(err)) }
        finally { setBulkDeleting(false) }
    }

    const toggleSelectLead = (lid: string) => {
        setSelectedLeads(prev => { const n = new Set(prev); n.has(lid) ? n.delete(lid) : n.add(lid); return n })
    }
    // Select-all toggles only within the current filter: if every visible lead
    // is already selected, deselect them (leaving out-of-filter selections intact).
    // Otherwise, add every visible lead to the selection.
    const allFilteredSelected = filteredLeads.length > 0 && filteredLeads.every(l => selectedLeads.has(l.id))
    const toggleSelectAll = () => {
        setSelectedLeads(prev => {
            const next = new Set(prev)
            if (allFilteredSelected) {
                filteredLeads.forEach(l => next.delete(l.id))
            } else {
                filteredLeads.forEach(l => next.add(l.id))
            }
            return next
        })
    }

    const canEdit = campaign?.status === "draft" || campaign?.status === "paused"
    const leadsWithNotes = leads.filter(l => l.notes && l.notes.trim()).length
    const notesPercent = leads.length > 0 ? Math.round((leadsWithNotes / leads.length) * 100) : 0

    if (error) {
        const is404 = error.toLowerCase().includes("not found") || error.toLowerCase().includes("404")
        return <ErrorPage title={is404 ? "Campaign Not Found" : "Something Went Wrong"} message={error} statusCode={is404 ? 404 : 500} />
    }

    const canStart = (campaign?.status === "draft" || campaign?.status === "paused") && leads.length > 0
    const canStop = campaign?.status === "active"
    const showToggle = campaign?.status === "draft" || campaign?.status === "paused" || campaign?.status === "active"
    const isCompleted = campaign?.status === "completed"
    const hasLeads = stats ? stats.emails_target > 0 : false
    const campaignProgress = hasLeads && stats ? Math.min(100, Math.round((stats.emails_sent / stats.emails_target) * 100)) : 0
    const rateLimitProgress = stats ? Math.min(100, Math.round((stats.emails_in_window / stats.rate_limit) * 100)) : 0
    const isRateLimited = stats ? stats.rate_limit_remaining === 0 : false

    return (
        <div className="p-6">
            <div className="space-y-5">

                {/* ── Header ──────────────────────────────────────────── */}
                <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
                    <div className="min-w-0 flex-1">
                        {loading ? (
                            <><Skeleton className="h-8 w-64 mb-2" /><Skeleton className="h-4 w-48" /></>
                        ) : (
                            <>
                                <div className="flex items-center gap-3 mb-0.5">
                                    <h1 className="text-2xl font-semibold tracking-tight truncate">{campaign?.name}</h1>
                                    {campaign && (() => { const s = getCampaignStatus(campaign.status); return <Badge variant={s.variant} className={s.className}>{s.label}</Badge> })()}
                                </div>
                                <p className="text-[13px] text-muted-foreground">{campaign?.sender_name} &middot; {campaign?.sender_email}</p>
                            </>
                        )}
                    </div>
                    {!loading && (
                        <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
                            {showToggle && (
                                <TooltipProvider>
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <span>
                                                <Button variant={canStart ? "default" : "outline"} size="sm" onClick={handleToggleStatus} disabled={toggling || (!canStart && !canStop)} className="gap-1.5">
                                                    {canStop ? <Pause size={14} /> : <Play size={14} />}
                                                    {canStop ? (toggling ? "Pausing..." : "Pause") : (toggling ? "Starting..." : "Start")}
                                                </Button>
                                            </span>
                                        </TooltipTrigger>
                                        {!canStart && !canStop && <TooltipContent>Add leads to start campaign</TooltipContent>}
                                    </Tooltip>
                                </TooltipProvider>
                            )}
                            {leads.length > 0 && <Button variant="outline" size="sm" onClick={() => setShowPreview(true)} className="gap-1.5"><Eye size={14} /> Preview</Button>}
                            <Button variant="outline" size="sm" onClick={handleDuplicate} className="gap-1.5"><Copy size={14} /> Duplicate</Button>
                            {canEdit && <Button variant="outline" size="sm" onClick={startEditing} className="gap-1.5"><Pencil size={14} /> Edit</Button>}
                            {!isCompleted && (
                                <>
                                    <Button variant="outline" size="sm" onClick={() => setShowImportCSV(true)} className="gap-1.5"><Upload size={14} /> Import</Button>
                                    <Button variant="outline" size="sm" onClick={() => setShowAddLead(true)} className="gap-1.5"><UserPlus size={14} /> Add Lead</Button>
                                </>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setShowDelete(true)} className="text-muted-foreground hover:text-destructive"><Trash2 size={14} /></Button>
                        </div>
                    )}
                </div>

                {/* ── Unified Overview Panel ──────────────────────────── */}
                {loading ? (
                    <Skeleton className="h-40 rounded-xl" />
                ) : campaign && stats && (
                    <div className="bg-card border rounded-xl overflow-hidden">
                        {/* Stat row: single container, divided columns */}
                        <div className="grid grid-cols-3 sm:grid-cols-6 divide-x">
                            {[
                                { label: "Leads", value: leads.length },
                                { label: "Sent", value: <>{stats.emails_sent}<span className="text-xs font-normal text-muted-foreground">/{stats.emails_target}</span></> },
                                { label: "Reply Rate", value: `${stats.reply_rate}%` },
                                { label: "Avg to Reply", value: stats.avg_sequence_at_reply ? stats.avg_sequence_at_reply.toFixed(1) : "—" },
                                { label: "Delay", value: formatDelay(campaign.follow_up_delay_minutes) },
                                { label: "Follow-ups", value: campaign.max_follow_ups },
                            ].map(s => (
                                <div key={s.label} className="px-4 py-3">
                                    <p className="text-[11px] text-muted-foreground mb-0.5">{s.label}</p>
                                    <p className="text-lg font-semibold leading-tight">{s.value}</p>
                                </div>
                            ))}
                        </div>

                        {/* Progress bars */}
                        <div className="border-t px-4 py-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2.5">
                            <div className="space-y-1">
                                <div className="flex justify-between text-[11px] text-muted-foreground">
                                    <span>Campaign Progress</span>
                                    <span>{hasLeads ? `${campaignProgress}%` : "No leads"}</span>
                                </div>
                                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                    <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${campaignProgress}%` }} />
                                </div>
                            </div>
                            <div className="space-y-1">
                                <div className="flex justify-between text-[11px] text-muted-foreground">
                                    <span>Sending Quota</span>
                                    <span>{isCompleted ? "Done" : `${stats.emails_in_window}/${stats.rate_limit}`}</span>
                                </div>
                                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                    <div className={`h-full rounded-full transition-all ${isCompleted ? "bg-muted-foreground/30" : isRateLimited ? "bg-red-500" : rateLimitProgress > 80 ? "bg-yellow-500" : "bg-emerald-500"}`} style={{ width: `${isCompleted ? 100 : rateLimitProgress}%` }} />
                                </div>
                            </div>
                        </div>

                        {/* Lead quality inline */}
                        {leads.length > 0 && (
                            <div className="border-t px-4 py-2 flex items-center gap-3 text-[11px]">
                                <span className="text-muted-foreground">{leadsWithNotes}/{leads.length} leads have notes</span>
                                <div className="h-1 bg-muted rounded-full flex-1 max-w-24 overflow-hidden">
                                    <div className={`h-full rounded-full ${notesPercent >= 50 ? "bg-emerald-500" : "bg-yellow-500"}`} style={{ width: `${notesPercent}%` }} />
                                </div>
                                {notesPercent < 50 && <span className="text-yellow-600">Add notes for better personalization</span>}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Rate-limit banner ───────────────────────────────── */}
                {!loading && isRateLimited && stats?.rate_limit_resets_at && (
                    <Alert variant="destructive">
                        <AlertTriangle />
                        <AlertTitle>Sending paused — hourly quota reached</AlertTitle>
                        <AlertDescription>
                            {stats.rate_limit} emails sent in the last {stats.rate_limit_window_minutes} minutes. Sending resumes at{" "}
                            {new Date(stats.rate_limit_resets_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}.
                        </AlertDescription>
                    </Alert>
                )}

                {/* ── Scheduled Start (subtle, no card) ───────────────── */}
                {!loading && campaign?.scheduled_start_at && campaign.status === "draft" && (
                    <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
                        <CalendarClock size={13} />
                        <span>Scheduled to start <span className="text-foreground font-medium">{new Date(campaign.scheduled_start_at).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}</span></span>
                    </div>
                )}

                {/* ── Goal (no card, just text) ───────────────────────── */}
                {!loading && !editing && campaign?.goal && (
                    <div>
                        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-1">Goal</p>
                        <p className="text-[13px] leading-relaxed text-foreground/80">{campaign.goal}</p>
                    </div>
                )}

                {/* ── Attached documents ─────────────────────────────── */}
                {!loading && campaign && !editing && (
                    <AttachedDocumentsCard
                        campaignId={campaign.id}
                        canEdit={canEdit}
                        attached={campaign.documents || []}
                        onChange={fetchData}
                    />
                )}

                {/* ── Edit Panel ──────────────────────────────────────── */}
                {editing && (
                    <div className="bg-card border rounded-xl p-5 space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold">Edit Campaign</h2>
                            <div className="flex items-center gap-2">
                                <Button size="sm" onClick={handleSaveEdit} disabled={saving} className="gap-1.5"><Check size={14} />{saving ? "Saving..." : "Save"}</Button>
                                <Button size="sm" variant="ghost" onClick={() => setEditing(false)} className="gap-1.5"><X size={14} /> Cancel</Button>
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
                )}

                {/* ── Leads Section ───────────────────────────────────── */}
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <h2 className="text-[15px] font-semibold">Leads</h2>
                        {!loading && <span className="text-[12px] text-muted-foreground">{filteredLeads.length} total</span>}
                    </div>

                    {!loading && (
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
                            <Input placeholder="Search leads..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-9 h-8 text-[13px]" />
                        </div>
                    )}

                    {selectedLeads.size > 0 && (
                        <div className="flex items-center gap-3 bg-muted/50 border rounded-lg px-3 py-2">
                            <span className="text-[13px] font-medium">{selectedLeads.size} selected</span>
                            <Button variant="destructive" size="sm" onClick={handleBulkDelete} disabled={bulkDeleting} className="gap-1.5 h-7 text-[12px]">
                                <Trash2 size={12} />{bulkDeleting ? "Deleting..." : "Delete"}
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setSelectedLeads(new Set())} className="h-7 text-[12px]">Clear</Button>
                        </div>
                    )}

                    {loading ? (
                        <Skeleton className="h-48 rounded-xl" />
                    ) : filteredLeads.length === 0 ? (
                        <div className="text-center py-12 border border-dashed rounded-xl">
                            <p className="text-muted-foreground text-[13px]">
                                {leads.length === 0 ? "No leads yet. Add leads manually or import from CSV." : "No leads match your search."}
                            </p>
                        </div>
                    ) : (
                        <div className="border rounded-xl overflow-auto max-h-[50vh]">
                            <Table>
                                <TableHeader className="sticky top-0 bg-card z-10">
                                    <TableRow>
                                        <TableHead className="w-10">
                                            <input type="checkbox" checked={allFilteredSelected} onChange={toggleSelectAll} aria-label={allFilteredSelected ? "Deselect all visible leads" : "Select all visible leads"} className="rounded border-input" />
                                        </TableHead>
                                        <TableHead className="text-[12px]">Name</TableHead>
                                        <TableHead className="text-[12px]">Email</TableHead>
                                        <TableHead className="text-[12px]">Company</TableHead>
                                        <TableHead className="text-[12px]">Status</TableHead>
                                        <TableHead className="text-[12px]">Seq</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {filteredLeads.map(lead => {
                                        const s = getLeadStatus(lead.status)
                                        return (
                                            <TableRow key={lead.id} className="cursor-pointer group hover:bg-muted/40" onClick={() => navigate(`/campaigns/${id}/leads/${lead.id}`)}>
                                                <TableCell onClick={e => e.stopPropagation()}>
                                                    <input type="checkbox" checked={selectedLeads.has(lead.id)} onChange={() => toggleSelectLead(lead.id)} className="rounded border-input" />
                                                </TableCell>
                                                <TableCell>
                                                    <span className="inline-flex items-center gap-1.5 font-medium text-[13px] group-hover:text-primary transition-colors">
                                                        {lead.first_name} {lead.last_name}
                                                        <ArrowUpRight size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                                                    </span>
                                                </TableCell>
                                                <TableCell className="text-[13px] text-muted-foreground max-w-[200px]"><span className="truncate block" title={lead.email}>{lead.email}</span></TableCell>
                                                <TableCell className="text-[13px]">{lead.company || "—"}</TableCell>
                                                <TableCell><Badge variant={s.variant} className={`${s.className} text-[10px]`}>{s.label}</Badge></TableCell>
                                                <TableCell className="text-[13px] text-muted-foreground">{lead.current_sequence}</TableCell>
                                            </TableRow>
                                        )
                                    })}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </div>

                {/* ── Modals ──────────────────────────────────────────── */}
                {id && (
                    <>
                        <AddLeadModal open={showAddLead} onClose={() => setShowAddLead(false)} onSuccess={handleLeadsAdded} campaignId={id} />
                        <ImportCSVModal open={showImportCSV} onClose={() => setShowImportCSV(false)} onSuccess={handleLeadsAdded} campaignId={id} />
                        <DeleteCampaignModal open={showDelete} onClose={() => setShowDelete(false)} campaignId={id} campaignName={campaign?.name || ""} />
                        <PreviewEmailModal open={showPreview} onClose={() => setShowPreview(false)} campaignId={id} leads={leads} />
                    </>
                )}
            </div>
        </div>
    )
}
