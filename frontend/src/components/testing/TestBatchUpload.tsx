import { useRef, useState } from "react";
import { uploadTestBatch } from "../../api/client";
import type { TestBatchUploadResult } from "../../types";

interface Props {
  onSuccess: (result: TestBatchUploadResult) => void;
}

export function TestBatchUpload({ onSuccess }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<TestBatchUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const res = await uploadTestBatch(file);
      setResult(res);
      onSuccess(res);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Upload failed";
      setError(msg);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-gray-900">Upload Test Batch</h2>
        <p className="mt-1 text-sm text-gray-500">
          CSV with columns: <code className="bg-gray-100 px-1 rounded">campaign_name</code>,{" "}
          <code className="bg-gray-100 px-1 rounded">price</code>,{" "}
          <code className="bg-gray-100 px-1 rounded">commission_rate</code>,{" "}
          <code className="bg-gray-100 px-1 rounded">asin</code> (optional)
        </p>
      </div>

      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-blue-400 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        }`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={onInputChange}
        />
        {uploading ? (
          <span className="text-sm text-gray-500">Uploading...</span>
        ) : (
          <span className="text-sm text-gray-500">
            Drop CSV here or click to browse
          </span>
        )}
      </div>

      {result && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
          {result.message}
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
