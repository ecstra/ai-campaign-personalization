import DOMPurify from "dompurify"
import { formatTime } from "@/lib/utils"
import { getEmailStatus } from "@/lib/status"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"


export type EmailActivity = {
    id: string
    sequence_number: number
    subject: string
    body: string
    status: string
    sent_at: string | null
    created_at: string
}

function formatDate(dateString: string | null) {
    if (!dateString) return ""
    const date = new Date(dateString)
    const timeStr = formatTime(dateString)
    const dateStr = date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
    return timeStr ? `${dateStr}, ${timeStr.time} IST` : dateStr
}

export default function EmailActivityTimeline({
    activity,
    loading,
    expandedIds,
    toggleExpand,
}: {
    activity: EmailActivity[]
    loading: boolean
    expandedIds: Set<string>
    toggleExpand: (id: string) => void
}) {
    if (loading) {
        return (
            <div className="space-y-3">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 rounded-2xl" />)}
            </div>
        )
    }

    if (activity.length === 0) {
        return (
            <div className="text-center py-12 border border-dashed rounded-2xl">
                <p className="text-body-m text-muted-foreground">No emails sent yet</p>
            </div>
        )
    }

    return (
        <div className="relative pl-6">
            <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

            <div className="space-y-3">
                {activity.map(email => {
                    const isExpanded = expandedIds.has(email.id)
                    const s = getEmailStatus(email.status)
                    const dotColor = email.status === "sent" ? "bg-success"
                        : email.status === "received" ? "bg-info"
                        : email.status === "failed" ? "bg-destructive-container-foreground"
                        : "bg-warning"

                    return (
                        <div key={email.id} className="relative">
                            <div className={`absolute -left-6 top-4 w-3.5 h-3.5 rounded-full border-2 border-background ${dotColor} ring-2 ring-background`} />

                            <div
                                className={`bg-card border border-border rounded-2xl p-5 cursor-pointer transition-colors hover:bg-accent/50 ${isExpanded ? "bg-accent/30" : ""}`}
                                onClick={() => toggleExpand(email.id)}
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex items-center gap-3 min-w-0">
                                        {email.status === "sent" ? <span className="material-symbols-rounded text-success-foreground flex-shrink-0" style={{ fontSize: '18px', transform: 'rotate(-45deg) translateX(8%)' }}>send</span>
                                            : email.status === "received" ? <span className="material-symbols-rounded text-info-foreground text-[18px] flex-shrink-0">reply</span>
                                            : email.status === "failed" ? <span className="material-symbols-rounded text-destructive-container-foreground text-[18px] flex-shrink-0">error</span>
                                            : <span className="material-symbols-rounded text-warning-foreground text-[18px] flex-shrink-0">schedule</span>}
                                        <span className="text-title-m">
                                            {email.status === "received" || email.sequence_number <= 0
                                                ? "Reply Received"
                                                : `Email #${email.sequence_number}`}
                                        </span>
                                        <span className="text-body-s text-muted-foreground hidden sm:inline">
                                            {formatDate(email.sent_at || email.created_at)}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Badge variant={s.variant} className={`${s.className} text-[11px] px-3 py-1 rounded-full`}>{s.label}</Badge>
                                        <span className={`material-symbols-rounded text-muted-foreground text-[20px] transition-transform ${isExpanded ? "rotate-180" : ""}`}>expand_more</span>
                                    </div>
                                </div>

                                <p className={`text-body-m mt-3 ${isExpanded ? "" : "line-clamp-1"} text-muted-foreground`}>
                                    {email.subject}
                                </p>

                                <div
                                    className={`grid transition-[grid-template-rows,opacity,margin-top] duration-300 ease-out ${
                                        isExpanded ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0 mt-0"
                                    }`}
                                >
                                    <div className="overflow-hidden">
                                        <div className="pt-4 border-t">
                                        <div
                                            className="text-body-m leading-relaxed [&>p]:mb-3 [&>p:last-child]:mb-0"
                                            dangerouslySetInnerHTML={{
                                                __html: email.status === "failed"
                                                    ? "We couldn't send this email. Please check if the email address is valid."
                                                    : DOMPurify.sanitize(email.body, {
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
    )
}
