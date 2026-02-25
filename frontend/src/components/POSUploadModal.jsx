import { useState, useRef } from "react";
import { Upload, Camera, FileImage, Loader2, CheckCircle, AlertCircle, X, Download, Edit3, FileText } from "lucide-react";
import { Button } from "./ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

export const POSUploadModal = ({ isOpen, onClose, onDataExtracted, year, quarter }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [fileType, setFileType] = useState(null); // 'image' or 'pdf'
  const [extractedData, setExtractedData] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const file = e.dataTransfer.files[0];
    if (file) {
      await processFile(file);
    }
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (file) {
      await processFile(file);
    }
  };

  const processFile = async (file) => {
    // Validate file type
    const validImageTypes = ["image/jpeg", "image/png", "image/webp"];
    const validPdfTypes = ["application/pdf"];
    const allValidTypes = [...validImageTypes, ...validPdfTypes];
    
    if (!allValidTypes.includes(file.type)) {
      setError("Please upload a JPEG, PNG, WEBP image or PDF file");
      return;
    }

    const isPdf = validPdfTypes.includes(file.type);
    const maxSize = isPdf ? 20 * 1024 * 1024 : 10 * 1024 * 1024; // 20MB for PDF, 10MB for images

    // Validate file size
    if (file.size > maxSize) {
      setError(`File too large. Maximum size is ${maxSize / (1024 * 1024)}MB`);
      return;
    }

    setFileType(isPdf ? 'pdf' : 'image');

    // Create preview (only for images)
    if (!isPdf) {
      const reader = new FileReader();
      reader.onload = (e) => setPreviewUrl(e.target.result);
      reader.readAsDataURL(file);
    } else {
      setPreviewUrl(null); // No preview for PDFs
    }

    // Process with OCR
    setIsProcessing(true);
    setError(null);
    setExtractedData(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(`${API}/api/v2/pos-ocr/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      if (response.data.success) {
        setExtractedData(response.data);
        toast.success(`Extracted ${response.data.employee_count} employees from POS report`);
      } else {
        setError(response.data.error || "Failed to extract data from image");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to process image");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConfirmData = () => {
    if (extractedData && onDataExtracted) {
      onDataExtracted(extractedData.employees);
      handleClose();
    }
  };

  const handleClose = () => {
    setPreviewUrl(null);
    setExtractedData(null);
    setError(null);
    setIsProcessing(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-slate-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col border border-slate-700">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
              <Camera className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">POS Report Scanner</h2>
              <p className="text-sm text-slate-400">Upload Aloha POS report image for {quarter} {year}</p>
            </div>
          </div>
          <button 
            onClick={handleClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {!extractedData ? (
            <div className="space-y-6">
              {/* Upload Area */}
              <div
                className={`
                  relative border-2 border-dashed rounded-xl p-8 transition-all text-center
                  ${isDragging ? "border-primary bg-primary/10" : "border-slate-600 hover:border-primary/50"}
                  ${isProcessing ? "pointer-events-none opacity-50" : "cursor-pointer"}
                `}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !isProcessing && fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={handleFileSelect}
                />

                {isProcessing ? (
                  <div className="flex flex-col items-center gap-4">
                    <Loader2 className="w-12 h-12 text-primary animate-spin" />
                    <div>
                      <p className="text-lg font-semibold text-white">Processing POS Report...</p>
                      <p className="text-sm text-slate-400">AI is extracting employee data</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-4">
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                      <Upload className="w-8 h-8 text-primary" />
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-white">Drop POS report image here</p>
                      <p className="text-sm text-slate-400">or click to browse • JPEG, PNG, WEBP up to 10MB</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Preview */}
              {previewUrl && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-slate-400">Preview:</p>
                  <div className="relative rounded-xl overflow-hidden border border-slate-600 bg-slate-900">
                    <img 
                      src={previewUrl} 
                      alt="POS Report Preview" 
                      className="w-full max-h-64 object-contain"
                    />
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-red-500">Extraction Failed</p>
                    <p className="text-sm text-red-400">{error}</p>
                  </div>
                </div>
              )}

              {/* Tips */}
              <div className="bg-slate-700/50 rounded-xl p-4">
                <p className="text-sm font-medium text-white mb-2">Tips for best results:</p>
                <ul className="text-sm text-slate-300 space-y-1">
                  <li>• Ensure the report is clearly visible and not blurry</li>
                  <li>• Include all columns: Employee Name, PPA, LBW, Glassware, Guest Count</li>
                  <li>• Screenshot or photo of the full report works best</li>
                  <li>• Avoid cropping important data columns</li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Success Header */}
              <div className="flex items-center gap-3 p-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                <CheckCircle className="w-6 h-6 text-green-500" />
                <div>
                  <p className="font-medium text-green-400">
                    Successfully extracted {extractedData.employee_count} employees
                  </p>
                  {extractedData.extraction_notes && (
                    <p className="text-sm text-green-400/80">{extractedData.extraction_notes}</p>
                  )}
                </div>
              </div>

              {/* Report Info */}
              {(extractedData.report_date || extractedData.report_type) && (
                <div className="flex gap-4">
                  {extractedData.report_date && (
                    <div className="px-3 py-2 bg-slate-700 rounded-lg">
                      <span className="text-xs text-slate-400">Date:</span>
                      <span className="ml-2 text-sm font-medium text-white">{extractedData.report_date}</span>
                    </div>
                  )}
                  {extractedData.report_type && (
                    <div className="px-3 py-2 bg-slate-700 rounded-lg">
                      <span className="text-xs text-slate-400">Type:</span>
                      <span className="ml-2 text-sm font-medium text-white capitalize">{extractedData.report_type}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Extracted Data Table */}
              <div className="border border-slate-600 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-700">
                      <tr>
                        <th className="px-4 py-3 text-left font-semibold text-white">Employee</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">PPA</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">LBW/Guest</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">Glass/Guest</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">Guests</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">Net Sales</th>
                        <th className="px-4 py-3 text-right font-semibold text-white">G/LSC</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-600">
                      {extractedData.employees.map((emp, idx) => (
                        <tr key={idx} className="hover:bg-slate-700/50">
                          <td className="px-4 py-3 font-medium text-white">{emp.name}</td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.ppa ? `$${emp.ppa.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.lbw_per_guest ? `$${emp.lbw_per_guest.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.glassware_per_guest ? `$${emp.glassware_per_guest.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.guest_count || "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.net_sales ? `$${emp.net_sales.toLocaleString()}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-300">
                            {emp.guests_per_lsc ? emp.guests_per_lsc.toFixed(0) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Preview (collapsed) */}
              {previewUrl && (
                <details className="group">
                  <summary className="cursor-pointer text-sm text-slate-400 hover:text-white">
                    Show original image
                  </summary>
                  <div className="mt-2 rounded-xl overflow-hidden border border-slate-600">
                    <img src={previewUrl} alt="Original" className="w-full max-h-48 object-contain" />
                  </div>
                </details>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-700 bg-slate-800/50">
          <Button variant="outline" onClick={handleClose} className="border-slate-600 text-slate-300 hover:bg-slate-700">
            Cancel
          </Button>
          
          {extractedData ? (
            <div className="flex gap-3">
              <Button 
                variant="outline" 
                onClick={() => {
                  setExtractedData(null);
                  setPreviewUrl(null);
                }}
                className="border-slate-600 text-slate-300 hover:bg-slate-700"
              >
                <Edit3 className="w-4 h-4 mr-2" />
                Upload Different Image
              </Button>
              <Button onClick={handleConfirmData} className="bg-primary hover:bg-primary/90">
                <CheckCircle className="w-4 h-4 mr-2" />
                Use This Data
              </Button>
            </div>
          ) : (
            <p className="text-sm text-slate-400">
              Upload a POS report image to extract employee data
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default POSUploadModal;
