import { useState, useEffect, useRef } from "react"
import { Link } from "react-router-dom"
import { get, del, API_URL } from "@/lib/api"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { FileText, Upload, Trash2, ArrowUpRight, AlertCircle } from "lucide-react"

type DocumentSummary = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string
    updated_at: string
}

const ACCEPT = ".pdf,.docx,.pptx,.txt,.md"
const MAX_MB = 10

function formatSize(bytes: number | null): string {
    if (!bytes) return "—"
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
        month: "short", day: "numeric", year: "numeric",
        hour: "numeric", minute: "2-digit",
    })
}

export default function Documents() {
    useBreadcrumbs([{ label: "Documents" }])

    const [docs, setDocs] = useState<DocumentSummary[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [isDragging, setIsDragging] = useState(false)

    const fileInputRef = useRef<HTMLInputElement>(null)

    const fetchDocs = async () => {
        try {
            setLoading(true)
            const data = await get<DocumentSummary[]>("/documents")
            setDocs(data)
            setError(null)
        } catch (err) {
            setError(parseApiError(err))
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchDocs() }, [])

    const uploadFile = (file: File) => {
        const ext = "." + (file.name.split(".").pop() || "").toLowerCase()
        if (!ACCEPT.includes(ext)) {
            toast.error(`Unsupported file type. Allowed: ${ACCEPT}.`)
            return
        }
        if (file.size > MAX_MB * 1024 * 1024) {
            toast.error(`File too large. Max ${MAX_MB} MB.`)
            return
        }

        // Kick off the upload and immediately hand it to sonner's toast.promise.
        // sonner's Toaster is mounted at the app root, so the loading +
        // success/error notification follows the user across route changes —
        // they can navigate away and still see the final toast when it lands.
        const uploadPromise = (async () => {
            const form = new FormData()
            form.append("file", file)
            const resp = await fetch(`${API_URL}/documents`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${localStorage.getItem("auth_token") || ""}`,
                },
                body: form,
            })
            if (!resp.ok) {
                let detail = `Upload failed (${resp.status})`
                try {
                    const body = await resp.json()
                    if (body?.detail) detail = body.detail
                } catch { /* ignore */ }
                throw new Error(detail)
            }
            return await resp.json()
        })()

        toast.promise(uploadPromise, {
            loading: `Parsing ${file.name}...`,
            success: "Document processed",
            error: (err) => err instanceof Error ? err.message : "Upload failed",
        })

        // If the user stays on this page, refresh the library when it lands.
        // If they navigate away, the refresh is a no-op on the unmounted
        // component and the library will fetch fresh on next mount.
        uploadPromise.then(fetchDocs).catch(() => { /* toast already handled */ })
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) uploadFile(file)
    }

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) uploadFile(file)
        if (fileInputRef.current) fileInputRef.current.value = ""
    }

    const handleDelete = async (doc: DocumentSummary, e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        if (!confirm(`Delete "${doc.name}"? Any campaign using it will lose the attachment.`)) return
        try {
            await del(`/documents/${doc.id}`)
            toast.success("Document deleted")
            await fetchDocs()
        } catch (err) {
            toast.error(parseApiError(err))
        }
    }

    // ── Render ──────────────────────────────────────────────────────────

    return (
        <div className="p-6">
            <div className="max-w-5xl mx-auto space-y-5">
                <div>
                    <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
                    <p className="text-muted-foreground text-[13px] mt-1">
                        Upload briefs, decks, and datasheets once. Attach them to any campaign to personalize emails with real product facts.
                    </p>
                </div>

                {/* Upload area */}
                <label
                    htmlFor="doc-upload-input"
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    className={`block border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer ${
                        isDragging
                            ? "border-primary bg-primary/5"
                            : "border-muted-foreground/25 hover:border-muted-foreground/50"
                    }`}
                >
                    <Upload size={22} className={`mx-auto mb-2 ${isDragging ? "text-primary" : "text-muted-foreground"}`} />
                    <p className="text-[13px] text-muted-foreground">Drag &amp; drop or click to upload</p>
                    <p className="text-[11px] text-muted-foreground/70 mt-1">
                        PDF, DOCX, PPTX, TXT, MD · Max {MAX_MB} MB · Parsing takes ~30-60s
                    </p>
                </label>
                <input
                    ref={fileInputRef}
                    type="file"
                    id="doc-upload-input"
                    accept={ACCEPT}
                    className="hidden"
                    onChange={handleInputChange}
                />

                {error && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {/* Library list */}
                <div>
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-2">
                        Your library ({docs.length})
                    </p>

                    {loading ? (
                        <div className="space-y-2">
                            {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
                        </div>
                    ) : docs.length === 0 ? (
                        <div className="text-center py-12 border border-dashed rounded-xl">
                            <FileText size={22} className="mx-auto mb-2 text-muted-foreground/60" />
                            <p className="text-[13px] text-muted-foreground">No documents yet</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {docs.map(doc => (
                                <Link
                                    key={doc.id}
                                    to={`/documents/${doc.id}`}
                                    className="group bg-card border rounded-xl p-4 flex items-center gap-3 transition-colors hover:bg-accent/30 hover:border-primary/30"
                                >
                                    <div className="h-9 w-9 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                                        <FileText size={16} className="text-primary" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-[13px] font-medium truncate flex items-center gap-1.5 group-hover:text-primary transition-colors">
                                            {doc.name}
                                            <ArrowUpRight size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                                        </p>
                                        <p className="text-[11px] text-muted-foreground">
                                            {formatSize(doc.size_bytes)} · Uploaded {formatDate(doc.created_at)}
                                        </p>
                                    </div>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={(e) => handleDelete(doc, e)}
                                        className="text-muted-foreground hover:text-destructive"
                                        aria-label={`Delete ${doc.name}`}
                                    >
                                        <Trash2 size={13} />
                                    </Button>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>

            </div>
        </div>
    )
}
