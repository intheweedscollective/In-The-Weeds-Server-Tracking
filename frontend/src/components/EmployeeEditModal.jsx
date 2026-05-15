import { X, Plus, Pencil } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

/**
 * EmployeeEditModal - Add/Edit employee form modal
 * Extracted from EmployeeList.js to reduce component size
 */
export const EmployeeEditModal = ({
  isOpen,
  editingEmployee,
  formData,
  saving,
  onFormChange,
  onSave,
  onClose
}) => {
  if (!isOpen) return null;

  const handleFormChange = (field, value) => {
    onFormChange(field, value);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4" onClick={onClose}>
      <div className="bg-slate-800 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-700 p-4 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            {editingEmployee ? <Pencil className="w-5 h-5 text-white" /> : <Plus className="w-5 h-5 text-white" />}
            <h2 className="text-lg font-serif font-bold text-white">
              {editingEmployee ? `Edit ${editingEmployee.name}` : 'Add New Employee'}
            </h2>
          </div>
          <button onClick={onClose} className="text-white hover:bg-slate-800/20 rounded-full p-2">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-4 overflow-y-auto flex-1">
          {/* Basic Info */}
          <BasicInfoSection formData={formData} onChange={handleFormChange} />

          {/* Sales Data */}
          <SalesDataSection formData={formData} onChange={handleFormChange} />

          {/* LSC Count */}
          <LSCSection formData={formData} onChange={handleFormChange} />

          {/* Customer Voice */}
          <CustomerVoiceSection formData={formData} onChange={handleFormChange} />
        </div>
        
        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-slate-700 bg-slate-800/50 flex-shrink-0">
          <Button 
            variant="outline" 
            onClick={onClose}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            Cancel
          </Button>
          <Button
            onClick={onSave}
            disabled={saving}
            className="bg-green-600 hover:bg-green-700"
          >
            {saving ? 'Saving...' : 'Save Employee'}
          </Button>
        </div>
      </div>
    </div>
  );
};

/**
 * Basic information section
 */
const BasicInfoSection = ({ formData, onChange }) => (
  <div className="mb-4">
    <h3 className="font-semibold text-slate-200 mb-2">Basic Information</h3>
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Display Name *</label>
        <Input
          value={formData.name}
          onChange={(e) => onChange('name', e.target.value)}
          placeholder="Name shown in dashboards"
          className="w-full"
        />
        <p className="text-xs text-slate-500 mt-1">Shown in reports & leaderboards</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Job Title</label>
        <select
          value={formData.job_title}
          onChange={(e) => onChange('job_title', e.target.value)}
          className="w-full px-3 py-2 border border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-slate-700 text-slate-200"
        >
          <option value="server">Server</option>
          <option value="bartender">Bartender</option>
          <option value="trainer">Trainer</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Report Name (POS)</label>
        <Input
          value={formData.report_name}
          onChange={(e) => onChange('report_name', e.target.value)}
          placeholder="Name in POS system"
          className="w-full bg-slate-800"
        />
        <p className="text-xs text-slate-500 mt-1">Used for matching uploads</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Aliases (Nicknames)</label>
        <Input
          type="text"
          value={formData.aliases}
          onChange={(e) => onChange('aliases', e.target.value)}
          placeholder="Trey, T.Q. (comma-separated)"
          className="w-full"
        />
        <p className="text-xs text-slate-500 mt-1">Additional names for matching</p>
      </div>
    </div>
  </div>
);

/**
 * Sales data section with LBW breakdown
 */
