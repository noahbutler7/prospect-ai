import { useState, useEffect, useRef, useCallback } from "react";
import {
  Users, Mail, Search, Settings, LinkedinIcon, CheckCircle,
  XCircle, Edit3, Send, Building2, Briefcase, Tag, Plus, Trash2,
  Clock, TrendingUp, Target, Zap, Eye, MoreHorizontal, X,
  ChevronRight, RefreshCw, Filter, AlertCircle, Inbox, ArrowRight,
  Sparkles, UserCheck, BadgeCheck, CircleDashed, Circle
} from "lucide-react";

// ─── Mock Data ────────────────────────────────────────────────────────────────

const MOCK_COMPANY_ACCOUNTS = [
  { id: 1, name: "Salesforce", domain: "salesforce.com", industry: "SaaS / CRM", size: "50,000+" },
  { id: 2, name: "HubSpot", domain: "hubspot.com", industry: "SaaS / Marketing", size: "7,000+" },
  { id: 3, name: "Outreach.io", domain: "outreach.io", industry: "SaaS / Sales", size: "1,200+" },
  { id: 4, name: "Gong", domain: "gong.io", industry: "SaaS / Revenue Intelligence", size: "900+" },
  { id: 5, name: "Drift", domain: "drift.com", industry: "SaaS / Conversational Marketing", size: "600+" },
];

const FIRST_NAMES = ["Sarah", "James", "Priya", "Marcus", "Elena", "Tyler", "Aisha", "Ben", "Natalie", "Ravi", "Jessica", "Chris"];
const LAST_NAMES = ["Chen", "Rodriguez", "Patel", "Thompson", "Novak", "Washington", "Kim", "Okafor", "Martinez", "Sharma", "Walsh", "Lee"];
const TITLES = [
  "VP of Sales", "Head of Sales Development", "Director of Revenue Operations",
  "Senior Sales Manager", "VP of Growth", "Director of Inside Sales",
  "Head of Business Development", "Chief Revenue Officer", "Sales Development Manager",
  "VP of Revenue", "Director of Sales Enablement"
];
const SIGNALS = [
  "Recently promoted", "Posted about scaling outbound",
  "Hiring 3 SDRs", "Just raised Series B", "Attended SaaStr 2025",
  "Posted about pipeline generation", "Expanding into EMEA",
  "New VP of Sales — likely rebuilding stack"
];

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function generateProspect(id, account) {
  const firstName = randomItem(FIRST_NAMES);
  const lastName = randomItem(LAST_NAMES);
  const title = randomItem(TITLES);
  const domain = account.domain;
  const emailFormats = [
    `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${domain}`,
    `${firstName.toLowerCase()[0]}${lastName.toLowerCase()}@${domain}`,
    `${firstName.toLowerCase()}@${domain}`,
  ];
  const email = Math.random() > 0.25 ? randomItem(emailFormats) : null;
  const signal = Math.random() > 0.3 ? randomItem(SIGNALS) : null;

  return {
    id,
    firstName,
    lastName,
    name: `${firstName} ${lastName}`,
    title,
    company: account.name,
    companyId: account.id,
    domain,
    email,
    emailConfidence: email ? (Math.random() > 0.5 ? "verified" : "inferred") : null,
    linkedinUrl: `https://linkedin.com/in/${firstName.toLowerCase()}-${lastName.toLowerCase()}-${Math.floor(Math.random() * 9000) + 1000}`,
    signal,
    avatar: `${firstName[0]}${lastName[0]}`,
    status: "pending", // pending | reviewing | approved | rejected | sent
    emailDraft: null,
    addedAt: new Date(),
  };
}

function generateEmailDraft(prospect) {
  const openings = [
    `Hi ${prospect.firstName},`,
    `Hey ${prospect.firstName} —`,
    `${prospect.firstName},`,
  ];
  const closings = [
    `Worth a quick 15?`,
    `Open to a 15-min chat this week?`,
    `Would love to show you what we're doing — 15 mins?`,
  ];

  const signalLine = prospect.signal
    ? `\nI noticed ${prospect.signal.toLowerCase()} — congrats on the momentum.`
    : "";

  const body = `${randomItem(openings)}${signalLine}

I work with ${prospect.title.includes("VP") || prospect.title.includes("Chief") ? "revenue leaders" : "sales development teams"} at companies like ${prospect.company} to help them cut prospecting time by 60% while keeping personalization high.

Most ${prospect.title}s I talk to are fighting the same battle: their reps spend more time researching than actually selling. We fix that with an AI agent that finds, qualifies, and drafts outreach for every prospect in your ICP — automatically.

${randomItem(closings)}

Best,
[Your name]`;

  return {
    subject: `Quick idea for ${prospect.company}'s outbound motion`,
    body: body.trim(),
  };
}

