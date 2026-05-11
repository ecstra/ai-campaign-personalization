/**
 * Centralized status configuration for campaigns, leads, and emails.
 * Used with shadcn Badge component across all pages.
 */

type StatusConfig = {
    label: string
    variant: "default" | "secondary" | "destructive" | "outline" | "custom"
    className: string
}

const badgeBase = {
    green: "bg-badge-emerald text-foreground border-transparent",
    amber: "bg-badge-amber text-foreground border-transparent",
    orange: "bg-badge-orange text-foreground border-transparent",
    sky: "bg-badge-sky text-foreground border-transparent",
    red: "bg-badge-red text-foreground border-transparent",
    slate: "bg-badge-slate text-foreground border-transparent",
}

const campaignStatuses: Record<string, StatusConfig> = {
    draft: { label: "Draft", variant: "custom", className: "bg-muted text-muted-foreground" },
    active: { label: "Active", variant: "custom", className: badgeBase.green },
    paused: { label: "Paused", variant: "custom", className: badgeBase.amber },
    completed: { label: "Completed", variant: "custom", className: badgeBase.sky },
}

const leadStatuses: Record<string, StatusConfig> = {
    pending: { label: "Pending", variant: "custom", className: badgeBase.amber },
    processing: { label: "Processing", variant: "custom", className: badgeBase.orange },
    active: { label: "Active", variant: "custom", className: badgeBase.green },
    replied: { label: "Replied", variant: "custom", className: badgeBase.sky },
    completed: { label: "Completed", variant: "custom", className: badgeBase.slate },
    failed: { label: "Failed", variant: "custom", className: badgeBase.red },
}

const emailStatuses: Record<string, StatusConfig> = {
    sent: { label: "Sent", variant: "custom", className: badgeBase.green },
    pending: { label: "Pending", variant: "custom", className: badgeBase.amber },
    failed: { label: "Failed", variant: "custom", className: badgeBase.red },
    received: { label: "Received", variant: "custom", className: badgeBase.sky },
}

const fallback: StatusConfig = { label: "Unknown", variant: "outline", className: "bg-muted text-muted-foreground" }

export function getCampaignStatus(status: string): StatusConfig {
    return campaignStatuses[status] ?? fallback
}

export function getLeadStatus(status: string): StatusConfig {
    return leadStatuses[status] ?? fallback
}

export function getEmailStatus(status: string): StatusConfig {
    return emailStatuses[status] ?? fallback
}
