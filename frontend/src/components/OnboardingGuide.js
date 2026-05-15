import { useState, useEffect } from "react";
import { X, ChevronRight, ChevronLeft, Rocket, Upload, Settings, BarChart3, FileText, Trophy, Tv, CheckCircle2 } from "lucide-react";
import { Button } from "./ui/button";
import { useAuth } from "../context/AuthContext";

const ONBOARDING_STEPS = [
  {
    id: 'welcome',
    title: 'Welcome to Performance Review',
    description: 'Your complete employee performance management system for tracking, analyzing, and improving team performance.',
    icon: Rocket,
    tips: [
      'Track PPA, LBW, Glassware, LSC, and Customer Voice metrics',
      'Generate AI-powered performance reviews',
      'Create beautiful slides for digital signage',
      'Analyze trends and identify top performers'
    ]
  },
  {
    id: 'snapshots',
    title: 'Step 1: Upload Your Data',
    description: 'Start by creating a bi-weekly snapshot with your employee performance data.',
    icon: Upload,
    tips: [
      'Go to Snapshots page and click "New Snapshot"',
      'Set the snapshot date (the date the data represents)',
      'Upload your Excel/CSV file with employee metrics',
      'The system will auto-calculate scores and rankings'
    ],
    link: '/snapshots'
  },
  {
    id: 'settings',
    title: 'Step 2: Configure Settings',
    description: 'Customize benchmarks, weights, and tier thresholds for your location.',
    icon: Settings,
    tips: [
      'Set benchmark targets for each metric (PPA, LBW, etc.)',
      'Adjust metric weights based on priorities',
      'Define A/B/C server score thresholds',
      'Customize slide themes for Yodeck'
    ],
    link: '/settings'
  },
  {
    id: 'dashboard',
    title: 'Step 3: Monitor Dashboard',
    description: 'View real-time team performance at a glance.',
    icon: BarChart3,
    tips: [
      'See total crew, average score, and top performers',
      'Click green/red cards to see detailed breakdowns',
      'Track performance against benchmarks',
      'Data updates automatically from latest snapshot'
    ],
    link: '/'
  },
  {
    id: 'reviews',
    title: 'Step 4: Generate Reviews',
    description: 'Create AI-powered performance reviews for each employee.',
    icon: FileText,
    tips: [
      'Go to Reviews page and select an employee',
      'Click "Generate" to create AI-written review',
      'Reviews include trend charts and specific feedback',
      'Download as PDF for printing or sharing'
    ],
    link: '/reviews'
  },
  {
    id: 'analytics',
    title: 'Step 5: Analyze Trends',
    description: 'Dive deep into performance analytics and trends.',
    icon: Trophy,
    tips: [
      'Compare quarter-over-quarter performance',
      'View performance distribution by metric',
      'Identify areas needing improvement',
      'Track tier distribution changes'
    ],
    link: '/analytics'
  },
  {
    id: 'yodeck',
    title: 'Step 6: Digital Signage',
    description: 'Generate beautiful slides for your Yodeck displays.',
    icon: Tv,
    tips: [
      'Create leaderboard slides for motivation',
      'Generate snapshot overview slides',
      'Customize themes and backgrounds',
      'Download PNG files for Yodeck playlists'
    ],
    link: '/yodeck'
  }
];

// Bump this when ONBOARDING_STEPS changes meaningfully so users see the
// updated tour. localStorage key includes this so old "seen" flags don't
// prevent the new content from showing once.
const ONBOARDING_VERSION = "v2";
const LS_KEY = `hasSeenOnboarding_${ONBOARDING_VERSION}`;