// ─── Status Config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  pending: { label: "Pending Review", color: "text-amber-400 bg-amber-400/10", dot: "bg-amber-400", icon: CircleDashed },
  reviewing: { label: "Reviewing", color: "text-blue-400 bg-blue-400/10", dot: "bg-blue-400", icon: Eye },
  approved: { label: "Approved", color: "text-emerald-400 bg-emerald-400/10", dot: "bg-emerald-400", icon: CheckCircle },
  rejected: { label: "Rejected", color: "text-red-400 bg-red-400/10", dot: "bg-red-400", icon: XCircle },
  sent: { label: "Sent", color: "text-purple-400 bg-purple-400/10", dot: "bg-purple-400", icon: Send },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function Avatar({ initials, size = "md", color = "indigo" }) {
  const sizes = { sm: "w-7 h-7 text-xs", md: "w-9 h-9 text-sm", lg: "w-12 h-12 text-base" };
  const colors = {
    indigo: "bg-indigo-500/20 text-indigo-300 ring-1 ring-indigo-500/30",
    emerald: "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30",
    violet: "bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30",
    amber: "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/30",
  };
  return (
    <div className={`${sizes[size]} ${colors[color]} rounded-full flex items-center justify-center font-semibold flex-shrink-0`}>
      {initials}
    </div>
  );
}

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status];
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      <Icon size={10} />
      {cfg.label}
    </span>
  );
}

function LinkedInTag({ url, name }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-blue-600/15 text-blue-400 hover:bg-blue-600/25 border border-blue-600/20 transition-colors"
      onClick={e => e.stopPropagation()}
    >
      <LinkedinIcon size={10} />
      {name}
    </a>
  );
}

