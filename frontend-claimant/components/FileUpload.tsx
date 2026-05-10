"use client";

import { useCallback, useState } from "react";

interface FileUploadProps {
  onFilesChange: (files: File[]) => void;
}

const ACCEPTED = ".jpg,.jpeg,.png,.webp,.pdf,.mp3,.wav,.m4a,.mp4,.ogg,.webm";

export default function FileUpload({ onFilesChange }: FileUploadProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback(
    (incoming: FileList | null) => {
      if (!incoming) return;
      const updated = [...files, ...Array.from(incoming)];
      setFiles(updated);
      onFilesChange(updated);
    },
    [files, onFilesChange]
  );

  const removeFile = (index: number) => {
    const updated = files.filter((_, i) => i !== index);
    setFiles(updated);
    onFilesChange(updated);
  };

  const fileIcon = (file: File) => {
    if (file.type.startsWith("image/")) return "🖼️";
    if (file.type === "application/pdf") return "📄";
    if (file.type.startsWith("audio/") || file.type.startsWith("video/")) return "🎙️";
    return "📎";
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors
          ${dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"}`}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <p className="text-4xl mb-2">📁</p>
        <p className="text-gray-600 font-medium">Drag & drop files here, or click to browse</p>
        <p className="text-sm text-gray-400 mt-1">Images, PDFs, audio or video recordings</p>
        <input
          id="file-input"
          type="file"
          multiple
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file, i) => (
            <li key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-2 text-sm">
              <span className="flex items-center gap-2 truncate">
                <span>{fileIcon(file)}</span>
                <span className="truncate text-gray-700">{file.name}</span>
                <span className="text-gray-400">({(file.size / 1024).toFixed(0)} KB)</span>
              </span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="text-gray-400 hover:text-red-500 ml-2 shrink-0"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
