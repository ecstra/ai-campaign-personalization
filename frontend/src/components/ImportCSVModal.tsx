/*
NOTE:
It is better to use server-side CSV parsing to avoid security risks and handle large files.
BUT, do that only when there are like 5k+ leads.
For now, we are using client-side CSV parsing.
*/

import { useState, useCallback } from "react"
import Papa from "papaparse"
import { post } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Upload, AlertCircle, CheckCircle2, Download } from "lucide-react"

type Props = {
    open: boolean
    onClose: () => void
    onSuccess: () => void
    campaignId: string
}

type ParsedLead = {
    email: string
    first_name: string
    last_name: string
    company?: string
    title?: string
    notes?: string
    valid: boolean
    errors: string[]
}

const REQUIRED_HEADERS = ["email", "first_name", "last_name"]
const OPTIONAL_HEADERS = ["company", "title", "notes"]

// Two sample rows so users see exactly what a valid row looks like, including
// a "notes" field that shows how free-form text should be quoted.
const TEMPLATE_ROWS: string[][] = [
    ["jane.doe@acmecorp.com", "Jane", "Doe", "Acme Corp", "VP Marketing", "Met at SaaStr, interested in AI outreach"],
    ["john.smith@example.com", "John", "Smith", "Example Inc", "CTO", ""],
]

function downloadTemplateCSV(): void {
    const headers = [...REQUIRED_HEADERS, ...OPTIONAL_HEADERS]
    // Use Papa.unparse so any commas or quotes in sample values get escaped
    // per RFC 4180 — matches exactly what our parser expects on import.
    const csv = Papa.unparse({
        fields: headers,
        data: TEMPLATE_ROWS,
    })
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = "leads_template.csv"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
}

// Uses papaparse to correctly handle RFC 4180 quoted fields, including
// fields that contain commas, quotes, or newlines (common in LinkedIn / Apollo
// exports where the "notes" column has multi-line content).
function parseCSV(text: string): { headers: string[]; rows: string[][] } {
    const result = Papa.parse<string[]>(text, {
        skipEmptyLines: "greedy",
    })

    if (!result.data || result.data.length === 0) {
        return { headers: [], rows: [] }
    }

    const headers = result.data[0].map(h => h.trim().toLowerCase())
    const rows = result.data.slice(1).map(row => row.map(cell => cell.trim()))
    return { headers, rows }
}

function validateLead(row: string[], headers: string[]): ParsedLead {
    const lead: ParsedLead = {
        email: "",
        first_name: "",
        last_name: "",
        valid: true,
        errors: []
    }

    headers.forEach((header, i) => {
        const value = row[i] || ""
        if (header === "email") lead.email = value
        if (header === "first_name") lead.first_name = value
        if (header === "last_name") lead.last_name = value
        if (header === "company") lead.company = value
        if (header === "title") lead.title = value
        if (header === "notes") lead.notes = value
    })

    if (!lead.email) {
        lead.errors.push("Missing email")
        lead.valid = false
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email)) {
        lead.errors.push("Invalid email")
        lead.valid = false
    }
    if (!lead.first_name) {
        lead.errors.push("Missing first_name")
        lead.valid = false
    }
    if (!lead.last_name) {
        lead.errors.push("Missing last_name")
        lead.valid = false
    }

    return lead
}

