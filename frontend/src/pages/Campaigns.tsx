import { useState, useEffect, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { get } from "@/lib/api"
import { getCampaignStatus } from "@/lib/status"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { Plus, Search, Mail, Users, AlertCircle, ArrowUpRight } from "lucide-react"

type Campaign = {
    id: string
    name: string
    sender_name: string
    sender_email: string
    goal: string | null
    max_follow_ups: number
    status: string
    created_at: string
}

function CampaignCard({ campaign }: { campaign: Campaign }) {
    const status = getCampaignStatus(campaign.status)

    return (
        <Link to={`/campaigns/${campaign.id}`} className="group">
            <div className="bg-card border rounded-xl p-5 h-full transition-all duration-200 hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5">
                <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                        <h3 className="font-semibold text-[15px] truncate">{campaign.name}</h3>
                        <ArrowUpRight size={14} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                    </div>
                    <Badge variant={status.variant} className={`${status.className} text-[11px] ml-2`}>
                        {status.label}
                    </Badge>
                </div>

                <p className="text-[13px] text-muted-foreground line-clamp-2 mb-4 leading-relaxed">
                    {campaign.goal || "No goal specified"}
                </p>

                <div className="flex items-center justify-between text-[12px] text-muted-foreground pt-3 border-t">
                    <div className="flex items-center gap-1.5 min-w-0">
                        <Mail size={12} className="flex-shrink-0" />
                        <span className="truncate">{campaign.sender_email}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                        <Users size={12} />
                        <span>{campaign.max_follow_ups} follow-ups</span>
                    </div>
                </div>
            </div>
        </Link>
    )
}

function CampaignSkeleton() {
    return (
        <div className="bg-card border rounded-xl p-5">
            <div className="flex justify-between items-start mb-3">
                <Skeleton className="h-5 w-36" />
                <Skeleton className="h-5 w-14" />
            </div>
            <Skeleton className="h-4 w-full mb-1" />
            <Skeleton className="h-4 w-2/3 mb-4" />
            <div className="flex justify-between pt-3 border-t">
                <Skeleton className="h-3 w-32" />
                <Skeleton className="h-3 w-20" />
            </div>
        </div>
    )
}

function CampaignContent({
    campaigns,
    onCreate,
    loading
}: {
    campaigns: Campaign[]
    onCreate: () => void
    loading: boolean
}) {
    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3, 4, 5, 6].map(i => <CampaignSkeleton key={i} />)}
            </div>
        )
    }

    if (campaigns.length === 0) {
        return (
            <div className="text-center py-20">
                <div className="rounded-full bg-muted w-12 h-12 flex items-center justify-center mx-auto mb-4">
                    <Mail size={20} className="text-muted-foreground" />
                </div>
                <p className="text-muted-foreground mb-1 text-sm">No campaigns yet</p>
                <p className="text-muted-foreground/60 text-xs mb-6">Create your first campaign to get started.</p>
                <Button onClick={onCreate} size="sm" className="gap-2">
                    <Plus size={14} />
                    Create Campaign
                </Button>
            </div>
        )
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {campaigns.map((campaign) => (
                <CampaignCard key={campaign.id} campaign={campaign} />
            ))}
        </div>
    )
}

export default function Campaigns() {
    const navigate = useNavigate()
    const [campaigns, setCampaigns] = useState<Campaign[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState("")

    useBreadcrumbs([{ label: "Campaigns" }])

    const fetchCampaigns = async () => {
        try {
            setLoading(true)
            const data = await get<Campaign[]>("/campaigns")
            setCampaigns(data)
            setError(null)
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to fetch campaigns")
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchCampaigns()
    }, [])

    const filteredCampaigns = useMemo(() => {
        if (!searchQuery.trim()) return campaigns
        const query = searchQuery.toLowerCase()
        return campaigns.filter(c =>
            c.name.toLowerCase().includes(query) ||
            c.sender_name.toLowerCase().includes(query) ||
            c.sender_email.toLowerCase().includes(query) ||
            c.status.toLowerCase().includes(query) ||
            (c.goal && c.goal.toLowerCase().includes(query))
        )
    }, [campaigns, searchQuery])

    const goToCreate = () => navigate("/campaigns/new")

    return (
        <div className="p-6 space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
                    <p className="text-muted-foreground text-sm">Manage your email outreach campaigns</p>
                </div>
                <Button onClick={goToCreate} className="gap-2" size="sm">
                    <Plus size={14} />
                    Create Campaign
                </Button>
            </div>

            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={15} />
                <Input
                    placeholder="Search campaigns..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 h-9 text-sm"
                />
            </div>

            {error ? (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            ) : (
                <CampaignContent
                    campaigns={filteredCampaigns}
                    onCreate={goToCreate}
                    loading={loading}
                />
            )}
        </div>
    )
}
