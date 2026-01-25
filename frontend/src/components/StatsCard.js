import { Link } from "react-router-dom";

const colorMap = {
  'bg-blue-500': { accent: '#005B96', iconClass: 'text-blue-600 dark:text-blue-400' },
  'bg-green-500': { accent: '#10B981', iconClass: 'text-green-600 dark:text-green-400' },
  'bg-yellow-500': { accent: '#F4D03F', iconClass: 'text-yellow-600 dark:text-yellow-400' },
  'bg-purple-500': { accent: '#8B5CF6', iconClass: 'text-purple-600 dark:text-purple-400' },
  'bg-red-500': { accent: '#D12E2E', iconClass: 'text-red-600 dark:text-red-400' },
};

export default function StatsCard({ icon: Icon, title, value, color, testId, linkTo }) {
  const colorConfig = colorMap[color] || colorMap['bg-blue-500'];
  
  const cardContent = (
    <div 
      className={`kpi-card ${linkTo ? 'cursor-pointer' : ''}`}
      style={{ '--kpi-accent': colorConfig.accent }}
      data-testid={testId}
    >
      <div 
        className={`p-3 rounded-full bg-current/10 mb-3 ${colorConfig.iconClass}`}
        data-testid={`${testId}-icon`}
      >
        <Icon className="w-7 h-7" />
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
