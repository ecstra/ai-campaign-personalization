import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { get, del } from "@/lib/api"
import { parseApiError } from "@/lib/errors"
import { formatSize, formatDate } from "@/lib/utils"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import ErrorPage from "./ErrorPage"
import ConfirmDialog from "@/components/ConfirmDialog"

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

export default function DocumentDetail() {
    const { id } = useParams<{ id: string }>()
    const navigate = useNavigate()

    const [doc, setDoc] = useState<DocumentDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [copied, setCopied] = useState(false)
    const [showDelete, setShowDelete] = useState(false)
    const [deleting, setDeleting] = useState(false)

    useBreadcrumbs(
        doc
            ? [{ label: "Documents", href: "/documents" }, { label: doc.name }]
            : [{ label: "Documents", href: "/documents" }, { label: "Loading..." }]
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

    const handleDelete = () => {
        if (!doc) return
        setShowDelete(true)
    }

    const confirmDelete = async () => {
        if (!doc) return
        setDeleting(true)
        try {
            await del(`/documents/${doc.id}`)
            toast.success("Document deleted")
            navigate("/documents")
        } catch (err) {
            toast.error(parseApiError(err))
        } finally {
            setDeleting(false)
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
                        <Skeleton className="h-8 w-64 rounded-full" />
                        <Skeleton className="h-4 w-48 rounded-full" />
                    </div>
                ) : doc ? (
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-4 min-w-0">
                            <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-1">
                                <span className="material-symbols-rounded text-[24px] text-primary">description</span>
                            </div>
                            <div className="min-w-0">
                                <h1 className="text-[28px] font-bold tracking-tight truncate">{doc.name}</h1>
                                <p className="text-muted-foreground text-[14px] mt-1">
                                    {formatSize(doc.size_bytes)} · {doc.word_count} words · Uploaded {formatDate(doc.created_at)}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                            <Button variant="outline" onClick={handleCopy} className="gap-2 rounded-full h-10 px-5  text-[14px] hover:bg-muted/80">
                                <span className="material-symbols-rounded text-[18px]">{copied ? "check" : "content_copy"}</span>
                                {copied ? "Copied" : "Copy"}
                            </Button>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={handleDelete}
                                className="rounded-full h-10 w-10 text-muted-foreground hover:text-destructive-hover-foreground hover:bg-destructive-hover"
                            >
                                <span className="material-symbols-rounded text-[20px]">delete</span>
                            </Button>
                        </div>
                    </div>
                ) : null}

                {/* Context note */}
                {doc && (
                    <p className="text-[13px] text-muted-foreground leading-relaxed bg-muted/30 border rounded-lg px-5 py-4">
                        This is the brief the LLM consults when personalizing every email for campaigns that attach this document. The original file was discarded after parsing — to update the brief, re-upload the source document.
                    </p>
                )}

                {/* Brief */}
                {loading ? (
                    <div className="space-y-2">
                        {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-4 w-full rounded-full" />)}
                    </div>
                ) : doc ? (
                    <article
                        className="bg-card border rounded-lg p-8 text-[14px] leading-relaxed whitespace-pre-wrap font-mono "
                    >
                        {doc.brief}
                    </article>
                ) : null}
            </div>

            <ConfirmDialog
                open={showDelete}
                onClose={() => !deleting && setShowDelete(false)}
                onConfirm={confirmDelete}
                title="Delete Document"
                description={`Delete "${doc?.name}"? Any campaign using it will lose the attachment.`}
                loading={deleting}
            />
        </div>
    )
}
