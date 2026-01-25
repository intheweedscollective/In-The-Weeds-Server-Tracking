import { Link } from "react-router-dom";

export default function StatsCard({ icon: Icon, title, value, color, testId, linkTo }) {
  const cardContent = (
    <div 
      className={`kpi-card ${linkTo ? 'cursor-pointer' : ''}`} 
      data-testid={testId}
    >
      <div className="flex flex-col">
        <div className="kpi-value" data-testid={`${testId}-value`}>{value}</div>
        <div className="kpi-label" data-testid={`${testId}-label`}>{title}</div>
      </div>
      <div 
        className={`p-3 rounded-full ${color} bg-opacity-15`} 
        data-testid={`${testId}-icon`}
      >
        <Icon className={`w-6 h-6 ${color.replace('bg-', 'text-')}`} />
      </div>
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
