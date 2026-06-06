import { useRef, useState, useEffect } from "react";
import axios from "axios";
import { fetchAccounts } from "../../api/client";

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
  const [account, setAccount] = useState("");
  const [knownAccounts, setKnownAccounts] = useState<string[]>([]);

  useEffect(() => {
    fetchAccounts().then(setKnownAccounts).catch(() => {});
  }, []);

  async function handleFile(file: File) {
    const acct = account.trim();
    if (!acct) {
      setError("Enter the account name first, then choose the file.");
      return;
    }
    setUploading(true);
    setResult(null);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("account", acct);
    try {
      const { data } = await axios.post<UploadResult>("/api/upload/google-ads", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      // Refresh the known-accounts datalist so a new label shows up next time
      fetchAccounts().then(setKnownAccounts).catch(() => {});
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

  const accountMissing = !account.trim();

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
        <input
          type="text"
          list="known-accounts"
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          placeholder="Which Google Ads account is this report for?"
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <datalist id="known-accounts">
          {knownAccounts.map((a) => (
            <option key={a} value={a} />
          ))}
        </datalist>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => {
          if (accountMissing) { setError("Enter the account name first, then choose the file."); return; }
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
