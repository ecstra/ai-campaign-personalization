import { Skeleton } from "@/components/ui/skeleton"
import type { Campaign, CampaignStats, Lead } from "@/lib/types"
import { formatDelay } from "@/lib/utils"

interface CampaignOverviewProps {
    campaign: Campaign | null
    stats: CampaignStats | null
    leads: Lead[]
    loading: boolean
}

export default function CampaignOverview({ campaign, stats, leads, loading }: CampaignOverviewProps) {
    if (loading) {
        return <Skeleton className="h-40 rounded-lg" />
    }

    if (!campaign || !stats) {
        return null
    }

    const isCompleted = campaign.status === "completed"
    const hasLeads = stats.emails_target > 0
    const campaignProgress = hasLeads ? Math.min(100, Math.round((stats.emails_sent / stats.emails_target) * 100)) : 0
    const rateLimitProgress = Math.min(100, Math.round((stats.emails_in_window / stats.rate_limit) * 100))
    const isRateLimited = stats.rate_limit_remaining === 0

    const leadsWithNotes = leads.filter(l => l.notes && l.notes.trim()).length
    const notesPercent = leads.length > 0 ? Math.round((leadsWithNotes / leads.length) * 100) : 0

    return (
        <div className="bg-card border rounded-lg overflow-hidden ">
            {/* Stat row: single container, divided columns */}
            <div className="grid grid-cols-3 sm:grid-cols-6 divide-x">
                {[
                    { label: "Leads", value: leads.length },
                    { label: "Sent", value: <>{stats.emails_sent}<span className="text-xs font-normal text-muted-foreground">/{stats.emails_target}</span></> },
                    { label: "Reply Rate", value: `${stats.reply_rate}%` },
                    { label: "Avg to Reply", value: stats.avg_sequence_at_reply ? stats.avg_sequence_at_reply.toFixed(1) : "—" },
                    { label: "Delay", value: formatDelay(campaign.follow_up_delay_minutes) },
                    { label: "Follow-ups", value: campaign.max_follow_ups },
                ].map((s, i) => (
                    <div key={i} className="px-4 py-3">
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
                        <div className="h-full rounded-full bg-success transition-all" style={{ width: `${campaignProgress}%` }} />
                    </div>
                </div>
                <div className="space-y-1">
                    <div className="flex justify-between text-[11px] text-muted-foreground">
                        <span>Sending Quota</span>
                        <span>{isCompleted ? "Done" : `${stats.emails_in_window}/${stats.rate_limit}`}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${isCompleted ? "bg-muted-foreground/30" : isRateLimited ? "bg-destructive-alert-foreground" : rateLimitProgress > 80 ? "bg-warning" : "bg-success"}`} style={{ width: `${isCompleted ? 100 : rateLimitProgress}%` }} />
                    </div>
                </div>
            </div>

            {/* Lead quality inline */}
            {leads.length > 0 && (
                <div className="border-t px-4 py-2 flex items-center gap-3 text-[11px]">
                    <span className="text-muted-foreground">{leadsWithNotes}/{leads.length} leads have notes</span>
                    <div className="h-1 bg-muted rounded-full flex-1 max-w-24 overflow-hidden">
                        <div className={`h-full rounded-full ${notesPercent >= 50 ? "bg-success" : "bg-warning"}`} style={{ width: `${notesPercent}%` }} />
                    </div>
                    {notesPercent < 50 && <span className="text-warning-foreground">Add notes for better personalization</span>}
                </div>
            )}
        </div>
    )
}
