import {
  Component,
  useEffect,
  useRef,
  useState,
} from "react";
import ChartView from "./ChartView.jsx";
import {
  ArrowUp,
  FileText,
  LibraryBig,
  LoaderCircle,
  LogOut,
  Menu,
  Plus,
  SquarePen,
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

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.data = data;
    throw error;
  }
  return data;
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
    <main className="grid min-h-screen place-items-center bg-[#212121] px-5 text-[#ececec]">
      <form
        className="w-full max-w-sm space-y-4 rounded-2xl border border-white/10 bg-[#2b2b2b] p-7"
        onSubmit={submit}
      >
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="text-sm text-white/60">
          Sign in to chat with your files.
        </p>
        <label className="block space-y-2 text-sm">
          Username or email
          <input
            autoComplete="username"
            className="w-full rounded-lg border border-white/15 bg-[#212121] px-3 py-2.5 outline-none focus:border-white/40"
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label className="block space-y-2 text-sm">
          Password
          <input
            autoComplete="current-password"
            className="w-full rounded-lg border border-white/15 bg-[#212121] px-3 py-2.5 outline-none focus:border-white/40"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button
          className="w-full rounded-lg bg-white py-2.5 font-medium text-[#212121] disabled:opacity-60"
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
          className="mt-4 w-full rounded-2xl border border-white/10 bg-[#171717] p-4"
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
                      <td
                        className="px-2 py-2"
                        key={`${series}-${columnIndex}`}
                      >
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
            ? "max-w-[85%] rounded-3xl bg-[#303030] px-5 py-3"
            : "w-full max-w-[85%] py-2"
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

