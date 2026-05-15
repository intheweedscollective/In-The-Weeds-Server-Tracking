/**
 * Employee display name helper — SINGLE SOURCE for ALL user-facing employee names.
 *
 * Policy (non-negotiable):
 *   1. Return ONLY the first word of the employee's Display Name.
 *   2. If Display Name is empty, fallback to first word of Report Name (`name`).
 *   3. Never return last names, initials, or report names in the UI.
 *   4. Case is preserved; whitespace is trimmed.
 *
 * Backend ingestion/matching still uses the full Report Name + aliases — this
 * helper is ONLY for rendering.
 */
export function getDisplayFirstName(employee) {
  if (!employee) return "Unknown";
  const display = employee.display_name;
  const report = employee.name || employee.report_name;
  for (const candidate of [display, report]) {
    if (candidate && typeof candidate === "string" && candidate.trim()) {
      const parts = candidate.trim().split(/\s+/);
      if (parts.length && parts[0]) return parts[0];
    }
  }
  return "Unknown";
}

/**
 * When we only have a bare string (rare — prefer passing the full employee),
 * extract the first word safely.
 */
export function firstWordOf(nameString) {
  if (!nameString || typeof nameString !== "string") return "Unknown";
  const parts = nameString.trim().split(/\s+/);
  return parts[0] || "Unknown";
}

export default getDisplayFirstName;
