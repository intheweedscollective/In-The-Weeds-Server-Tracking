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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header Row - Logo and Title */}
        <div className="flex items-center justify-center py-6 border-b border-white/20">
          <div className="flex items-center gap-4 md:gap-6" data-testid="nav-brand">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-16 h-16 md:w-24 md:h-24 lg:w-28 lg:h-28 rounded-full flex-shrink-0 border-4 border-white/40 shadow-lg"
              data-testid="nav-logo"
            />
            <div className="text-white text-center md:text-left">
              <h1 className="text-2xl md:text-4xl lg:text-5xl font-serif font-bold tracking-wide" data-testid="nav-title">
                Bubba Gump Shrimp Co.
              </h1>
              <p className="text-sm md:text-xl lg:text-2xl opacity-90 mt-1" data-testid="nav-subtitle">
                Las Vegas • Performance Management
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Tabs Row */}
        <div className="flex items-center justify-center py-4 overflow-x-auto" data-testid="nav-links">
          <div className="flex space-x-2 md:space-x-3">
            {navItems.map(({ path, label, icon: Icon }) => {
              const isActive = location.pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={`flex items-center gap-2 px-4 py-2 md:px-6 md:py-3 rounded-full text-sm md:text-base font-semibold transition-all whitespace-nowrap ${
                    isActive
                      ? "bg-white text-primary shadow-md"
                      : "text-white/90 hover:bg-white/20 hover:text-white"
                  }`}
                  data-testid={`nav-link-${path.replace("/", "") || "dashboard"}`}
                >
                  <Icon className="w-5 h-5 md:w-6 md:h-6 flex-shrink-0" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
