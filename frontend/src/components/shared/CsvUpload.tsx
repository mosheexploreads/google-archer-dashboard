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

// The two Google Ads accounts campaigns can come from.
const ACCOUNTS = ["Explorads", "Archer"] as const;

export function CsvUpload({ onSuccess }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [account, setAccount] = useState("");

  async function handleFile(file: File) {
    if (!account) {
      setError("Choose the account first, then select the file.");
      return;
    }
    setUploading(true);
    setResult(null);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("account", account);
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

  const accountMissing = !account;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Upload Google Ads CSV
      </h3>

      {/* Account selector — required before uploading */}
      <div className="mb-3">
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Account <span className="text-red-500">*</span>
        </label>
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-sm font-medium w-fit">
          {ACCOUNTS.map((a, i) => (
            <button
              key={a}
              type="button"
              onClick={() => { setAccount(a); setError(null); }}
              className={`px-4 py-1.5 transition-colors ${
                account === a
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              } ${i > 0 ? "border-l border-gray-300" : ""}`}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => {
          if (accountMissing) { setError("Choose the account first, then select the file."); return; }
          inputRef.current?.click();
        }}
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
          accountMissing
            ? "border-gray-200 bg-gray-50 cursor-not-allowed"
            : "border-gray-300 cursor-pointer hover:border-blue-400 hover:bg-blue-50"
        }`}
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
              {accountMissing
                ? "Choose an account above first"
                : <>Drop your <strong>{account}</strong> CSV here, or <span className="text-blue-600 font-medium">click to browse</span></>}
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
