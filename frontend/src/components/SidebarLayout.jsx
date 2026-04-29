import { useState, useRef, useCallback } from "react";
import { Link, useLocation } from "react-router-dom";
import { 
  Home, 
  Trophy, 
  Users, 
  Star, 
  FileText, 
  Monitor,
  BarChart3, 
  Settings, 
  HelpCircle,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  ClipboardCheck,
  Menu,
  X,
  Sun,
  Moon,
  Upload,
  QrCode,
  Building2,
  Filter,
  BookOpen,
  Calculator,
  Layers,
  Globe
} from "lucide-react";
import { useTheme } from "../context/ThemeContext";

// Navigation structure with grouping
const navGroups = [
  {
    id: "main",
    items: [
      { path: "/", label: "Dashboard", icon: Home },
      { path: "/snapshot-workflow", label: "Snapshot Workflow", icon: Layers },
      { path: "/uploads", label: "Data Uploads", icon: Upload },
      { path: "/reports", label: "Reports", icon: FileText }
    ]
  },
  {
    id: "performance",
    label: "Performance",
    items: [
      { path: "/rankings", label: "Rankings", icon: Trophy },
      { path: "/leaderboard", label: "Leaderboard", icon: BarChart3 },
      { path: "/analytics", label: "Analytics", icon: BarChart3 }
    ]
  },
  {
    id: "feedback",
    label: "Feedback",
    items: [
      { path: "/review-tracker", label: "Review Tracker", icon: Star }
    ]
  },
  {
    id: "exports",
    label: "Exports",
    items: [
      { path: "/yodeck", label: "Reports & Slides", icon: Monitor },
      { path: "/reviews", label: "PDF Reviews", icon: FileText }
    ]
  },
  {
    id: "team",
    label: "Team",
    items: [
      { path: "/employees", label: "Employees", icon: Users }
    ]
  },
  {
    id: "stores",
    label: "Multi-Store",
    items: [
      { path: "/global", label: "Global Overview", icon: Globe },
      { path: "/stores", label: "Store Management", icon: Building2 },
      { path: "/stores/leaderboard", label: "Store Leaderboard", icon: Trophy }
    ]
  },
  {
    id: "qr",
    label: "QR Track Hub",
    items: [
      { path: "/qr", label: "QR Dashboard", icon: QrCode },
      { path: "/qr/leaderboard", label: "QR Leaderboard", icon: Trophy },
      { path: "/qr/codes", label: "QR Codes", icon: QrCode },
      { path: "/qr/settings", label: "QR Settings", icon: Settings }
    ]
  },
  {
    id: "admin",
    label: "Admin",
    items: [
      { path: "/scoring-audit", label: "Scoring Audit", icon: ClipboardCheck },
      { path: "/cv-adjustment", label: "CV NPS Adjustment", icon: Filter },
      { path: "/data-integrity", label: "Data Integrity", icon: ShieldCheck }
    ]
  }
];

const bottomNav = [
  { path: "/upload-tutorial", label: "Upload Tutorial", icon: BookOpen },
  { path: "/scoring-guide", label: "Scoring Guide", icon: Calculator },
  { path: "/settings", label: "Settings", icon: Settings },
  { path: "/help", label: "Help Center", icon: HelpCircle }
];

