import { useState } from "react";
import { 
  Calculator, TrendingUp, Award, MessageSquare, AlertTriangle,
  ChevronDown, ChevronUp, HelpCircle, Target, DollarSign,
  Users, Star, ThumbsUp, ThumbsDown, Minus, Building2
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";

export default function ScoringGuide() {
  const [expandedSections, setExpandedSections] = useState(new Set(['overview']));

  const toggleSection = (section) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev);
      if (newSet.has(section)) {
        newSet.delete(section);
      } else {
        newSet.add(section);
      }
      return newSet;
    });
  };

  const Section = ({ id, title, icon: Icon, children, color = "blue" }) => {
    const isExpanded = expandedSections.has(id);
    const colorClasses = {
      blue: "from-blue-500/20 to-blue-600/20 border-blue-500/30",
      green: "from-green-500/20 to-green-600/20 border-green-500/30",
      purple: "from-purple-500/20 to-purple-600/20 border-purple-500/30",
      amber: "from-amber-500/20 to-amber-600/20 border-amber-500/30",
      red: "from-red-500/20 to-red-600/20 border-red-500/30",
      pink: "from-pink-500/20 to-pink-600/20 border-pink-500/30"
    };

    return (
      <Card className={`bg-gradient-to-br ${colorClasses[color]} border overflow-hidden`}>
        <CardHeader 
          className="cursor-pointer hover:bg-white/5 transition-colors"
          onClick={() => toggleSection(id)}
        >
          <CardTitle className="flex items-center justify-between text-white">
            <div className="flex items-center gap-3">
              <Icon className="w-5 h-5" />
              {title}
            </div>
            {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </CardTitle>
        </CardHeader>
        {isExpanded && (
          <CardContent className="pt-0">
            {children}
          </CardContent>
        )}
      </Card>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Calculator className="w-6 h-6 text-white" />
            </div>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-white mb-2">Scoring Guide</h1>
          <p className="text-slate-400">How employee performance scores are calculated</p>
        </div>

        {/* Quick Summary Card */}
        <Card className="bg-gradient-to-r from-slate-800 to-slate-900 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-center mb-4">
              <h2 className="text-xl font-bold text-white mb-2">Score Formula</h2>
              <div className="bg-slate-950 rounded-lg p-4 font-mono text-sm">
                <span className="text-blue-400">Total</span>
                <span className="text-slate-400"> = </span>
                <span className="text-green-400">POS Metrics</span>
                <span className="text-slate-400"> + </span>
                <span className="text-amber-400">Metric Bonus</span>
                <span className="text-slate-400"> + </span>
                <span className="text-purple-400">Customer Voice</span>
                <span className="text-slate-400"> + </span>
                <span className="text-pink-400">RT Bonus</span>
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
              <div className="bg-green-500/10 rounded-lg p-3 border border-green-500/20">
                <p className="text-2xl font-bold text-green-400">75</p>
                <p className="text-xs text-slate-400">POS Max</p>
              </div>
              <div className="bg-amber-500/10 rounded-lg p-3 border border-amber-500/20">
                <p className="text-2xl font-bold text-amber-400">20</p>
                <p className="text-xs text-slate-400">Metric Bonus Max</p>
              </div>
              <div className="bg-purple-500/10 rounded-lg p-3 border border-purple-500/20">
                <p className="text-2xl font-bold text-purple-400">∞</p>
                <p className="text-xs text-slate-400">Cust. Voice</p>
              </div>
              <div className="bg-pink-500/10 rounded-lg p-3 border border-pink-500/20">
                <p className="text-2xl font-bold text-pink-400">15</p>
                <p className="text-xs text-slate-400">RT Max</p>
              </div>
              <div className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20 col-span-2 md:col-span-1">
                <p className="text-2xl font-bold text-blue-400">110+</p>
                <p className="text-xs text-slate-400">Top Score</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Detailed Sections */}
        <div className="space-y-4">
          
          {/* POS Metrics */}
          <Section id="pos" title="Weighted POS Metrics (75 pts max)" icon={DollarSign} color="green">
            <p className="text-slate-300 mb-4">
              Core performance metrics from your POS system. Each metric is compared to a benchmark and weighted.
            </p>
            
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-600">
                    <th className="text-left py-2 text-slate-300">Metric</th>
                    <th className="text-center py-2 text-slate-300">Weight</th>
                    <th className="text-center py-2 text-slate-300">Max Pts</th>
                    <th className="text-center py-2 text-slate-300">Benchmark</th>
                  </tr>
                </thead>
                <tbody className="text-slate-400">
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">PPA (Per Person Avg)</td>
                    <td className="text-center">25%</td>
                    <td className="text-center text-green-400">25 pts</td>
                    <td className="text-center">$55.00</td>
                  </tr>
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">LSC (Loyalty Sales)</td>
                    <td className="text-center">25%</td>
                    <td className="text-center text-green-400">25 pts</td>
                    <td className="text-center">1:1 ratio</td>
                  </tr>
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">LBW (Liquor/Beer/Wine)</td>
                    <td className="text-center">15%</td>
                    <td className="text-center text-green-400">15 pts</td>
                    <td className="text-center">$8.00/guest</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-medium text-white">Glassware</td>
                    <td className="text-center">10%</td>
                    <td className="text-center text-green-400">10 pts</td>
                    <td className="text-center">$1.25/guest</td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <div className="mt-4 p-3 bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-400">
                <strong className="text-slate-300">Calculation:</strong> Score = (Your Value ÷ Benchmark) × 100, capped at 100%, then multiplied by weight.
              </p>
            </div>
          </Section>

          {/* Metric Bonuses */}
          <Section id="bonuses" title="Metric Bonuses (20 pts max)" icon={Award} color="amber">
            <p className="text-slate-300 mb-4">
              Extra points for exceeding benchmarks. Each metric can earn up to 5 bonus points.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="bg-slate-800/50 rounded-lg p-4">
                <h4 className="font-semibold text-white mb-2">Bonus Scale</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">At 100% of benchmark</span>
                    <span className="text-slate-300">0 pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">At 110% of benchmark</span>
                    <span className="text-amber-400">2.5 pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">At 120%+ of benchmark</span>
                    <span className="text-amber-400 font-bold">5 pts (max)</span>
                  </div>
                </div>
              </div>
              
              <div className="bg-slate-800/50 rounded-lg p-4">
                <h4 className="font-semibold text-white mb-2">Max by Metric</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">PPA Bonus</span>
                    <span className="text-amber-400">5 pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">LSC Bonus</span>
                    <span className="text-amber-400">5 pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">LBW Bonus</span>
                    <span className="text-amber-400">5 pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Glassware Bonus</span>
                    <span className="text-amber-400">5 pts</span>
                  </div>
                </div>
              </div>
            </div>
          </Section>

          {/* Customer Voice */}
          <Section id="cv" title="Customer Voice - UNCAPPED" icon={MessageSquare} color="purple">
            <p className="text-slate-300 mb-4">
              Survey feedback scoring. <strong className="text-purple-400">This is uncapped to heavily reward great service!</strong>
            </p>
            
            <div className="space-y-4">
              <div className="bg-slate-800/50 rounded-lg p-4">
                <h4 className="font-semibold text-white mb-3 flex items-center gap-2">
                  <Users className="w-4 h-4 text-purple-400" />
                  Survey Points (NO CAP)
                </h4>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-2 bg-green-500/10 rounded border border-green-500/20">
                    <ThumbsUp className="w-5 h-5 text-green-400" />
                    <div>
                      <p className="text-white font-medium">Promoter (9-10 rating)</p>
                      <p className="text-green-400 font-bold">+0.5 pts each</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-2 bg-slate-700/50 rounded">
                    <Minus className="w-5 h-5 text-slate-400" />
                    <div>
                      <p className="text-white font-medium">Passive (7-8 rating)</p>
                      <p className="text-slate-400">0 pts</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-2 bg-red-500/10 rounded border border-red-500/20">
                    <ThumbsDown className="w-5 h-5 text-red-400" />
                    <div>
                      <p className="text-white font-medium">Detractor (1-6 rating)</p>
                      <p className="text-red-400 font-bold">-1 pt each</p>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="bg-purple-900/30 border border-purple-500/30 rounded-lg p-4">
                <p className="text-sm text-purple-300">
                  <strong>Formula:</strong> Customer Voice = (Promoters × 0.5) - (Detractors × 1)
                </p>
                <p className="text-xs text-slate-400 mt-2">
                  This score is displayed as a combined total on all leaderboards and employee cards.
                </p>
              </div>
            </div>
          </Section>

          {/* Review Tracker */}
          <Section id="rt" title="Review Tracker (15 pts max)" icon={Star} color="pink">
            <p className="text-slate-300 mb-4">
              Points for being mentioned in online reviews (Yelp, Google, TripAdvisor, etc.)
            </p>
            
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-sm text-slate-400 mb-3">
                <strong className="text-white">Formula:</strong> 0.5 pts per mention, capped at 30 mentions
              </p>
              <div className="grid grid-cols-4 gap-2 text-center text-sm">
                <div className="bg-slate-700/50 rounded p-2">
                  <p className="text-pink-400 font-bold">10</p>
                  <p className="text-slate-500">= 5 pts</p>
                </div>
                <div className="bg-slate-700/50 rounded p-2">
                  <p className="text-pink-400 font-bold">20</p>
                  <p className="text-slate-500">= 10 pts</p>
                </div>
                <div className="bg-slate-700/50 rounded p-2">
                  <p className="text-pink-400 font-bold">30</p>
                  <p className="text-slate-500">= 15 pts</p>
                </div>
                <div className="bg-slate-700/50 rounded p-2">
                  <p className="text-pink-400 font-bold">40+</p>
                  <p className="text-slate-500">= 15 pts (max)</p>
                </div>
              </div>
            </div>
          </Section>

          {/* DAR Penalties */}
          <Section id="dar" title="DAR Penalties (Admin-Only)" icon={AlertTriangle} color="red">
            <p className="text-slate-300 mb-4">
              Disciplinary Action Reports reduce the final score. <strong className="text-red-400">Not visible in public rankings.</strong>
            </p>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/20 text-center">
                <p className="text-white font-medium">Written Warning</p>
                <p className="text-2xl font-bold text-red-400">-3 pts</p>
                <p className="text-xs text-slate-500">each</p>
              </div>
              <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/20 text-center">
                <p className="text-white font-medium">Suspension</p>
                <p className="text-2xl font-bold text-red-400">-5 pts</p>
                <p className="text-xs text-slate-500">each</p>
              </div>
            </div>
          </Section>

          {/* Store Health */}
          <Section id="store" title="Store Health Index" icon={Building2} color="blue">
            <p className="text-slate-300 mb-4">
              The Store Performance Index aggregates all employee scores into 4 categories.
            </p>
            
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-600">
                    <th className="text-left py-2 text-slate-300">Category</th>
                    <th className="text-center py-2 text-slate-300">Weight</th>
                    <th className="text-left py-2 text-slate-300">Data Source</th>
                  </tr>
                </thead>
                <tbody className="text-slate-400">
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">Sales Execution</td>
                    <td className="text-center">25%</td>
                    <td>Average PPA scores</td>
                  </tr>
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">Upsell Performance</td>
                    <td className="text-center">25%</td>
                    <td>Average LBW + Glassware</td>
                  </tr>
                  <tr className="border-b border-slate-700">
                    <td className="py-2 font-medium text-white">Loyalty Engagement</td>
                    <td className="text-center">20%</td>
                    <td>Average LSC scores</td>
                  </tr>
                  <tr>
                    <td className="py-2 font-medium text-white">Guest Experience</td>
                    <td className="text-center">30%</td>
                    <td>NPS (70%) + RT mentions (30%)</td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <div className="mt-4 grid grid-cols-4 gap-2 text-center text-xs">
              <div className="bg-green-500/20 rounded p-2 border border-green-500/30">
                <p className="font-bold text-green-400">85+</p>
                <p className="text-green-300">Excellent</p>
              </div>
              <div className="bg-blue-500/20 rounded p-2 border border-blue-500/30">
                <p className="font-bold text-blue-400">70-84</p>
                <p className="text-blue-300">Good</p>
              </div>
              <div className="bg-amber-500/20 rounded p-2 border border-amber-500/30">
                <p className="font-bold text-amber-400">55-69</p>
                <p className="text-amber-300">Needs Work</p>
              </div>
              <div className="bg-red-500/20 rounded p-2 border border-red-500/30">
                <p className="font-bold text-red-400">&lt;55</p>
                <p className="text-red-300">Critical</p>
              </div>
            </div>
          </Section>

          {/* Performance Tiers */}
          <Section id="tiers" title="Performance Tiers" icon={TrendingUp} color="blue">
            <p className="text-slate-300 mb-4">
              Employees are ranked by score and assigned tiers based on percentile.
            </p>
            
            <div className="space-y-2">
              <div className="flex items-center justify-between p-3 bg-green-500/10 rounded-lg border border-green-500/20">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  <span className="text-white font-medium">Top Performer</span>
                </div>
                <span className="text-green-400">Top 25%</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-blue-500/10 rounded-lg border border-blue-500/20">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="text-white font-medium">Above Average</span>
                </div>
                <span className="text-blue-400">51-75%</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-amber-500/10 rounded-lg border border-amber-500/20">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                  <span className="text-white font-medium">Below Average</span>
                </div>
                <span className="text-amber-400">26-50%</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-red-500/10 rounded-lg border border-red-500/20">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500"></div>
                  <span className="text-white font-medium">Needs Improvement</span>
                </div>
                <span className="text-red-400">Bottom 25%</span>
              </div>
            </div>
          </Section>

        </div>

        {/* Footer */}
        <div className="text-center text-slate-500 text-sm pt-4">
          <p>Q1 2026 Scoring Model • Bubba Gump Shrimp Co.</p>
        </div>
      </div>
    </div>
  );
}
