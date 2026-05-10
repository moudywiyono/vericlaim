"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { submitClaim } from "@/lib/api";

type ClaimType = "auto" | "property" | "health" | "";
type Section = "photos" | "documents" | "audio" | "description" | "submit";
type FileZone = "photos" | "documents" | "audio";

const CLAIM_OPTIONS = [
  { value: "auto" as ClaimType,     label: "Vehicle Claim",  desc: "Car, truck, motorcycle" },
  { value: "property" as ClaimType, label: "Property Claim", desc: "Home, building, contents" },
  { value: "health" as ClaimType,   label: "Health Claim",   desc: "Injury, illness, medical" },
  { value: "" as ClaimType,         label: "Not sure",        desc: "We will figure it out" },
];

const SECTIONS: { key: Section; label: string }[] = [
  { key: "photos",      label: "Damage Photos" },
  { key: "documents",   label: "Documents" },
  { key: "audio",       label: "Voice Statement" },
  { key: "description", label: "Description" },
  { key: "submit",      label: "Submit Application" },
];

const ZONE_CONFIG: Record<FileZone, {
  title: string;
  accept: string;
  hint: Record<ClaimType, string>;
  filetypes: Record<ClaimType, string>;
}> = {
  photos: {
    title: "Damage Photos",
    accept: ".jpg,.jpeg,.png,.webp",
    hint: {
      auto:     "Attach photos of the damaged vehicle. Include multiple angles — front, rear, sides, and interior if applicable.",
      property: "Attach photos of the property damage. Include wide shots and close-ups of affected areas.",
      health:   "Attach photos of the injury if applicable. Medical equipment or hospital documentation also accepted.",
      "":       "Attach photos showing the extent of the damage from multiple angles.",
    },
    filetypes: { auto: "jpg, png, webp", property: "jpg, png, webp", health: "jpg, png, webp", "": "jpg, png, webp" },
  },
  documents: {
    title: "Supporting Documents",
    accept: ".pdf",
    hint: {
      auto:     "Attach your repair estimate, police report, or vehicle registration. PDF format only.",
      property: "Attach a contractor quote, inspection report, or insurance policy document. PDF format only.",
      health:   "Attach your medical bill, doctor's note, or prescription. PDF format only.",
      "":       "Attach any relevant supporting documents. PDF format only.",
    },
    filetypes: { auto: "pdf", property: "pdf", health: "pdf", "": "pdf" },
  },
  audio: {
    title: "Voice Statement",
    accept: ".mp3,.wav,.m4a,.mp4,.ogg,.webm",
    hint: {
      auto:     "Record yourself describing the collision — when and where it happened, the sequence of events, and any witnesses.",
      property: "Record yourself describing the property damage — when you noticed it, what caused it, and the extent of the loss.",
      health:   "Record yourself describing your injury or illness — when it occurred, what happened, and your current condition.",
      "":       "Record yourself describing what happened in your own words. Speak clearly and include as much detail as possible.",
    },
    filetypes: { auto: "mp3, wav, mp4", property: "mp3, wav, mp4", health: "mp3, wav, mp4", "": "mp3, wav, mp4" },
  },
};

