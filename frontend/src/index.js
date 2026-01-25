import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";


// Suppress known ResizeObserver errors (not actionable, common on mobile Safari with dropdowns)
if (typeof window !== "undefined") {
  window.addEventListener("error", (e) => {
    if (
      typeof e?.message === "string" &&
      (e.message.includes("ResizeObserver loop") ||
        e.message.includes("ResizeObserver Loop"))
    ) {
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  });
}


// Default to dark theme (user preference) and allow future toggle
if (typeof document !== "undefined") {
  document.documentElement.classList.add("dark");
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
