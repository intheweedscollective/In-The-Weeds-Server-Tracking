import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { 
  Home, 
  Trophy, 
  Users, 
  Star, 
  Camera, 
  FileText, 
  Monitor,
  BarChart3, 
  Settings, 
  HelpCircle,
  ChevronDown,
  ChevronRight,
  Menu,
  X,
  Building2
} from "lucide-react";

// Navigation structure with grouping
const navGroups = [
  {
    id: "main",
    items: [
      { path: "/", label: "Dashboard", icon: Home }
    ]
  },
  {
    id: "performance",
    label: "Performance",
    items: [
      { path: "/rankings", label: "Rankings", icon: Trophy },
      { path: "/snapshots", label: "Snapshots", icon: Camera },
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
  }
];

const bottomNav = [
  { path: "/settings", label: "Settings", icon: Settings },
  { path: "/help", label: "Help Center", icon: HelpCircle }
];

export const SidebarLayout = ({ children }) => {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState(["performance", "feedback", "exports", "team"]);

  const toggleGroup = (groupId) => {
    setExpandedGroups(prev => 
      prev.includes(groupId) 
        ? prev.filter(id => id !== groupId)
        : [...prev, groupId]
    );
  };

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
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        }
      `}
      data-testid={`nav-${item.path.replace("/", "") || "home"}`}
    >
      <item.icon className={`w-5 h-5 flex-shrink-0 ${isActive(item.path) ? "" : "text-slate-400 group-hover:text-primary"}`} />
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
    <div className="flex flex-col h-full">
      {/* Logo Header */}
      <div className={`p-4 border-b border-sand ${isCollapsed ? "px-2" : ""}`}>
        <Link to="/" className="flex items-center gap-3" onClick={() => setIsMobileOpen(false)}>
          <img 
            src="https://customer-assets.emergentagent.com/job_eaa669fd-7426-41e2-82fc-765ab916d7f3/artifacts/f0uz68d3_IMG_0599.png" 
            alt="Bubba Gump" 
            className={`rounded-full border-2 border-primary/20 shadow-md flex-shrink-0 transition-all ${isCollapsed ? "w-10 h-10" : "w-14 h-14"}`}
          />
          {!isCollapsed && (
            <div className="min-w-0">
              <h1 className="font-serif font-bold text-slate-800 text-lg leading-tight truncate">
                Bubba Gump
              </h1>
              <p className="text-xs text-slate-500 truncate">Performance Hub</p>
            </div>
          )}
        </Link>
      </div>

      {/* Store Selector (for multi-store future) */}
      {!isCollapsed && (
        <div className="px-3 py-3 border-b border-sand">
          <button className="w-full flex items-center gap-2 px-3 py-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-sm font-medium text-slate-700 transition-colors">
            <Building2 className="w-4 h-4 text-slate-400" />
            <span className="flex-1 text-left truncate">Las Vegas</span>
            <ChevronDown className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      )}

      {/* Navigation Groups */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navGroups.map((group) => (
          <div key={group.id} className="mb-2">
            {group.label && !isCollapsed && (
              <button
                onClick={() => toggleGroup(group.id)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wider hover:text-slate-600"
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
      <div className="border-t border-sand px-3 py-3 space-y-1">
        {bottomNav.map((item) => (
          <NavLink key={item.path} item={item} showLabel={!isCollapsed} />
        ))}
      </div>

      {/* Collapse Toggle (Desktop only) */}
      <div className="hidden lg:block border-t border-sand p-3">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
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
    <div className="min-h-screen bg-paper flex">
      {/* Desktop Sidebar */}
      <aside 
        className={`
          hidden lg:flex flex-col bg-white border-r border-sand
          transition-all duration-300 ease-in-out
          ${isCollapsed ? "w-20" : "w-64"}
        `}
        style={{ position: "sticky", top: 0, height: "100vh" }}
      >
        <SidebarContent />
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-white border-b border-sand">
        <div className="flex items-center justify-between px-4 py-3">
          <Link to="/" className="flex items-center gap-3">
            <img 
              src="https://customer-assets.emergentagent.com/job_eaa669fd-7426-41e2-82fc-765ab916d7f3/artifacts/f0uz68d3_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-10 h-10 rounded-full border-2 border-primary/20"
            />
            <span className="font-serif font-bold text-slate-800">Performance Hub</span>
          </Link>
          <button
            onClick={() => setIsMobileOpen(!isMobileOpen)}
            className="p-2 text-slate-600 hover:bg-slate-100 rounded-lg"
          >
            {isMobileOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Sidebar Overlay */}
      {isMobileOpen && (
        <div 
          className="lg:hidden fixed inset-0 z-50 bg-black/50"
          onClick={() => setIsMobileOpen(false)}
        >
          <aside 
            className="w-72 h-full bg-white shadow-xl"
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
