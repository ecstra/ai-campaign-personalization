import { createContext, useContext, useState, useEffect } from "react"

export type BreadcrumbItem = {
    label: string
    href?: string
}

type BreadcrumbContextType = {
    items: BreadcrumbItem[]
    setItems: (items: BreadcrumbItem[]) => void
}

const BreadcrumbContext = createContext<BreadcrumbContextType | undefined>(undefined)

export function BreadcrumbProvider({ children }: { children: React.ReactNode }) {
    const [items, setItems] = useState<BreadcrumbItem[]>([])

    return (
        <BreadcrumbContext.Provider value={{ items, setItems }}>
            {children}
        </BreadcrumbContext.Provider>
    )
}

/**
 * Hook for pages to set their breadcrumb trail.
 * Call with an array of items; the layout header renders them.
 */
export function useBreadcrumbs(items: BreadcrumbItem[]): void {
    const context = useContext(BreadcrumbContext)
    if (!context) {
        throw new Error("useBreadcrumbs must be used within a BreadcrumbProvider")
    }

    const { setItems } = context

    const serialized = JSON.stringify(items)
    useEffect(() => {
        setItems(JSON.parse(serialized))
        return () => setItems([])
    }, [serialized, setItems])
}

export function useBreadcrumbItems(): BreadcrumbItem[] {
    const context = useContext(BreadcrumbContext)
    if (!context) {
        throw new Error("useBreadcrumbItems must be used within a BreadcrumbProvider")
    }
    return context.items
}
