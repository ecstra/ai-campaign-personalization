import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { get, del } from "@/lib/api"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { FileText, Trash2, Copy, Check } from "lucide-react"
import ErrorPage from "./ErrorPage"

type DocumentDetail = {
    id: string
    name: string
    brief: string
    word_count: number
    size_bytes: number | null
    extension: string | null
    created_at: string
    updated_at: string
}

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

export default function DocumentDetail() {
    const { id } = useParams<{ id: string }>()
    const navigate = useNavigate()

    const [doc, setDoc] = useState<DocumentDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [copied, setCopied] = useState(false)

    useBreadcrumbs(
        doc
            ? [{ label: "Documents", href: "/documents" }, { label: doc.name }]
            : [{ label: "Documents", href: "/documents" }]
    )

    useEffect(() => {
        if (!id) return
        let cancelled = false
            ; (async () => {
                try {
                    setLoading(true)
                    const data = await get<DocumentDetail>(`/documents/${id}`)
                    if (!cancelled) {
                        setDoc(data)
                        setError(null)
                    }
                } catch (err) {
                    if (!cancelled) setError(parseApiError(err))
                } finally {
                    if (!cancelled) setLoading(false)
                }
            })()
        return () => { cancelled = true }
    }, [id])

    const handleCopy = async () => {
        if (!doc) return
        try {
            await navigator.clipboard.writeText(doc.brief)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
        } catch {
            toast.error("Copy failed")
        }
    }

    const handleDelete = async () => {
        if (!doc) return
        if (!confirm(`Delete "${doc.name}"? Any campaign using it will lose the attachment.`)) return
        try {
            await del(`/documents/${doc.id}`)
            toast.success("Document deleted")
            navigate("/documents")
        } catch (err) {
            toast.error(parseApiError(err))
        }
    }

    if (error) {
        const is404 = error.toLowerCase().includes("not found") || error.toLowerCase().includes("404")
        return (
            <ErrorPage
                title={is404 ? "Document Not Found" : "Something Went Wrong"}
                message={error}
                statusCode={is404 ? 404 : 500}
            />
        )
    }

    return (
        <div className="p-6">
            <div className="max-w-3xl mx-auto space-y-5">
                {/* Header */}
                {loading ? (
                    <div className="space-y-2">
                        <Skeleton className="h-8 w-64" />
                        <Skeleton className="h-4 w-48" />
                    </div>
                ) : doc ? (
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3 min-w-0">
                            <div className="h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center shrink-0 mt-1">
                                <FileText size={18} className="text-primary" />
                            </div>
                            <div className="min-w-0">
                                <h1 className="text-2xl font-semibold tracking-tight truncate">{doc.name}</h1>
                                <p className="text-muted-foreground text-[13px] mt-1">
                                    {formatSize(doc.size_bytes)} · {doc.word_count} words · Uploaded {formatDate(doc.created_at)}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                            <Button size="sm" variant="outline" onClick={handleCopy} className="gap-1.5">
                                {copied ? <Check size={13} /> : <Copy size={13} />}
                                {copied ? "Copied" : "Copy"}
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={handleDelete}
                                className="gap-1.5 text-destructive hover:text-destructive"
                            >
                                <Trash2 size={13} />
                                Delete
                            </Button>
                        </div>
                    </div>
                ) : null}

                {/* Context note */}
                {doc && (
                    <p className="text-[12px] text-muted-foreground leading-relaxed bg-muted/30 border rounded-md px-3 py-2">
                        This is the brief the LLM consults when personalizing every email for campaigns that attach this document. The original file was discarded after parsing — to update the brief, re-upload the source document.
                    </p>
                )}

                {/* Brief */}
                {loading ? (
                    <div className="space-y-2">
                        {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-4 w-full" />)}
                    </div>
                ) : doc ? (
                    <article
                        className="bg-card border rounded-xl p-6 text-[13px] leading-relaxed whitespace-pre-wrap font-mono"
                    >
                        {doc.brief}
                    </article>
                ) : null}
            </div>
        </div>
    )
}
