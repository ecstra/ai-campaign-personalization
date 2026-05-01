/**
 * Parse API error responses into human-readable messages.
 * Handles the JSON detail pattern from FastAPI error responses.
 */
export function parseApiError(err: unknown): string {
    if (!(err instanceof Error)) {
        return "An unexpected error occurred"
    }

    try {
        const errorObj = JSON.parse(err.message)
        if (errorObj.detail) {
            return typeof errorObj.detail === "string"
                ? errorObj.detail
                : JSON.stringify(errorObj.detail)
        }
    } catch {
        // Not JSON, use raw message
    }

    return err.message || "An unexpected error occurred"
}
