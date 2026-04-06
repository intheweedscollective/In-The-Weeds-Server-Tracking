import { useStore } from '../contexts/StoreContext';
import { Building2, ChevronDown, Globe, MapPin } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

export default function StoreSelector({ className = '' }) {
  const { stores, selectedStore, selectStore, selectAllStores, loading, regions, isGlobalView } = useStore();
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Filter stores based on search
  const filteredStores = stores.filter(store => 
    store.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    store.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (store.city && store.city.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Group stores by region
  const groupedStores = regions.reduce((acc, region) => {
    acc[region] = filteredStores.filter(s => s.region === region);
    return acc;
  }, {});

  if (loading) {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg bg-[hsl(var(--sidebar-bg))] ${className}`}>
        <Building2 className="w-4 h-4 animate-pulse" />
        <span className="text-sm">Loading...</span>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Selected Store Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[hsl(var(--card))] border border-[hsl(var(--border))] hover:bg-[hsl(var(--accent))] transition-colors w-full"
        data-testid="store-selector-btn"
      >
        {isGlobalView ? (
          <>
            <Globe className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium">All Stores</span>
          </>
        ) : (
          <>
            <MapPin className="w-4 h-4 text-green-400" />
            <div className="flex-1 text-left">
              <span className="text-sm font-medium">{selectedStore?.code}</span>
              <span className="text-xs text-muted-foreground ml-2">{selectedStore?.city}</span>
            </div>
          </>
        )}
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg shadow-lg z-50 max-h-96 overflow-y-auto">
          {/* Search Input */}
          <div className="p-2 border-b border-[hsl(var(--border))]">
            <input
              type="text"
              placeholder="Search stores..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-[hsl(var(--background))] border border-[hsl(var(--border))] rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="store-search-input"
            />
          </div>

          {/* All Stores Option */}
          <button
            onClick={() => {
              selectAllStores();
              setIsOpen(false);
              setSearchTerm('');
            }}
            className={`w-full flex items-center gap-2 px-3 py-2 hover:bg-[hsl(var(--accent))] transition-colors ${isGlobalView ? 'bg-blue-500/10' : ''}`}
            data-testid="store-option-all"
          >
            <Globe className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium">All Stores (Global View)</span>
          </button>

          <div className="border-t border-[hsl(var(--border))]" />

          {/* Grouped Stores */}
          {Object.entries(groupedStores).map(([region, regionStores]) => (
            regionStores.length > 0 && (
              <div key={region}>
                <div className="px-3 py-1.5 text-xs font-semibold text-muted-foreground bg-[hsl(var(--accent))/50]">
                  {region || 'Other'}
                </div>
                {regionStores.map(store => (
                  <button
                    key={store.id}
                    onClick={() => {
                      selectStore(store);
                      setIsOpen(false);
                      setSearchTerm('');
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 hover:bg-[hsl(var(--accent))] transition-colors ${selectedStore?.id === store.id ? 'bg-green-500/10' : ''}`}
                    data-testid={`store-option-${store.code}`}
                  >
                    <MapPin className={`w-4 h-4 ${store.employee_count > 0 ? 'text-green-400' : 'text-gray-400'}`} />
                    <div className="flex-1 text-left">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{store.code}</span>
                        <span className="text-xs text-muted-foreground">{store.city}, {store.state}</span>
                      </div>
                      {store.employee_count > 0 && (
                        <div className="text-xs text-muted-foreground">
                          {store.employee_count} employees • Avg: {store.avg_score?.toFixed(1) || 0}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )
          ))}

          {filteredStores.length === 0 && (
            <div className="px-3 py-4 text-sm text-center text-muted-foreground">
              No stores found
            </div>
          )}
        </div>
      )}
    </div>
  );
}
