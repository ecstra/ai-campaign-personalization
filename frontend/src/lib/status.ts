/**
 * Centralized status configuration for campaigns, leads, and emails.
 * Used with shadcn Badge component across all pages.
 */

type StatusConfig = {
    label: string
    variant: "default" | "secondary" | "destructive" | "outline"
    className: string
}

const campaignStatuses: Record<string, StatusConfig> = {
    draft: { label: "Draft", variant: "secondary", className: "bg-muted text-muted-foreground" },
    active: { label: "Active", variant: "default", className: "bg-green-100 text-green-700 border-green-200" },
    paused: { label: "Paused", variant: "outline", className: "bg-yellow-100 text-yellow-700 border-yellow-200" },
    completed: { label: "Completed", variant: "secondary", className: "bg-blue-100 text-blue-700 border-blue-200" },
}

const leadStatuses: Record<string, StatusConfig> = {
    pending: { label: "Pending", variant: "outline", className: "bg-yellow-100 text-yellow-700 border-yellow-200" },
    processing: { label: "Processing", variant: "outline", className: "bg-orange-100 text-orange-700 border-orange-200" },
    active: { label: "Active", variant: "default", className: "bg-green-100 text-green-700 border-green-200" },
    replied: { label: "Replied", variant: "default", className: "bg-blue-100 text-blue-700 border-blue-200" },
    completed: { label: "Completed", variant: "secondary", className: "bg-gray-100 text-gray-700 border-gray-200" },
    failed: { label: "Failed", variant: "destructive", className: "bg-red-100 text-red-700 border-red-200" },
}

const emailStatuses: Record<string, StatusConfig> = {
    sent: { label: "Sent", variant: "default", className: "bg-green-100 text-green-700 border-green-200" },
    pending: { label: "Pending", variant: "outline", className: "bg-yellow-100 text-yellow-700 border-yellow-200" },
    failed: { label: "Failed", variant: "destructive", className: "bg-red-100 text-red-700 border-red-200" },
    received: { label: "Received", variant: "default", className: "bg-blue-100 text-blue-700 border-blue-200" },
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
