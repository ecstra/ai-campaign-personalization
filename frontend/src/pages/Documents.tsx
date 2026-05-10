import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { Link, useBlocker } from "react-router-dom"
import { get, del, API_URL } from "@/lib/api"
import { formatSize } from "@/lib/utils"
import { parseApiError } from "@/lib/errors"
import { useBreadcrumbs } from "@/contexts/BreadcrumbContext"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { FileText, Upload, Trash2, ArrowUpRight, AlertCircle, CheckCircle2, XCircle, Loader2, Search } from "lucide-react"

type DocumentSummary = {
    id: string
    name: string
    size_bytes: number | null
    extension: string | null
    created_at: string
    updated_at: string
}

type UploadTaskStatus = {
    taskId: string
    task_id?: string
    status: "processing" | "parsing" | "summarizing" | "saving" | "success" | "error"
    progress: number
    filename?: string
    error?: string
    document?: DocumentSummary
}

type UploadTask = {
    id: string 
    file?: File // Optional since reloaded tasks don't have the File object
    name: string // Display name
    progress: number
    status: "uploading" | "processing" | "parsing" | "summarizing" | "saving" | "success" | "error"
    error?: string
}

const ACCEPT = ".pdf,.docx,.pptx,.txt,.md"
const MAX_MB = 30

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
    const [uploads, setUploads] = useState<UploadTask[]>([])
    const [searchQuery, setSearchQuery] = useState("")

    const fileInputRef = useRef<HTMLInputElement>(null)
    const pollingIntervals = useRef<Record<string, ReturnType<typeof setInterval>>>({})

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

    const pollTaskStatus = useCallback((localId: string, taskId: string) => {
        if (pollingIntervals.current[localId]) return // Already polling

        const interval = setInterval(async () => {
            try {
                const status = await get<UploadTaskStatus>(`/documents/status/${taskId}`)
                setUploads(prev => prev.map(u => {
                    if (u.id === localId) {
                        return {
                            ...u,
                            progress: status.progress,
                            status: status.status,
                            error: status.error,
                            name: status.filename || u.name
                        }
                    }
                    return u
                }))

                if (status.status === "success") {
                    clearInterval(interval)
                    delete pollingIntervals.current[localId]
                    fetchDocs()
                    setTimeout(() => {
                        setUploads(prev => prev.filter(u => u.id !== localId))
                    }, 3000)
                } else if (status.status === "error") {
                    clearInterval(interval)
                    delete pollingIntervals.current[localId]
                }
            } catch {
                clearInterval(interval)
                delete pollingIntervals.current[localId]
                setUploads(prev => prev.map(u => 
                    u.id === localId ? { ...u, status: "error", error: "Failed to fetch status" } : u
                ))
            }
        }, 1000)

        pollingIntervals.current[localId] = interval
    }, [])

    const fetchActiveTasks = useCallback(async () => {
        try {
            const activeTasks = await get<UploadTaskStatus[]>("/documents/tasks")
            activeTasks.forEach(task => {
                const taskId = task.taskId || task.task_id
                if (!taskId) return

                setUploads(prev => {
                    if (prev.find(u => u.id === taskId)) return prev
                    return [...prev, {
                        id: taskId,
                        name: task.filename || "Unknown document",
                        progress: task.progress,
                        status: task.status,
                        error: task.error
                    }]
                })
                pollTaskStatus(taskId, taskId)
            })
        } catch { /* ignore silenty */ }
    }, [pollTaskStatus])

    useEffect(() => { 
        fetchDocs()
        fetchActiveTasks()
        return () => {
            // eslint-disable-next-line react-hooks/exhaustive-deps
            Object.values(pollingIntervals.current).forEach(clearInterval)
        }
    }, [fetchActiveTasks])

    const hasUploadingFiles = uploads.some(u => u.status === "uploading")

    // Block SPA navigation ONLY if there are active network uploads
    const blocker = useBlocker(({ currentLocation, nextLocation }) => {
        if (!hasUploadingFiles) return false
        return currentLocation.pathname !== nextLocation.pathname
    })

    useEffect(() => {
        if (blocker.state === "blocked") {
            const leave = window.confirm("A file is still uploading. If you leave now, the upload will be cancelled. Continue?")
            if (leave) {
                blocker.proceed()
            } else {
                blocker.reset()
            }
        }
    }, [blocker])

    // Prevent browser refresh/close ONLY if uploads are active
    useEffect(() => {
        const handleBeforeUnload = (e: BeforeUnloadEvent) => {
            if (hasUploadingFiles) {
                e.preventDefault()
                e.returnValue = "A file is still uploading."
                return e.returnValue
            }
        }
        window.addEventListener("beforeunload", handleBeforeUnload)
        return () => window.removeEventListener("beforeunload", handleBeforeUnload)
    }, [hasUploadingFiles])

    const startUpload = (file: File) => {
        const ext = "." + (file.name.split(".").pop() || "").toLowerCase()
        if (!ACCEPT.includes(ext)) {
            toast.error(`Unsupported file: ${file.name}`)
            return
        }
        if (file.size > MAX_MB * 1024 * 1024) {
            toast.error(`File too large: ${file.name} (Max ${MAX_MB} MB)`)
            return
        }

        const localId = Math.random().toString(36).substring(7)
        
        setUploads(prev => [...prev, {
            id: localId,
            file,
            name: file.name,
            progress: 0,
            status: "uploading"
        }])

        const xhr = new XMLHttpRequest()
        xhr.open("POST", `${API_URL}/documents`)
        xhr.setRequestHeader("Authorization", `Bearer ${localStorage.getItem("auth_token") || ""}`)

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 50)
                setUploads(prev => prev.map(u => 
                    u.id === localId && u.status === "uploading" ? { ...u, progress: percent } : u
                ))
            }
        }

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const resp = JSON.parse(xhr.responseText)
                    const backendTaskId = resp.taskId || resp.task_id
                    if (!backendTaskId) throw new Error("No task ID")

                    setUploads(prev => prev.map(u => 
                        u.id === localId ? { ...u, id: backendTaskId, status: "processing", progress: 50 } : u
                    ))
                    pollTaskStatus(backendTaskId, backendTaskId)
                } catch {
                    setUploads(prev => prev.map(u => 
                        u.id === localId ? { ...u, status: "error", error: "Invalid server response" } : u
                    ))
                }
            } else {
                let errorMsg = `Upload failed (${xhr.status})`
                try {
                    const resp = JSON.parse(xhr.responseText)
                    if (resp.detail) errorMsg = resp.detail
                } catch { /* ignore */ }
                setUploads(prev => prev.map(u => 
                    u.id === localId ? { ...u, progress: 100, status: "error", error: errorMsg } : u
                ))
            }
        }

        xhr.onerror = () => {
            setUploads(prev => prev.map(u => 
                u.id === localId ? { ...u, progress: 100, status: "error", error: "Network error" } : u
            ))
        }

        const form = new FormData()
        form.append("file", file)
        xhr.send(form)
    }

    const handleFiles = (files: FileList | null) => {
        if (!files) return
        Array.from(files).forEach(startUpload)
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        handleFiles(e.dataTransfer.files)
    }

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        handleFiles(e.target.files)
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

    const removeTask = (taskId: string) => {
        setUploads(prev => prev.filter(u => u.id !== taskId))
        if (pollingIntervals.current[taskId]) {
            clearInterval(pollingIntervals.current[taskId])
            delete pollingIntervals.current[taskId]
        }
    }

    const filteredDocs = useMemo(() => {
        if (!searchQuery.trim()) return docs
        const query = searchQuery.toLowerCase()
        return docs.filter(d => d.name.toLowerCase().includes(query))
    }, [docs, searchQuery])

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
                        PDF, DOCX, PPTX, TXT, MD · Max {MAX_MB} MB
                    </p>
                </label>
                <input
                    ref={fileInputRef}
                    type="file"
                    id="doc-upload-input"
                    accept={ACCEPT}
                    multiple
                    className="hidden"
                    onChange={handleInputChange}
                />

                {error && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {/* Active Uploads */}
                {uploads.length > 0 && (
                    <div className="space-y-3">
                        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-2">
                            Uploading & Processing ({uploads.length})
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {uploads.map(task => (
                                <div key={task.id} className="bg-card border rounded-xl p-4 space-y-3 shadow-sm relative overflow-hidden">
                                    <div className="flex items-start justify-between gap-3 relative z-10">
                                        <div className="flex items-center gap-3 min-w-0">
                                            <div className={`h-8 w-8 rounded-md flex items-center justify-center shrink-0 ${
                                                task.status === "success" ? "bg-emerald-500/10 text-emerald-600" :
                                                task.status === "error" ? "bg-red-500/10 text-red-600" :
                                                "bg-primary/10 text-primary"
                                            }`}>
                                                {task.status === "success" ? <CheckCircle2 size={16} /> :
                                                 task.status === "error" ? <XCircle size={16} /> :
                                                 <Loader2 size={16} className="animate-spin" />}
                                            </div>
                                            <div className="min-w-0">
                                                <p className="text-[13px] font-medium truncate">{task.name}</p>
                                                <p className={`text-[11px] ${task.status === "error" ? "text-red-500" : "text-muted-foreground"}`}>
                                                    {task.status === "uploading" ? `Uploading... ${task.progress}%` :
                                                     task.status === "parsing" ? `Parsing via LLM... ${task.progress}%` :
                                                     task.status === "summarizing" ? `Summarizing... ${task.progress}%` :
                                                     task.status === "saving" ? `Saving to DB... ${task.progress}%` :
                                                     task.status === "processing" ? `Processing... ${task.progress}%` :
                                                     task.status === "success" ? "Completed" :
                                                     task.error}
                                                </p>
                                            </div>
                                        </div>
                                        {(task.status === "success" || task.status === "error") && (
                                            <Button variant="ghost" size="icon-sm" onClick={() => removeTask(task.id)} className="h-6 w-6 text-muted-foreground hover:bg-muted">
                                                <XCircle size={14} />
                                            </Button>
                                        )}
                                    </div>
                                    <Progress 
                                        value={task.progress} 
                                        className="h-1.5" 
                                        indicatorClassName={
                                            task.status === "success" ? "bg-emerald-500" :
                                            task.status === "error" ? "bg-red-500" :
                                            "bg-primary transition-all duration-500 ease-out"
                                        }
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Library list */}
                <div>
                    <div className="flex items-center justify-between mb-3 mt-2">
                        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                            Your library ({filteredDocs.length})
                        </p>
                        <div className="relative w-64">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
                            <Input 
                                placeholder="Search documents..." 
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="pl-8 h-8 text-[13px]" 
                            />
                        </div>
                    </div>

                    {loading ? (
                        <div className="space-y-2">
                            {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
                        </div>
                    ) : filteredDocs.length === 0 ? (
                        <div className="text-center py-12 border border-dashed rounded-xl">
                            <FileText size={22} className="mx-auto mb-2 text-muted-foreground/60" />
                            <p className="text-[13px] text-muted-foreground">
                                {docs.length === 0 ? "No documents yet" : "No documents match your search"}
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {filteredDocs.map(doc => (
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
