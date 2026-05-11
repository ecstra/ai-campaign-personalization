import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

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
    const [confirmingDelete, setConfirmingDelete] = useState(false)

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
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-[20px] font-bold tracking-tight">Leads</h2>
                {!loading && <span className="text-[13px] text-muted-foreground">{filteredLeads.length} total</span>}
            </div>

            {!loading && (
                <div className="relative">
                    <span className="material-symbols-rounded absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground text-[20px]">search</span>
                    <Input placeholder="Search leads..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-12 h-12 text-[14px] rounded-full bg-card" />
                </div>
            )}

            {selectedLeads.size > 0 && (
                <div className="flex items-center gap-2 bg-muted/30 border rounded-full px-5 py-3 shadow-sm">
                    <span className="text-[14px] font-medium leading-none">
                        {confirmingDelete ? `Delete ${selectedLeads.size} lead(s)?` : `${selectedLeads.size} selected`}
                    </span>
                    {confirmingDelete ? (
                        <>
                            <Button variant="destructive" onClick={() => { onBulkDelete(); setConfirmingDelete(false) }} disabled={bulkDeleting} className="h-9 text-[13px] rounded-full px-4">
                                {bulkDeleting ? "Deleting..." : "Confirm"}
                            </Button>
                            <Button variant="ghost" onClick={() => setConfirmingDelete(false)} className="h-9 text-[13px] rounded-full px-4">Cancel</Button>
                        </>
                    ) : (
                        <>
                            <Button variant="ghost" size="icon" onClick={() => setConfirmingDelete(true)} className="h-9 w-9 rounded-full text-muted-foreground hover:text-destructive-hover-foreground hover:bg-destructive-hover">
                                <span className="material-symbols-rounded text-[18px]">delete</span>
                            </Button>
                            <Button variant="ghost" onClick={() => setSelectedLeads(new Set())} className="h-9 text-[13px] rounded-full px-4">Clear</Button>
                        </>
                    )}
                </div>
            )}

            {loading ? (
                <Skeleton className="h-48 rounded-lg" />
            ) : filteredLeads.length === 0 ? (
                <div className="text-center py-12 border border-dashed rounded-lg">
                    <p className="text-muted-foreground text-[13px]">
                        {leads.length === 0 ? "No leads yet. Add leads manually or import from CSV." : "No leads match your search."}
                    </p>
                </div>
            ) : (
                <div className="border rounded-lg overflow-y-auto max-h-[50vh] shadow-sm bg-card">
                    <Table containerClassName="rounded-lg">
                        <TableHeader className="bg-muted">
                            <TableRow>
                                <TableHead className="w-10">
                                    <label className="flex items-center justify-center cursor-pointer" onClick={e => e.stopPropagation()}>
                                        <input 
                                            type="checkbox" 
                                            checked={allFilteredSelected} 
                                            onChange={toggleSelectAll} 
                                            aria-label={allFilteredSelected ? "Deselect all visible leads" : "Select all visible leads"} 
                                            className="sr-only" 
                                        />
                                        <span className={`h-[18px] w-[18px] rounded-[5px] border-2 flex items-center justify-center transition-colors ${allFilteredSelected ? 'bg-primary border-primary' : 'border-muted-foreground'}`}>
                                            {allFilteredSelected && <span className="material-symbols-rounded !text-[12px] leading-none text-primary-foreground">check</span>}
                                        </span>
                                    </label>
                                </TableHead>
                                <TableHead className="text-[13px] font-semibold py-4">Name</TableHead>
                                <TableHead className="text-[13px] font-semibold py-4">Email</TableHead>
                                <TableHead className="text-[13px] font-semibold py-4">Company</TableHead>
                                <TableHead className="text-[13px] font-semibold py-4">Status</TableHead>
                                <TableHead className="text-[13px] font-semibold py-4">Seq</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {filteredLeads.map(lead => {
                                const s = getLeadStatus(lead.status)
                                return (
                                    <TableRow key={lead.id} tabIndex={0} role="button" className="cursor-pointer group hover:bg-muted/60" onClick={() => navigate(`/campaigns/${campaignId}/leads/${lead.id}`)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate(`/campaigns/${campaignId}/leads/${lead.id}`) } }}>
                                        <TableCell onClick={e => e.stopPropagation()}>
                                            <label className="flex items-center justify-center cursor-pointer">
                                                <input 
                                                    type="checkbox" 
                                                    checked={selectedLeads.has(lead.id)} 
                                                    onChange={() => toggleSelectLead(lead.id)} 
                                                    className="sr-only" 
                                                />
                                                <span className={`h-[18px] w-[18px] rounded-[5px] border-2 flex items-center justify-center transition-colors ${selectedLeads.has(lead.id) ? 'bg-primary border-primary' : 'border-muted-foreground'}`}>
                                                    {selectedLeads.has(lead.id) && <span className="material-symbols-rounded !text-[12px] leading-none text-primary-foreground">check</span>}
                                                </span>
                                            </label>
                                        </TableCell>
                                        <TableCell className="py-4">
                                            <span className="inline-flex items-center gap-1.5 font-medium text-[14px] group-hover:text-primary transition-colors">
                                                {lead.first_name} {lead.last_name}
                                                <span className="material-symbols-rounded text-[14px] opacity-0 group-hover:opacity-100 transition-opacity">arrow_outward</span>
                                            </span>
                                        </TableCell>
                                        <TableCell className="text-[14px] text-muted-foreground max-w-[200px] py-4"><span className="truncate block" title={lead.email}>{lead.email}</span></TableCell>
                                        <TableCell className="text-[14px] py-4">{lead.company || "—"}</TableCell>
                                        <TableCell className="py-4"><Badge variant={s.variant} className={`${s.className} text-[11px] px-3 py-1 rounded-full`}>{s.label}</Badge></TableCell>
                                        <TableCell className="text-[14px] text-muted-foreground py-4">{lead.current_sequence}</TableCell>
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
