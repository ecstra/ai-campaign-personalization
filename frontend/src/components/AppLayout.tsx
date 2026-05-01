import { Link, useLocation } from "react-router-dom"
import { useBreadcrumbItems } from "@/contexts/BreadcrumbContext"
import { useAuth } from "@/contexts/AuthContext"
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarGroup,
    SidebarGroupContent,
    SidebarHeader,
    SidebarInset,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Send, MailPlus, LogOut, ChevronsUpDown, Moon, Sun, Plus, FileText } from "lucide-react"
import { useTheme } from "@/components/theme-provider"

export default function AppLayout({ children }: { children: React.ReactNode }) {
    const breadcrumbItems = useBreadcrumbItems()
    const location = useLocation()
    const { user, logout } = useAuth()
    const { theme, setTheme } = useTheme()

    const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)

    return (
        <SidebarProvider>
            <Sidebar variant="inset">
                <SidebarHeader>
                    <SidebarMenu>
                        <SidebarMenuItem>
                            <SidebarMenuButton size="lg" asChild>
                                <Link to="/">
                                    <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                                        <Send className="size-4" />
                                    </div>
                                    <div className="grid flex-1 text-left text-sm leading-tight">
                                        <span className="truncate font-semibold">Outreach</span>
                                        <span className="truncate text-xs text-muted-foreground">AI Mail Campaigns</span>
                                    </div>
                                </Link>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </SidebarHeader>

                <SidebarContent>
                    <SidebarGroup>
                        <SidebarGroupContent>
                            <Button asChild size="sm" className="w-full justify-start gap-2 h-9">
                                <Link to="/campaigns/new">
                                    <Plus className="size-4" />
                                    New campaign
                                </Link>
                            </Button>
                        </SidebarGroupContent>
                    </SidebarGroup>
                    <SidebarGroup>
                        <SidebarGroupContent>
                            <SidebarMenu>
                                <SidebarMenuItem>
                                    <SidebarMenuButton
                                        asChild
                                        isActive={location.pathname === "/" || (location.pathname.startsWith("/campaigns") && location.pathname !== "/campaigns/new")}
                                    >
                                        <Link to="/">
                                            <MailPlus className="size-4" />
                                            <span>Campaigns</span>
                                        </Link>
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                                <SidebarMenuItem>
                                    <SidebarMenuButton
                                        asChild
                                        isActive={location.pathname.startsWith("/documents")}
                                    >
                                        <Link to="/documents">
                                            <FileText className="size-4" />
                                            <span>Documents</span>
                                        </Link>
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                            </SidebarMenu>
                        </SidebarGroupContent>
                    </SidebarGroup>
                </SidebarContent>

                <SidebarFooter>
                    <SidebarMenu>
                        <SidebarMenuItem>
                            <SidebarMenuButton
                                size="lg"
                                onClick={() => setTheme(isDark ? "light" : "dark")}
                                className="cursor-pointer"
                            >
                                {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
                                <span>{isDark ? "Light Mode" : "Dark Mode"}</span>
                            </SidebarMenuButton>
                        </SidebarMenuItem>
                        <SidebarMenuItem>
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <SidebarMenuButton size="lg" className="cursor-pointer">
                                        <Avatar className="size-8">
                                            {user?.picture_url && (
                                                <AvatarImage src={user.picture_url} referrerPolicy="no-referrer" />
                                            )}
                                            <AvatarFallback className="text-xs">
                                                {user?.name?.charAt(0)?.toUpperCase() || "?"}
                                            </AvatarFallback>
                                        </Avatar>
                                        <div className="grid flex-1 text-left text-sm leading-tight">
                                            <span className="truncate font-medium">{user?.name}</span>
                                            <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
                                        </div>
                                        <ChevronsUpDown className="ml-auto size-4" />
                                    </SidebarMenuButton>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent side="top" align="start" className="w-[--radix-dropdown-menu-trigger-width]">
                                    <div className="px-2 py-1.5">
                                        <p className="text-sm font-medium">{user?.name}</p>
                                        <p className="text-xs text-muted-foreground">{user?.email}</p>
                                    </div>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem onClick={logout} className="text-destructive">
                                        <LogOut className="mr-2 size-4" />
                                        Sign out
                                    </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </SidebarFooter>
            </Sidebar>

            <SidebarInset>
                {/* Top bar with trigger + breadcrumbs */}
                <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
                    <SidebarTrigger className="-ml-1" />
                    {breadcrumbItems.length > 0 && (
                        <>
                            <Separator orientation="vertical" className="mr-2 !h-4" />
                            <Breadcrumb>
                                <BreadcrumbList>
                                    {breadcrumbItems.map((item, index) => {
                                        const isLast = index === breadcrumbItems.length - 1
                                        return (
                                            <span key={item.label} className="flex items-center gap-1.5">
                                                {index > 0 && <BreadcrumbSeparator />}
                                                <BreadcrumbItem>
                                                    {isLast || !item.href ? (
                                                        <BreadcrumbPage>{item.label}</BreadcrumbPage>
                                                    ) : (
                                                        <BreadcrumbLink asChild>
                                                            <Link to={item.href}>{item.label}</Link>
                                                        </BreadcrumbLink>
                                                    )}
                                                </BreadcrumbItem>
                                            </span>
                                        )
                                    })}
                                </BreadcrumbList>
                            </Breadcrumb>
                        </>
                    )}
                </header>

                {/* Page content */}
                <main className="flex-1 overflow-y-auto">
                    {children}
                </main>
            </SidebarInset>
        </SidebarProvider>
    )
}
