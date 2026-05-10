import DOMPurify from "dompurify"
import { formatTime } from "@/lib/utils"
import { getEmailStatus } from "@/lib/status"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Send, Reply, AlertCircle, Clock } from "lucide-react"

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
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
            </div>
        )
    }

    if (activity.length === 0) {
        return (
            <div className="text-center py-12 border border-dashed rounded-xl">
                <p className="text-sm text-muted-foreground">No emails sent yet</p>
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
                    const dotColor = email.status === "sent" ? "bg-emerald-500"
                        : email.status === "received" ? "bg-blue-500"
                        : email.status === "failed" ? "bg-red-500"
                        : "bg-yellow-500"

                    return (
                        <div key={email.id} className="relative">
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
