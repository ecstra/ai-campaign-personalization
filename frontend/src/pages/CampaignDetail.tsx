import { useState, useEffect, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { get, post, patch } from "@/lib/api"
import { getCampaignStatus } from "@/lib/status"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import ErrorPage from "./ErrorPage"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"

import AddLeadModal from "@/components/AddLeadModal"
import ImportCSVModal from "@/components/ImportCSVModal"
import DeleteCampaignModal from "@/components/DeleteCampaignModal"
import AttachedDocumentsCard from "@/components/AttachedDocumentsCard"
import type { Campaign, CampaignStats, Lead } from "@/lib/types"

import { useAsyncAction } from "@/hooks/use-async-action"
import CampaignOverview from "@/components/campaign/CampaignOverview"
import CampaignEditForm from "@/components/campaign/CampaignEditForm"
import LeadsTable from "@/components/campaign/LeadsTable"

export default function CampaignDetail() {
    const { id } = useParams<{ id: string }>()
    const navigate = useNavigate()

    const [campaign, setCampaign] = useState<Campaign | null>(null)
    const [leads, setLeads] = useState<Lead[]>([])
    const [stats, setStats] = useState<CampaignStats | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    // Modal state
    const [showAddLead, setShowAddLead] = useState(false)
    const [showImportCSV, setShowImportCSV] = useState(false)
    const [showDelete, setShowDelete] = useState(false)

    // Edit state
    const [editing, setEditing] = useState(false)
    const [editForm, setEditForm] = useState({ name: "", sender_name: "", goal: "", follow_up_delay_minutes: 0, max_follow_ups: 0 })

    // Leads table state
    const [searchQuery, setSearchQuery] = useState("")
    const [selectedLeads, setSelectedLeads] = useState<Set<string>>(new Set())

    useBreadcrumbs([
        { label: "Campaigns", href: "/" },
        { label: campaign?.name || "Loading..." },
    ])

    const fetchData = useCallback(async () => {
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
    }, [id])

    useEffect(() => { if (id) fetchData() }, [id, fetchData])

    const handleLeadsAdded = () => { setShowAddLead(false); setShowImportCSV(false); fetchData() }

    const { execute: toggleStatus, isLoading: toggling } = useAsyncAction(
        async (action: string) => patch<Campaign>(`/campaigns/${id}/status?action=${action}`, {}),
        {
            onSuccess: setCampaign,
            successMessage: () => `Campaign status updated`
        }
    )

    const handleToggleStatus = () => {
        if (!id || !campaign || toggling) return
        const action = campaign.status === "active" ? "stop" : "start"
        toggleStatus(action)
    }

    const startEditing = () => {
        if (!campaign) return
        setEditForm({
            name: campaign.name, sender_name: campaign.sender_name, goal: campaign.goal || "",
            follow_up_delay_minutes: campaign.follow_up_delay_minutes, max_follow_ups: campaign.max_follow_ups,
        })
        setEditing(true)
    }

    const { execute: handleSaveEdit, isLoading: saving } = useAsyncAction(
        async () => patch<Campaign>(`/campaigns/${id}`, editForm),
        {
            onSuccess: (result) => { setCampaign(result); setEditing(false) },
            successMessage: "Campaign updated"
        }
    )

    const { execute: handleDuplicate } = useAsyncAction(
        async () => post<Campaign>(`/campaigns/${id}/duplicate`, {}),
        {
            onSuccess: (result) => navigate(`/campaigns/${result.id}`),
            successMessage: "Campaign duplicated"
        }
    )

    const { execute: executeBulkDelete, isLoading: bulkDeleting } = useAsyncAction(
        async () => post(`/campaigns/${id}/leads/bulk-delete`, { lead_ids: Array.from(selectedLeads) }),
        {
            onSuccess: () => { setSelectedLeads(new Set()); fetchData() },
            successMessage: () => `${selectedLeads.size} lead(s) deleted`
        }
    )

    const handleBulkDelete = () => {
        if (!id || selectedLeads.size === 0) return
        executeBulkDelete()
    }

    const canEdit = campaign?.status === "draft" || campaign?.status === "paused"
    const campaignStatus = campaign ? getCampaignStatus(campaign.status) : null

    if (error) {
        const is404 = error.toLowerCase().includes("not found") || error.toLowerCase().includes("404")
        return <ErrorPage title={is404 ? "Campaign Not Found" : "Something Went Wrong"} message={error} statusCode={is404 ? 404 : 500} />
    }

    const canStart = (campaign?.status === "draft" || campaign?.status === "paused") && leads.length > 0
    const canStop = campaign?.status === "active"
    const showToggle = campaign?.status === "draft" || campaign?.status === "paused" || campaign?.status === "active"
    const isCompleted = campaign?.status === "completed"
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
                                <div className="flex items-center gap-3 mb-1">
                                    <h1 className="text-[28px] font-bold tracking-tight truncate">{campaign?.name}</h1>
                                    {campaignStatus && <Badge variant={campaignStatus.variant} className={`${campaignStatus.className} text-[12px] px-3 py-1 rounded-full`}>{campaignStatus.label}</Badge>}
                                </div>
                                <p className="text-[14px] text-muted-foreground">{campaign?.sender_name} &middot; {campaign?.sender_email}</p>
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
                                                <Button variant={canStart ? "default" : "outline"} onClick={handleToggleStatus} disabled={toggling || (!canStart && !canStop)} className="gap-1 rounded-full h-10 px-5 shadow-sm text-[14px]">
                                                    <span className="material-symbols-rounded text-[18px] -ml-0.5">{canStop ? "pause" : "play_arrow"}</span>
                                                    <span className="leading-none">{canStop ? (toggling ? "Pausing..." : "Pause") : (toggling ? "Starting..." : "Start")}</span>
                                                </Button>
                                            </span>
                                        </TooltipTrigger>
                                        {!canStart && !canStop && <TooltipContent>Add leads to start campaign</TooltipContent>}
                                    </Tooltip>
                                </TooltipProvider>
                            )}
                            <Button variant="outline" onClick={handleDuplicate} className="gap-2 rounded-full h-10 px-5 shadow-sm text-[14px]"><span className="material-symbols-rounded text-[18px]">content_copy</span> Duplicate</Button>
                            {canEdit && <Button variant="outline" onClick={startEditing} className="gap-2 rounded-full h-10 px-5 shadow-sm text-[14px]"><span className="material-symbols-rounded text-[18px]">edit</span> Edit</Button>}
                            {!isCompleted && (
                                <>
                                    <Button variant="outline" onClick={() => setShowImportCSV(true)} className="gap-2 rounded-full h-10 px-5 shadow-sm text-[14px]"><span className="material-symbols-rounded text-[18px]">upload</span> Import</Button>
                                    <Button variant="outline" onClick={() => setShowAddLead(true)} className="gap-2 rounded-full h-10 px-5 shadow-sm text-[14px]"><span className="material-symbols-rounded text-[18px]">person_add</span> Add Lead</Button>
                                </>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setShowDelete(true)} className="text-muted-foreground hover:text-destructive-hover-foreground hover:bg-destructive-hover rounded-full h-10 w-10"><span className="material-symbols-rounded text-[20px]">delete</span></Button>
                        </div>
                    )}
                </div>

                <CampaignOverview campaign={campaign} stats={stats} leads={leads} loading={loading} />

                {/* ── Rate-limit banner ───────────────────────────────── */}
                {!loading && isRateLimited && stats?.rate_limit_resets_at && (
                    <Alert variant="destructive" className="rounded-lg bg-destructive-alert text-destructive-alert-foreground border-none p-6">
                        <span className="material-symbols-rounded text-[20px] mr-3">warning</span>
                        <AlertTitle className="text-[15px] font-semibold">Sending paused — hourly quota reached</AlertTitle>
                        <AlertDescription className="text-[13px]">
                            {stats.rate_limit} emails sent in the last {stats.rate_limit_window_minutes} minutes. Sending resumes at{" "}
                            {new Date(stats.rate_limit_resets_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}.
                        </AlertDescription>
                    </Alert>
                )}

                {/* ── Goal ────────────────────────────────────────────── */}
                {!loading && !editing && campaign?.goal && (
                    <div className="bg-card border rounded-lg p-6 space-y-3 shadow-sm">
                        <h2 className="text-[15px] font-semibold">Campaign goal</h2>
                        <div className="border-t" />
                        <p className="text-[14px] leading-relaxed text-foreground/80">{campaign.goal}</p>
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

                {editing && (
                    <CampaignEditForm 
                        editForm={editForm} 
                        setEditForm={setEditForm} 
                        saving={saving} 
                        onSave={handleSaveEdit} 
                        onCancel={() => setEditing(false)} 
                    />
                )}

                {id && (
                    <LeadsTable
                        campaignId={id}
                        leads={leads}
                        loading={loading}
                        searchQuery={searchQuery}
                        setSearchQuery={setSearchQuery}
                        selectedLeads={selectedLeads}
                        setSelectedLeads={setSelectedLeads}
                        bulkDeleting={bulkDeleting}
                        onBulkDelete={handleBulkDelete}
                    />
                )}

                {/* ── Modals ──────────────────────────────────────────── */}
                {id && (
                    <>
                        <AddLeadModal open={showAddLead} onClose={() => setShowAddLead(false)} onSuccess={handleLeadsAdded} campaignId={id} />
                        <ImportCSVModal open={showImportCSV} onClose={() => setShowImportCSV(false)} onSuccess={handleLeadsAdded} campaignId={id} />
                        <DeleteCampaignModal open={showDelete} onClose={() => setShowDelete(false)} campaignId={id} campaignName={campaign?.name || ""} />
                    </>
                )}
            </div>
        </div>
    )
}
