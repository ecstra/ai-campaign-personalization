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
import { Separator } from "@/components/ui/separator"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/components/theme-provider"
import { Skeleton } from "@/components/ui/skeleton"

export default function AppLayout({ children }: { children: React.ReactNode }) {
    const breadcrumbItems = useBreadcrumbItems()
    const location = useLocation()
    const { user, logout } = useAuth()
    const { theme, setTheme } = useTheme()

    const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)

    return (
        <SidebarProvider className="h-svh overflow-hidden">
            <Sidebar variant="inset">
                <SidebarHeader>
                    <SidebarMenu>
                        <SidebarMenuItem>
                            <SidebarMenuButton size="lg" asChild>
                                <Link to="/">
                                    <div className="flex aspect-square size-8 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm">
                                        <span className="material-symbols-rounded text-primary-foreground" style={{ fontSize: '16px', transform: 'rotate(-45deg) translateX(8%)' }}>send</span>
                                    </div>
                                    <div className="grid flex-1 text-left text-[14px] leading-tight ml-2">
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
                            <SidebarMenu className="gap-1">
                                <SidebarMenuItem>
                                    <SidebarMenuButton
                                        asChild
                                        isActive={location.pathname === "/" || (location.pathname.startsWith("/campaigns") && location.pathname !== "/campaigns/new")}
                                        className="h-12 rounded-full text-[15px] pl-3"
                                    >
                                        <Link to="/">
                                            <span className="material-symbols-rounded text-[22px]">mark_email_read</span>
                                            <span className="text-[15px] translate-y-[0.5px]">Campaigns</span>
                                        </Link>
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                                <SidebarMenuItem>
                                    <SidebarMenuButton
                                        asChild
                                        isActive={location.pathname.startsWith("/documents")}
                                        className="h-12 rounded-full text-[15px] pl-3"
                                    >
                                        <Link to="/documents">
                                            <span className="material-symbols-rounded text-[22px]">description</span>
                                            <span className="text-[15px] translate-y-[0.5px]">Documents</span>
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
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <SidebarMenuButton size="lg" className="cursor-pointer rounded-full h-14">
                                        <Avatar className="size-9 rounded-full">
                                            {user?.picture_url && (
                                                <AvatarImage src={user.picture_url} referrerPolicy="no-referrer" />
                                            )}
                                            <AvatarFallback className="text-xs bg-primary/10 text-primary">
                                                {user?.name?.charAt(0)?.toUpperCase() || "?"}
                                            </AvatarFallback>
                                        </Avatar>
                                        <div className="grid flex-1 text-left text-sm leading-tight ml-1">
                                            <span className="truncate font-medium text-[14px]">{user?.name}</span>
                                            <span className="truncate text-[12px] text-muted-foreground">{user?.email}</span>
                                        </div>
                                        <span className="material-symbols-rounded ml-auto text-[20px]">unfold_more</span>
                                    </SidebarMenuButton>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent side="top" align="start" className="min-w-52">
                                    <div className="px-2 py-1.5">
                                        <p className="text-sm font-medium">{user?.name}</p>
                                        <p className="text-xs text-muted-foreground">{user?.email}</p>
                                    </div>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem onSelect={(e) => e.preventDefault()} onClick={() => setTheme(isDark ? "light" : "dark")} className="rounded-full my-1 w-full cursor-pointer hover:bg-muted-foreground/15 focus:bg-muted-foreground/15">
                                        <span className="material-symbols-rounded mr-2 text-[18px]">{isDark ? "light_mode" : "dark_mode"}</span>
                                        {isDark ? "Light Mode" : "Dark Mode"}
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={logout} className="text-destructive-container-foreground hover:!text-foreground focus:!text-foreground focus:bg-destructive-hover rounded-full my-1 w-full cursor-pointer">
                                        <span className="material-symbols-rounded mr-2 text-[18px]">logout</span>
                                        Sign out
                                    </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </SidebarMenuItem>
                    </SidebarMenu>
                </SidebarFooter>
            </Sidebar>

            <SidebarInset className="flex flex-col">
                {/* Top bar with trigger + breadcrumbs */}
                <header className="flex h-16 shrink-0 items-center gap-3 border-b px-6">
                    <SidebarTrigger className="-ml-2 h-10 w-10 rounded-full" />
                    {breadcrumbItems.length > 0 && (
                        <>
                            <Separator orientation="vertical" className="mr-3 h-full" />
                            <Breadcrumb className="mt-[2px]">
                                <BreadcrumbList className="text-[15px]">
                                    {breadcrumbItems.map((item, index) => {
                                        const isLast = index === breadcrumbItems.length - 1
                                        return (
                                            <span key={index} className="flex items-center gap-1.5">
                                                {index > 0 && <BreadcrumbSeparator />}
                                                <BreadcrumbItem>
                                                    {item.label === "Loading..." ? (
                                                        <Skeleton className="h-4 w-24 rounded-full" />
                                                    ) : isLast || !item.href ? (
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
                <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
                    {children}
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
