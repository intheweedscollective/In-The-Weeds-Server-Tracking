import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

// Default shrimp logo for Bubba Gump (served from local public folder)
const SHRIMP_LOGO_URL = "/images/shrimp-logo.png";

/**
 * Styled QR Code Component
 * Generates professional-looking QR codes with:
 * - Rounded corner frame
 * - Center shrimp logo
 * - Custom colors
 * - High error correction for logo overlay
 */
export default function StyledQRCode({
  url,
  size = 280,
  logoUrl = SHRIMP_LOGO_URL, // Default to shrimp logo
  logoSize = 100, // Larger logo
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

        // Draw center logo
        if (logoUrl) {
          const img = new Image();
          img.crossOrigin = "anonymous";
          
          img.onload = () => {
            const logoX = totalSize / 2 - logoSize / 2;
            const logoY = totalSize / 2 - logoSize / 2;
            
            // Draw white background - form fitting with 1px padding
            ctx.fillStyle = bgColor;
            ctx.beginPath();
            ctx.arc(totalSize / 2, totalSize / 2, logoSize / 2 + 1, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw logo (keeping aspect ratio, centered)
            ctx.drawImage(img, logoX, logoY, logoSize, logoSize);
          };
          
          img.onerror = () => {
            // If logo fails to load, draw a simple "BG" fallback
            drawFallbackLogo(ctx, totalSize, logoSize, bgColor, frameColor);
          };
          
          img.src = logoUrl;
        } else {
          // Draw fallback logo if no URL provided
          drawFallbackLogo(ctx, totalSize, logoSize, bgColor, frameColor);
        }

        setError(null);
      } catch (err) {
        console.error("QR generation error:", err);
        setError("Failed to generate QR code");
      }
    };

    generateQR();
  }, [url, size, logoUrl, logoSize, qrColor, bgColor, frameColor, frameWidth, frameRadius, showFrame]);

  // Draw a fallback "BG" logo if image fails to load
  const drawFallbackLogo = (ctx, totalSize, logoSize, bgColor, accentColor) => {
    const centerX = totalSize / 2;
    const centerY = totalSize / 2;
    
    // White circle background
    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.arc(centerX, centerY, logoSize / 2 + 8, 0, Math.PI * 2);
    ctx.fill();
    
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
    logoUrl = SHRIMP_LOGO_URL,
    logoSize = 130, // Even larger for downloads
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
      
      // White background - form fitting with 1px padding
      ctx.fillStyle = bgColor;
      ctx.beginPath();
      ctx.arc(centerX, centerY, logoSize / 2 + 1, 0, Math.PI * 2);
      ctx.fill();

      // Load and draw shrimp logo
      if (logoUrl) {
        const img = new Image();
        img.crossOrigin = "anonymous";
        
        await new Promise((imgResolve, imgReject) => {
          img.onload = () => {
            const logoX = centerX - logoSize / 2;
            const logoY = centerY - logoSize / 2;
            ctx.drawImage(img, logoX, logoY, logoSize, logoSize);
            imgResolve();
          };
          img.onerror = () => {
            // Fallback to "BG" text if image fails
            ctx.fillStyle = "#C41E3A";
            ctx.beginPath();
            ctx.arc(centerX, centerY, logoSize / 2 - 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "#FFFFFF";
            ctx.font = `bold ${logoSize * 0.45}px Arial, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("BG", centerX, centerY + 2);
            imgResolve();
          };
          img.src = logoUrl;
        });
      }

      resolve(canvas.toDataURL("image/png"));
    } catch (err) {
      reject(err);
    }
  });
}
