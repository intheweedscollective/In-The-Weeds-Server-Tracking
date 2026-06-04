import { createContext, useContext, useState, useEffect } from 'react';
import api from '../lib/api';

// Store context for global store selection
const StoreContext = createContext(null);

export function StoreProvider({ children }) {
  const [stores, setStores] = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regions, setRegions] = useState([]);

  // Load stores on mount
  useEffect(() => {
    loadStores();
  }, []);

  // Load selected store from localStorage
  useEffect(() => {
    const savedStoreId = localStorage.getItem('selectedStoreId');
    if (savedStoreId && stores.length > 0) {
      const store = stores.find(s => s.id === savedStoreId);
      if (store) {
        setSelectedStore(store);
      } else if (stores.length > 0) {
        // Default to first store with data or first store
        const storeWithData = stores.find(s => s.employee_count > 0);
        setSelectedStore(storeWithData || stores[0]);
      }
    } else if (stores.length > 0 && !selectedStore) {
      const storeWithData = stores.find(s => s.employee_count > 0);
      setSelectedStore(storeWithData || stores[0]);
    }
  }, [stores]);

  const loadStores = async () => {
    try {
      // Use the shared axios client so cookies/auth headers stay consistent
      // with the rest of the app (was raw fetch — risk of stale session).
      const { data } = await api.get('/v2/stores?include_stats=true');
      setStores(data?.stores || []);
      setRegions(data?.regions || []);
    } catch (error) {

      console.error('Failed to load stores:', error);
    } finally {
      setLoading(false);
    }
  };

  const selectStore = (store) => {
    setSelectedStore(store);
    if (store?.id) {
      localStorage.setItem('selectedStoreId', store.id);
    }
  };

  // "All Stores" mode for regional/executive view
  const selectAllStores = () => {
    setSelectedStore(null);
    localStorage.removeItem('selectedStoreId');
  };

  const value = {
    stores,
    selectedStore,
    selectStore,
    selectAllStores,
    loading,
    regions,
    refreshStores: loadStores,
    // Helper to check if viewing all stores
    isGlobalView: selectedStore === null,
    // Get current store ID for API calls
    currentStoreId: selectedStore?.id || null
  };

  return (
    <StoreContext.Provider value={value}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  const context = useContext(StoreContext);
  if (!context) {
    throw new Error('useStore must be used within a StoreProvider');
  }
  return context;
}

export default StoreContext;
