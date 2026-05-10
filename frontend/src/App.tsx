import { createBrowserRouter, RouterProvider, Outlet } from "react-router-dom"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/contexts/AuthContext"
import { BreadcrumbProvider } from "@/contexts/BreadcrumbContext"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import ErrorBoundary from "@/components/ErrorBoundary"
import ProtectedRoute from "@/components/ProtectedRoute"
import AppLayout from "@/components/AppLayout"

import Login from "./pages/Login"
import AuthCallback from "./pages/AuthCallback"
import Campaigns from "./pages/Campaigns"
import CampaignCreate from "./pages/CampaignCreate"
import CampaignDetail from "./pages/CampaignDetail"
import LeadDetail from "./pages/LeadDetail"
import Documents from "./pages/Documents"
import DocumentDetail from "./pages/DocumentDetail"
import NotFound from "./pages/NotFound"

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <AppLayout>
        <Outlet />
      </AppLayout>
    </ProtectedRoute>
  )
}

const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  { path: "/auth/callback", element: <AuthCallback /> },
  {
    element: <ProtectedLayout />,
    children: [
      { path: "/", element: <Campaigns /> },
      { path: "/campaigns/new", element: <CampaignCreate /> },
      { path: "/campaigns/:id", element: <CampaignDetail /> },
      { path: "/campaigns/:campaignId/leads/:leadId", element: <LeadDetail /> },
      { path: "/documents", element: <Documents /> },
      { path: "/documents/:id", element: <DocumentDetail /> }
    ]
  },
  { path: "*", element: <NotFound /> }
])

export default function App() {
  return (
    <ThemeProvider defaultTheme="light" storageKey="vite-ui-theme">
      <ErrorBoundary>
        <AuthProvider>
          <BreadcrumbProvider>
            <TooltipProvider>
              <RouterProvider router={router} />
              <Toaster />
            </TooltipProvider>
          </BreadcrumbProvider>
        </AuthProvider>
      </ErrorBoundary>
    </ThemeProvider>
  )
}