export const SidebarLayout = ({ children }) => {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState(["performance", "feedback", "exports", "team", "qr", "stores"]);
  const { theme, toggleTheme } = useTheme();
  const navRef = useRef(null);

  const toggleGroup = useCallback((groupId) => {
    // Store current scroll position before state update
    const scrollTop = navRef.current?.scrollTop || 0;
    
    setExpandedGroups(prev => 
      prev.includes(groupId) 
        ? prev.filter(id => id !== groupId)
        : [...prev, groupId]
    );
    
    // Restore scroll position after a micro-delay to allow DOM update
    requestAnimationFrame(() => {
      if (navRef.current) {
        navRef.current.scrollTop = scrollTop;
      }
    });
  }, []);

  const isActive = (path) => location.pathname === path;

  const NavLink = ({ item, showLabel = true }) => (
    <Link
      to={item.path}
      onClick={() => setIsMobileOpen(false)}
      className={`
        flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium
        transition-all duration-200 group relative
        ${isActive(item.path) 
          ? "bg-primary text-white shadow-lg shadow-primary/25" 
          : "text-[hsl(var(--sidebar-text,215_20%_65%))] hover:bg-[hsl(var(--sidebar-hover,220_26%_18%))] hover:text-foreground"
        }
      `}
      data-testid={`nav-${item.path.replace("/", "") || "home"}`}
    >
      <item.icon className={`w-5 h-5 flex-shrink-0 ${isActive(item.path) ? "" : "text-[hsl(var(--sidebar-text,215_20%_65%))] group-hover:text-primary"}`} />
      {showLabel && (
        <span className={`${isCollapsed ? "hidden" : "block"} truncate`}>
          {item.label}
        </span>
      )}
      {isActive(item.path) && (
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-full -ml-3" />
      )}
    </Link>
  );

  const SidebarContent = () => (
    <div className="flex flex-col h-full bg-[hsl(var(--sidebar-bg,220_26%_12%))]">
      {/* Logo Header */}
      <div className={`p-4 border-b border-border ${isCollapsed ? "px-2" : ""}`}>
        <Link to="/" className="flex items-center gap-3" onClick={() => setIsMobileOpen(false)}>
          <img 
            src="https://customer-assets.emergentagent.com/job_eaa669fd-7426-41e2-82fc-765ab916d7f3/artifacts/f0uz68d3_IMG_0599.png" 
            alt="Bubba Gump" 
            className={`rounded-full border-2 border-primary/30 shadow-md flex-shrink-0 transition-all ${isCollapsed ? "w-10 h-10" : "w-14 h-14"}`}
          />
          {!isCollapsed && (
            <div className="min-w-0">
              <h1 className="font-bold text-foreground text-lg leading-tight truncate">
                Bubba Gump
              </h1>
              <p className="text-xs text-muted-foreground truncate">Performance Hub</p>
            </div>
          )}
        </Link>
      </div>

      {/* Navigation Groups */}
      <nav ref={navRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navGroups.map((group) => (
          <div key={group.id} className="mb-2">
            {group.label && !isCollapsed && (
              <button
                onClick={() => toggleGroup(group.id)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground"
              >
                <span>{group.label}</span>
                {expandedGroups.includes(group.id) ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronRight className="w-3 h-3" />
                )}
              </button>
            )}
            {(group.label ? expandedGroups.includes(group.id) : true) && (
              <div className="space-y-1">
                {group.items.map((item) => (
                  <NavLink key={item.path} item={item} showLabel={!isCollapsed} />
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* Bottom Navigation */}
      <div className="border-t border-border px-3 py-3 space-y-1">
        {bottomNav.map((item) => (
          <NavLink key={item.path} item={item} showLabel={!isCollapsed} />
        ))}
        
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium
            text-muted-foreground hover:bg-[hsl(var(--sidebar-hover,220_26%_18%))] hover:text-foreground transition-all duration-200"
          data-testid="theme-toggle"
        >
          {theme === 'dark' ? (
            <>
              <Sun className="w-5 h-5 text-yellow-400" />
              {!isCollapsed && <span>Light Mode</span>}
            </>
          ) : (
            <>
              <Moon className="w-5 h-5 text-blue-400" />
              {!isCollapsed && <span>Dark Mode</span>}
            </>
          )}
        </button>
      </div>

      {/* Collapse Toggle (Desktop only) */}
      <div className="hidden lg:block border-t border-border p-3">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronDown className="w-4 h-4 rotate-90" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex">
      {/* Desktop Sidebar */}
      <aside 
        className={`
          hidden lg:flex flex-col bg-[hsl(var(--sidebar-bg,220_26%_12%))] border-r border-border
          transition-all duration-300 ease-in-out
          ${isCollapsed ? "w-20" : "w-64"}
        `}
        style={{ position: "sticky", top: 0, height: "100vh" }}
      >
        <SidebarContent />
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-[hsl(var(--sidebar-bg,220_26%_12%))] border-b border-border">
        <div className="flex items-center justify-between px-4 py-3">
          <Link to="/" className="flex items-center gap-3">
            <img 
              src="https://customer-assets.emergentagent.com/job_eaa669fd-7426-41e2-82fc-765ab916d7f3/artifacts/f0uz68d3_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-10 h-10 rounded-full border-2 border-primary/30"
            />
            <span className="font-bold text-foreground">Performance Hub</span>
          </Link>
          <button
            onClick={() => setIsMobileOpen(!isMobileOpen)}
            className="p-2 text-muted-foreground hover:bg-muted rounded-lg"
          >
            {isMobileOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Sidebar Overlay */}
      {isMobileOpen && (
        <div 
          className="lg:hidden fixed inset-0 z-50 bg-black/60"
          onClick={() => setIsMobileOpen(false)}
        >
          <aside 
            className="w-72 h-full bg-[hsl(var(--sidebar-bg,220_26%_12%))] shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 min-w-0 lg:pt-0 pt-16">
        {children}
      </main>
    </div>
  );
};

export default SidebarLayout;
