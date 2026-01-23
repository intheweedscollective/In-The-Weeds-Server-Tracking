// Utility functions for formatting KPIs
export const formatCurrency = (value) => {
  if (value === null || value === undefined) return 'N/A';
  return `$${parseFloat(value).toFixed(2)}`;
};

export const formatLSCRatio = (value) => {
  if (value === null || value === undefined || value === 0) return 'N/A';
  const ratio = Math.round(1 / parseFloat(value));
  return `1 in ${ratio}`;
};

export const formatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined) return 'N/A';
  return parseFloat(value).toFixed(decimals);
};

export const getPerformanceLevel = (score) => {
  if (!score) return { text: "Not Assessed", class: "performance-below" };
  
  if (score >= 90) return { text: "Excellent", class: "performance-excellent" };
  if (score >= 80) return { text: "Above Average", class: "performance-above-average" };
  if (score >= 70) return { text: "Satisfactory", class: "performance-satisfactory" };
  if (score >= 60) return { text: "Needs Improvement", class: "performance-needs-improvement" };
  return { text: "Below Expectations", class: "performance-below" };
};