export default function OnboardingGuide({ onComplete }) {
  const { user, loading: authLoading } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [hasSeenOnboarding, setHasSeenOnboarding] = useState(false);

  // Only admins ever see the onboarding. Public/anonymous viewers should
  // never have a modal blocking the read-only dashboards (they were seeing
  // it as "the QR page is blank"). Wait for auth resolution so we don't
  // flash the modal during the initial /auth/me request.
  const isAdmin = !!(user && user.is_admin);

  useEffect(() => {
    if (authLoading) return;
    if (!isAdmin) {
      // Make sure any stale "open" state is closed for non-admins.
      setIsOpen(false);
      setHasSeenOnboarding(false);
      return;
    }
    const seen = localStorage.getItem(LS_KEY);
    if (!seen) {
      setIsOpen(true);
    } else {
      setHasSeenOnboarding(true);
    }
    // Best-effort: clean up legacy keys so we don't accumulate old flags.
    try {
      localStorage.removeItem("hasSeenOnboarding");
    } catch {
      /* localStorage might be disabled in private mode — non-fatal */
    }
  }, [authLoading, isAdmin]);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) {
        handleSkip();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  const handleComplete = () => {
    localStorage.setItem(LS_KEY, 'true');
    setHasSeenOnboarding(true);
    setIsOpen(false);
    if (onComplete) onComplete();
  };

  const handleSkip = () => {
    localStorage.setItem(LS_KEY, 'true');
    setHasSeenOnboarding(true);
    setIsOpen(false);
  };

  const handleReopen = () => {
    setCurrentStep(0);
    setIsOpen(true);
  };

  const nextStep = () => {
    if (currentStep < ONBOARDING_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const prevStep = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const step = ONBOARDING_STEPS[currentStep];
  const Icon = step?.icon;

  if (!isOpen) {
    // Hide the floating launcher entirely for public/anonymous viewers —
    // there's nothing for them to onboard into.
    if (!isAdmin) return null;
    return (
      <button
        onClick={handleReopen}
        className="fixed bottom-6 left-6 z-30 bg-primary text-white p-2.5 rounded-full shadow-lg hover:bg-primary/90 transition-all hover:scale-105 opacity-70 hover:opacity-100"
        title="Quick Start Guide — re-open onboarding"
        data-testid="onboarding-trigger"
      >
        <Rocket className="w-4 h-4" />
      </button>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" data-testid="onboarding-modal">
      <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-primary to-secondary p-6 text-white relative">
          <button
            onClick={handleSkip}
            className="absolute top-3 right-3 text-white bg-white/15 hover:bg-white/25 rounded-full p-1.5 transition-colors"
            data-testid="onboarding-close-btn"
            title="Close (Esc)"
            aria-label="Close onboarding"
          >
            <X className="w-5 h-5" />
          </button>
          
          <div className="flex items-center gap-4 pr-12">
            <div className="w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center flex-shrink-0">
              {Icon && <Icon className="w-7 h-7 text-white" />}
            </div>
            <div className="min-w-0">
              <p className="text-white/70 text-sm">Step {currentStep + 1} of {ONBOARDING_STEPS.length}</p>
              <h2 className="text-xl font-serif font-bold truncate">{step.title}</h2>
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="h-1 bg-gray-200">
          <div 
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${((currentStep + 1) / ONBOARDING_STEPS.length) * 100}%` }}
          />
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-gray-600 mb-4">{step.description}</p>
          
          <ul className="space-y-2 mb-6">
            {step.tips.map((tip) => (
              <li key={tip} className="flex items-start gap-2 text-sm text-gray-700">
                <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                <span>{tip}</span>
              </li>
            ))}
          </ul>

          {step.link && (
            <a 
              href={step.link}
              className="inline-flex items-center gap-2 text-primary hover:underline text-sm font-medium"
            >
              Go to {step.title.replace('Step ', '').split(':')[1]?.trim() || 'Page'}
              <ChevronRight className="w-4 h-4" />
            </a>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={prevStep}
            disabled={currentStep === 0}
            className="text-gray-600"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back
          </Button>

          <div className="flex gap-1">
            {ONBOARDING_STEPS.map((s, idx) => (
              <button
                key={s.title}
                onClick={() => setCurrentStep(idx)}
                className={`w-2 h-2 rounded-full transition-colors ${
                  idx === currentStep ? 'bg-primary' : 'bg-gray-300 hover:bg-gray-400'
                }`}
              />
            ))}
          </div>

          <Button onClick={nextStep} className="bg-primary hover:bg-primary/90">
            {currentStep === ONBOARDING_STEPS.length - 1 ? (
              <>
                Get Started
                <CheckCircle2 className="w-4 h-4 ml-1" />
              </>
            ) : (
              <>
                Next
                <ChevronRight className="w-4 h-4 ml-1" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
