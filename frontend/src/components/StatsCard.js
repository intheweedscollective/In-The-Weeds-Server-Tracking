export default function StatsCard({ icon: Icon, title, value, color, testId }) {
  return (
    <div className="kpi-card" data-testid={testId}>
      <div className="flex items-center justify-between mb-4">
        <div className={`p-3 rounded-lg ${color} text-white`} data-testid={`${testId}-icon`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
      <div className="kpi-value" data-testid={`${testId}-value`}>{value}</div>
      <div className="kpi-label" data-testid={`${testId}-label`}>{title}</div>
    </div>
  );
}