function EmailTag({ email, confidence }) {
  if (!email) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-500 border border-zinc-700">
      <Mail size={10} />
      No email found
    </span>
  );
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${
      confidence === "verified"
        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
        : "bg-amber-500/10 text-amber-400 border-amber-500/20"
    }`}>
      <Mail size={10} />
      {email}
      {confidence === "inferred" && <span className="opacity-60">(inferred)</span>}
      {confidence === "verified" && <BadgeCheck size={10} />}
    </span>
  );
}

// ─── Email Draft Modal ─────────────────────────────────────────────────────────

function EmailDraftModal({ prospect, onClose, onApprove, onReject, onUpdateDraft }) {
  const [subject, setSubject] = useState(prospect.emailDraft?.subject || "");
  const [body, setBody] = useState(prospect.emailDraft?.body || "");
  const [editing, setEditing] = useState(false);

  const handleSave = () => {
    onUpdateDraft(prospect.id, { subject, body });
    setEditing(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl bg-zinc-900 border border-zinc-700/60 rounded-2xl shadow-2xl flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <Avatar initials={prospect.avatar} color="indigo" />
            <div>
              <p className="font-semibold text-white text-sm">{prospect.name}</p>
              <p className="text-xs text-zinc-400">{prospect.title} · {prospect.company}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge status={prospect.status} />
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Tags row */}
        <div className="px-6 py-3 border-b border-zinc-800 flex flex-wrap gap-2">
          <LinkedInTag url={prospect.linkedinUrl} name={`${prospect.firstName} ${prospect.lastName}`} />
          <EmailTag email={prospect.email} confidence={prospect.emailConfidence} />
          {prospect.signal && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-violet-500/10 text-violet-400 border border-violet-500/20">
              <Zap size={10} />
              {prospect.signal}
            </span>
          )}
        </div>

        {/* Email draft */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">AI-Drafted Email</span>
            <button
              onClick={() => setEditing(!editing)}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              <Edit3 size={12} />
              {editing ? "Preview" : "Edit"}
            </button>
          </div>

          {editing ? (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-zinc-500 mb-1 block">Subject</label>
                <input
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 mb-1 block">Body</label>
                <textarea
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors resize-none"
                  rows={12}
                  value={body}
                  onChange={e => setBody(e.target.value)}
                />
              </div>
              <button
                onClick={handleSave}
                className="text-xs px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
              >
                Save changes
              </button>
            </div>
          ) : (
            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-4 space-y-3">
              <div className="flex items-start gap-2">
                <span className="text-xs text-zinc-500 w-14 flex-shrink-0 pt-0.5">Subject</span>
                <span className="text-sm text-zinc-100 font-medium">{subject}</span>
              </div>
              <div className="border-t border-zinc-700/50 pt-3">
                <pre className="text-sm text-zinc-200 whitespace-pre-wrap font-sans leading-relaxed">{body}</pre>
              </div>
            </div>
          )}
        </div>

        {/* Action footer */}
        <div className="px-6 py-4 border-t border-zinc-800 flex items-center justify-between">
          <button
            onClick={() => { onReject(prospect.id); onClose(); }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 text-sm transition-colors border border-red-500/20"
          >
            <XCircle size={14} />
            Reject
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { onApprove(prospect.id, { subject, body }); onClose(); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-sm transition-colors border border-emerald-500/20"
            >
              <CheckCircle size={14} />
              Approve
            </button>
            <button
              onClick={() => { onApprove(prospect.id, { subject, body }, true); onClose(); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm transition-colors font-medium"
            >
              <Send size={14} />
              Approve & Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Prospect Card ─────────────────────────────────────────────────────────────

function ProspectCard({ prospect, onOpen, isNew }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(t);
  }, []);

  const avatarColors = ["indigo", "emerald", "violet", "amber"];
  const color = avatarColors[prospect.id % avatarColors.length];

  return (
    <div
      className={`group border border-zinc-800 hover:border-zinc-600 rounded-xl bg-zinc-900/60 hover:bg-zinc-800/60 transition-all duration-300 cursor-pointer ${
        isNew ? "ring-1 ring-indigo-500/40" : ""
      } ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"}`}
      style={{ transition: "opacity 0.3s ease, transform 0.3s ease, border-color 0.2s, background 0.2s" }}
      onClick={() => onOpen(prospect)}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <Avatar initials={prospect.avatar} color={color} />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-white text-sm">{prospect.name}</span>
                {isNew && (
                  <span className="text-xs px-1.5 py-0.5 bg-indigo-500/15 text-indigo-400 rounded font-medium border border-indigo-500/20">New</span>
                )}
              </div>
              <p className="text-xs text-zinc-400 mt-0.5 truncate">{prospect.title}</p>
              <div className="flex items-center gap-1 mt-1">
                <Building2 size={10} className="text-zinc-500 flex-shrink-0" />
                <span className="text-xs text-zinc-500">{prospect.company}</span>
              </div>
            </div>
          </div>
          <div className="flex-shrink-0">
            <Badge status={prospect.status} />
          </div>
        </div>

        {/* Tags */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          <LinkedInTag url={prospect.linkedinUrl} name={`${prospect.firstName} ${prospect.lastName}`} />
          <EmailTag email={prospect.email} confidence={prospect.emailConfidence} />
          {prospect.signal && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-violet-500/10 text-violet-400 border border-violet-500/20">
              <Zap size={10} />
              {prospect.signal}
            </span>
          )}
        </div>

        {/* Collapsed email preview */}
        {prospect.emailDraft && (
          <div className="mt-3 pt-3 border-t border-zinc-800 flex items-center justify-between">
            <span className="text-xs text-zinc-500 truncate flex items-center gap-1.5">
              <Sparkles size={10} className="text-indigo-400 flex-shrink-0" />
              <span className="truncate">{prospect.emailDraft.subject}</span>
            </span>
            <span className="text-xs text-indigo-400 flex items-center gap-1 flex-shrink-0 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
              Review <ChevronRight size={10} />
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── ICP Config Panel ─────────────────────────────────────────────────────────

function ICPConfigPanel({ config, onChange }) {
  const [newTitle, setNewTitle] = useState("");
  const [newKeyword, setNewKeyword] = useState("");

  const addTitle = () => {
    if (newTitle.trim()) {
      onChange({ ...config, titles: [...config.titles, newTitle.trim()] });
      setNewTitle("");
    }
  };
  const addKeyword = () => {
    if (newKeyword.trim()) {
      onChange({ ...config, keywords: [...config.keywords, newKeyword.trim()] });
      setNewKeyword("");
    }
  };
  const removeTitle = idx => onChange({ ...config, titles: config.titles.filter((_, i) => i !== idx) });
  const removeKeyword = idx => onChange({ ...config, keywords: config.keywords.filter((_, i) => i !== idx) });

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-white mb-1">Job Titles & Seniority</h3>
        <p className="text-xs text-zinc-500 mb-3">Prospects matching these titles will be targeted.</p>
        <div className="space-y-2">
          {config.titles.map((t, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-2 bg-zinc-800 rounded-lg">
              <div className="flex items-center gap-2">
                <Briefcase size={12} className="text-indigo-400" />
                <span className="text-sm text-zinc-200">{t}</span>
              </div>
              <button onClick={() => removeTitle(i)} className="text-zinc-600 hover:text-red-400 transition-colors">
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <input
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
            placeholder="e.g. VP of Sales"
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addTitle()}
          />
          <button onClick={addTitle} className="px-3 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white transition-colors">
            <Plus size={14} />
          </button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-white mb-1">Buying Signals & Keywords</h3>
        <p className="text-xs text-zinc-500 mb-3">Signals from LinkedIn activity, hiring, or posts that indicate intent.</p>
        <div className="flex flex-wrap gap-2">
          {config.keywords.map((k, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-violet-500/10 text-violet-300 border border-violet-500/20 rounded-full text-xs">
              <Zap size={10} />
              {k}
              <button onClick={() => removeKeyword(i)} className="hover:text-red-400 transition-colors ml-0.5">
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <input
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
            placeholder="e.g. Recently hired, Hiring SDRs"
            value={newKeyword}
            onChange={e => setNewKeyword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addKeyword()}
          />
          <button onClick={addKeyword} className="px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-lg text-white transition-colors">
            <Plus size={14} />
          </button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-white mb-1">Seniority Levels</h3>
        <div className="flex flex-wrap gap-2">
          {["C-Suite", "VP", "Director", "Manager", "Individual Contributor"].map(level => (
            <button
              key={level}
              onClick={() => {
                const active = config.seniority.includes(level);
                onChange({
                  ...config,
                  seniority: active
                    ? config.seniority.filter(s => s !== level)
                    : [...config.seniority, level]
                });
              }}
              className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                config.seniority.includes(level)
                  ? "bg-indigo-600/20 text-indigo-300 border-indigo-500/40"
                  : "bg-zinc-800 text-zinc-500 border-zinc-700 hover:border-zinc-600"
              }`}
            >
              {level}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Stats Bar ─────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center gap-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color}`}>
        <Icon size={16} />
      </div>
      <div>
        <p className="text-xl font-bold text-white">{value}</p>
        <p className="text-xs text-zinc-500">{label}</p>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function ProspectAgent() {
  const [view, setView] = useState("queue"); // queue | config | accounts
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [prospects, setProspects] = useState([]);
  const [newIds, setNewIds] = useState(new Set());
  const [selectedProspect, setSelectedProspect] = useState(null);
  const [filter, setFilter] = useState("all");
  const [selectedAccounts, setSelectedAccounts] = useState([1, 2]);
  const [icpConfig, setIcpConfig] = useState({
    titles: ["VP of Sales", "Head of Sales Development", "Director of Revenue Operations", "Chief Revenue Officer"],
    keywords: ["Hiring SDRs", "Recently promoted", "Raised funding", "Posted about pipeline"],
    seniority: ["VP", "Director", "C-Suite"],
  });

  const scanIntervalRef = useRef(null);
  const idCounterRef = useRef(1);

  const stats = {
    total: prospects.length,
    pending: prospects.filter(p => p.status === "pending").length,
    approved: prospects.filter(p => p.status === "approved" || p.status === "sent").length,
    sent: prospects.filter(p => p.status === "sent").length,
    withEmail: prospects.filter(p => p.email).length,
  };

  const filteredProspects = prospects.filter(p => {
    if (filter === "all") return true;
    return p.status === filter;
  });

  const startScan = useCallback(() => {
    if (scanning) return;
    setScanning(true);
    setScanProgress(0);

    const targetAccounts = MOCK_COMPANY_ACCOUNTS.filter(a => selectedAccounts.includes(a.id));
    let count = 0;
    const total = 12 + Math.floor(Math.random() * 8);

    scanIntervalRef.current = setInterval(() => {
      count++;
      setScanProgress(Math.min(Math.round((count / total) * 100), 98));

      const account = randomItem(targetAccounts);
      const id = idCounterRef.current++;
      const prospect = generateProspect(id, account);
      const draft = generateEmailDraft(prospect);
      prospect.emailDraft = draft;

      setProspects(prev => [prospect, ...prev]);
      setNewIds(prev => new Set([...prev, id]));

      setTimeout(() => {
        setNewIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }, 5000);

      if (count >= total) {
        clearInterval(scanIntervalRef.current);
        setScanProgress(100);
        setTimeout(() => setScanning(false), 800);
      }
    }, 900);
  }, [scanning, selectedAccounts]);

  const stopScan = useCallback(() => {
    clearInterval(scanIntervalRef.current);
    setScanning(false);
    setScanProgress(0);
  }, []);

  const updateStatus = useCallback((id, status) => {
    setProspects(prev => prev.map(p => p.id === id ? { ...p, status } : p));
  }, []);

  const updateDraft = useCallback((id, draft) => {
    setProspects(prev => prev.map(p => p.id === id ? { ...p, emailDraft: draft } : p));
  }, []);

  const approveProspect = useCallback((id, draft, send = false) => {
    setProspects(prev => prev.map(p => p.id === id ? { ...p, status: send ? "sent" : "approved", emailDraft: draft } : p));
  }, []);

  const rejectProspect = useCallback((id) => {
    updateStatus(id, "rejected");
  }, [updateStatus]);

  // ── Nav tabs ──────────────────────────────────────────────────────────────

  const NAV = [
    { id: "queue", label: "Prospect Queue", icon: Inbox, badge: stats.pending },
    { id: "accounts", label: "Accounts", icon: Building2 },
    { id: "config", label: "ICP Config", icon: Target },
  ];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Top Bar */}
      <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Zap size={14} className="text-white" />
            </div>
            <span className="font-bold text-white text-sm tracking-tight">ProspectAI</span>
            <span className="text-zinc-700 text-xs hidden sm:block">· SDR Agent</span>
          </div>

          <nav className="flex items-center gap-1">
            {NAV.map(({ id, label, icon: Icon, badge }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  view === id
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
                }`}
              >
                <Icon size={14} />
                <span className="hidden sm:block">{label}</span>
                {badge > 0 && (
                  <span className="w-4 h-4 rounded-full bg-indigo-500 text-white text-xs flex items-center justify-center font-bold leading-none">
                    {badge > 9 ? "9+" : badge}
                  </span>
                )}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {scanning ? (
              <button
                onClick={stopScan}
                className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg text-sm transition-colors"
              >
                <X size={13} />
                Stop
              </button>
            ) : (
              <button
                onClick={startScan}
                className="flex items-center gap-2 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Search size={13} />
                Start Scan
              </button>
            )}
          </div>
        </div>

        {/* Scan progress bar */}
        {scanning && (
          <div className="h-0.5 bg-zinc-800">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
              style={{ width: `${scanProgress}%` }}
            />
          </div>
        )}
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6">

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard icon={Users} label="Total Prospects" value={stats.total} color="bg-indigo-500/10 text-indigo-400" />
          <StatCard icon={Clock} label="Pending Review" value={stats.pending} color="bg-amber-500/10 text-amber-400" />
          <StatCard icon={UserCheck} label="Approved" value={stats.approved} color="bg-emerald-500/10 text-emerald-400" />
          <StatCard icon={Send} label="Emails Sent" value={stats.sent} color="bg-purple-500/10 text-purple-400" />
        </div>

        {/* ── QUEUE VIEW ───────────────────────────────────────────────────── */}
        {view === "queue" && (
          <div>
            {/* Filter tabs */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
                {["all", "pending", "approved", "rejected", "sent"].map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                      filter === f ? "bg-zinc-700 text-white" : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {f}
                    {f !== "all" && (
                      <span className="ml-1.5 text-zinc-500">
                        {prospects.filter(p => p.status === f).length}
                      </span>
                    )}
                  </button>
                ))}
              </div>
              {prospects.length > 0 && (
                <span className="text-xs text-zinc-500">{filteredProspects.length} prospects</span>
              )}
            </div>

            {/* Live scan indicator */}
            {scanning && (
              <div className="flex items-center gap-3 px-4 py-3 mb-4 bg-indigo-500/8 border border-indigo-500/20 rounded-xl">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
                  <span className="text-sm text-indigo-300 font-medium">Scanning LinkedIn...</span>
                </div>
                <span className="text-xs text-indigo-400/60">{scanProgress}% complete</span>
                <span className="ml-auto text-xs text-indigo-400/60">{prospects.length} found so far</span>
              </div>
            )}

            {/* Prospect grid */}
            {filteredProspects.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {filteredProspects.map(p => (
                  <ProspectCard
                    key={p.id}
                    prospect={p}
                    onOpen={setSelectedProspect}
                    isNew={newIds.has(p.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mb-4">
                  <Search size={24} className="text-zinc-600" />
                </div>
                <p className="text-zinc-300 font-medium mb-1">No prospects yet</p>
                <p className="text-zinc-500 text-sm mb-6 max-w-xs">
                  Configure your ICP and target accounts, then hit Start Scan to find prospects.
                </p>
                <button
                  onClick={startScan}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <Zap size={14} />
                  Start your first scan
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── ACCOUNTS VIEW ────────────────────────────────────────────────── */}
        {view === "accounts" && (
          <div className="max-w-2xl">
            <div className="mb-4">
              <h2 className="text-base font-semibold text-white">Target Accounts</h2>
              <p className="text-xs text-zinc-500 mt-0.5">Select which accounts to scan in your next run.</p>
            </div>
            <div className="space-y-2">
              {MOCK_COMPANY_ACCOUNTS.map(account => {
                const active = selectedAccounts.includes(account.id);
                const count = prospects.filter(p => p.companyId === account.id).length;
                return (
                  <div
                    key={account.id}
                    onClick={() => {
                      setSelectedAccounts(prev =>
                        active ? prev.filter(id => id !== account.id) : [...prev, account.id]
                      );
                    }}
                    className={`flex items-center gap-4 px-4 py-3.5 rounded-xl border cursor-pointer transition-all ${
                      active
                        ? "bg-indigo-500/8 border-indigo-500/30"
                        : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
                    }`}
                  >
                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                      active ? "bg-indigo-500 border-indigo-500" : "border-zinc-600"
                    }`}>
                      {active && <CheckCircle size={10} className="text-white" />}
                    </div>
                    <div className="w-9 h-9 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs font-bold text-zinc-300">
                      {account.name[0]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white">{account.name}</p>
                      <p className="text-xs text-zinc-500">{account.industry} · {account.size} employees</p>
                    </div>
                    {count > 0 && (
                      <span className="text-xs text-zinc-500">{count} prospects found</span>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-4 px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl flex items-center justify-between">
              <span className="text-xs text-zinc-500">{selectedAccounts.length} account{selectedAccounts.length !== 1 ? "s" : ""} selected</span>
              <button
                onClick={startScan}
                className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                <Search size={12} />
                Scan selected
              </button>
            </div>
          </div>
        )}

        {/* ── ICP CONFIG VIEW ───────────────────────────────────────────────── */}
        {view === "config" && (
          <div className="max-w-xl">
            <div className="mb-5">
              <h2 className="text-base font-semibold text-white">ICP Configuration</h2>
              <p className="text-xs text-zinc-500 mt-0.5">Define your Ideal Customer Profile. The agent uses this to filter and score prospects.</p>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
              <ICPConfigPanel config={icpConfig} onChange={setIcpConfig} />
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setView("queue")}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Save & go to queue
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Email Draft Modal */}
      {selectedProspect && (
        <EmailDraftModal
          prospect={prospects.find(p => p.id === selectedProspect.id) || selectedProspect}
          onClose={() => setSelectedProspect(null)}
          onApprove={approveProspect}
          onReject={rejectProspect}
          onUpdateDraft={updateDraft}
        />
      )}
    </div>
  );
}
