import Link from "next/link";

export default function Home() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-16 space-y-16">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold" style={{ color: "var(--text)" }}>
          File Your Insurance Claim
        </h1>
        <p className="text-lg max-w-xl mx-auto" style={{ color: "var(--text-muted)" }}>
          Upload your evidence and get an AI-powered decision in minutes — no paperwork, no phone queues.
        </p>
        <Link
          href="/submit"
          className="inline-block mt-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-10 py-3.5 rounded-xl text-lg transition-colors"
        >
          Start My Claim →
        </Link>
      </div>

      <div>
        <h2 className="text-xl font-semibold text-center mb-8" style={{ color: "var(--text)" }}>How it works</h2>
        <div className="grid grid-cols-3 gap-6 text-center">
          {[
            { icon: "📋", title: "Describe the incident", desc: "Tell us what happened — a collision, property damage, or injury." },
            { icon: "📎", title: "Upload your evidence", desc: "Attach damage photos, a repair estimate PDF, or a voice recording." },
            { icon: "⚡", title: "Get a decision", desc: "Our AI reviews your claim and returns a determination in under 2 minutes." },
          ].map((item) => (
            <div key={item.title}
              className="rounded-2xl border p-6 space-y-3 shadow-sm"
              style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <div className="w-10 h-10 rounded-full flex items-center justify-center mx-auto text-xl"
                style={{ background: "var(--accent-subtle)" }}>{item.icon}</div>
              <p className="font-semibold" style={{ color: "var(--text)" }}>{item.title}</p>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border p-6 space-y-3"
        style={{ background: "var(--accent-subtle)", borderColor: "var(--accent)" }}>
        <h2 className="font-semibold" style={{ color: "var(--accent)" }}>What to prepare before you start</h2>
        <ul className="space-y-2.5 text-sm" style={{ color: "var(--text-muted)" }}>
          <li className="flex items-start gap-2">
            <span className="mt-0.5">📸</span>
            <span><b>Damage photos</b> (JPG or PNG) — take multiple angles of the damage</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5">📄</span>
            <span><b>Repair estimate or police report</b> as a PDF — attach if you have one</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5">🎙️</span>
            <span><b>Voice recording</b> (MP3, WAV, or MP4) describing the incident in your own words</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5">📝</span>
            <span><b>Written description</b> of what happened — required if not uploading a voice recording</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
