import { Link } from "react-router-dom";

const colorMap = {
  'bg-blue-500': { accent: '#005B96', iconBg: 'bg-blue-100 dark:bg-blue-900/30', iconColor: 'text-blue-600 dark:text-blue-400' },
  'bg-green-500': { accent: '#10B981', iconBg: 'bg-green-100 dark:bg-green-900/30', iconColor: 'text-green-600 dark:text-green-400' },
  'bg-yellow-500': { accent: '#F4D03F', iconBg: 'bg-yellow-100 dark:bg-yellow-900/30', iconColor: 'text-yellow-600 dark:text-yellow-400' },
  'bg-purple-500': { accent: '#8B5CF6', iconBg: 'bg-purple-100 dark:bg-purple-900/30', iconColor: 'text-purple-600 dark:text-purple-400' },
  'bg-red-500': { accent: '#D12E2E', iconBg: 'bg-red-100 dark:bg-red-900/30', iconColor: 'text-red-600 dark:text-red-400' },
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
        className={`w-14 h-14 rounded-full ${colorConfig.iconBg} flex items-center justify-center mb-3`}
        data-testid={`${testId}-icon`}
      >
        <Icon className={`w-7 h-7 ${colorConfig.iconColor}`} />
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
