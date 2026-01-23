// KPI Definitions and Benchmarks
export const KPI_DEFINITIONS = {
  ppa: {
    name: "Per Person Average",
    shortName: "PPA", 
    benchmark: 55.00,
    format: "currency"
  },
  pplbw: {
    name: "Per Person Liquor Beer and Wine",
    shortName: "PPLBW",
    benchmark: 8.00,
    format: "currency"
  },
  gpg: {
    name: "Glassware $ Per Guest", 
    shortName: "GPG",
    benchmark: 1.00,
    format: "currency"
  },
  lsc_ratio: {
    name: "Landry's Select Card (LSC) Memberships Sold",
    shortName: "LSC Ratio",
    benchmark: 0.01, // 1 in 100
    format: "ratio"
  },
  metric_bonus_points: {
    name: "Metric Bonus Points",
    shortName: "Metric Bonus",
    description: "Special incentives when an employee exceeds the benchmark for the store",
    format: "number"
  },
  cumulative_score: {
    name: "Cumulative Score",
    shortName: "Final Grade",
    description: "Overall performance score",
    format: "number"
  }
};

// Utility functions for formatting KPIs
export const formatCurrency = (value) => {
  if (value === null || value === undefined) return 'N/A';
  return `$${parseFloat(value).toFixed(2)}`;
};

export const formatLSCRatio = (value) => {
  if (value === null || value === undefined || value === 0) return 'N/A';
  // The value from the spreadsheet is already the denominator (e.g., 34 means "1 in 34")
  return `1 in ${Math.round(parseFloat(value))}`;
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

export const getBenchmarkStatus = (kpi, value) => {
  if (!value || !KPI_DEFINITIONS[kpi]) return { status: "neutral", text: "" };
  
  const benchmark = KPI_DEFINITIONS[kpi].benchmark;
  const isAbove = value >= benchmark;
  
  return {
    status: isAbove ? "above" : "below",
    text: isAbove ? "Above Benchmark" : "Below Benchmark",
    class: isAbove ? "text-green-600" : "text-orange-600"
  };
};