function FileSection({ zone, claimType, files, onAdd, onRemove }: {
  zone: FileZone; claimType: ClaimType;
  files: File[]; onAdd: (z: FileZone, f: FileList) => void; onRemove: (z: FileZone, i: number) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const cfg = ZONE_CONFIG[zone];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>{cfg.hint[claimType]}</p>
        <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
          File types: {cfg.filetypes[claimType]}. Max file size: 50 MB
        </p>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); onAdd(zone, e.dataTransfer.files); }}
        className="border-2 border-dashed rounded-lg px-6 py-8 text-center transition-all"
        style={{
          borderColor: dragging ? "var(--accent)" : "var(--border)",
          background: dragging ? "var(--accent-subtle)" : "var(--bg-subtle)",
        }}
      >
        <p className="text-sm mb-3" style={{ color: "var(--text-muted)" }}>
          Drag and drop your files here, or
        </p>
        <button
          type="button"
          onClick={() => document.getElementById(`input-${zone}`)?.click()}
          className="border rounded-md px-4 py-1.5 text-sm font-medium transition-colors hover:opacity-80"
          style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "transparent" }}
        >
          Browse
        </button>
        <input id={`input-${zone}`} type="file" multiple accept={cfg.accept} className="hidden"
          onChange={(e) => e.target.files && onAdd(zone, e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((f, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border px-4 py-3"
              style={{ background: "#fff", borderColor: "var(--border)" }}>
              <div className="w-8 h-8 rounded bg-blue-50 flex items-center justify-center shrink-0">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>{f.name}</p>
                <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
                  Size: {(f.size / 1024).toFixed(0)} KB
                </p>
              </div>
              <span className="text-xs font-medium text-green-600">Uploaded</span>
              <button type="button"
                onClick={(e) => { e.stopPropagation(); onRemove(zone, i); }}
                className="text-xs hover:text-red-500 transition-colors ml-1"
                style={{ color: "var(--text-subtle)" }}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SubmitClaimPage() {
  const router = useRouter();
  const [claimType, setClaimType] = useState<ClaimType>("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<Section>("photos");
  const [filesByZone, setFilesByZone] = useState<Record<FileZone, File[]>>({ photos: [], documents: [], audio: [] });
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const addFiles = useCallback((zone: FileZone, incoming: FileList) => {
    setFilesByZone((prev) => ({ ...prev, [zone]: [...prev[zone], ...Array.from(incoming)] }));
  }, []);

  const removeFile = useCallback((zone: FileZone, index: number) => {
    setFilesByZone((prev) => ({ ...prev, [zone]: prev[zone].filter((_, i) => i !== index) }));
  }, []);

  const sectionDone = (s: Section): boolean => {
    if (s === "photos") return filesByZone.photos.length > 0;
    if (s === "documents") return filesByZone.documents.length > 0;
    if (s === "audio") return filesByZone.audio.length > 0;
    if (s === "description") return description.trim().length > 0;
    return false;
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      Object.values(filesByZone).flat().forEach((f) => formData.append("files", f));
      formData.append("description", description);
      if (claimType) formData.append("claim_type", claimType);
      const { claim_id } = await submitClaim(formData);
      router.push(`/status/${claim_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed. Please try again.");
      setLoading(false);
    }
  };

  const selectedOption = CLAIM_OPTIONS.find((o) => o.value === claimType) ?? CLAIM_OPTIONS[3];
  const totalFiles = Object.values(filesByZone).flat().length;
  const hasAudio = filesByZone.audio.length > 0;
  const hasDescription = description.trim().length > 0;
  const canSubmit = hasAudio || hasDescription;

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">

      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>File a Claim</h1>

        {/* Claim type tab + dropdown */}
        <div className="relative mt-2 inline-block" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-1 text-sm font-semibold pb-1.5 border-b-2 transition-colors"
            style={{ color: "var(--text)", borderColor: "#2563eb" }}
          >
            {selectedOption.label}
            <svg className="w-3.5 h-3.5 ml-0.5" style={{ color: "var(--text-subtle)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {dropdownOpen && (
            <div className="absolute top-full left-0 mt-2 rounded-xl border shadow-lg z-20 w-56 overflow-hidden"
              style={{ background: "#fff", borderColor: "var(--border)" }}>
              {CLAIM_OPTIONS.map((opt) => (
                <button key={opt.value}
                  onClick={() => { setClaimType(opt.value); setDropdownOpen(false); }}
                  className="w-full flex items-center justify-between px-4 py-3 text-left text-sm transition-colors hover:bg-gray-50"
                  style={{ borderBottom: "1px solid var(--border)", color: "var(--text)" }}>
                  <div>
                    <p className="font-medium">{opt.label}</p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-subtle)" }}>{opt.desc}</p>
                  </div>
                  {claimType === opt.value && (
                    <svg className="w-4 h-4 text-blue-600 shrink-0 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Stepper */}
        <div className="flex items-center mt-7">
          <div className="flex flex-col items-center gap-1.5 shrink-0">
            <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">1</div>
            <span className="text-xs font-semibold" style={{ color: "var(--text)" }}>File Submission</span>
          </div>
          <div className="flex-1 h-px mx-3 mb-5"
            style={{ background: activeSection === "submit" ? "#2563eb" : "#d1d5db" }} />
          <div className="flex flex-col items-center gap-1.5 shrink-0">
            <div className="w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-semibold"
              style={activeSection === "submit"
                ? { borderColor: "#2563eb", color: "#2563eb", background: "#eff6ff" }
                : { borderColor: "#d1d5db", color: "#9ca3af" }}>2</div>
            <span className="text-xs font-semibold"
              style={{ color: activeSection === "submit" ? "var(--text)" : "var(--text-subtle)" }}>
              Review & Result
            </span>
          </div>
        </div>
      </div>

      {/* Main card */}
      <div className="rounded-2xl border overflow-hidden" style={{ background: "#fff", borderColor: "var(--border)" }}>

        {/* Card header */}
        <div className="px-7 py-5 border-b" style={{ borderColor: "var(--border)" }}>
          <p className="font-semibold" style={{ color: "var(--text)" }}>Claim Submission</p>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
            Get started by providing the details and documents required below.
          </p>
        </div>

        <div className="flex min-h-[520px]">
          {/* Left sidebar */}
          <div className="w-52 shrink-0 border-r py-4" style={{ borderColor: "var(--border)" }}>
            {SECTIONS.map((section) => {
              const isActive = activeSection === section.key;
              const isDone = sectionDone(section.key);
              const isLocked = section.key === "submit" && !canSubmit;
              return (
                <button key={section.key} onClick={() => setActiveSection(section.key)}
                  className="w-full flex items-center justify-between px-6 py-2.5 text-sm text-left transition-colors"
                  style={{
                    borderLeft: isActive ? "2px solid #2563eb" : "2px solid transparent",
                    color: isActive ? "#111827" : "#6b7280",
                    fontWeight: isActive ? 500 : 400,
                  }}>
                  <span>{section.label}</span>
                  {isDone && !isLocked && (
                    <svg className="w-3.5 h-3.5 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>

          {/* Right content panel */}
          <div className="flex-1 px-8 py-7 space-y-6">

            {activeSection !== "submit" && (
              <div>
                <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>
                  {SECTIONS.find(s => s.key === activeSection)?.label}
                </h2>
                {activeSection === "audio" && !filesByZone.audio.length && (
                  <p className="text-xs mt-0.5 text-red-500">Required if no written description is provided</p>
                )}
                {activeSection === "description" && !description.trim() && filesByZone.audio.length === 0 && (
                  <p className="text-xs mt-0.5 text-red-500">Required if no voice recording is attached</p>
                )}
              </div>
            )}

            {activeSection === "photos" && (
              <FileSection zone="photos" claimType={claimType} files={filesByZone.photos} onAdd={addFiles} onRemove={removeFile} />
            )}

            {activeSection === "documents" && (
              <FileSection zone="documents" claimType={claimType} files={filesByZone.documents} onAdd={addFiles} onRemove={removeFile} />
            )}

            {activeSection === "audio" && (
              <FileSection zone="audio" claimType={claimType} files={filesByZone.audio} onAdd={addFiles} onRemove={removeFile} />
            )}

            {activeSection === "description" && (
              <div className="space-y-3">
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {claimType === "auto"
                    ? "Describe the incident: when and where it happened, the sequence of events, and any other relevant details."
                    : claimType === "property"
                    ? "Describe the damage: when you noticed it, what caused it, and the extent of the loss."
                    : claimType === "health"
                    ? "Describe your injury or illness: when it occurred, what happened, and your current condition."
                    : "Describe the incident in detail: when and where it happened, what caused the damage, and any other relevant information."}
                </p>
                <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
                  This field is {filesByZone.audio.length > 0 ? "optional — voice recording is already attached." : "required if no voice recording is attached."}
                </p>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={7}
                  placeholder="Start typing here..."
                  className="w-full rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-300 transition-shadow"
                  style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)", color: "var(--text)" }}
                />
              </div>
            )}

            {activeSection === "submit" && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-base font-semibold" style={{ color: "var(--text)" }}>Review your submission</h2>
                  <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Please confirm the details below before submitting.
                  </p>
                </div>

                <div className="rounded-lg border overflow-hidden" style={{ borderColor: "var(--border)" }}>
                  {[
                    { label: "Claim type",         value: selectedOption.label },
                    { label: "Damage photos",       value: filesByZone.photos.length > 0 ? `${filesByZone.photos.length} file(s) attached` : "None" },
                    { label: "Documents",           value: filesByZone.documents.length > 0 ? `${filesByZone.documents.length} file(s) attached` : "None" },
                    { label: "Voice statement",     value: filesByZone.audio.length > 0 ? `${filesByZone.audio.length} file(s) attached` : "None", required: true },
                    { label: "Written description", value: description.trim() ? `${description.trim().split(/\s+/).length} words` : "None", required: true },
                  ].map((row, i, arr) => {
                    const isMissing = "required" in row && row.value === "None" && !canSubmit;
                    return (
                      <div key={row.label}
                        className="flex items-center justify-between px-5 py-3 text-sm"
                        style={{ borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : undefined, background: isMissing ? "rgba(239,68,68,0.04)" : undefined }}>
                        <span style={{ color: isMissing ? "#ef4444" : "var(--text-muted)" }}>{row.label}</span>
                        <span className="font-medium" style={{ color: isMissing ? "#ef4444" : row.value === "None" ? "var(--text-subtle)" : "var(--text)" }}>
                          {isMissing ? "Required — at least one needed" : row.value}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {totalFiles === 0 && !description.trim() && (
                  <div className="rounded-lg border border-amber-300 px-4 py-3 text-sm"
                    style={{ background: "rgba(245,158,11,0.05)", color: "#92400e" }}>
                    No evidence added yet. Please go back and attach at least one file or write a description.
                  </div>
                )}

                {error && (
                  <div className="rounded-lg border border-red-300 px-4 py-3 text-sm text-red-600"
                    style={{ background: "rgba(239,68,68,0.05)" }}>
                    {error}
                  </div>
                )}

                <button onClick={handleSubmit} disabled={loading || !canSubmit}
                  className="w-full text-white font-semibold py-3 rounded-lg transition-colors text-sm flex items-center justify-center gap-2"
                  style={{
                    background: canSubmit ? "#2563eb" : "#d1d5db",
                    cursor: canSubmit ? "pointer" : "not-allowed",
                  }}>
                  {!canSubmit && (
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  )}
                  {loading ? "Submitting your claim..." : "Submit Application"}
                </button>
                {!canSubmit && (
                  <p className="text-center text-xs text-red-500">
                    Add a voice recording or written description to enable submission.
                  </p>
                )}
                {canSubmit && (
                  <p className="text-center text-xs" style={{ color: "var(--text-subtle)" }}>
                    Processing takes approximately 60–90 seconds. Do not close this page after submitting.
                  </p>
                )}
              </div>
            )}

            {(activeSection === "photos" || activeSection === "documents" || activeSection === "audio") && (
              <p className="text-xs pt-2" style={{ color: "var(--text-subtle)" }}>
                This section is optional — you may skip it if you do not have {activeSection === "photos" ? "photos" : activeSection === "documents" ? "documents" : "a recording"}.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
