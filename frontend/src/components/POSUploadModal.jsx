import { useState, useRef } from "react";
import { Upload, Camera, FileImage, Loader2, CheckCircle, AlertCircle, X, Download, Edit3 } from "lucide-react";
import { Button } from "./ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

export const POSUploadModal = ({ isOpen, onClose, onDataExtracted, year, quarter }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
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
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) {
      setError("Please upload a JPEG, PNG, or WEBP image");
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large. Maximum size is 10MB");
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onload = (e) => setPreviewUrl(e.target.result);
    reader.readAsDataURL(file);

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
      <div className="bg-card rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center">
              <Camera className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">POS Report Scanner</h2>
              <p className="text-sm text-muted-foreground">Upload Aloha POS report image for {quarter} {year}</p>
            </div>
          </div>
          <button 
            onClick={handleClose}
            className="p-2 hover:bg-muted rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-muted-foreground" />
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
                  ${isDragging ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"}
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
                      <p className="text-lg font-semibold text-foreground">Processing POS Report...</p>
                      <p className="text-sm text-muted-foreground">AI is extracting employee data</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-4">
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                      <Upload className="w-8 h-8 text-primary" />
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-foreground">Drop POS report image here</p>
                      <p className="text-sm text-muted-foreground">or click to browse • JPEG, PNG, WEBP up to 10MB</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Preview */}
              {previewUrl && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-muted-foreground">Preview:</p>
                  <div className="relative rounded-xl overflow-hidden border border-border bg-muted">
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
              <div className="bg-muted/50 rounded-xl p-4">
                <p className="text-sm font-medium text-foreground mb-2">Tips for best results:</p>
                <ul className="text-sm text-muted-foreground space-y-1">
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
                  <p className="font-medium text-green-500">
                    Successfully extracted {extractedData.employee_count} employees
                  </p>
                  {extractedData.extraction_notes && (
                    <p className="text-sm text-green-400">{extractedData.extraction_notes}</p>
                  )}
                </div>
              </div>

              {/* Report Info */}
              {(extractedData.report_date || extractedData.report_type) && (
                <div className="flex gap-4">
                  {extractedData.report_date && (
                    <div className="px-3 py-2 bg-muted rounded-lg">
                      <span className="text-xs text-muted-foreground">Date:</span>
                      <span className="ml-2 text-sm font-medium text-foreground">{extractedData.report_date}</span>
                    </div>
                  )}
                  {extractedData.report_type && (
                    <div className="px-3 py-2 bg-muted rounded-lg">
                      <span className="text-xs text-muted-foreground">Type:</span>
                      <span className="ml-2 text-sm font-medium text-foreground capitalize">{extractedData.report_type}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Extracted Data Table */}
              <div className="border border-border rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted">
                      <tr>
                        <th className="px-4 py-3 text-left font-semibold text-foreground">Employee</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">PPA</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">LBW/Guest</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">Glass/Guest</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">Guests</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">Net Sales</th>
                        <th className="px-4 py-3 text-right font-semibold text-foreground">G/LSC</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {extractedData.employees.map((emp, idx) => (
                        <tr key={idx} className="hover:bg-muted/50">
                          <td className="px-4 py-3 font-medium text-foreground">{emp.name}</td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {emp.ppa ? `$${emp.ppa.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {emp.lbw_per_guest ? `$${emp.lbw_per_guest.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {emp.glassware_per_guest ? `$${emp.glassware_per_guest.toFixed(2)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {emp.guest_count || "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {emp.net_sales ? `$${emp.net_sales.toLocaleString()}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
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
                  <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                    Show original image
                  </summary>
                  <div className="mt-2 rounded-xl overflow-hidden border border-border">
                    <img src={previewUrl} alt="Original" className="w-full max-h-48 object-contain" />
                  </div>
                </details>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-muted/30">
          <Button variant="outline" onClick={handleClose}>
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
            <p className="text-sm text-muted-foreground">
              Upload a POS report image to extract employee data
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default POSUploadModal;
