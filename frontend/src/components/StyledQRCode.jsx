import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

/**
 * Styled QR Code Component
 * Generates professional-looking QR codes with:
 * - Rounded corner frame
 * - Center logo
 * - Custom colors
 * - High error correction for logo overlay
 */
export default function StyledQRCode({
  url,
  size = 280,
  logoUrl = null, // URL or data URI for center logo
  logoSize = 60,
  qrColor = "#000000",
  bgColor = "#FFFFFF",
  frameColor = "#1a1a2e",
  frameWidth = 16,
  frameRadius = 24,
  showFrame = true,
  className = ""
}) {
  const canvasRef = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const generateQR = async () => {
      if (!canvasRef.current || !url) return;

      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      const totalSize = showFrame ? size + frameWidth * 2 : size;
      
      canvas.width = totalSize;
      canvas.height = totalSize;

      // Clear canvas
      ctx.clearRect(0, 0, totalSize, totalSize);

      // Draw frame if enabled
      if (showFrame) {
        ctx.fillStyle = frameColor;
        ctx.beginPath();
        ctx.roundRect(0, 0, totalSize, totalSize, frameRadius);
        ctx.fill();
      }

      // Generate QR code to a temporary canvas
      const tempCanvas = document.createElement("canvas");
      try {
        await QRCode.toCanvas(tempCanvas, url, {
          width: size,
          margin: 2,
          errorCorrectionLevel: "H", // High error correction for logo overlay
          color: {
            dark: qrColor,
            light: bgColor
          }
        });

        // Draw white background for QR area
        const qrX = showFrame ? frameWidth : 0;
        const qrY = showFrame ? frameWidth : 0;
        
        ctx.fillStyle = bgColor;
        ctx.beginPath();
        ctx.roundRect(qrX, qrY, size, size, frameRadius - frameWidth / 2);
        ctx.fill();

        // Draw QR code
        ctx.drawImage(tempCanvas, qrX, qrY, size, size);

        // Draw center logo if provided
        if (logoUrl) {
          const img = new Image();
          img.crossOrigin = "anonymous";
          
          img.onload = () => {
            const logoX = totalSize / 2 - logoSize / 2;
            const logoY = totalSize / 2 - logoSize / 2;
            
            // Draw white circle background for logo
            ctx.fillStyle = bgColor;
            ctx.beginPath();
            ctx.arc(totalSize / 2, totalSize / 2, logoSize / 2 + 6, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw logo
            ctx.save();
            ctx.beginPath();
            ctx.arc(totalSize / 2, totalSize / 2, logoSize / 2, 0, Math.PI * 2);
            ctx.clip();
            ctx.drawImage(img, logoX, logoY, logoSize, logoSize);
            ctx.restore();
          };
          
          img.onerror = () => {
            // If logo fails to load, draw a placeholder
            drawPlaceholderLogo(ctx, totalSize, logoSize, bgColor);
          };
          
          img.src = logoUrl;
        } else {
          // Draw default shrimp-inspired logo
          drawDefaultLogo(ctx, totalSize, logoSize, bgColor, frameColor);
        }

        setError(null);
      } catch (err) {
        console.error("QR generation error:", err);
        setError("Failed to generate QR code");
      }
    };

    generateQR();
  }, [url, size, logoUrl, logoSize, qrColor, bgColor, frameColor, frameWidth, frameRadius, showFrame]);

  // Draw a stylized "BG" logo (Bubba Gump initials)
  const drawDefaultLogo = (ctx, totalSize, logoSize, bgColor, accentColor) => {
    const centerX = totalSize / 2;
    const centerY = totalSize / 2;
    
    // White circle background
    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 + 8, 0, Math.PI * 2);
    ctx.fill();
    
    // Outer ring
    ctx.strokeStyle = accentColor;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 + 2, 0, Math.PI * 2);
    ctx.stroke();
    
    // Inner circle with accent color
    ctx.fillStyle = "#C41E3A"; // Bubba Gump red
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 - 4, 0, Math.PI * 2);
    ctx.fill();
    
    // Draw "BG" text
    ctx.fillStyle = "#FFFFFF";
    ctx.font = `bold ${logoSize * 0.45}px Arial, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("BG", centerX, centerY + 2);
  };

  const drawPlaceholderLogo = (ctx, totalSize, logoSize, bgColor) => {
    const centerX = totalSize / 2;
    const centerY = totalSize / 2;
    
    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 + 4, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.fillStyle = "#C41E3A";
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 - 2, 0, Math.PI * 2);
    ctx.fill();
  };

  if (error) {
    return (
      <div className={`flex items-center justify-center bg-slate-800 rounded-lg ${className}`}
           style={{ width: size, height: size }}>
        <span className="text-red-400 text-sm">{error}</span>
      </div>
    );
  }

  return (
    <canvas 
      ref={canvasRef} 
      className={className}
      style={{ 
        maxWidth: "100%",
        height: "auto"
      }}
    />
  );
}

/**
 * Generate a styled QR code as a data URL for downloading
 */
export async function generateStyledQRDataUrl(url, options = {}) {
  const {
    size = 400,
    logoUrl = null,
    logoSize = 80,
    qrColor = "#000000",
    bgColor = "#FFFFFF",
    frameColor = "#1a1a2e",
    frameWidth = 20,
    frameRadius = 32,
    showFrame = true
  } = options;

  return new Promise(async (resolve, reject) => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const totalSize = showFrame ? size + frameWidth * 2 : size;
    
    canvas.width = totalSize;
    canvas.height = totalSize;

    // Draw frame
    if (showFrame) {
      ctx.fillStyle = frameColor;
      ctx.beginPath();
      ctx.roundRect(0, 0, totalSize, totalSize, frameRadius);
      ctx.fill();
    }

    // Generate QR code
    const tempCanvas = document.createElement("canvas");
    try {
      await QRCode.toCanvas(tempCanvas, url, {
        width: size,
        margin: 2,
        errorCorrectionLevel: "H",
        color: {
          dark: qrColor,
          light: bgColor
        }
      });

      // Draw QR area
      const qrX = showFrame ? frameWidth : 0;
      const qrY = showFrame ? frameWidth : 0;
      
      ctx.fillStyle = bgColor;
      ctx.beginPath();
      ctx.roundRect(qrX, qrY, size, size, frameRadius - frameWidth / 2);
      ctx.fill();

      ctx.drawImage(tempCanvas, qrX, qrY, size, size);

      // Draw logo
      const centerX = totalSize / 2;
      const centerY = totalSize / 2;
      
      // White circle background
      ctx.fillStyle = bgColor;
      ctx.beginPath();
      ctx.arc(centerX, centerY, logoSize / 2 + 8, 0, Math.PI * 2);
      ctx.fill();
      
      // Outer ring
      ctx.strokeStyle = frameColor;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(centerX, centerY, logoSize / 2 + 2, 0, Math.PI * 2);
      ctx.stroke();
      
      // Inner circle
      ctx.fillStyle = "#C41E3A";
      ctx.beginPath();
      ctx.arc(centerX, centerY, logoSize / 2 - 4, 0, Math.PI * 2);
      ctx.fill();
      
      // Text
      ctx.fillStyle = "#FFFFFF";
      ctx.font = `bold ${logoSize * 0.45}px Arial, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("BG", centerX, centerY + 2);

      resolve(canvas.toDataURL("image/png"));
    } catch (err) {
      reject(err);
    }
  });
}