function App({ config }) {
  const [authenticated, setAuthenticated] = useState(config.authenticated);
  const [username, setUsername] = useState(config.username);
  const [companies] = useState(config.companies || []);
  const [activeCompanyId, setActiveCompanyId] = useState(config.activeCompanyId || "");
  const [conversations, setConversations] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [sidebarView, setSidebarView] = useState("chats");
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [pendingDocumentId, setPendingDocumentId] = useState(null);
  const [pendingChat, setPendingChat] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const messagesRef = useRef(null);

  useEffect(() => {
    if (!authenticated || (companies.length > 1 && !activeCompanyId)) return;
    loadConversations();
  }, [authenticated, activeCompanyId]);

  useEffect(() => {
    if (!authenticated || (companies.length > 1 && !activeCompanyId)) return undefined;
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
              (document.status === "queued" ||
                document.status === "processing") &&
              !document.can_retry,
          )
        ) {
          timer = window.setTimeout(refreshProcessingDocuments, pollDelay);
          pollDelay = Math.min(pollDelay * 2, 15000);
        }
      } catch (err) {
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
  }, [activeCompanyId, authenticated, companies.length, pendingDocumentId]);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages, busy]);

  async function loadConversations() {
    try {
      const data = await request(config.conversationsUrl);
      setConversations(data.conversations);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadDocuments() {
    try {
      const data = await request(config.documentsUrl);
      setDocuments(data.documents);
    } catch (err) {
      setError(err.message);
    }
  }

  async function changeCompany(companyId) {
    if (busy || !companyId) return;
    setError("");
    try {
      await request(config.companySelectionUrl, {
        method: "POST",
        headers: { "X-CSRFToken": readCookie("csrftoken") },
        body: new URLSearchParams({ company_id: companyId }),
      });
      setActiveCompanyId(companyId);
      setActiveId(null);
      setMessages([]);
      setConversations([]);
      setDocuments([]);
      setPrompt("");
      setSelectedFile(null);
      setSidebarView("chats");
      setPendingDocumentId(null);
      setPendingChat(null);
      setUploadStatus(null);
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

  function newChat() {
    setSidebarView("chats");
    setActiveId(null);
    setMessages([]);
    setPrompt("");
    setError("");
    setUploadStatus(null);
    setSelectedFile(null);
    setPendingDocumentId(null);
    setSidebarOpen(false);
    inputRef.current?.focus();
  }

  async function openConversation(id) {
    try {
      const data = await request(config.conversationUrl.replace(config.conversationPlaceholder, id));
      setActiveId(id);
      setSidebarView("chats");
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
    fileRef.current.value = "";
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
        data.document.status === "queued" ||
        data.document.status === "processing";
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
        setMessages((current) =>
          current.filter((message) => message !== userMessage),
        );
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

  const empty = messages.length === 0;
  const waitingForIndex =
    Boolean(pendingDocumentId) ||
    messages.some((message) =>
      message.documents?.some(
        (document) =>
          document.status === "queued" || document.status === "processing",
      ),
    );
  const activeCompanyName =
    companies.find((company) => company.id === activeCompanyId)?.name ||
    (companies.length ? "Choose a company" : "Personal workspace");
  return (
    <div
      className="flex h-dvh min-h-[480px] overflow-hidden bg-black text-[#ececec]"
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
      {sidebarOpen && (
        <button
          aria-label="Close sidebar"
          className="fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-[272px] shrink-0 flex-col bg-[#0c0c0c] p-3 transition-transform md:static md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-3 flex items-center justify-between">
          <span className="px-2 text-lg font-semibold text-white/90">{activeCompanyName}</span>
          <button
            aria-label="Close sidebar"
            className="rounded-lg p-2 text-white/60 hover:bg-white/10 md:hidden"
            onClick={() => setSidebarOpen(false)}
            type="button"
          >
            <X size={18} />
          </button>
        </div>
        {companies.length > 1 && (
          <label className="mb-2 block px-2 text-xs text-white/55">
            Company workspace
            <select
              className="mt-1 w-full rounded-lg border border-white/10 bg-[#202020] px-2 py-2 text-sm text-white"
              disabled={busy}
              onChange={(event) => changeCompany(event.target.value)}
              value={activeCompanyId}
            >
              <option value="">Choose a company</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm hover:bg-white/10 ${
            sidebarView === "chats" && !activeId ? "bg-white/10" : ""
          }`}
          onClick={newChat}
          type="button"
        >
          <SquarePen aria-hidden="true" size={18} />
          <span className="flex-1">New chat</span>
          <Plus aria-hidden="true" size={17} className="text-white/45" />
        </button>
        <button
          className={`mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm hover:bg-white/10 ${
            sidebarView === "library" ? "bg-white/10" : ""
          }`}
          onClick={() => {
            setSidebarView("library");
            setSidebarOpen(false);
            loadDocuments();
          }}
          type="button"
        >
          <LibraryBig aria-hidden="true" size={18} />
          <span>Library</span>
        </button>
        <div className="mb-2 mt-7 px-3 text-xs font-medium text-white/45">
          {sidebarView === "chats" ? "Recents" : "Your files"}
        </div>
        {sidebarView === "chats" ? (
          <nav aria-label="Recent conversations" className="min-h-0 flex-1 space-y-1 overflow-y-auto">
            {conversations.map((conversation) => (
              <button
                className={`block w-full truncate rounded-lg px-3 py-2.5 text-left text-sm ${
                  activeId === conversation.id
                    ? "bg-white/10 text-white"
                    : "text-white/70 hover:bg-white/5 hover:text-white"
                }`}
                key={conversation.id}
                onClick={() => openConversation(conversation.id)}
                title={conversation.title}
                type="button"
              >
                {conversation.title || "New chat"}
              </button>
            ))}
            {conversations.length === 0 && (
              <p className="px-3 py-2 text-xs leading-5 text-white/35">
                Your chats will appear here.
              </p>
            )}
          </nav>
        ) : (
          <nav aria-label="Uploaded files" className="min-h-0 flex-1 space-y-1 overflow-y-auto">
            {documents.map((document) => (
              <div
                className="flex items-center gap-1 rounded-lg hover:bg-white/5"
                key={document.id}
              >
                <a
                  className="flex min-w-0 flex-1 items-start gap-2 px-3 py-2.5 text-sm text-white/70 hover:text-white"
                  href={document.file_url}
                  rel="noreferrer"
                  target="_blank"
                  title={`${document.title} · ${document.status}`}
                >
                  <FileText aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
                  <span className="min-w-0">
                    <span className="block truncate">{document.title}</span>
                    <span className="block text-xs text-white/40">
                      {document.status === "ready"
                        ? `${document.chunk_count} searchable chunks`
                        : document.status === "processing"
                          ? `${processingLabel(document.processing_stage)} · ${document.processing_progress}%`
                          : document.status === "queued"
                            ? "Queued for processing"
                            : document.status}
                    </span>
                    {(document.status === "queued" ||
                      document.status === "processing") && (
                      <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/10">
                        <span
                          className="block h-full rounded-full bg-emerald-400 transition-[width]"
                          style={{
                            width: `${document.processing_progress || 4}%`,
                          }}
                        />
                      </span>
                    )}
                  </span>
                </a>
                {document.can_retry && (
                  <button
                    className="mr-2 shrink-0 rounded-md px-2 py-1 text-xs text-white/60 hover:bg-white/10 hover:text-white"
                    onClick={() => retryDocument(document)}
                    type="button"
                  >
                    Retry
                  </button>
                )}
              </div>
            ))}
            {documents.length === 0 && (
              <p className="px-3 py-2 text-xs leading-5 text-white/35">
                Uploaded files will appear here.
              </p>
            )}
          </nav>
        )}
        <button
          className="flex items-center gap-3 rounded-lg px-3 py-3 text-left text-sm text-white/70 hover:bg-white/10"
          onClick={logout}
          type="button"
        >
          <LogOut aria-hidden="true" size={17} />
          <span className="truncate">{username} · Sign out</span>
        </button>
      </aside>

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between px-3">
          <div className="flex items-center gap-2">
            <button
              aria-label="Open sidebar"
              className="rounded-lg p-2 text-white/70 hover:bg-white/10 md:hidden"
              onClick={() => setSidebarOpen(true)}
              type="button"
            >
              <Menu size={20} />
            </button>
            <span className="text-sm font-medium md:hidden">{activeCompanyName}</span>
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-white/80 hover:bg-white/10 md:hidden"
            onClick={newChat}
            type="button"
          >
            <SquarePen aria-hidden="true" size={17} />
            New chat
          </button>
        </header>

        {dragging && (
          <div className="pointer-events-none absolute inset-3 z-10 grid place-items-center rounded-2xl border-2 border-dashed border-white/40 bg-black/70 text-lg">
            Drop a supported file to add it
          </div>
        )}

        <section
          aria-live="polite"
          className={`mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 overflow-y-auto px-4 py-8 md:px-6 ${
            empty ? "justify-center" : "justify-start"
          }`}
          ref={messagesRef}
        >
          {empty ? (
            <div className="mb-8 text-center">
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                {companies.length > 1 && !activeCompanyId
                  ? "Choose a company to open its workspace"
                  : "What’s on the agenda today?"}
              </h1>
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
              <div className="mb-2 flex w-fit max-w-full items-center gap-2 rounded-xl border border-white/10 bg-[#303030] px-3 py-2 text-sm">
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
              className="rounded-[28px] border border-white/15 bg-[#303030] px-3 py-2 shadow-lg shadow-black/10 focus-within:border-white/25"
              onSubmit={sendMessage}
            >
              <textarea
                className="block max-h-48 min-h-10 w-full resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-white outline-none placeholder:text-white/40"
                disabled={companies.length > 1 && !activeCompanyId}
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
                  disabled={companies.length > 1 && !activeCompanyId}
                  onClick={() => fileRef.current?.click()}
                  title="Attach a supported file"
                  type="button"
                >
                  <Plus size={21} />
                </button>
                <button
                  aria-label="Send message"
                  className="grid h-9 w-9 place-items-center rounded-full bg-white text-[#212121] transition hover:bg-white/80 disabled:cursor-not-allowed disabled:opacity-35"
                  disabled={
                    busy ||
                    (companies.length > 1 && !activeCompanyId) ||
                    (!selectedFile && waitingForIndex) ||
                    (!prompt.trim() && !selectedFile)
                  }
                  type="submit"
                >
                  {busy ? (
                    <LoaderCircle className="animate-spin" size={17} />
                  ) : (
                    <ArrowUp size={19} strokeWidth={2.5} />
                  )}
                </button>
              </div>
            </form>
            <p className="mt-2 text-center text-[11px] text-white/30">
              Supported file contents and your questions are sent to OpenAI.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
