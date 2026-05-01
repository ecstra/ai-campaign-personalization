import { useState, useEffect } from "react"
import { Link } from "react-router-dom"
import { get, put } from "@/lib/api"
import { parseApiError } from "@/lib/errors"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { FileText, Plus, X, Check, AlertCircle, ArrowUpRight } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"

const MAX_PER_CAMPAIGN = 2

type AttachedDoc = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string | null
    updated_at: string | null
}

type LibraryDoc = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string
}

type Props = {
    campaignId: string
    canEdit: boolean
    attached: AttachedDoc[]
    onChange: () => void
}

export default function AttachedDocumentsCard({
    campaignId, canEdit, attached, onChange,
}: Props) {
    const [pickerOpen, setPickerOpen] = useState(false)
    const [library, setLibrary] = useState<LibraryDoc[]>([])
    const [loadingLibrary, setLoadingLibrary] = useState(false)
    const [selected, setSelected] = useState<Set<string>>(new Set())
    const [saving, setSaving] = useState(false)

    // Keep the picker's selection in sync with what's currently attached
    useEffect(() => {
        setSelected(new Set(attached.map(d => d.id)))
    }, [attached, pickerOpen])

    const openPicker = async () => {
        setPickerOpen(true)
        setLoadingLibrary(true)
        try {
            const all = await get<LibraryDoc[]>("/documents")
            setLibrary(all)
        } catch (err) {
            toast.error(parseApiError(err))
        } finally {
            setLoadingLibrary(false)
        }
    }

    const toggleSelect = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev)
            if (next.has(id)) next.delete(id)
            else {
                if (next.size >= MAX_PER_CAMPAIGN) {
                    toast.error(`You can attach at most ${MAX_PER_CAMPAIGN} documents per campaign.`)
                    return prev
                }
                next.add(id)
            }
            return next
        })
    }

    const saveSelection = async () => {
        setSaving(true)
        try {
            await put(`/campaigns/${campaignId}/documents`, {
                document_ids: Array.from(selected),
            })
            toast.success("Documents updated")
            setPickerOpen(false)
            onChange()
        } catch (err) {
            toast.error(parseApiError(err))
        } finally {
            setSaving(false)
        }
    }

    const detachOne = async (docId: string) => {
        try {
            await put(`/campaigns/${campaignId}/documents`, {
                document_ids: attached.filter(d => d.id !== docId).map(d => d.id),
            })
            toast.success("Document detached")
            onChange()
        } catch (err) {
            toast.error(parseApiError(err))
        }
    }

    const remainingSlots = MAX_PER_CAMPAIGN - attached.length

    return (
        <div className="bg-card border rounded-xl p-5 space-y-3">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <h2 className="text-[13px] font-semibold tracking-tight">Attached documents</h2>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                        Up to {MAX_PER_CAMPAIGN} documents from your library. The LLM uses their briefs when personalizing every email for this campaign.
                    </p>
                </div>
                {canEdit && (
                    <Button size="sm" variant="outline" onClick={openPicker} className="gap-1.5 shrink-0">
                        <Plus size={13} />
                        Manage
                    </Button>
                )}
            </div>

            {attached.length === 0 ? (
                <div className="text-center py-5 border border-dashed rounded-lg">
                    <FileText size={18} className="mx-auto mb-1.5 text-muted-foreground/60" />
                    <p className="text-[12px] text-muted-foreground">No documents attached</p>
                    <p className="text-[11px] text-muted-foreground/70 mt-0.5">
                        Upload in <Link to="/documents" className="underline hover:text-foreground">Documents</Link>, then attach from here.
                    </p>
                </div>
            ) : (
                <div className="space-y-2">
                    {attached.map(doc => (
                        <div key={doc.id} className="group flex items-center gap-3 p-2.5 border rounded-lg bg-muted/20 hover:bg-muted/40 transition-colors">
                            <FileText size={14} className="text-primary shrink-0" />
                            <Link
                                to={`/documents/${doc.id}`}
                                className="text-[13px] font-medium truncate flex-1 hover:text-primary transition-colors inline-flex items-center gap-1.5"
                            >
                                {doc.name}
                                <ArrowUpRight size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                            </Link>
                            {canEdit && (
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => detachOne(doc.id)}
                                    className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                                    aria-label={`Detach ${doc.name}`}
                                >
                                    <X size={13} />
                                </Button>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Picker dialog */}
            <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
                <DialogContent className="max-w-lg max-h-[80vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                        <DialogTitle>Attach documents</DialogTitle>
                        <DialogDescription>
                            Pick up to {MAX_PER_CAMPAIGN} from your library.
                            {remainingSlots < MAX_PER_CAMPAIGN && (
                                <> Currently selected: <span className="font-medium">{selected.size}/{MAX_PER_CAMPAIGN}</span>.</>
                            )}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="flex-1 overflow-y-auto -mx-6 px-6">
                        {loadingLibrary ? (
                            <p className="text-[13px] text-muted-foreground py-4">Loading library...</p>
                        ) : library.length === 0 ? (
                            <Alert>
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription>
                                    Your library is empty. <Link to="/documents" className="underline">Upload your first document</Link>.
                                </AlertDescription>
                            </Alert>
                        ) : (
                            <div className="space-y-1.5">
                                {library.map(doc => {
                                    const isSelected = selected.has(doc.id)
                                    return (
                                        <button
                                            key={doc.id}
                                            type="button"
                                            onClick={() => toggleSelect(doc.id)}
                                            className={`w-full flex items-center gap-3 p-3 border rounded-lg text-left transition-colors ${
                                                isSelected
                                                    ? "border-primary bg-primary/5"
                                                    : "hover:bg-muted/40"
                                            }`}
                                        >
                                            <FileText size={14} className={isSelected ? "text-primary" : "text-muted-foreground"} />
                                            <p className="text-[13px] font-medium truncate flex-1">{doc.name}</p>
                                            {isSelected && <Check size={14} className="text-primary shrink-0" />}
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </div>

                    <div className="flex justify-end gap-2 pt-2 border-t -mx-6 px-6 mt-2">
                        <Button variant="outline" onClick={() => setPickerOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={saveSelection} disabled={saving}>
                            {saving ? "Saving..." : "Save"}
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    )
}
