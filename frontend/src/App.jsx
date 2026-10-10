import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ChartView from "./ChartView.jsx";
import {
  ArrowUp,
  Building2,
  CheckCircle2,
  ChevronDown,
  FileText,
  LayoutDashboard,
  LibraryBig,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquareText,
  MoreVertical,
  Plus,
  Upload,
  Users,
  X,
} from "lucide-react";

const SUPPORTED_FILE_EXTENSIONS = new Set([
  "pdf",
  "docx",
  "txt",
  "md",
  "csv",
  "xlsx",
  "json",
]);

function readCookie(name) {
  const prefix = `${name}=`;
  const cookie = document.cookie
    .split("; ")
    .find((part) => part.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

function processingLabel(stage) {
  return (
    {
      queued: "Queued",
      extracting: "Extracting text",
      embedding: "Creating embeddings",
      indexing: "Saving to search index",
    }[stage] || "Processing"
  );
}

function roleLabel(role) {
  return (
    {
      system_admin: "System admin",
      company_admin: "Company admin",
      owner: "Owner",
      admin: "Admin",
      member: "Member",
      viewer: "Viewer",
    }[role] || "Member"
  );
}

function statusTone(status) {
  return (
    {
      ready: "text-emerald-300 bg-emerald-400/10",
      processing: "text-amber-300 bg-amber-400/10",
      queued: "text-sky-300 bg-sky-400/10",
      failed: "text-red-300 bg-red-400/10",
      uploaded: "text-white/60 bg-white/10",
    }[status] || "text-white/60 bg-white/10"
  );
}

function formatBytes(size) {
  if (!size) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
}

function CompanyLogo({ company, size = 36 }) {
  const logoUrl = company?.logo_url;
  const initial = (company?.name || "?").trim().charAt(0).toUpperCase();
  if (logoUrl) {
    return (
      <img
        alt={`${company.name} logo`}
        className="shrink-0 rounded-lg object-cover"
        height={size}
        src={logoUrl}
        style={{ width: size, height: size }}
        width={size}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="grid shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-sky-500 font-semibold text-white"
      style={{ width: size, height: size, fontSize: size * 0.44 }}
    >
      {initial}
    </span>
  );
}

function LoginScreen({ config }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = new URLSearchParams({ username, password });
      if (config.postLoginUrl) body.set("next", config.postLoginUrl);
      const data = await request(config.loginUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body,
      });
      if (data.redirect_url) {
        window.location.assign(data.redirect_url);
      } else {
        window.location.reload();
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#0b0d12] px-5 text-[#ececec]">
      <form
        className="w-full max-w-sm space-y-5 rounded-2xl border border-white/10 bg-[#141821] p-8 shadow-2xl shadow-black/40"
        onSubmit={submit}
      >
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-sky-500">
            <LayoutDashboard aria-hidden="true" size={20} />
          </span>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Workspace sign in</h1>
            <p className="text-xs text-white/50">Access your company dashboard</p>
          </div>
        </div>
        <label className="block space-y-2 text-sm">
          Username or email
          <input
            autoComplete="username"
            className="w-full rounded-lg border border-white/15 bg-[#0b0d12] px-3 py-2.5 outline-none focus:border-indigo-400"
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label className="block space-y-2 text-sm">
          Password
          <input
            autoComplete="current-password"
            className="w-full rounded-lg border border-white/15 bg-[#0b0d12] px-3 py-2.5 outline-none focus:border-indigo-400"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button
          className="w-full rounded-lg bg-indigo-500 py-2.5 font-medium text-white transition hover:bg-indigo-400 disabled:opacity-60"
          disabled={busy}
          type="submit"
        >
          {busy ? "Signing in…" : "Continue"}
        </button>
      </form>
    </main>
  );
}

class ChartErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error("Could not render the chart in this message.", error);
  }

  render() {
    if (this.state.hasError) {
      const { chart } = this.props;
      return (
        <section
          aria-label={`Chart data: ${chart.title}`}
          className="mt-4 w-full rounded-2xl border border-white/10 bg-[#11141b] p-4"
          role="status"
        >
          <h3 className="mb-3 text-sm font-medium">{chart.title}</h3>
          <p className="mb-3 text-xs text-white/50">
            The chart could not be displayed. Here is the data returned by the
            chart API.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-white/10 text-white/60">
                  <th className="px-2 py-2">{chart.x_axis}</th>
                  {chart.series.map((series) => (
                    <th className="px-2 py-2" key={series}>
                      {series}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.data.map((point, rowIndex) => (
                  <tr
                    className="border-b border-white/5"
                    key={`${point.label}-${rowIndex}`}
                  >
                    <td className="px-2 py-2">{point.label}</td>
                    {chart.series.map((series, columnIndex) => (
                      <td className="px-2 py-2" key={`${series}-${columnIndex}`}>
                        {point.values[columnIndex]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      );
    }
    return this.props.children;
  }
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return (
    <article className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-3xl bg-indigo-500/90 px-5 py-3 text-white"
            : "w-full max-w-[85%] rounded-3xl bg-[#161a22] px-5 py-3"
        }
      >
        <p className="whitespace-pre-wrap break-words text-[15px] leading-7">
          {message.content}
        </p>
        {message.documents?.map((document) => (
          <a
            className="mt-3 flex w-fit max-w-full items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm hover:bg-white/10"
            href={document.file_url}
            key={document.id}
            rel="noreferrer"
            target="_blank"
          >
            <FileText aria-hidden="true" className="shrink-0 text-white/60" size={18} />
            <span className="min-w-0">
              <span className="block truncate">{document.title}</span>
              <span className="text-xs text-white/45">
                {document.status === "ready"
                  ? `${document.chunk_count} searchable chunks`
                  : document.status === "processing"
                    ? `${processingLabel(document.processing_stage)} · ${document.processing_progress}%`
                    : document.status === "failed"
                      ? "Processing failed"
                      : "Queued for processing"}
              </span>
            </span>
          </a>
        ))}
        {message.citations?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {message.citations.map((citation, index) => (
              <span
                className="rounded-md bg-white/10 px-2 py-0.5 text-[11px] text-white/60"
                key={`${citation.reference_id || index}`}
              >
                {citation.source_location ||
                  (citation.page ? `page ${citation.page}` : `source ${index + 1}`)}
              </span>
            ))}
          </div>
        )}
        {!isUser && message.chart_data && (
          <ChartErrorBoundary
            chart={message.chart_data}
            key={`${message.chart_data.type}-${message.chart_data.title}`}
          >
            <ChartView chart={message.chart_data} />
          </ChartErrorBoundary>
        )}
      </div>
    </article>
  );
}

function StatCard({ icon: Icon, label, value, tone = "indigo" }) {
  const tones = {
    indigo: "from-indigo-500/20 to-indigo-500/5 text-indigo-300",
    emerald: "from-emerald-500/20 to-emerald-500/5 text-emerald-300",
    amber: "from-amber-500/20 to-amber-500/5 text-amber-300",
    sky: "from-sky-500/20 to-sky-500/5 text-sky-300",
  };
  return (
    <div className="rounded-2xl border border-white/10 bg-[#141821] p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-white/55">{label}</span>
        <span
          className={`grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br ${tones[tone]}`}
        >
          <Icon aria-hidden="true" size={18} />
        </span>
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}

function EmptyState({ icon: Icon, title, hint }) {
  return (
    <div className="grid flex-1 place-items-center px-6 py-16 text-center">
      <div>
        <span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-white/5 text-white/40">
          <Icon aria-hidden="true" size={26} />
        </span>
        <h3 className="text-base font-medium text-white/80">{title}</h3>
        {hint && <p className="mt-1 text-sm text-white/40">{hint}</p>}
      </div>
    </div>
  );
}

function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 px-6 py-10 text-sm text-white/45">
      <LoaderCircle className="animate-spin" size={16} />
      {label || "Loading…"}
    </div>
  );
}

function App({ config }) {
  const [authenticated] = useState(config.authenticated);
  const embedded = Boolean(config.embedded);
  const [username] = useState(config.username);
  const [companies] = useState(config.companies || []);
  const [activeCompanyId, setActiveCompanyId] = useState(config.activeCompanyId || "");
  const [activeCompany, setActiveCompany] = useState(config.activeCompany || null);
  const [role, setRole] = useState(config.role || "member");
  const [permissions, setPermissions] = useState(config.permissions || {});
  const canSwitch = companies.length > 1;
  const needsCompany = canSwitch && !activeCompanyId;

  // Navigation: dashboard | chats | documents | members
  const [view, setView] = useState(embedded ? "chats" : "dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [switcherOpen, setSwitcherOpen] = useState(false);

  const [dashboard, setDashboard] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [libraryStatus, setLibraryStatus] = useState(null);
  const [openActionMenu, setOpenActionMenu] = useState(null);
  const libraryFileRef = useRef(null);
  const [members, setMembers] = useState([]);
  const [membersLoading, setMembersLoading] = useState(false);

  const [activeId, setActiveId] = useState(null);
  const [activeTitle, setActiveTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [pendingDocumentId, setPendingDocumentId] = useState(null);
  const [pendingChat, setPendingChat] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const messagesRef = useRef(null);

  const ready = authenticated && !needsCompany;
  const isAdmin = Boolean(permissions.is_company_admin);

  const waitingForIndex = useMemo(
    () =>
      Boolean(pendingDocumentId) ||
      messages.some((message) =>
        message.documents?.some(
          (document) =>
            document.status === "queued" || document.status === "processing",
        ),
      ),
    [pendingDocumentId, messages],
  );

  const loadConversations = useCallback(async () => {
    setConversationsLoading(true);
    try {
      const data = await request(config.conversationsUrl);
      setConversations(data.conversations);
    } catch (err) {
      setError(err.message);
    } finally {
      setConversationsLoading(false);
    }
  }, [config.conversationsUrl]);

  const loadDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    try {
      const data = await request(config.documentsUrl);
      setDocuments(data.documents);
    } catch (err) {
      setError(err.message);
    } finally {
      setDocumentsLoading(false);
    }
  }, [config.documentsUrl]);

  const loadDashboard = useCallback(async () => {
    if (!config.dashboardUrl) return;
    setDashboardLoading(true);
    try {
      const data = await request(config.dashboardUrl);
      setDashboard(data);
    } catch (err) {
      setDashboard(null);
      if (err.status !== 409) setError(err.message);
    } finally {
      setDashboardLoading(false);
    }
  }, [config.dashboardUrl]);

  const loadMembers = useCallback(async () => {
    if (!config.membersUrl) return;
    setMembersLoading(true);
    try {
      const data = await request(config.membersUrl);
      setMembers(data.members);
    } catch (err) {
      setMembers([]);
      if (err.status !== 403 && err.status !== 409) setError(err.message);
    } finally {
      setMembersLoading(false);
    }
  }, [config.membersUrl]);

  // Initial + company-change data load.
  useEffect(() => {
    if (!ready) return;
    loadConversations();
    loadDocuments();
    loadDashboard();
    if (isAdmin) loadMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, activeCompanyId, isAdmin]);

  // Open a preselected conversation (admin chat-history deep links).
  useEffect(() => {
    if (!ready) return;
    const initialId = config.initialConversationId;
    if (initialId && !activeId) {
      setView("chats");
      openConversation(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  // Poll processing documents.
  useEffect(() => {
    if (!ready) return undefined;
    let timer;
    let cancelled = false;
    let pollDelay = 3000;

    async function refreshProcessingDocuments() {
      try {
        const data = await request(config.documentsUrl);
        if (cancelled) return;
        setDocuments(data.documents);
        setMessages((current) =>
          current.map((message) => {
            if (!message.documents?.length) return message;
            const updatedDocuments = message.documents.map(
              (document) =>
                data.documents.find((item) => item.id === document.id) || document,
            );
            return { ...message, documents: updatedDocuments };
          }),
        );
        if (pendingDocumentId) {
          const pendingDocument = data.documents.find(
            (document) => document.id === pendingDocumentId,
          );
          if (pendingDocument?.status === "ready") {
            setUploadStatus({
              type: "success",
              message: `${pendingDocument.title} is ready · ${pendingDocument.chunk_count} searchable chunks`,
            });
            setPendingDocumentId(null);
          } else if (pendingDocument?.status === "failed") {
            setUploadStatus({
              type: "error",
              message: pendingDocument.processing_error || "File processing failed.",
            });
            setPendingDocumentId(null);
          }
        }
        if (
          data.documents.some(
            (document) =>
              (document.status === "queued" || document.status === "processing") &&
              !document.can_retry,
          )
        ) {
          timer = window.setTimeout(refreshProcessingDocuments, pollDelay);
          pollDelay = Math.min(pollDelay * 2, 15000);
        }
      } catch {
        if (!cancelled) {
          timer = window.setTimeout(refreshProcessingDocuments, pollDelay);
          pollDelay = Math.min(pollDelay * 2, 15000);
        }
      }
    }

    refreshProcessingDocuments();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeCompanyId, ready, pendingDocumentId, config.documentsUrl]);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages, busy]);

  async function changeCompany(companyId) {
    if (busy || !companyId || companyId === activeCompanyId) {
      setSwitcherOpen(false);
      return;
    }
    setError("");
    try {
      const data = await request(config.companySelectionUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body: new URLSearchParams({ company_id: companyId }),
      });
      setActiveCompanyId(companyId);
      setActiveCompany(data.company || null);
      setRole(data.role || "member");
      setPermissions(data.permissions || {});
      setActiveId(null);
      setActiveTitle("");
      setMessages([]);
      setConversations([]);
      setDocuments([]);
      setMembers([]);
      setDashboard(null);
      setPrompt("");
      setSelectedFile(null);
      setPendingDocumentId(null);
      setPendingChat(null);
      setUploadStatus(null);
      setSwitcherOpen(false);
      setView("dashboard");
    } catch (err) {
      setError(err.message);
    }
  }

  async function retryDocument(document) {
    setUploadStatus({ type: "working", message: `Queueing ${document.title} for retry…` });
    try {
      const url = config.documentReprocessUrl.replace(
        "00000000-0000-0000-0000-000000000000",
        document.id,
      );
      await request(url, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
      });
      setPendingDocumentId(document.id);
      setUploadStatus({ type: "working", message: `${document.title} is queued for processing.` });
      await Promise.all([loadDocuments(), loadConversations()]);
    } catch (err) {
      setUploadStatus({ type: "error", message: err.message });
      if (err.data?.document) await loadDocuments();
    }
  }

  async function uploadLibraryDocument(file) {
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!SUPPORTED_FILE_EXTENSIONS.has(extension)) {
      setLibraryStatus({
        type: "error",
        message: "Choose a PDF, DOCX, TXT, MD, CSV, XLSX, or JSON file.",
      });
      return;
    }
    const body = new FormData();
    body.append("file", file);
    setLibraryStatus({ type: "working", message: `Uploading ${file.name} to the library…` });
    try {
      const data = await request(config.libraryUploadUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body,
      });
      setLibraryStatus({
        type: "working",
        message: `${data.document.title} is being chunked and embedded…`,
      });
      setPendingDocumentId(data.document.id);
      await loadDocuments();
    } catch (err) {
      setLibraryStatus({ type: "error", message: err.message });
    } finally {
      if (libraryFileRef.current) libraryFileRef.current.value = "";
    }
  }

  async function processDocument(document, backend) {
    setOpenActionMenu(null);
    setLibraryStatus({
      type: "working",
      message: `Processing ${document.title} with ${backend}…`,
    });
    try {
      const url = config.documentProcessUrl.replace(
        "00000000-0000-0000-0000-000000000000",
        document.id,
      );
      await request(url, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body: new URLSearchParams({ backend }),
      });
      setPendingDocumentId(document.id);
      setLibraryStatus({
        type: "working",
        message: `${document.title} queued on ${backend}.`,
      });
      await loadDocuments();
    } catch (err) {
      setLibraryStatus({ type: "error", message: err.message });
      if (err.data?.document) await loadDocuments();
    }
  }

  function newChat() {
    setView("chats");
    setActiveId(null);
    setActiveTitle("");
    setMessages([]);
    setPrompt("");
    setError("");
    setUploadStatus(null);
    setSelectedFile(null);
    setPendingDocumentId(null);
    setSidebarOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function openConversation(id) {
    try {
      const data = await request(
        config.conversationUrl.replace(config.conversationPlaceholder, id),
      );
      setActiveId(id);
      setActiveTitle(data.title || "");
      setView("chats");
      setMessages(data.messages);
      setPendingDocumentId(null);
      setError("");
      setSidebarOpen(false);
    } catch (err) {
      setError(err.message);
    }
  }

  function selectFile(file) {
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!SUPPORTED_FILE_EXTENSIONS.has(extension)) {
      setUploadStatus({
        type: "error",
        message: "Choose a PDF, DOCX, TXT, MD, CSV, XLSX, or JSON file.",
      });
      return;
    }
    setSelectedFile(file);
    setUploadStatus(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function uploadSelectedFile() {
    if (!selectedFile) return { ok: true, conversationId: activeId };
    const body = new FormData();
    body.append("file", selectedFile);
    body.append("message", prompt.trim());
    if (activeId) body.append("conversation_id", activeId);
    setUploadStatus({
      type: "working",
      message: `Adding ${selectedFile.name} to the processing queue…`,
    });
    try {
      const data = await request(config.uploadUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body,
      });
      const pending =
        data.document.status === "queued" || data.document.status === "processing";
      setUploadStatus({
        type: pending ? "working" : "success",
        message: pending
          ? prompt.trim()
            ? `Your question will be sent when ${data.document.title} is ready.`
            : `${data.document.title} is processing in the background.`
          : `${data.document.title} · ${data.document.chunk_count} searchable chunks ready`,
      });
      setActiveId(data.conversation_id);
      setMessages((current) => [...current, data.message]);
      setSelectedFile(null);
      setPendingDocumentId(pending ? data.document.id : null);
      await Promise.all([loadConversations(), loadDocuments()]);
      return {
        ok: true,
        pending,
        conversationId: data.conversation_id,
        messageId: data.message.id,
        documentId: data.document.id,
      };
    } catch (err) {
      setUploadStatus({ type: "error", message: err.message });
      if (err.data?.conversation_id) {
        setActiveId(err.data.conversation_id);
        if (err.data.message) {
          setMessages((current) => [...current, err.data.message]);
        }
        await Promise.all([loadConversations(), loadDocuments()]);
      }
      return { ok: false, conversationId: err.data?.conversation_id || activeId };
    }
  }

  async function sendChatQuestion(text, conversationId, userMessageId) {
    const userMessage = { role: "user", content: text, citations: [] };
    if (!userMessageId) {
      setMessages((current) => [...current, userMessage]);
    }
    setPrompt("");
    setBusy(true);
    try {
      const data = await request(config.chatUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": readCookie("csrftoken"),
        },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          ...(userMessageId ? { user_message_id: userMessageId } : {}),
        }),
      });
      setActiveId(data.conversation_id);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.response,
          citations: data.citations || [],
          chart_data: data.chart_data,
          documents: [],
        },
      ]);
      await loadConversations();
    } catch (err) {
      if (!userMessageId) {
        setMessages((current) => current.filter((message) => message !== userMessage));
      }
      setPrompt(text);
      setError(err.message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  useEffect(() => {
    if (!pendingChat || busy || activeId !== pendingChat.conversationId) return;
    const attachmentMessage = messages.find(
      (message) => message.id === pendingChat.messageId,
    );
    const document = attachmentMessage?.documents?.find(
      (item) => item.id === pendingChat.documentId,
    );
    if (document?.status === "ready") {
      setPendingChat(null);
      void sendChatQuestion(
        pendingChat.text,
        pendingChat.conversationId,
        pendingChat.messageId,
      );
    } else if (document?.status === "failed") {
      setPendingChat(null);
      setUploadStatus({
        type: "error",
        message:
          document.processing_error ||
          "File processing failed. Retry the file before sending your question.",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, busy, messages, pendingChat]);

  async function sendMessage(event) {
    event.preventDefault();
    const text = prompt.trim();
    if ((!text && !selectedFile) || busy) return;
    if (!selectedFile && waitingForIndex) {
      setUploadStatus({
        type: "working",
        message: "Your file is processing in the background. Ask about it when it is ready.",
      });
      return;
    }
    setError("");
    setBusy(true);

    const uploadResult = await uploadSelectedFile();
    if (!uploadResult.ok) {
      setBusy(false);
      return;
    }
    if (uploadResult.pending) {
      if (text) {
        setPendingChat({
          text,
          conversationId: uploadResult.conversationId,
          messageId: uploadResult.messageId,
          documentId: uploadResult.documentId,
        });
        setPrompt("");
      }
      setBusy(false);
      return;
    }
    if (!text) {
      setBusy(false);
      return;
    }
    await sendChatQuestion(
      text,
      uploadResult.conversationId,
      selectedFile ? uploadResult.messageId : null,
    );
  }

  async function logout() {
    try {
      await request(config.logoutUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
      });
      window.location.reload();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!authenticated) return <LoginScreen config={config} />;

  const companyName =
    activeCompany?.name ||
    companies.find((company) => company.id === activeCompanyId)?.name ||
    (companies.length ? "Choose a company" : "Personal workspace");
  const headerCompany =
    activeCompany ||
    companies.find((company) => company.id === activeCompanyId) ||
    { name: companyName };

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "chats", label: "Chats", icon: MessageSquareText },
    { id: "documents", label: "Documents", icon: LibraryBig },
    ...(isAdmin ? [{ id: "members", label: "Members", icon: Users }] : []),
  ];

  const stats = dashboard?.stats || {};

  return (
    <div
      className={`flex overflow-hidden bg-[#0b0d12] text-[#ececec] ${
        embedded ? "h-full min-h-[480px]" : "h-dvh min-h-[480px]"
      }`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (event.target === event.currentTarget) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        selectFile(event.dataTransfer.files[0]);
      }}
    >
      {sidebarOpen && !embedded && (
        <button
          aria-label="Close sidebar"
          className="fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      {!embedded && (
        <aside
          className={`fixed inset-y-0 left-0 z-30 flex w-[260px] shrink-0 flex-col border-r border-white/10 bg-[#0e1118] transition-transform md:static md:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-4">
            <div className="flex min-w-0 items-center gap-3">
              <CompanyLogo company={headerCompany} size={38} />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{companyName}</p>
                <p className="truncate text-xs text-white/45">{roleLabel(role)}</p>
              </div>
            </div>
            <button
              aria-label="Close sidebar"
              className="rounded-lg p-2 text-white/60 hover:bg-white/10 md:hidden"
              onClick={() => setSidebarOpen(false)}
              type="button"
            >
              <X size={18} />
            </button>
          </div>

          {canSwitch && (
            <div className="relative border-b border-white/10 px-3 py-3">
              <button
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/10 bg-[#141821] px-3 py-2 text-left text-sm hover:border-white/25"
                onClick={() => setSwitcherOpen((open) => !open)}
                type="button"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <Building2 className="shrink-0 text-white/50" size={16} />
                  <span className="truncate">{companyName}</span>
                </span>
                <ChevronDown className="shrink-0 text-white/50" size={16} />
              </button>
              {switcherOpen && (
                <div className="absolute inset-x-3 z-40 mt-1 max-h-72 overflow-y-auto rounded-lg border border-white/10 bg-[#141821] py-1 shadow-xl shadow-black/40">
                  {companies.map((company) => (
                    <button
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-white/5 ${
                        company.id === activeCompanyId ? "text-indigo-300" : "text-white/80"
                      }`}
                      key={company.id}
                      onClick={() => changeCompany(company.id)}
                      type="button"
                    >
                      <CompanyLogo company={company} size={22} />
                      <span className="truncate">{company.name}</span>
                      {company.id === activeCompanyId && (
                        <CheckCircle2 className="ml-auto shrink-0" size={15} />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <nav aria-label="Primary" className="flex-1 space-y-1 overflow-y-auto p-3">
            <button
              className="mb-2 flex w-full items-center gap-2 rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-400"
              onClick={newChat}
              type="button"
            >
              <Plus size={17} />
              New chat
            </button>
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = view === item.id;
              return (
                <button
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                    active ? "bg-white/10 text-white" : "text-white/65 hover:bg-white/5 hover:text-white"
                  }`}
                  key={item.id}
                  onClick={() => {
                    setView(item.id);
                    setSidebarOpen(false);
                    if (item.id === "documents") loadDocuments();
                    if (item.id === "members") loadMembers();
                    if (item.id === "dashboard") loadDashboard();
                  }}
                  type="button"
                >
                  <Icon aria-hidden="true" size={18} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <button
            className="flex items-center gap-3 border-t border-white/10 px-4 py-3 text-left text-sm text-white/70 hover:bg-white/5"
            onClick={logout}
            type="button"
          >
            <LogOut aria-hidden="true" size={17} />
            <span className="truncate">{username} · Sign out</span>
          </button>
        </aside>
      )}

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4">
          <div className="flex min-w-0 items-center gap-3">
            {!embedded && (
              <button
                aria-label="Open sidebar"
                className="rounded-lg p-2 text-white/70 hover:bg-white/10 md:hidden"
                onClick={() => setSidebarOpen(true)}
                type="button"
              >
                <Menu size={20} />
              </button>
            )}
            <CompanyLogo company={headerCompany} size={28} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold leading-tight">{companyName}</p>
              <p className="truncate text-[11px] text-white/45">
                {view === "chats" && activeTitle ? activeTitle : navItems.find((n) => n.id === view)?.label}
              </p>
            </div>
          </div>
          <span className="hidden shrink-0 items-center gap-1.5 rounded-full bg-white/5 px-3 py-1 text-xs text-white/60 sm:inline-flex">
            {roleLabel(role)}
          </span>
        </header>

        {dragging && !embedded && (
          <div className="pointer-events-none absolute inset-3 z-10 grid place-items-center rounded-2xl border-2 border-dashed border-white/40 bg-black/70 text-lg">
            Drop a supported file to add it
          </div>
        )}

        {needsCompany ? (
          <EmptyState
            icon={Building2}
            title="Choose a company to open its workspace"
            hint="Use the company switcher in the sidebar."
          />
        ) : view === "dashboard" ? (
          <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
            {dashboardLoading && !dashboard ? (
              <Spinner label="Loading dashboard…" />
            ) : (
              <div className="mx-auto max-w-5xl space-y-6">
                <div className="flex items-center gap-4">
                  <CompanyLogo company={headerCompany} size={48} />
                  <div>
                    <h1 className="text-2xl font-semibold tracking-tight">{companyName}</h1>
                    <p className="text-sm text-white/45">
                      {isAdmin ? "Company overview" : "Your workspace overview"}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  <StatCard icon={MessageSquareText} label="Chat sessions" value={stats.conversation_count ?? 0} tone="indigo" />
                  <StatCard icon={LibraryBig} label="Documents" value={stats.document_count ?? 0} tone="sky" />
                  <StatCard icon={CheckCircle2} label="Ready" value={stats.ready_document_count ?? 0} tone="emerald" />
                  {isAdmin ? (
                    <StatCard icon={Users} label="Members" value={stats.member_count ?? 0} tone="amber" />
                  ) : (
                    <StatCard icon={FileText} label="Messages" value={stats.message_count ?? 0} tone="amber" />
                  )}
                </div>
                <section className="rounded-2xl border border-white/10 bg-[#141821]">
                  <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
                    <h2 className="text-sm font-semibold">Recent chat sessions</h2>
                    <button
                      className="text-xs text-indigo-300 hover:text-indigo-200"
                      onClick={() => setView("chats")}
                      type="button"
                    >
                      View all
                    </button>
                  </div>
                  {dashboard?.recent_conversations?.length ? (
                    <ul className="divide-y divide-white/5">
                      {dashboard.recent_conversations.map((conversation) => (
                        <li key={conversation.id}>
                          <button
                            className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-white/5"
                            onClick={() => openConversation(conversation.id)}
                            type="button"
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-sm">{conversation.title || "New chat"}</span>
                              {isAdmin && conversation.owner && (
                                <span className="block text-xs text-white/40">{conversation.owner}</span>
                              )}
                            </span>
                            <span className="shrink-0 text-xs text-white/35">{formatDate(conversation.updated_at)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="px-5 py-8 text-center text-sm text-white/40">No chat sessions yet.</p>
                  )}
                </section>
              </div>
            )}
          </div>
        ) : view === "documents" ? (
          <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6 md:px-8">
            <div className="mx-auto w-full max-w-5xl">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h1 className="text-xl font-semibold tracking-tight">Document library</h1>
                  <p className="text-xs text-white/45">
                    Company knowledge base — chunked and embedded for search.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="hidden text-sm text-white/45 sm:inline">{documents.length} files</span>
                  <input
                    accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.json"
                    className="hidden"
                    onChange={(event) => uploadLibraryDocument(event.target.files[0])}
                    ref={libraryFileRef}
                    type="file"
                  />
                  <button
                    className="inline-flex items-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
                    onClick={() => libraryFileRef.current?.click()}
                    type="button"
                  >
                    <Upload size={16} />
                    Upload document
                  </button>
                </div>
              </div>
              {libraryStatus && (
                <p
                  className={`mb-3 text-xs ${
                    libraryStatus.type === "error"
                      ? "text-red-300"
                      : libraryStatus.type === "success"
                        ? "text-emerald-300"
                        : "text-white/50"
                  }`}
                  role="status"
                >
                  {libraryStatus.message}
                </p>
              )}
              {documentsLoading && !documents.length ? (
                <Spinner label="Loading documents…" />
              ) : documents.length === 0 ? (
                <EmptyState icon={LibraryBig} title="No documents yet" hint="Upload a document to build the company knowledge base." />
              ) : (
                <div className="overflow-visible rounded-2xl border border-white/10 bg-[#141821]">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-white/10 text-xs uppercase text-white/40">
                      <tr>
                        <th className="px-5 py-3 font-medium">File</th>
                        <th className="hidden px-5 py-3 font-medium sm:table-cell">Size</th>
                        <th className="px-5 py-3 font-medium">Status</th>
                        <th className="hidden px-5 py-3 font-medium md:table-cell">Added</th>
                        <th className="px-5 py-3 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {documents.map((document) => (
                        <tr key={document.id} className="hover:bg-white/5">
                          <td className="px-5 py-3">
                            <a className="flex min-w-0 items-center gap-2 hover:text-indigo-300" href={document.file_url} rel="noreferrer" target="_blank">
                              <FileText className="shrink-0 text-white/50" size={16} />
                              <span className="min-w-0">
                                <span className="block truncate">{document.title}</span>
                                <span className="block text-xs text-white/40">
                                  {document.source === "library"
                                    ? document.status === "ready"
                                      ? `${document.chunk_count} chunks`
                                      : "Knowledge base"
                                    : "Chat attachment"}
                                </span>
                              </span>
                            </a>
                            {(document.status === "queued" || document.status === "processing") && (
                              <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-white/10">
                                <span className="block h-full rounded-full bg-emerald-400 transition-[width]" style={{ width: `${document.processing_progress || 4}%` }} />
                              </span>
                            )}
                          </td>
                          <td className="hidden px-5 py-3 text-white/55 sm:table-cell">{formatBytes(document.file_size)}</td>
                          <td className="px-5 py-3">
                            <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusTone(document.status)}`}>
                              {document.status === "processing"
                                ? `${document.processing_progress}%`
                                : document.status}
                            </span>
                          </td>
                          <td className="hidden px-5 py-3 text-white/45 md:table-cell">{formatDate(document.created_at)}</td>
                          <td className="px-5 py-3">
                            {document.source === "library" ? (
                              <div className="relative">
                                <button
                                  aria-label="Document actions"
                                  className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-white/70 hover:bg-white/10 hover:text-white"
                                  onClick={() =>
                                    setOpenActionMenu(
                                      openActionMenu === document.id ? null : document.id,
                                    )
                                  }
                                  type="button"
                                >
                                  <MoreVertical size={14} />
                                  Actions
                                </button>
                                {openActionMenu === document.id && (
                                  <div className="absolute right-0 z-40 mt-1 w-56 overflow-hidden rounded-lg border border-white/10 bg-[#1a1f2a] py-1 shadow-xl shadow-black/50">
                                    {["kafka", "celery", "temporal"].map((backend) => (
                                      <button
                                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs capitalize text-white/80 hover:bg-white/5"
                                        key={backend}
                                        onClick={() => processDocument(document, backend)}
                                        type="button"
                                      >
                                        Process with {backend}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs text-white/30">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : view === "members" ? (
          <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6 md:px-8">
            <div className="mx-auto w-full max-w-5xl">
              <div className="mb-4 flex items-center justify-between">
                <h1 className="text-xl font-semibold tracking-tight">Members</h1>
                <span className="text-sm text-white/45">{members.length} people</span>
              </div>
              {membersLoading && !members.length ? (
                <Spinner label="Loading members…" />
              ) : members.length === 0 ? (
                <EmptyState icon={Users} title="No members to show" hint="Only company administrators can view the roster." />
              ) : (
                <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#141821]">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-white/10 text-xs uppercase text-white/40">
                      <tr>
                        <th className="px-5 py-3 font-medium">Member</th>
                        <th className="px-5 py-3 font-medium">Role</th>
                        <th className="hidden px-5 py-3 font-medium sm:table-cell">Status</th>
                        <th className="hidden px-5 py-3 font-medium md:table-cell">Joined</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {members.map((member) => (
                        <tr key={member.id} className="hover:bg-white/5">
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-3">
                              <span className="grid h-8 w-8 place-items-center rounded-full bg-white/10 text-xs font-semibold">
                                {(member.username || member.email || "?").charAt(0).toUpperCase()}
                              </span>
                              <span className="min-w-0">
                                <span className="block truncate">{member.username}</span>
                                <span className="block truncate text-xs text-white/40">{member.email}</span>
                              </span>
                            </div>
                          </td>
                          <td className="px-5 py-3">
                            <span className="inline-flex rounded-full bg-indigo-400/10 px-2.5 py-0.5 text-xs font-medium capitalize text-indigo-300">
                              {member.role}
                            </span>
                          </td>
                          <td className="hidden px-5 py-3 capitalize text-white/55 sm:table-cell">{member.status}</td>
                          <td className="hidden px-5 py-3 text-white/45 md:table-cell">{formatDate(member.joined_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          // Chats view
          <div className="flex min-h-0 flex-1">
            {!embedded && (
              <div className="hidden w-[280px] shrink-0 flex-col border-r border-white/10 bg-[#0e1118] lg:flex">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-xs font-semibold uppercase text-white/40">Chat sessions</span>
                  <button className="rounded-md p-1 text-white/60 hover:bg-white/10" onClick={newChat} title="New chat" type="button">
                    <Plus size={16} />
                  </button>
                </div>
                <nav aria-label="Chat sessions" className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
                  {conversationsLoading && !conversations.length ? (
                    <p className="px-3 py-2 text-xs text-white/35">Loading…</p>
                  ) : conversations.length === 0 ? (
                    <p className="px-3 py-2 text-xs leading-5 text-white/35">Your chats will appear here.</p>
                  ) : (
                    conversations.map((conversation) => (
                      <button
                        className={`block w-full rounded-lg px-3 py-2.5 text-left ${
                          activeId === conversation.id ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
                        }`}
                        key={conversation.id}
                        onClick={() => openConversation(conversation.id)}
                        title={conversation.title}
                        type="button"
                      >
                        <span className="block truncate text-sm">{conversation.title || "New chat"}</span>
                        <span className="block truncate text-xs text-white/40">
                          {isAdmin && conversation.owner ? `${conversation.owner} · ` : ""}
                          {formatDate(conversation.updated_at)}
                        </span>
                      </button>
                    ))
                  )}
                </nav>
              </div>
            )}

            <div className="flex min-w-0 flex-1 flex-col">
              <section
                aria-live="polite"
                className={`mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 overflow-y-auto px-4 py-8 md:px-6 ${
                  messages.length === 0 ? "justify-center" : "justify-start"
                }`}
                ref={messagesRef}
              >
                {messages.length === 0 ? (
                  <div className="text-center">
                    <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                      What's on the agenda today?
                    </h1>
                    <p className="mt-2 text-sm text-white/45">
                      Ask a question or attach a file to get started.
                    </p>
                  </div>
                ) : (
                  messages.map((message, index) => (
                    <ChatMessage key={`${index}-${message.role}`} message={message} />
                  ))
                )}
                {busy && (
                  <div className="flex items-center gap-2 text-sm text-white/45">
                    <LoaderCircle className="animate-spin" size={16} />
                    {selectedFile ? "Uploading file…" : "Thinking…"}
                  </div>
                )}
              </section>

              <div className="w-full px-3 pb-4 md:px-6 md:pb-6">
                <div className="mx-auto max-w-3xl">
                  {selectedFile && (
                    <div className="mb-2 flex w-fit max-w-full items-center gap-2 rounded-xl border border-white/10 bg-[#161a22] px-3 py-2 text-sm">
                      <FileText className="shrink-0 text-white/60" size={16} />
                      <span className="max-w-[240px] truncate">{selectedFile.name}</span>
                      <button
                        aria-label="Remove selected file"
                        className="rounded p-1 text-white/50 hover:bg-white/10 hover:text-white"
                        onClick={() => setSelectedFile(null)}
                        type="button"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  )}
                  {uploadStatus && (
                    <p
                      className={`mb-2 px-2 text-xs ${
                        uploadStatus.type === "error"
                          ? "text-red-300"
                          : uploadStatus.type === "success"
                            ? "text-emerald-300"
                            : "text-white/50"
                      }`}
                      role="status"
                    >
                      {uploadStatus.message}
                    </p>
                  )}
                  {error && (
                    <p className="mb-2 px-2 text-sm text-red-300" role="alert">
                      {error}
                    </p>
                  )}
                  <form
                    className="rounded-[26px] border border-white/15 bg-[#161a22] px-3 py-2 shadow-lg shadow-black/20 focus-within:border-indigo-400/60"
                    onSubmit={sendMessage}
                  >
                    <textarea
                      className="block max-h-48 min-h-10 w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-white outline-none placeholder:text-white/40"
                      disabled={needsCompany}
                      onChange={(event) => setPrompt(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          event.currentTarget.form.requestSubmit();
                        }
                      }}
                      placeholder="Ask anything"
                      ref={inputRef}
                      rows={1}
                      value={prompt}
                    />
                    <div className="flex items-center justify-between">
                      <input
                        accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.json"
                        className="hidden"
                        onChange={(event) => selectFile(event.target.files[0])}
                        ref={fileRef}
                        type="file"
                      />
                      <button
                        aria-label="Attach file"
                        className="grid h-9 w-9 place-items-center rounded-full text-white/70 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
                        disabled={needsCompany}
                        onClick={() => fileRef.current?.click()}
                        title="Attach a supported file"
                        type="button"
                      >
                        <Plus size={21} />
                      </button>
                      <button
                        aria-label="Send message"
                        className="grid h-9 w-9 place-items-center rounded-full bg-indigo-500 text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-35"
                        disabled={
                          busy ||
                          needsCompany ||
                          (!selectedFile && waitingForIndex) ||
                          (!prompt.trim() && !selectedFile)
                        }
                        type="submit"
                      >
                        {busy ? <LoaderCircle className="animate-spin" size={17} /> : <ArrowUp size={19} strokeWidth={2.5} />}
                      </button>
                    </div>
                  </form>
                  <p className="mt-2 text-center text-[11px] text-white/30">
                    Supported file contents and your questions are sent to OpenAI.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
