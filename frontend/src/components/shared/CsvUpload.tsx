import { useRef, useState } from "react";
import axios from "axios";

interface UploadResult {
  rows_imported: number;
  date_from: string;
  date_to: string;
  campaigns: number;
  message: string;
}

interface Props {
  onSuccess: () => void;
}

export function CsvUpload({ onSuccess }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setUploading(true);
    setResult(null);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await axios.post<UploadResult>("/api/upload/google-ads", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      onSuccess();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail ?? err.message);
      } else {
        setError("Upload failed");
      }
    } finally {
      setUploading(false);
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // Reset input so the same file can be re-uploaded
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Upload Google Ads CSV
      </h3>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleChange}
        />
        {uploading ? (
          <p className="text-sm text-blue-600 font-medium animate-pulse">Importing...</p>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              Drop your Google Ads CSV here, or <span className="text-blue-600 font-medium">click to browse</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Export from Google Ads → Reports → Campaigns, add the <strong>Day</strong> segment
            </p>
          </>
        )}
      </div>

      {/* Success */}
      {result && (
        <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-800">
          {result.message}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