export default function ImportCSVModal({ open, onClose, onSuccess, campaignId }: Props) {
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [parsedLeads, setParsedLeads] = useState<ParsedLead[]>([])
    const [missingHeaders, setMissingHeaders] = useState<string[]>([])
    const [fileName, setFileName] = useState<string | null>(null)
    const [isDragging, setIsDragging] = useState(false)

    const resetState = () => {
        setParsedLeads([])
        setMissingHeaders([])
        setFileName(null)
        setError(null)
        setIsDragging(false)
    }

    const processFile = useCallback((file: File) => {
        if (!file.name.endsWith('.csv')) {
            setError('Please upload a CSV file')
            return
        }

        setFileName(file.name)
        setError(null)
        const reader = new FileReader()

        reader.onload = (event) => {
            const text = event.target?.result as string
            const { headers, rows } = parseCSV(text)

            const missing = REQUIRED_HEADERS.filter(h => !headers.includes(h))
            setMissingHeaders(missing)

            if (missing.length > 0) {
                setParsedLeads([])
                return
            }

            const leads = rows.filter(row => row.some(cell => cell.trim())).map(row => validateLead(row, headers))
            setParsedLeads(leads)
        }

        reader.readAsText(file)
    }, [])

    const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) processFile(file)
    }, [processFile])

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
    }, [])

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) processFile(file)
    }, [processFile])

    const handleSubmit = async () => {
        const validLeads = parsedLeads.filter(l => l.valid)
        if (validLeads.length === 0) {
            setError("No valid leads to import")
            return
        }

        setLoading(true)
        setError(null)

        try {
            await post(`/campaigns/${campaignId}/leads/bulk`, {
                leads: validLeads.map(l => ({
                    email: l.email,
                    first_name: l.first_name,
                    last_name: l.last_name,
                    company: l.company || null,
                    title: l.title || null,
                    notes: l.notes || null
                }))
            })
            resetState()
            onSuccess()
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to import leads")
        } finally {
            setLoading(false)
        }
    }

    const handleClose = () => {
        resetState()
        onClose()
    }

    const validCount = parsedLeads.filter(l => l.valid).length
    const invalidCount = parsedLeads.filter(l => !l.valid).length

    return (
        <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
            <DialogContent className="w-[95vw] max-w-3xl max-h-[90vh] overflow-hidden flex flex-col p-4 sm:p-6">
                <DialogHeader>
                    <DialogTitle>Import Leads from CSV</DialogTitle>
                    <DialogDescription>
                        Upload a CSV file with lead information
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
                    {/* Requirements hint */}
                    <div className="text-sm bg-muted p-3 rounded-lg space-y-2 shrink-0">
                        <div className="flex items-start justify-between gap-3">
                            <div className="space-y-2 min-w-0">
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Required</p>
                                    <div className="flex flex-wrap gap-1">
                                        {REQUIRED_HEADERS.map(col => (
                                            <span key={col} className="px-2 py-0.5 text-xs bg-background border rounded-sm">{col}</span>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Optional</p>
                                    <div className="flex flex-wrap gap-1">
                                        {OPTIONAL_HEADERS.map(col => (
                                            <span key={col} className="px-2 py-0.5 text-xs bg-background border rounded-sm">{col}</span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={downloadTemplateCSV}
                                className="shrink-0 gap-1.5 h-8 text-xs"
                            >
                                <Download size={12} />
                                Template
                            </Button>
                        </div>
                    </div>

                    {/* File input with drag and drop */}
                    <div
                        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors shrink-0 ${isDragging
                            ? "border-primary bg-primary/5"
                            : "border-muted-foreground/25 hover:border-muted-foreground/50"
                            }`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        <input
                            type="file"
                            accept=".csv"
                            onChange={handleFileChange}
                            className="hidden"
                            id="csv-upload"
                        />
                        <label htmlFor="csv-upload" className="cursor-pointer">
                            <Upload className={`mx-auto mb-2 transition-colors ${isDragging ? "text-primary" : "text-muted-foreground"}`} size={32} />
                            <p className="text-sm text-muted-foreground">
                                {fileName ? fileName : "Drag & drop CSV file or click to upload"}
                            </p>
                        </label>
                    </div>

                    {/* Missing headers warning */}
                    {missingHeaders.length > 0 && (
                        <div className="flex items-start gap-2 text-destructive bg-destructive/10 p-3 rounded-lg shrink-0">
                            <AlertCircle size={16} className="mt-0.5" />
                            <div className="text-sm">
                                <p className="font-medium">Missing required columns:</p>
                                <p>{missingHeaders.join(", ")}</p>
                            </div>
                        </div>
                    )}

                    {/* Preview table */}
                    {parsedLeads.length > 0 && (
                        <div className="flex-1 flex flex-col min-h-[200px] border rounded-lg">
                            <div className="flex-1 overflow-auto">
                                <Table>
                                    <TableHeader className="sticky top-0 bg-background z-10 shadow-md">
                                        <TableRow>
                                            <TableHead className="w-8"></TableHead>
                                            <TableHead>Email</TableHead>
                                            <TableHead>First Name</TableHead>
                                            <TableHead>Last Name</TableHead>
                                            <TableHead>Company</TableHead>
                                            <TableHead>Title</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {/* Show invalid rows first so the user can act on them;
                                            fall back to valid rows to fill the 10-row preview. */}
                                        {[...parsedLeads]
                                            .sort((a, b) => Number(a.valid) - Number(b.valid))
                                            .slice(0, 10)
                                            .map((lead, i) => (
                                            <TableRow key={i} className={!lead.valid ? "bg-destructive/5" : ""}>
                                                <TableCell>
                                                    {lead.valid ? (
                                                        <CheckCircle2 size={14} className="text-green-600" />
                                                    ) : (
                                                        <AlertCircle size={14} className="text-destructive" />
                                                    )}
                                                </TableCell>
                                                <TableCell className={!lead.email ? "text-destructive" : ""}>
                                                    {lead.email || "—"}
                                                </TableCell>
                                                <TableCell className={!lead.first_name ? "text-destructive" : ""}>
                                                    {lead.first_name || "—"}
                                                </TableCell>
                                                <TableCell className={!lead.last_name ? "text-destructive" : ""}>
                                                    {lead.last_name || "—"}
                                                </TableCell>
                                                <TableCell>{lead.company || "—"}</TableCell>
                                                <TableCell>{lead.title || "—"}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                            {parsedLeads.length > 10 && (
                                <p className="text-xs text-muted-foreground p-2 text-center border-t bg-muted/30 shrink-0">
                                    Showing 10 of {parsedLeads.length} leads (errors first)
                                </p>
                            )}
                        </div>
                    )}

                    {/* Summary */}
                    {parsedLeads.length > 0 && (
                        <div className="flex gap-4 text-sm">
                            <span className="text-green-600">{validCount} valid</span>
                            {invalidCount > 0 && (
                                <span className="text-destructive">{invalidCount} invalid (will be skipped)</span>
                            )}
                        </div>
                    )}

                    {error && (
                        <div className="text-sm text-destructive">{error}</div>
                    )}
                </div>

                <DialogFooter>
                    <Button type="button" variant="outline" onClick={handleClose}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={loading || validCount === 0}
                    >
                        {loading ? "Importing..." : `Import ${validCount} Leads`}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}