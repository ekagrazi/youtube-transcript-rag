import { APP_CONFIG } from "./config.js";
import { supabase } from "./supabaseClient.js";

const page = document.body.dataset.page;
const SESSION_EXPIRED_PATH = "./index.html?reason=session-expired";
const SELECTED_VIDEO_PREFIX = "framewise:selected-video:";

function setText(element, value) {
  if (element) {
    element.textContent = value ?? "";
  }
}

function setStatus(element, message, type = "info") {
  if (!element) return;
  element.textContent = message;
  element.dataset.type = type;
  element.hidden = !message;
}

function setButtonBusy(button, busy, busyLabel) {
  if (!button) return;
  const label = button.querySelector("[data-button-label]");
  if (label && !label.dataset.defaultLabel) {
    label.dataset.defaultLabel = label.textContent.trim();
  }
  button.disabled = busy;
  button.classList.toggle("is-loading", busy);
  if (busyLabel && label) {
    label.textContent = busy ? busyLabel : label.dataset.defaultLabel;
  }
}

function safeErrorMessage(error, fallback) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function authRedirect(reason = "") {
  const target = reason === "expired"
    ? SESSION_EXPIRED_PATH
    : "./index.html";
  window.location.replace(target);
}

async function currentSession() {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  return data.session;
}

async function apiFetch(path, options = {}) {
  const session = await currentSession();
  if (!session?.access_token) {
    authRedirect("expired");
    throw new Error("Your session has expired. Please sign in again.");
  }

  const baseUrl = APP_CONFIG.backendBaseUrl.replace(/\/+$/, "");
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${session.access_token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new Error(
      "The API is unreachable. Confirm the backend is running and try again.",
    );
  }

  if (response.status === 401) {
    await supabase.auth.signOut({ scope: "local" });
    authRedirect("expired");
    throw new Error("Your session has expired. Please sign in again.");
  }

  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new Error(
      payload?.detail || `Request failed with status ${response.status}`,
    );
  }
  return payload;
}

function initAuthPage() {
  const form = document.querySelector("#auth-form");
  const emailInput = document.querySelector("#email");
  const passwordInput = document.querySelector("#password");
  const passwordToggle = document.querySelector("#password-toggle");
  const submitButton = document.querySelector("#auth-submit");
  const status = document.querySelector("#auth-status");
  const title = document.querySelector("#auth-title");
  const intro = document.querySelector("#auth-intro");
  const passwordHint = document.querySelector("#password-hint");
  const tabs = [...document.querySelectorAll("[data-auth-mode]")];
  let mode = "login";
  let submitting = false;

  const query = new URLSearchParams(window.location.search);
  if (query.get("reason") === "session-expired") {
    setStatus(status, "Your session ended. Sign in to continue.", "warning");
  }

  function setMode(nextMode) {
    mode = nextMode;
    const isSignup = mode === "signup";
    setText(title, isSignup ? "Create your account" : "Welcome back");
    setText(
      intro,
      isSignup
        ? "Start a private workspace for transcript-grounded conversations."
        : "Sign in to continue your transcript conversations.",
    );
    setText(passwordHint, isSignup ? "Use 6 or more characters" : "");
    passwordInput.autocomplete = isSignup
      ? "new-password"
      : "current-password";
    form.setAttribute(
      "aria-labelledby",
      isSignup ? "signup-tab" : "login-tab",
    );

    tabs.forEach((tab) => {
      const selected = tab.dataset.authMode === mode;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });

    submitButton.querySelector("[data-button-label]").textContent = isSignup
      ? "Create account"
      : "Sign in";
    setStatus(status, "");
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => setMode(tab.dataset.authMode));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextIndex = (index + direction + tabs.length) % tabs.length;
      tabs[nextIndex].focus();
      setMode(tabs[nextIndex].dataset.authMode);
    });
  });

  passwordToggle.addEventListener("click", () => {
    const showing = passwordInput.type === "text";
    passwordInput.type = showing ? "password" : "text";
    passwordToggle.setAttribute("aria-pressed", String(!showing));
    passwordToggle.setAttribute(
      "aria-label",
      showing ? "Show password" : "Hide password",
    );
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting || !form.reportValidity()) return;

    submitting = true;
    setButtonBusy(
      submitButton,
      true,
      mode === "signup" ? "Creating account…" : "Signing in…",
    );
    setStatus(status, "");

    const credentials = {
      email: emailInput.value.trim(),
      password: passwordInput.value,
    };

    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          ...credentials,
          options: {
            emailRedirectTo: new URL(
              "./chat.html",
              window.location.href,
            ).href,
          },
        });
        if (error) throw error;
        if (data.session) {
          window.location.replace("./chat.html");
          return;
        }
        form.reset();
        setStatus(
          status,
          "Check your email to confirm your account, then sign in.",
          "success",
        );
      } else {
        const { error } = await supabase.auth.signInWithPassword(credentials);
        if (error) throw error;
        window.location.replace("./chat.html");
      }
    } catch (error) {
      setStatus(
        status,
        safeErrorMessage(error, "Authentication failed. Please try again."),
        "error",
      );
    } finally {
      submitting = false;
      setButtonBusy(submitButton, false);
    }
  });

  currentSession()
    .then((session) => {
      if (session) window.location.replace("./chat.html");
    })
    .catch((error) => {
      setStatus(
        status,
        safeErrorMessage(error, "Unable to restore your session."),
        "error",
      );
    });

  supabase.auth.onAuthStateChange((event, session) => {
    if (event === "SIGNED_IN" && session) {
      window.location.replace("./chat.html");
    }
  });
}

