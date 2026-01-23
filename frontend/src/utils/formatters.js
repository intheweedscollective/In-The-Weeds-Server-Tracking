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
    benchmark: 5,
    description: "Special incentives when an employee exceeds the benchmark for the store",
    format: "number"
  },
  cumulative_score: {
    name: "Cumulative Score",
    shortName: "Final Grade",
    benchmark: 80,
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

export const formatOverallRank = (rank) => {
  if (!rank) return 'N/A';
  // Handle formats like "3 of 26" or "3/26" 
  if (typeof rank === 'string' && (rank.includes(' of ') || rank.includes('/'))) {
    return rank;
  }
  // If it's just a number, assume it's out of 26
  return `${rank} of 26`;
};

export const formatRanking = (ranking) => {
  if (!ranking) return 'N/A';
  return ranking.toString();
};

export const getRankingHierarchy = (ranking) => {
  if (!ranking) return { level: 'Unknown', color: 'text-gray-500', bgColor: 'bg-gray-100' };
  
  const rank = ranking.toString().toUpperCase();
  
  if (rank.startsWith('T')) return { 
    level: 'Trainer', 
    color: 'text-purple-700', 
    bgColor: 'bg-purple-100',
    priority: 1 
  };
  if (rank.startsWith('BAR')) return { 
    level: 'Bartender', 
    color: 'text-blue-700', 
    bgColor: 'bg-blue-100',
    priority: 2 
  };
  if (rank.startsWith('A')) return { 
    level: 'Top Server', 
    color: 'text-green-700', 
    bgColor: 'bg-green-100',
    priority: 3 
  };
  if (rank.startsWith('B')) return { 
    level: 'Middle Server', 
    color: 'text-yellow-700', 
    bgColor: 'bg-yellow-100',
    priority: 4 
  };
  if (rank.startsWith('C')) return { 
    level: 'Bottom Server', 
    color: 'text-orange-700', 
    bgColor: 'bg-orange-100',
    priority: 5 
  };
  
  return { level: 'Staff', color: 'text-gray-700', bgColor: 'bg-gray-100', priority: 6 };
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
  let isAbove = false;
  
  // Special handling for LSC Ratio - lower numbers are better (1 in 34 is better than 1 in 100)
  if (kpi === 'lsc_ratio') {
    // Convert benchmark to denominator format (0.01 = 1 in 100)
    const benchmarkDenominator = Math.round(1 / benchmark); // 100
    isAbove = value <= benchmarkDenominator; // 34 <= 100 = Above benchmark
  } else {
    isAbove = value >= benchmark;
  }
  
  return {
    status: isAbove ? "above" : "below",
    text: isAbove ? "Above Benchmark" : "Below Benchmark",
    class: isAbove ? "text-green-600" : "text-orange-600"
  };
};