const SalesDataSection = ({ formData, onChange }) => {
  const handleLBWChange = (field, value) => {
    const val = parseFloat(value) || 0;
    onChange(field, val);
    
    // Auto-calculate LBW total
    const liquor = field === 'liquor_sales' ? val : (formData.liquor_sales || 0);
    const beer = field === 'beer_sales' ? val : (formData.beer_sales || 0);
    const wine = field === 'wine_sales' ? val : (formData.wine_sales || 0);
    onChange('lbw', liquor + beer + wine);
  };

  return (
    <div className="mb-4">
      <h3 className="font-semibold text-slate-200 mb-3">Sales Data</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Guests</label>
          <Input
            type="number"
            value={formData.guests}
            onChange={(e) => onChange('guests', parseFloat(e.target.value) || 0)}
            placeholder="0"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Net Sales ($)</label>
          <Input
            type="number"
            value={formData.net_sales}
            onChange={(e) => onChange('net_sales', parseFloat(e.target.value) || 0)}
            placeholder="0"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-cyan-400 mb-1">PPA ($)</label>
          <Input
            type="number"
            step="0.01"
            value={formData.ppa}
            onChange={(e) => onChange('ppa', parseFloat(e.target.value) || 0)}
            placeholder="0.00"
            className="border-cyan-200"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Glassware Total ($)</label>
          <Input
            type="number"
            value={formData.glassware_sales}
            onChange={(e) => onChange('glassware_sales', parseFloat(e.target.value) || 0)}
            placeholder="0"
          />
        </div>
      </div>
      
      {/* LBW Breakdown */}
      <div className="bg-slate-700/30 p-4 rounded-lg">
        <h4 className="text-sm font-medium text-amber-400 mb-3">LBW Breakdown (Liquor + Beer + Wine)</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Liquor ($)</label>
            <Input
              type="number"
              value={formData.liquor_sales}
              onChange={(e) => handleLBWChange('liquor_sales', e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Beer ($)</label>
            <Input
              type="number"
              value={formData.beer_sales}
              onChange={(e) => handleLBWChange('beer_sales', e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Wine ($)</label>
            <Input
              type="number"
              value={formData.wine_sales}
              onChange={(e) => handleLBWChange('wine_sales', e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-amber-400 mb-1">LBW Total ($)</label>
            <Input
              type="number"
              value={formData.lbw}
              onChange={(e) => onChange('lbw', parseFloat(e.target.value) || 0)}
              placeholder="0"
              className="border-amber-200 bg-slate-700"
            />
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * LSC (Loyalty Signups) section
 */
const LSCSection = ({ formData, onChange }) => (
  <div className="mb-4">
    <h3 className="font-semibold text-slate-200 mb-3">LSC (Loyalty Signups)</h3>
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Loyalty Sales ($)</label>
        <Input
          type="number"
          value={formData.loyalty_sales}
          onChange={(e) => {
            const val = parseFloat(e.target.value) || 0;
            onChange('loyalty_sales', val);
            // Auto-calculate LSC count ($25 per signup)
            onChange('lsc_count', Math.round(val / 25));
          }}
          placeholder="0"
        />
        <p className="text-xs text-slate-500 mt-1">Each $25 = 1 LSC</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-green-400 mb-1">LSC Count</label>
        <Input
          type="number"
          value={formData.lsc_count}
          onChange={(e) => onChange('lsc_count', parseInt(e.target.value) || 0)}
          placeholder="0"
          className="border-green-200"
        />
      </div>
    </div>
  </div>
);

/**
 * Customer Voice & Reviews section
 */
const CustomerVoiceSection = ({ formData, onChange }) => (
  <div className="mb-4">
    <h3 className="font-semibold text-slate-200 mb-3">Customer Voice (Combined Score)</h3>
    
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
      <div>
        <label className="block text-sm font-medium text-green-400 mb-1">Promoters (9-10)</label>
        <Input
          type="number"
          min="0"
          step="1"
          value={formData.cv_promoters}
          onChange={(e) => onChange('cv_promoters', Math.max(0, parseInt(e.target.value) || 0))}
          placeholder="0"
          className="border-green-200"
        />
        <p className="text-xs text-green-600 mt-1">+1 pt each</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Passives (7-8)</label>
        <Input
          type="number"
          min="0"
          step="1"
          value={formData.cv_passives}
          onChange={(e) => onChange('cv_passives', Math.max(0, parseInt(e.target.value) || 0))}
          placeholder="0"
        />
        <p className="text-xs text-slate-500 mt-1">No pts</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-red-400 mb-1">Detractors (1-6)</label>
        <Input
          type="number"
          min="0"
          step="1"
          value={formData.cv_detractors}
          onChange={(e) => onChange('cv_detractors', Math.max(0, parseInt(e.target.value) || 0))}
          placeholder="0"
          className="border-red-200"
        />
        <p className="text-xs text-red-600 mt-1">−2 pts each</p>
      </div>
      <div>
        <label className="block text-sm font-medium text-purple-400 mb-1">RT Mentions</label>
        <Input
          type="number"
          min="0"
          step="1"
          value={formData.review_mentions}
          onChange={(e) => onChange('review_mentions', Math.max(0, parseInt(e.target.value) || 0))}
          placeholder="0"
          className="border-purple-200"
        />
        <p className="text-xs text-purple-600 mt-1">{(0.3).toFixed(1)} pts per mention (max 20)</p>
      </div>
    </div>
  </div>
);

export default EmployeeEditModal;
