export type AttachedDoc = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string | null
    updated_at: string | null
}

export type Campaign = {
    id: string
    name: string
    sender_name: string
    sender_email: string
    goal: string | null
    follow_up_delay_minutes: number
    max_follow_ups: number
    status: string
    documents: AttachedDoc[]
}

export type CampaignStats = {
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

export type Lead = {
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
    max_follow_ups: number
    next_email_at: string | null
    created_at: string
    updated_at: string
    campaign_name: string
}
