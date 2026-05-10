import { useState, useCallback } from "react"
import { toast } from "sonner"
import { parseApiError } from "@/lib/errors"

interface AsyncActionOptions<TRet> {
    onSuccess?: (result: TRet) => void
    onError?: (error: string) => void
    successMessage?: string | ((result: TRet) => string)
}

export function useAsyncAction<TArgs extends unknown[], TRet>(
    action: (...args: TArgs) => Promise<TRet>,
    options?: AsyncActionOptions<TRet>
) {
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const execute = useCallback(async (...args: TArgs) => {
        setIsLoading(true)
        setError(null)
        try {
            const result = await action(...args)
            if (options?.successMessage) {
                const msg = typeof options.successMessage === "function"
                    ? options.successMessage(result)
                    : options.successMessage
                toast.success(msg)
            }
            options?.onSuccess?.(result)
            return result
        } catch (err) {
            const msg = parseApiError(err)
            setError(msg)
            toast.error(msg)
            options?.onError?.(msg)
        } finally {
            setIsLoading(false)
        }
    }, [action, options])

    return { execute, isLoading, error }
}
