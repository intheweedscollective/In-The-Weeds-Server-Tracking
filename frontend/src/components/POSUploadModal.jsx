import { useState, useRef } from "react";
import { Upload, Camera, FileImage, Loader2, CheckCircle, AlertCircle, X, Download, Edit3, FileText, Files, Pencil } from "lucide-react";
import { Button } from "./ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

// Editable cell component for inline editing (numbers)
const EditableCell = ({ value, format, isMissing, onChange }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value || '');
  
  const handleSave = () => {
    let parsedValue = null;
    if (editValue !== '' && editValue !== null) {
      const numVal = parseFloat(String(editValue).replace(/[$,]/g, ''));
      if (!isNaN(numVal)) {
        parsedValue = numVal;
      }
    }
    onChange(parsedValue);
    setIsEditing(false);
  };
  
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') {
      setEditValue(value || '');
      setIsEditing(false);
    }
  };
  
  if (isEditing) {
    return (
      <input
        type="text"
        inputMode="decimal"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className="w-16 px-1 py-1 text-right text-xs bg-slate-600 border border-primary rounded text-white focus:outline-none"
        autoFocus
      />
    );
  }
  
  const displayValue = value != null 
    ? (format === 'currency' ? `$${value.toFixed(2)}` : value.toLocaleString())
    : null;
  
  return (
    <button
      onClick={() => {
        setEditValue(value || '');
        setIsEditing(true);
      }}
      className={`inline-block px-1 py-0.5 rounded text-xs transition-colors ${
        isMissing 
          ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/50' 
          : 'text-slate-300 hover:bg-slate-600'
      }`}
    >
      {displayValue || '—'}
    </button>
  );
};

// Editable name cell component (text)
const EditableNameCell = ({ value, onChange }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value || '');
  
  const handleSave = () => {
    onChange(editValue.trim() || value);
    setIsEditing(false);
  };
  
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') {
      setEditValue(value || '');
      setIsEditing(false);
    }
  };
  
  if (isEditing) {
    return (
      <input
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className="w-24 px-1 py-1 text-left text-xs bg-slate-600 border border-primary rounded text-white focus:outline-none"
        autoFocus
      />
    );
  }
  
  return (
    <button
      onClick={() => {
        setEditValue(value || '');
        setIsEditing(true);
      }}
      className="text-left text-white hover:bg-slate-600 px-1 py-0.5 rounded transition-colors truncate max-w-[100px] block"
      title={value}
    >
      {value || '—'}
    </button>
  );
};

