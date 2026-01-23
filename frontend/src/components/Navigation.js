import { Link, useLocation } from "react-router-dom";
import { Home, Users, FileText } from "lucide-react";

export default function Navigation() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Dashboard", icon: Home },
    { path: "/employees", label: "Employees", icon: Users },
    { path: "/reviews", label: "Reviews", icon: FileText },
  ];

  return (
    <nav className="bubba-header shadow-lg" data-testid="main-navigation">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-3" data-testid="nav-brand">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump" 
              className="w-10 h-10 rounded-full"
              data-testid="nav-logo"
            />
            <div>
              <h1 className="text-xl font-serif font-bold" data-testid="nav-title">
                Bubba Gump Reviews
              </h1>
              <p className="text-sm opacity-90" data-testid="nav-subtitle">Performance Management</p>
            </div>
          </div>

          <div className="flex space-x-1" data-testid="nav-links">
            {navItems.map(({ path, label, icon: Icon }) => {
              const isActive = location.pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={`nav-link ${
                    isActive
                      ? "bg-white/20 text-white"
                      : "text-white/80 hover:bg-white/10 hover:text-white"
                  }`}
                  data-testid={`nav-link-${path.replace("/", "") || "dashboard"}`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}