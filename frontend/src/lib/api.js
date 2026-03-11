import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Create axios instance with cache-busting headers
const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  headers: {
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0'
  }
});

// Add cache-busting timestamp to all GET requests
api.interceptors.request.use((config) => {
  if (config.method === 'get') {
    config.params = {
      ...config.params,
      _t: Date.now()
    };
  }
  return config;
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.status, error.message);
    return Promise.reject(error);
  }
);

export default api;
export { BACKEND_URL };