export const POSUploadModal = ({ isOpen, onClose, onDataExtracted, year, quarter }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState(""); // Shows progress
  const [previewUrl, setPreviewUrl] = useState(null);
  const [fileType, setFileType] = useState(null); // 'image', 'pdf', or 'multi'
  const [extractedData, setExtractedData] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);
  
  // Function to update an employee field
  const updateEmployeeField = (employeeIndex, field, value) => {
    if (!extractedData) return;
    
    const updatedEmployees = [...extractedData.employees];
    updatedEmployees[employeeIndex] = {
      ...updatedEmployees[employeeIndex],
      [field]: value
    };
    
    // Recalculate derived fields if needed
    const emp = updatedEmployees[employeeIndex];
    if (field === 'net_sales' || field === 'guest_count') {
      // Recalculate PPA
      if (emp.net_sales && emp.guest_count && emp.guest_count > 0) {
        updatedEmployees[employeeIndex].ppa = emp.net_sales / emp.guest_count;
      }
    }
    
    setExtractedData({
      ...extractedData,
      employees: updatedEmployees
    });
    
    toast.success(`Updated ${emp.name}'s ${field.replace(/_/g, ' ')}`);
  };

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
    
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 1) {
      await processMultipleFiles(files);
    } else if (files.length === 1) {
      await processFile(files[0]);
    }
  };

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 1) {
      await processMultipleFiles(files);
    } else if (files.length === 1) {
      await processFile(files[0]);
    }
  };

  // Process multiple files (batch upload)
  const processMultipleFiles = async (files) => {
    const validImageTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
    
    // Filter to only valid image files
    const validFiles = files.filter(f => validImageTypes.includes(f.type));
    
    if (validFiles.length === 0) {
      setError("No valid image files found. Please upload JPEG, PNG, WEBP, or HEIC images.");
      return;
    }

    setFileType('multi');
    setIsProcessing(true);
    setError(null);
    setExtractedData(null);
    setPreviewUrl(null);

    const allEmployees = [];
    const errors = [];
    let reportDate = null;

    try {
      for (let i = 0; i < validFiles.length; i++) {
        const file = validFiles[i];
        setProcessingStatus(`Processing ${i + 1} of ${validFiles.length}: ${file.name}`);

        try {
          const formData = new FormData();
          formData.append("file", file);

          const response = await axios.post(`${API}/api/v2/pos-ocr/upload`, formData, {
            headers: { "Content-Type": "multipart/form-data" },
            timeout: 60000 // 1 minute per file
          });

          if (response.data.success && response.data.employees?.length > 0) {
            allEmployees.push(...response.data.employees);
            if (response.data.report_date && !reportDate) {
              reportDate = response.data.report_date;
            }
          } else if (response.data.error) {
            errors.push(`${file.name}: ${response.data.error}`);
          }
        } catch (err) {
          errors.push(`${file.name}: ${err.message || 'Failed to process'}`);
        }
      }

      if (allEmployees.length > 0) {
        setExtractedData({
          success: true,
          employees: allEmployees,
          employee_count: allEmployees.length,
          report_date: reportDate,
          report_type: "server_sales_detail",
          pages_processed: validFiles.length,
          extraction_notes: errors.length > 0 ? `${errors.length} file(s) had issues` : `Processed ${validFiles.length} files`
        });
        toast.success(`Extracted ${allEmployees.length} employees from ${validFiles.length} files`);
      } else {
        setError(`No employee data extracted.\n\nErrors:\n${errors.join('\n')}`);
      }
    } catch (err) {
      setError(`Batch processing failed: ${err.message}`);
    } finally {
      setIsProcessing(false);
      setProcessingStatus("");
    }
  };

  const processFile = async (file) => {
    // Validate file type
    const validImageTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
    const validPdfTypes = ["application/pdf"];
    const allValidTypes = [...validImageTypes, ...validPdfTypes];
    
    if (!allValidTypes.includes(file.type)) {
      setError("Please upload a JPEG, PNG, WEBP, HEIC image or PDF file");
      return;
    }

    const isPdf = validPdfTypes.includes(file.type);
    const isHeic = file.type === "image/heic" || file.type === "image/heif";
    const maxSize = isPdf ? 20 * 1024 * 1024 : 10 * 1024 * 1024; // 20MB for PDF, 10MB for images

    // Validate file size
    if (file.size > maxSize) {
      setError(`File too large. Maximum size is ${maxSize / (1024 * 1024)}MB`);
      return;
    }

    setFileType(isPdf ? 'pdf' : (isHeic ? 'heic' : 'image'));

    // Create preview (only for regular images, not HEIC or PDF)
    if (!isPdf && !isHeic) {
      const reader = new FileReader();
      reader.onload = (e) => setPreviewUrl(e.target.result);
      reader.readAsDataURL(file);
    } else {
      setPreviewUrl(null); // No preview for PDFs or HEIC
    }

    // Process with OCR
    setIsProcessing(true);
    setError(null);
    setExtractedData(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      // Long timeout for PDF processing (up to 5 minutes for large PDFs)
      const response = await axios.post(`${API}/api/v2/pos-ocr/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 300000 // 5 minutes
      });

      if (response.data.success) {
        setExtractedData(response.data);
        const fileTypeMsg = response.data.file_type === 'pdf' 
          ? ` from ${response.data.pages_processed} PDF page(s)` 
          : '';
        toast.success(`Extracted ${response.data.employee_count} employees${fileTypeMsg}`);
      } else {
        // Show detailed error message
        let errorMsg = response.data.error || "Failed to extract data";
        if (response.data.extraction_notes) {
          errorMsg += `\n\nDetails: ${response.data.extraction_notes}`;
        }
        setError(errorMsg);
      }
    } catch (err) {
      console.error("OCR Upload Error:", err);
      let errorMsg = "Failed to process file";
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMsg = "Request timed out. The PDF may have too many pages. Try splitting it into smaller files (10 pages max) or upload individual page images.";
      } else if (err.response?.data?.detail) {
        errorMsg = err.response.data.detail;
      } else if (err.message) {
        errorMsg = err.message;
      }
      setError(errorMsg);
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
    setProcessingStatus("");
    setFileType(null);
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
                  accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
                  className="hidden"
                  onChange={handleFileSelect}
                  multiple
                />

                {isProcessing ? (
                  <div className="flex flex-col items-center gap-4">
                    <Loader2 className="w-12 h-12 text-primary animate-spin" />
                    <div>
                      <p className="text-lg font-semibold text-white">
                        {fileType === 'multi' ? 'Processing Multiple Files...' : fileType === 'pdf' ? 'Processing PDF...' : 'Processing POS Report...'}
                      </p>
                      <p className="text-sm text-slate-400">
                        {processingStatus || (fileType === 'pdf' 
                          ? 'Converting pages and extracting data' 
                          : 'AI is extracting employee data')}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-4">
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
                      <Upload className="w-8 h-8 text-primary" />
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-white">Drop POS reports here</p>
                      <p className="text-sm text-slate-400">
                        <strong>Select multiple images</strong> for batch upload • Or single PDF
                      </p>
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
              
              {/* PDF File Indicator */}
              {fileType === 'pdf' && !extractedData && (
                <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl">
                  <FileText className="w-6 h-6 text-blue-400" />
                  <div>
                    <p className="font-medium text-blue-400">PDF File Uploaded</p>
                    <p className="text-sm text-blue-400/80">Each page will be processed for employee data</p>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-start gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="font-medium text-red-500">Extraction Failed</p>
                    <p className="text-sm text-red-400 whitespace-pre-wrap">{error}</p>
                  </div>
                </div>
              )}

              {/* Tips */}
              <div className="bg-slate-700/50 rounded-xl p-4">
                <p className="text-sm font-medium text-white mb-2">Tips for best results:</p>
                <ul className="text-sm text-slate-300 space-y-1">
                  <li>• <strong>Batch Upload:</strong> Select multiple images at once (one per employee)</li>
                  <li>• Screenshot or photo of each employee's report page works best</li>
                  <li>• Ensure reports are clearly visible and not blurry</li>
                  <li>• PDF files: First 5 pages processed (use images for more)</li>
                  <li>• Data extracted: PPA, LBW, Glassware, LSC, Guest Count, Net Sales</li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Success/Warning Header */}
              {(() => {
                // Count employees with missing required fields (excluding LSC)
                const missingCount = extractedData.employees.filter(emp => 
                  !emp.ppa || !emp.lbw_per_guest || !emp.glassware_per_guest || !emp.guest_count || !emp.net_sales
                ).length;
                
                return missingCount > 0 ? (
                  <div className="flex items-center gap-3 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl">
                    <AlertCircle className="w-6 h-6 text-yellow-500" />
                    <div>
                      <p className="font-medium text-yellow-400">
                        Extracted {extractedData.employee_count} employees - {missingCount} need review
                      </p>
                      <p className="text-sm text-yellow-400/80">
                        Click on any "—" value to manually enter the missing data
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 p-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                    <CheckCircle className="w-6 h-6 text-green-500" />
                    <div>
                      <p className="font-medium text-green-400">
                        Successfully extracted {extractedData.employee_count} employees - All data complete!
                      </p>
                      {extractedData.extraction_notes && (
                        <p className="text-sm text-green-400/80">{extractedData.extraction_notes}</p>
                      )}
                    </div>
                  </div>
                );
              })()}

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

              {/* Editable Data Table */}
              <div className="border border-slate-600 rounded-xl overflow-hidden">
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-sm min-w-[700px]">
                    <thead className="bg-slate-700 sticky top-0 z-10">
                      <tr>
                        <th className="px-2 py-2 text-left font-semibold text-white sticky left-0 bg-slate-700 min-w-[100px]">Name</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">PPA</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">LBW</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">Glass</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">Guests</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">Sales</th>
                        <th className="px-2 py-2 text-right font-semibold text-white whitespace-nowrap">G/LSC</th>
                        <th className="px-2 py-2 text-center font-semibold text-white">✓</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-600">
                      {extractedData.employees.map((emp, idx) => {
                        // Check for missing required fields (LSC is optional)
                        const missingFields = [];
                        if (!emp.ppa) missingFields.push('ppa');
                        if (!emp.lbw_per_guest) missingFields.push('lbw');
                        if (!emp.glassware_per_guest) missingFields.push('glass');
                        if (!emp.guest_count) missingFields.push('guests');
                        if (!emp.net_sales) missingFields.push('sales');
                        const hasMissing = missingFields.length > 0;
                        
                        return (
                          <tr key={idx} className={`${hasMissing ? 'bg-yellow-500/5' : 'hover:bg-slate-700/50'}`}>
                            <td className="px-2 py-2 font-medium text-sm sticky left-0 bg-slate-800">
                              <EditableNameCell
                                value={emp.name}
                                onChange={(val) => updateEmployeeField(idx, 'name', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.ppa} 
                                format="currency"
                                isMissing={!emp.ppa}
                                onChange={(val) => updateEmployeeField(idx, 'ppa', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.lbw_per_guest} 
                                format="currency"
                                isMissing={!emp.lbw_per_guest}
                                onChange={(val) => updateEmployeeField(idx, 'lbw_per_guest', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.glassware_per_guest} 
                                format="currency"
                                isMissing={!emp.glassware_per_guest}
                                onChange={(val) => updateEmployeeField(idx, 'glassware_per_guest', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.guest_count} 
                                format="number"
                                isMissing={!emp.guest_count}
                                onChange={(val) => updateEmployeeField(idx, 'guest_count', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.net_sales} 
                                format="currency"
                                isMissing={!emp.net_sales}
                                onChange={(val) => updateEmployeeField(idx, 'net_sales', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-right">
                              <EditableCell 
                                value={emp.guests_per_lsc} 
                                format="number"
                                isMissing={false}
                                onChange={(val) => updateEmployeeField(idx, 'guests_per_lsc', val)}
                              />
                            </td>
                            <td className="px-2 py-2 text-center">
                              {hasMissing ? (
                                <span className="text-yellow-400 text-xs">{missingFields.length}</span>
                              ) : (
                                <CheckCircle className="w-4 h-4 text-green-500 mx-auto" />
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
              
              {/* Legend - simplified for mobile */}
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-yellow-500/50 rounded"></span>
                  Click to edit
                </span>
                <span className="text-slate-500">• G/LSC optional</span>
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

        {/* Footer - Mobile Responsive */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 px-4 py-4 border-t border-slate-700 bg-slate-800/50">
          {extractedData ? (
            <>
              <Button 
                variant="outline" 
                onClick={() => {
                  setExtractedData(null);
                  setPreviewUrl(null);
                  setFileType(null);
                }}
                className="border-slate-600 text-slate-300 hover:bg-slate-700 order-2 sm:order-1"
              >
                <Edit3 className="w-4 h-4 mr-2" />
                Re-upload
              </Button>
              <Button onClick={handleConfirmData} className="bg-primary hover:bg-primary/90 order-1 sm:order-2">
                <CheckCircle className="w-4 h-4 mr-2" />
                Save Data
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={handleClose} className="border-slate-600 text-slate-300 hover:bg-slate-700">
                Cancel
              </Button>
              <p className="text-sm text-slate-400 text-center sm:text-right">
                Upload images to extract data
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default POSUploadModal;
