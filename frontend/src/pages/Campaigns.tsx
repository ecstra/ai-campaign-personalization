import { useState, useEffect, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { get } from "@/lib/api"
import { type Campaign } from "@/lib/types"
import { getCampaignStatus } from "@/lib/status"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"

function CampaignCard({ campaign }: { campaign: Campaign }) {
    const status = getCampaignStatus(campaign.status)

    return (
        <Link to={`/campaigns/${campaign.id}`} className="group">
            <div className="bg-card border rounded-lg p-6 h-full transition-colors duration-150 hover:shadow-sm hover:border-primary/30">
                <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                        <h3 className="font-semibold text-[16px] truncate">{campaign.name}</h3>
                        <span className="material-symbols-rounded text-[16px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">arrow_outward</span>
                    </div>
                    <Badge variant={status.variant} className={`${status.className} text-[11px] ml-2 px-3 py-1 rounded-full`}>
                        {status.label}
                    </Badge>
                </div>

                <p className="text-[14px] text-muted-foreground line-clamp-2 mb-4 leading-relaxed">
                    {campaign.goal || "No goal specified"}
                </p>

                <div className="flex items-center justify-between text-[13px] text-muted-foreground pt-4 border-t">
                    <div className="flex items-center gap-1.5 min-w-0">
                        <span className="material-symbols-rounded text-[16px] flex-shrink-0">mail</span>
                        <span className="truncate">{campaign.sender_email}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className="material-symbols-rounded text-[16px]">group</span>
                        <span>{campaign.max_follow_ups} follow-ups</span>
                    </div>
                </div>
            </div>
        </Link>
    )
}

function CampaignSkeleton() {
    return (
        <div className="bg-card border rounded-lg p-6">
            <div className="flex justify-between items-start mb-3">
                <Skeleton className="h-6 w-36 rounded-full" />
                <Skeleton className="h-6 w-16 rounded-full" />
            </div>
            <Skeleton className="h-4 w-full mb-2 rounded-full" />
            <Skeleton className="h-4 w-2/3 mb-5 rounded-full" />
            <div className="flex justify-between pt-4 border-t">
                <Skeleton className="h-4 w-32 rounded-full" />
                <Skeleton className="h-4 w-20 rounded-full" />
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
            <div className="text-center py-20 bg-card rounded-lg border p-12">
                <div className="rounded-full bg-primary/10 w-16 h-16 flex items-center justify-center mx-auto mb-4">
                    <span className="material-symbols-rounded text-[28px] text-primary">mail</span>
                </div>
                <p className="font-semibold text-[16px] mb-1">No campaigns yet</p>
                <p className="text-muted-foreground text-[14px] mb-8">Create your first campaign to get started with outreach.</p>
                <Button onClick={onCreate} className="gap-2 rounded-lg px-6 h-12 text-[15px]">
                    <span className="material-symbols-rounded text-[18px] -ml-0.5">add</span>
                    <span className="leading-none">Create Campaign</span>
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
                    <h1 className="text-[28px] font-bold tracking-tight">Campaigns</h1>
                    <p className="text-muted-foreground text-[14px] mt-1">Manage your email outreach campaigns</p>
                </div>
                <Button onClick={goToCreate} className="gap-1.5 rounded-full h-12 px-6 shadow-sm hover:bg-primary/80 text-[15px]">
                    <span className="material-symbols-rounded text-[20px] -ml-0.5">add</span>
                    <span className="leading-none">Create Campaign</span>
                </Button>
            </div>

            <div className="relative">
                <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground text-[20px]">search</span>
                <Input
                    placeholder="Search campaigns..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-12 h-12 text-[14px] rounded-full bg-card"
                />
            </div>

            {error ? (
                <Alert variant="destructive" className="rounded-lg bg-destructive-alert text-destructive-alert-foreground border-none p-6">
                    <span className="material-symbols-rounded text-[20px] mr-3">error</span>
                    <AlertDescription className="flex items-center justify-between w-full">
                        <span>{error}</span>
                        <Button variant="outline" size="sm" onClick={() => { setError(null); fetchCampaigns() }} className="h-9 text-[13px] gap-2 rounded-full bg-transparent border-destructive-alert hover:bg-destructive-container text-inherit">
                            <span className="material-symbols-rounded text-[16px]">refresh</span> Retry
                        </Button>
                    </AlertDescription>
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
