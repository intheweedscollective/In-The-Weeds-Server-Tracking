import { Link, useLocation } from "react-router-dom";
import { Home, Users, FileText, BarChart3, Trophy } from "lucide-react";
import ThemeToggle from "./ThemeToggle";


export default function Navigation() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Dashboard", icon: Home },
    { path: "/employees", label: "Employees", icon: Users },
    { path: "/reviews", label: "Reviews", icon: FileText },
    { path: "/analytics", label: "Analytics", icon: BarChart3 },
    { path: "/top-performers", label: "Top", icon: Trophy },
  ];

  return (
    <nav className="bubba-header shadow-lg" data-testid="main-navigation">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-auto py-3 md:h-16 md:py-0">
          <div className="flex items-center gap-2 md:gap-3" data-testid="nav-brand">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-8 h-8 md:w-10 md:h-10 rounded-full flex-shrink-0"
              data-testid="nav-logo"
            />
            <div className="min-w-0 flex-1">
              <h1 className="text-sm md:text-xl font-serif font-bold truncate" data-testid="nav-title">
                Bubba Gump Shrimp Co.
              </h1>
              <p className="text-xs md:text-sm opacity-90 truncate" data-testid="nav-subtitle">Las Vegas • Performance Management</p>
            </div>
          </div>

          <div className="flex space-x-0.5 md:space-x-1" data-testid="nav-links">
            {navItems.map(({ path, label, icon: Icon }) => {
              const isActive = location.pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={`flex flex-col md:flex-row items-center gap-0.5 md:gap-2 px-2 py-1.5 md:px-4 md:py-2 rounded-md text-xs md:text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white/20 text-white"
                      : "text-white/80 hover:bg-white/10 hover:text-white"
                  }`}
                  data-testid={`nav-link-${path.replace("/", "") || "dashboard"}`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="hidden sm:block md:inline">{label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}