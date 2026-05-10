import { useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Search, Trash2, ArrowUpRight } from "lucide-react"
import type { Lead } from "@/lib/types"
import { getLeadStatus } from "@/lib/status"

interface LeadsTableProps {
    campaignId: string
    leads: Lead[]
    loading: boolean
    searchQuery: string
    setSearchQuery: (q: string) => void
    selectedLeads: Set<string>
    setSelectedLeads: (s: Set<string> | ((prev: Set<string>) => Set<string>)) => void
    bulkDeleting: boolean
    onBulkDelete: () => void
}

export default function LeadsTable({
    campaignId, leads, loading, searchQuery, setSearchQuery,
    selectedLeads, setSelectedLeads, bulkDeleting, onBulkDelete
}: LeadsTableProps) {
    const navigate = useNavigate()

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

    const toggleSelectLead = (lid: string) => {
        setSelectedLeads((prev: Set<string>) => { const n = new Set(prev); if (n.has(lid)) { n.delete(lid) } else { n.add(lid) }; return n })
    }

    const allFilteredSelected = filteredLeads.length > 0 && filteredLeads.every(l => selectedLeads.has(l.id))
    const toggleSelectAll = () => {
        setSelectedLeads((prev: Set<string>) => {
            const next = new Set(prev)
            if (allFilteredSelected) {
                filteredLeads.forEach(l => next.delete(l.id))
            } else {
                filteredLeads.forEach(l => next.add(l.id))
            }
            return next
        })
    }

    return (
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
                    <Button variant="destructive" size="sm" onClick={onBulkDelete} disabled={bulkDeleting} className="gap-1.5 h-7 text-[12px]">
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
                                    <input 
                                        type="checkbox" 
                                        checked={allFilteredSelected} 
                                        onChange={toggleSelectAll} 
                                        aria-label={allFilteredSelected ? "Deselect all visible leads" : "Select all visible leads"} 
                                        className="h-4 w-4 rounded border-input bg-background accent-primary cursor-pointer transition-colors" 
                                    />
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
                                    <TableRow key={lead.id} className="cursor-pointer group hover:bg-muted/40" onClick={() => navigate(`/campaigns/${campaignId}/leads/${lead.id}`)}>
                                        <TableCell onClick={e => e.stopPropagation()}>
                                            <input 
                                                type="checkbox" 
                                                checked={selectedLeads.has(lead.id)} 
                                                onChange={() => toggleSelectLead(lead.id)} 
                                                className="h-4 w-4 rounded border-input bg-background accent-primary cursor-pointer transition-colors" 
                                            />
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
    )
}
