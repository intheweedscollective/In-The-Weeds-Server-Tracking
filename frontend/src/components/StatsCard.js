import { Link } from "react-router-dom";

export default function StatsCard({ icon: Icon, title, value, color, testId, linkTo }) {
  const cardContent = (
    <div className={`kpi-card ${linkTo ? 'cursor-pointer hover:shadow-lg transform hover:scale-105 transition-all duration-200' : ''}`} data-testid={testId}>
      <div className="flex items-center justify-between mb-4">
        <div className={`p-3 rounded-lg ${color} text-white`} data-testid={`${testId}-icon`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
      <div className="kpi-value" data-testid={`${testId}-value`}>{value}</div>
      <div className="kpi-label" data-testid={`${testId}-label`}>{title}</div>
    </div>
  );

  if (linkTo) {
    return (
      <Link to={linkTo} className="block">
        {cardContent}
      </Link>
    );
  }

  return cardContent;
}