function initChatPage() {
  const loader = document.querySelector("#session-loader");
  const workspace = document.querySelector("#workspace");
  const userEmail = document.querySelector("#user-email");
  const logoutButton = document.querySelector("#logout-button");
  const refreshButton = document.querySelector("#refresh-videos");
  const ingestForm = document.querySelector("#ingest-form");
  const ingestInput = document.querySelector("#youtube-url");
  const ingestSubmit = document.querySelector("#ingest-submit");
  const ingestStatus = document.querySelector("#ingest-status");
  const videoList = document.querySelector("#video-list");
  const videoCount = document.querySelector("#video-count");
  const videoKicker = document.querySelector("#video-kicker");
  const videoTitle = document.querySelector("#video-title");
  const openVideo = document.querySelector("#open-video");
  const messageList = document.querySelector("#message-list");
  const emptyChat = document.querySelector("#empty-chat");
  const chatStatus = document.querySelector("#chat-status");
  const questionForm = document.querySelector("#question-form");
  const questionInput = document.querySelector("#question");
  const questionSubmit = document.querySelector("#question-submit");

  const state = {
    session: null,
    videos: [],
    selectedVideo: null,
    ingesting: false,
    asking: false,
    loadingHistory: false,
    deletingVideoIds: new Set(),
  };

  function selectedVideoStorageKey() {
    return `${SELECTED_VIDEO_PREFIX}${state.session?.user?.id || "unknown"}`;
  }

  function updateComposer() {
    const enabled = state.selectedVideo?.status === "ready";
    questionInput.disabled = !enabled || state.asking;
    questionSubmit.disabled = !enabled || state.asking;
    questionInput.placeholder = enabled
      ? "Ask a question about this transcript…"
      : "Select a ready video to start asking questions…";
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Recently added";
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(date);
  }

  function statusLabel(video) {
    if (video.status === "ready") return "Ready";
    if (video.status === "pending") return "Processing";
    return "Needs attention";
  }

  function createVideoItem(video) {
    const item = document.createElement("div");
    item.className = "video-item";
    item.dataset.videoId = String(video.id);
    if (state.selectedVideo?.id === video.id) {
      item.classList.add("is-selected");
    }

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "video-select-button";
    selectButton.setAttribute(
      "aria-pressed",
      String(state.selectedVideo?.id === video.id),
    );

    const thumbnail = document.createElement("span");
    thumbnail.className = "video-thumb";
    const thumbnailImage = document.createElement("img");
    thumbnailImage.src = `https://i.ytimg.com/vi/${encodeURIComponent(video.youtube_id)}/mqdefault.jpg`;
    thumbnailImage.alt = "";
    thumbnailImage.loading = "lazy";
    thumbnailImage.referrerPolicy = "no-referrer";
    thumbnail.append(thumbnailImage);

    const play = document.createElement("span");
    play.className = "thumb-play";
    play.textContent = "▶";
    thumbnail.append(play);

    const copy = document.createElement("span");
    copy.className = "video-copy";
    const name = document.createElement("strong");
    name.textContent = video.title || `YouTube · ${video.youtube_id}`;
    const meta = document.createElement("span");
    meta.className = `video-meta status-${video.status}`;
    meta.textContent = `${statusLabel(video)} · ${formatDate(video.created_at)}`;
    copy.append(name, meta);

    const arrow = document.createElement("span");
    arrow.className = "video-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "›";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "video-delete-button";
    deleteButton.setAttribute(
      "aria-label",
      `Delete ${name.textContent} from your library`,
    );
    deleteButton.title = "Delete from your library";
    deleteButton.textContent = "×";
    deleteButton.disabled = state.deletingVideoIds.has(video.id);

    selectButton.append(thumbnail, copy, arrow);
    selectButton.addEventListener("click", () => selectVideo(video));
    deleteButton.addEventListener("click", () => deleteVideo(video));
    item.append(selectButton, deleteButton);
    return item;
  }

  function renderVideos() {
    videoList.replaceChildren();
    setText(videoCount, String(state.videos.length));

    if (!state.videos.length) {
      const empty = document.createElement("p");
      empty.className = "empty-library";
      empty.textContent = "No videos yet. Add your first one above.";
      videoList.append(empty);
      return;
    }

    state.videos.forEach((video) => {
      videoList.append(createVideoItem(video));
    });
  }

  function createMessage(role, content, sources = []) {
    const article = document.createElement("article");
    article.className = `message message-${role}`;

    const label = document.createElement("div");
    label.className = "message-label";
    const badge = document.createElement("span");
    badge.className = "message-badge";
    badge.textContent = role === "user" ? "You" : "F";
    const name = document.createElement("strong");
    name.textContent = role === "user" ? "Your question" : "Framewise";
    label.append(badge, name);

    const body = document.createElement("p");
    body.className = "message-content";
    body.textContent = content;
    article.append(label, body);

    if (role === "assistant" && sources.length) {
      const sourceGroup = document.createElement("div");
      sourceGroup.className = "source-group";
      const sourceLabel = document.createElement("span");
      sourceLabel.className = "source-heading";
      sourceLabel.textContent = "Transcript evidence";
      sourceGroup.append(sourceLabel);

      const links = document.createElement("div");
      links.className = "source-links";
      sources.forEach((source, index) => {
        const link = document.createElement("a");
        link.className = "source-link";
        link.href = source.youtube_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = source.text;

        const play = document.createElement("span");
        play.className = "source-play";
        play.textContent = "▶";
        const time = document.createElement("span");
        time.textContent = formatTimestamp(source.start_time);
        const excerpt = document.createElement("span");
        excerpt.className = "source-excerpt";
        excerpt.textContent = source.text;
        const indexLabel = document.createElement("span");
        indexLabel.className = "source-index";
        indexLabel.textContent = String(index + 1).padStart(2, "0");

        link.append(play, time, excerpt, indexLabel);
        links.append(link);
      });
      sourceGroup.append(links);
      article.append(sourceGroup);
    }

    return article;
  }

  function formatTimestamp(value) {
    const totalSeconds = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
      : `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function appendMessage(role, content, sources = []) {
    emptyChat?.remove();
    messageList.append(createMessage(role, content, sources));
    messageList.scrollTo({
      top: messageList.scrollHeight,
      behavior: "smooth",
    });
  }

  function showConversationPlaceholder(video, message) {
    messageList.replaceChildren();
    const placeholder = document.createElement("div");
    placeholder.className = "empty-chat compact";
    const icon = document.createElement("div");
    icon.className = "status-orb";
    icon.textContent = video.status === "failed" ? "!" : "…";
    const heading = document.createElement("h3");
    heading.textContent = video.status === "failed"
      ? "This transcript needs attention"
      : "Transcript processing";
    const copy = document.createElement("p");
    copy.textContent = message;
    placeholder.append(icon, heading, copy);
    messageList.append(placeholder);
  }

  function clearSelectedVideo() {
    state.selectedVideo = null;
    localStorage.removeItem(selectedVideoStorageKey());
    setText(videoKicker, "No video selected");
    setText(videoTitle, "Start with a transcript");
    openVideo.hidden = true;
    openVideo.removeAttribute("href");
    messageList.replaceChildren();

    const placeholder = document.createElement("div");
    placeholder.className = "empty-chat compact";
    const heading = document.createElement("h3");
    heading.textContent = "Choose a video";
    const copy = document.createElement("p");
    copy.textContent = "Select another video or add one to your library.";
    placeholder.append(heading, copy);
    messageList.append(placeholder);
    setStatus(chatStatus, "");
    updateComposer();
  }

  async function deleteVideo(video) {
    if (state.deletingVideoIds.has(video.id)) return;

    const confirmed = window.confirm(
      `Delete "${video.title || video.youtube_id}" from your library?\n\n`
      + "Your chat history for this video will also be deleted.",
    );
    if (!confirmed) return;

    state.deletingVideoIds.add(video.id);
    renderVideos();
    setStatus(ingestStatus, "Removing video from your library…", "loading");

    try {
      await apiFetch(`/videos/${video.id}`, { method: "DELETE" });
      state.videos = state.videos.filter((item) => item.id !== video.id);
      const removedSelectedVideo = state.selectedVideo?.id === video.id;
      if (removedSelectedVideo) clearSelectedVideo();
      setStatus(
        ingestStatus,
        "Video and its chat history were removed from your library.",
        "success",
      );
      renderVideos();

      if (removedSelectedVideo && state.videos.length) {
        const next = state.videos.find((item) => item.status === "ready")
          || state.videos[0];
        await selectVideo(next);
      }
    } catch (error) {
      setStatus(
        ingestStatus,
        safeErrorMessage(error, "Unable to delete this video."),
        "error",
      );
    } finally {
      state.deletingVideoIds.delete(video.id);
      renderVideos();
    }
  }

  async function loadVideos({ preserveStatus = false } = {}) {
    refreshButton.classList.add("is-spinning");
    refreshButton.disabled = true;
    try {
      const videos = await apiFetch("/videos");
      state.videos = Array.isArray(videos) ? videos : [];
      renderVideos();

      const storedId = Number(localStorage.getItem(selectedVideoStorageKey()));
      const selected = state.videos.find(
        (video) => video.id === state.selectedVideo?.id,
      ) || state.videos.find((video) => video.id === storedId);

      if (selected) {
        await selectVideo(selected);
      } else if (!preserveStatus && state.videos.length) {
        const firstReady = state.videos.find(
          (video) => video.status === "ready",
        );
        await selectVideo(firstReady || state.videos[0]);
      }
    } catch (error) {
      setStatus(
        ingestStatus,
        safeErrorMessage(error, "Unable to load videos."),
        "error",
      );
      videoList.replaceChildren();
      const message = document.createElement("p");
      message.className = "empty-library";
      message.textContent = "The video library could not be loaded.";
      videoList.append(message);
    } finally {
      refreshButton.classList.remove("is-spinning");
      refreshButton.disabled = false;
    }
  }

  async function selectVideo(video) {
    state.selectedVideo = video;
    localStorage.setItem(selectedVideoStorageKey(), String(video.id));
    renderVideos();

    setText(videoKicker, `YouTube · ${statusLabel(video)}`);
    setText(videoTitle, video.title || `Video ${video.youtube_id}`);
    openVideo.href = `https://www.youtube.com/watch?v=${encodeURIComponent(video.youtube_id)}`;
    openVideo.hidden = false;
    updateComposer();

    if (video.status !== "ready") {
      showConversationPlaceholder(
        video,
        video.error_message || (
          video.status === "pending"
            ? "This video is still being prepared. Refresh the library shortly."
            : "Try ingesting the video again to restart transcript processing."
        ),
      );
      return;
    }

    state.loadingHistory = true;
    questionInput.disabled = true;
    questionSubmit.disabled = true;
    messageList.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "conversation-loading";
    loading.textContent = "Loading this conversation…";
    messageList.append(loading);

    try {
      const history = await apiFetch(`/chat/${video.id}/history`);
      if (state.selectedVideo?.id !== video.id) return;
      messageList.replaceChildren();
      if (!history.length) {
        const prompt = document.createElement("div");
        prompt.className = "empty-chat compact ready";
        const orb = document.createElement("div");
        orb.className = "status-orb ready";
        orb.textContent = "✓";
        const heading = document.createElement("h3");
        heading.textContent = "Transcript ready";
        const copy = document.createElement("p");
        copy.textContent = "Ask for a summary, a key idea, or a specific detail.";
        prompt.append(orb, heading, copy);
        messageList.append(prompt);
      } else {
        history.forEach((message) => {
          messageList.append(createMessage(message.role, message.content));
        });
        messageList.scrollTop = messageList.scrollHeight;
      }
    } catch (error) {
      setStatus(
        chatStatus,
        safeErrorMessage(error, "Unable to load chat history."),
        "error",
      );
    } finally {
      state.loadingHistory = false;
      updateComposer();
    }
  }

  ingestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.ingesting || !ingestForm.reportValidity()) return;

    state.ingesting = true;
    ingestInput.disabled = true;
    setButtonBusy(ingestSubmit, true);
    setStatus(
      ingestStatus,
      "Fetching and indexing the transcript. This can take a minute…",
      "loading",
    );

    try {
      const video = await apiFetch("/videos/ingest", {
        method: "POST",
        body: JSON.stringify({ youtube_url: ingestInput.value.trim() }),
      });
      ingestInput.value = "";
      await loadVideos({ preserveStatus: true });

      const refreshed = state.videos.find((item) => item.id === video.id)
        || video;
      await selectVideo(refreshed);

      if (video.status === "ready") {
        setStatus(
          ingestStatus,
          "Transcript ready. You can start asking questions.",
          "success",
        );
      } else if (video.status === "failed") {
        setStatus(
          ingestStatus,
          video.error_message || "Transcript ingestion failed. Please retry.",
          "error",
        );
      } else {
        setStatus(
          ingestStatus,
          "This transcript is already being processed. Refresh shortly.",
          "warning",
        );
      }
    } catch (error) {
      setStatus(
        ingestStatus,
        safeErrorMessage(error, "Unable to ingest this video."),
        "error",
      );
    } finally {
      state.ingesting = false;
      ingestInput.disabled = false;
      setButtonBusy(ingestSubmit, false);
      ingestInput.focus();
    }
  });

  questionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = questionInput.value.trim();
    const video = state.selectedVideo;
    if (
      state.asking
      || !question
      || !video
      || video.status !== "ready"
    ) return;

    state.asking = true;
    questionInput.value = "";
    questionInput.style.height = "";
    updateComposer();
    setStatus(chatStatus, "Generating a transcript-grounded answer…");
    appendMessage("user", question);

    const thinking = document.createElement("div");
    thinking.className = "thinking-message";
    thinking.setAttribute("role", "status");
    thinking.append(
      document.createElement("span"),
      document.createElement("span"),
      document.createElement("span"),
    );
    messageList.append(thinking);
    messageList.scrollTop = messageList.scrollHeight;

    try {
      const response = await apiFetch(`/chat/${video.id}`, {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      thinking.remove();
      appendMessage("assistant", response.answer, response.sources || []);
      setStatus(chatStatus, "");
    } catch (error) {
      thinking.remove();
      const message = safeErrorMessage(
        error,
        "Unable to answer that question right now.",
      );
      appendMessage("assistant", message);
      setStatus(chatStatus, message, "error");
    } finally {
      state.asking = false;
      updateComposer();
      questionInput.focus();
    }
  });

  questionInput.addEventListener("input", () => {
    questionInput.style.height = "auto";
    questionInput.style.height = `${Math.min(questionInput.scrollHeight, 180)}px`;
  });

  questionInput.addEventListener("keydown", (event) => {
    if (
      event.key === "Enter"
      && !event.shiftKey
      && !event.isComposing
    ) {
      event.preventDefault();
      questionForm.requestSubmit();
    }
  });

  refreshButton.addEventListener("click", () => loadVideos());

  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      await supabase.auth.signOut({ scope: "local" });
    } finally {
      authRedirect();
    }
  });

  async function start() {
    try {
      state.session = await currentSession();
      if (!state.session) {
        authRedirect("expired");
        return;
      }
      setText(userEmail, state.session.user.email || "Signed in");
      loader.hidden = true;
      workspace.hidden = false;
      await loadVideos();
    } catch {
      authRedirect("expired");
    }
  }

  supabase.auth.onAuthStateChange((event, session) => {
    state.session = session;
    if (event === "SIGNED_OUT" || !session) {
      authRedirect("expired");
      return;
    }
    if (event === "TOKEN_REFRESHED" || event === "USER_UPDATED") {
      setText(userEmail, session.user.email || "Signed in");
    }
  });

  start();
}

try {
  if (page === "auth") {
    initAuthPage();
  } else if (page === "chat") {
    initChatPage();
  }
} catch (error) {
  const fallback = document.createElement("p");
  fallback.className = "fatal-error";
  fallback.textContent = safeErrorMessage(
    error,
    "The application could not start. Check the public configuration.",
  );
  document.body.replaceChildren(fallback);
}
