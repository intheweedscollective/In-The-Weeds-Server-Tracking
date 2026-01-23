import { useState } from "react";
import { CheckCircle2, FileText, Upload } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "./ui/button";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LineGraphUpload({ employeeId, quarter, year, graphKind = "quarter", onUploadSuccess }) {
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);

  const onDrop = async (acceptedFiles) => {
    const file = acceptedFiles?.[0];
    if (!file) return;

    if (!file.name.match(/\.(png|jpg|jpeg|pdf)$/i)) {
      toast.error("Please upload a PNG, JPG, or PDF file");
      return;
    }

    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);

      if (!employeeId) {
        toast.error("Select an employee first to upload their graph");
        return;
      }

      await axios.post(`${API}/line-graphs`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        params: { quarter, year, employee_id: employeeId, graph_kind: graphKind },
      });

      setUploadedFile(file);
      toast.success("Graph uploaded successfully");
      onUploadSuccess?.();
    } catch (error) {
      console.error("Upload error:", error);
      toast.error(
        "Error uploading line graph: " +
          (error.response?.data?.detail || error.message)
      );
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "application/pdf": [".pdf"],
    },
    multiple: false,
  });

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={`upload-zone p-6 text-center cursor-pointer transition-all duration-300 ${
          isDragActive ? "drag-over" : ""
        }`}
        data-testid="line-graph-upload-zone"
      >
        <input {...getInputProps()} />

        {uploading ? (
          <div className="flex flex-col items-center" data-testid="uploading-state">
            <div className="loading-spinner mb-4"></div>
            <p className="text-primary font-medium">Uploading line graph...</p>
          </div>
        ) : uploadedFile ? (
          <div className="flex flex-col items-center" data-testid="uploaded-state">
            <CheckCircle2 className="w-12 h-12 text-green-600 mx-auto mb-4" />
            <p className="text-lg font-medium text-green-700 mb-2">
              Graph uploaded successfully!
            </p>
            <p className="text-muted-foreground mb-2">File: {uploadedFile.name}</p>
            <p className="text-sm text-muted-foreground">
              This graph will be included as page 2 in {quarter} {year} review for this employee
            </p>
          </div>
        ) : (
          <div data-testid="upload-ready-state">
            <FileText className="w-12 h-12 text-primary mx-auto mb-4" />
            <p className="text-lg font-medium text-primary mb-2">
              {isDragActive
                ? "Drop the graph file here"
                : "Upload Quarterly Line Graph"}
            </p>
            <p className="text-muted-foreground mb-4">
              Drag & drop or click to select the line graph for {quarter} {year}
            </p>
            <p className="text-sm text-muted-foreground">
              Supported formats: PNG, JPG, PDF  Max size: 10MB
            </p>
          </div>
        )}
      </div>

      {uploadedFile && (
        <div className="text-center pt-4 border-t border-border">
          <Button
            onClick={() => setUploadedFile(null)}
            variant="outline"
            size="sm"
          >
            <Upload className="w-4 h-4 mr-2" />
            Upload Different Graph
          </Button>
        </div>
      )}
    </div>
  );
}