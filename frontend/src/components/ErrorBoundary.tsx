import { Component, type ReactNode } from "react"
import ErrorPage from "@/pages/ErrorPage"

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
    state: State = { error: null }

    static getDerivedStateFromError(error: Error) {
        return { error }
    }

    render() {
        if (this.state.error) {
            return <ErrorPage title="Something Went Wrong" message={this.state.error.message} statusCode={500} />
        }
        return this.props.children
    }
}
