/**
 * Get the current fiscal quarter and year based on the current date.
 * Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec
 */
export function getCurrentQuarter() {
  const now = new Date();
  const month = now.getMonth(); // 0-indexed
  const year = now.getFullYear();
  
  if (month < 3) return { quarter: "Q1", year };
  if (month < 6) return { quarter: "Q2", year };
  if (month < 9) return { quarter: "Q3", year };
  return { quarter: "Q4", year };
}
