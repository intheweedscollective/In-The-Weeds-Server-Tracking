import { Link, useLocation } from "react-router-dom";
import { Home, Users, FileText, BarChart3, Trophy, Settings, ListOrdered, Monitor, Camera } from "lucide-react";

export default function Navigation() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Dashboard", icon: Home },
    { path: "/rankings", label: "Rankings", icon: ListOrdered },
    { path: "/employees", label: "Employees", icon: Users },
    { path: "/reviews", label: "Reviews", icon: FileText },
    { path: "/snapshots", label: "Snapshots", icon: Camera },
    { path: "/yodeck", label: "Yodeck", icon: Monitor },
    { path: "/analytics", label: "Analytics", icon: BarChart3 },
    { path: "/top-performers", label: "Top", icon: Trophy },
    { path: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <nav className="bg-gradient-to-r from-secondary via-secondary to-primary shadow-lg" data-testid="main-navigation">
      <div className="w-full px-2 sm:px-4 lg:px-8">
        {/* Header Row - Logo and Title - LARGE */}
        <div className="flex items-center justify-center py-6 md:py-8 border-b border-white/20">
          <div className="flex items-center gap-4 md:gap-8" data-testid="nav-brand">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-20 h-20 md:w-28 md:h-28 lg:w-36 lg:h-36 rounded-full flex-shrink-0 border-4 border-white/40 shadow-xl"
              data-testid="nav-logo"
            />
            <div className="text-white text-center md:text-left">
              <h1 className="text-2xl md:text-5xl lg:text-6xl font-serif font-bold tracking-wide" data-testid="nav-title">
                Bubba Gump Shrimp Co.
              </h1>
              <p className="text-sm md:text-2xl lg:text-3xl opacity-90 mt-1 md:mt-2" data-testid="nav-subtitle">
                Las Vegas • Performance Management
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Tabs Row - Scrollable */}
        <div className="py-3 md:py-4" data-testid="nav-links">
          <div className="overflow-x-auto scrollbar-hide">
            <div className="flex items-center justify-start md:justify-center gap-1 md:gap-2 px-2 min-w-max">
              {navItems.map(({ path, label, icon: Icon }) => {
                const isActive = location.pathname === path;
                return (
                  <Link
                    key={path}
                    to={path}
                    className={`flex items-center gap-1.5 md:gap-2 px-3 py-2 md:px-5 md:py-2.5 rounded-full text-xs md:text-sm font-semibold transition-all whitespace-nowrap ${
                      isActive
                        ? "bg-white text-primary shadow-md"
                        : "text-white/90 hover:bg-white/20 hover:text-white"
                    }`}
                    data-testid={`nav-link-${path.replace("/", "") || "dashboard"}`}
                  >
                    <Icon className="w-4 h-4 md:w-5 md:h-5 flex-shrink-0" />
                    <span>{label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
