(() => {
  const bootstrap = window.TALE_BOOTSTRAP || {};
  const transferCode = localStorage.getItem("TALE_TRANSFER_CODE");
  const sample = transferCode || bootstrap.sample || "";
  if (transferCode) {
    localStorage.removeItem("TALE_TRANSFER_CODE");
  }
  const terminalEl = document.getElementById("terminal");
  const runBtn = document.getElementById("run-btn");
  const statusPill = document.getElementById("status-pill");
  const wrapToggle = document.getElementById("wrap-toggle");
  const fontSlider = document.getElementById("font-slider");
  const insertExampleBtn = document.getElementById("insert-example");
  const exampleHideBtn = document.getElementById("example-hide");
  const exampleShowBtn = document.getElementById("example-show");
  const spinnerOverlay = document.getElementById("spinner-overlay");
  const spinnerText = spinnerOverlay?.querySelector(".spinner-text");
  const terminalOnBtn = document.getElementById("terminal-on");
  const terminalClear = document.getElementById("terminal-clear");
  const terminalOffBtn = document.getElementById("terminal-off");
  const examplePanel = document.querySelector(".example-panel");
  const mainStack = document.querySelector(".main-stack");
  const workspaceShell = document.querySelector(".workspace-shell");
  const workspaceEl = document.querySelector(".workspace");
  const editorPane = document.querySelector(".editor-pane");
  const sidePane = document.querySelector(".side-pane");
  const terminalPane = document.querySelector(".terminal-pane");
  const verticalDivider = document.querySelector('[data-divider="vertical"]');
  const horizontalDivider = document.querySelector('[data-divider="horizontal"]');

  let editor;
  let analyzeTimer;
  let analyzeVersion = 0;
  let collectedInputs = [];
  let inputForm;
  let examplesHidden = false;
  let promptMode = false;
  let promptOverlay;
  let codeSnapshot = sample;
  let wrapBeforePrompt = "off";

  const PROMPT_PLACEHOLDER = "Describe what program you want to build...";

  const KEYWORDS = [
    "say","ask","if","else","elif","end","repeat","while","for","each","in","function","return","class","import","try","catch","finally","raise","lambda","is"
  ];
  const TYPES = ["list","tuple","set","dict","number","text","decimal","boolean","none"];
  const OPERATORS = ["+","-","*","/","%",">","<",">=","<=","==","!=","and","or","not"];
  const BUILTINS = ["len","sum","min","max","sorted","map","filter","zip","any","all"];
  const METHODS = ["upper","lower","split","join","replace","strip","find","count"];
  const SIGNATURES = {
    say: {
      label: "say value",
      documentation: "Prints one or more values to the terminal.",
      parameters: ["value"],
    },
    repeat: {
      label: "repeat count",
      documentation: "Repeats a block count times.",
      parameters: ["count"],
    },
    function: {
      label: "function name params",
      documentation: "Defines a function with optional parameters.",
      parameters: ["name", "params"],
    },
  };

  const setStatus = (state, text) => {
    statusPill.classList.remove("idle","running","error");
    statusPill.classList.add(state);
    statusPill.textContent = text;
  };

  const toggleSpinner = (show, message) => {
    if (!spinnerOverlay) return;
    if (spinnerText && message) spinnerText.textContent = message;
    spinnerOverlay.classList.toggle("visible", Boolean(show));
    spinnerOverlay.setAttribute("aria-hidden", show ? "false" : "true");
  };

  const showSpinner = (message) => toggleSpinner(true, message || "Working...");
  const hideSpinner = () => toggleSpinner(false);

  const clearTerminal = () => {
    terminalEl.innerHTML = "";
  };

  const appendLine = (text, type) => {
    const line = document.createElement("div");
    line.className = `terminal-line ${type}`;
    line.textContent = text;
    terminalEl.appendChild(line);
    terminalEl.scrollTop = terminalEl.scrollHeight;
  };

  const renderOutput = (payload) => {
    if (!payload) {
      appendLine("(no output)", "stdout");
      return;
    }
    const lines = payload.replace(/\r/g, "").split("\n");
    lines.forEach((l) => appendLine(l, "stdout"));
  };

  const renderError = (message) => {
    appendLine(message || "Error", "stderr");
  };

  const detectAsk = (code) => /\bask\b/i.test(code || editor.getValue());

  const destroyInputForm = () => {
    if (inputForm && inputForm.parentElement) inputForm.parentElement.removeChild(inputForm);
    inputForm = null;
  };

  const collectInputsInteractive = (expectedCount = 1, promptLabels = []) => new Promise((resolve) => {
    destroyInputForm();
    collectedInputs = [];
    appendLine(`Program needs input (${expectedCount}). Press Enter for each; it auto-runs after the last one.`, "input");

    const form = document.createElement("form");
    form.className = "terminal-input-form";

    const label = document.createElement("label");
    const labelForIndex = (idx) => {
      const name = promptLabels[idx] || `${idx + 1}`;
      return `ask ${name} >`;
    };
    label.textContent = labelForIndex(0);

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Enter value then press Enter";

    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.textContent = "Send inputs";

    const commit = () => {
      const value = input.value;
      collectedInputs.push(value);
      appendLine(`› ${value}`, "stdout");
      input.value = "";
      label.textContent = labelForIndex(collectedInputs.length);
      if (collectedInputs.length >= expectedCount) {
        finish();
      }
    };

    const finish = () => {
      destroyInputForm();
      resolve(collectedInputs);
    };

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        commit();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        finish();
      }
    });

    submitBtn.addEventListener("click", () => finish());

    form.appendChild(label);
    form.appendChild(input);
    form.appendChild(submitBtn);
    terminalEl.appendChild(form);
    inputForm = form;
    input.focus();
  });

  const languageConfig = {
    comments: { lineComment: "#" },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"' },
      { open: "'", close: "'" },
    ],
    surroundingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"' },
      { open: "'", close: "'" },
    ],
    indentationRules: {
      increaseIndentPattern: /(\b(if|elif|else|while|repeat|function|class|try|catch|finally|for each)\b.*$)/,
      decreaseIndentPattern: /^\s*end\b/,
    },
  };

  const monarchTokens = {
    defaultToken: "identifier",
    tokenizer: {
      root: [
        [/#[^$]*/, "comment"],
        [/\"[^\\\"]*(?:\\.[^\\\"]*)*\"/, "string"],
        [/\'[^\\\']*(?:\\.[^\\\']*)*\'/, "string"],
        [/\d+\.\d+/, "number.float"],
        [/\d+/, "number"],
        [new RegExp(`\\b(${KEYWORDS.join("|")})\\b`, "i"), "keyword"],
        [new RegExp(`\\b(${TYPES.join("|")})\\b`, "i"), "type"],
        [new RegExp(`\\b(${BUILTINS.join("|")})\\b`, "i"), "predefined"],
        [new RegExp(`\\b(${METHODS.join("|")})\\b`, "i"), "method"],
        [/\b[A-Za-z_][\w]*\b(?=\s*\()/, "function"],
        [/\b[A-Za-z_][\w]*\b/, "identifier"],
      ],
    },
  };

  const theme = {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7d91a3" },
      { token: "keyword", foreground: "c792ea", fontStyle: "bold" },
      { token: "string", foreground: "f6d365" },
      { token: "number", foreground: "a3e635" },
      { token: "type", foreground: "64b5f6" },
      { token: "predefined", foreground: "4dd0e1" },
      { token: "method", foreground: "9ae6b4" },
      { token: "function", foreground: "7da6ff" },
      { token: "identifier", foreground: "e5ecf1" },
    ],
    colors: {
      "editor.background": "#0f1419",
      "editorLineNumber.foreground": "#556678",
      "editorLineNumber.activeForeground": "#dff1ff",
      "editorCursor.foreground": "#7b6dff",
      "editor.selectionBackground": "#1f2b38",
      "editor.lineHighlightBackground": "#161f29",
      "editorBracketMatch.border": "#4dd0e1",
      "scrollbarSlider.background": "#2b3a47",
      "scrollbarSlider.hoverBackground": "#3b4a57",
    },
  };

  const promptTheme = {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7d91a3" },
      { token: "keyword", foreground: "9fd1ff", fontStyle: "bold" },
      { token: "string", foreground: "ffd685" },
      { token: "number", foreground: "c4f1f9" },
      { token: "type", foreground: "86c5ff" },
      { token: "predefined", foreground: "7ad8f0" },
      { token: "method", foreground: "b2f5ea" },
      { token: "function", foreground: "a8b4ff" },
      { token: "identifier", foreground: "e9f1f8" },
    ],
    colors: {
      "editor.background": "#0e1926",
      "editorLineNumber.foreground": "#5c6f85",
      "editorLineNumber.activeForeground": "#f0f6ff",
      "editorCursor.foreground": "#89b4ff",
      "editor.selectionBackground": "#1d2f43",
      "editor.lineHighlightBackground": "#142234",
      "editorBracketMatch.border": "#5aa4ff",
      "scrollbarSlider.background": "#203347",
      "scrollbarSlider.hoverBackground": "#2a3e52",
    },
  };

  const buildKeywordSuggestions = (range) => {
    const base = [...KEYWORDS, ...TYPES, ...OPERATORS, ...BUILTINS, ...METHODS];
    return base.map((label) => ({
      label,
      kind: monaco.languages.CompletionItemKind.Keyword,
      insertText: label,
      range,
    }));
  };

  const blockSnippets = (range) => ([
    {
      label: "if",
      kind: monaco.languages.CompletionItemKind.Snippet,
      insertText: "if ${1:condition}\n  ${2:body}\nend",
      insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
      range,
    },
    {
      label: "repeat",
      kind: monaco.languages.CompletionItemKind.Snippet,
      insertText: "repeat ${1:count}\n  ${2:body}\nend",
      insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
      range,
    },
    {
      label: "function",
      kind: monaco.languages.CompletionItemKind.Snippet,
      insertText: "function ${1:name} ${2:params}\n  ${3:body}\nend",
      insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
      range,
    },
    {
      label: "end",
      kind: monaco.languages.CompletionItemKind.Keyword,
      insertText: "end",
      range,
    },
  ]);

  const variableSuggestions = (model, range, lineLimit) => {
    const lines = model.getLinesContent().slice(0, lineLimit || model.getLineCount());
    const vars = new Set();
    lines.forEach((ln) => {
      const match = ln.match(/([A-Za-z_][\w]*)\s+is\b/);
      if (match) vars.add(match[1]);
    });
    return Array.from(vars).map((label) => ({
      label,
      kind: monaco.languages.CompletionItemKind.Variable,
      insertText: label,
      range,
    }));
  };

  const registerLanguage = () => {
    monaco.languages.register({ id: "tale" });
    monaco.languages.setLanguageConfiguration("tale", languageConfig);
    monaco.languages.setMonarchTokensProvider("tale", monarchTokens);
    monaco.editor.defineTheme("tale-dark", theme);
    monaco.editor.defineTheme("tale-prompt", promptTheme);

    monaco.languages.registerCompletionItemProvider("tale", {
      triggerCharacters: [" ", "\n", "(", "[", "{"],
      provideCompletionItems: (model, position) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endLineNumber: position.lineNumber,
          endColumn: word.endColumn,
        };
        const suggestions = [
          ...buildKeywordSuggestions(range),
          ...blockSnippets(range),
          ...variableSuggestions(model, range, position.lineNumber),
        ];
        return { suggestions };
      },
    });

    monaco.languages.registerSignatureHelpProvider("tale", {
      signatureHelpTriggerCharacters: [" ", "("],
      provideSignatureHelp: (model, position) => {
        const lineText = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
        const token = (lineText.trim().split(/\s+/).pop() || "").toLowerCase();
        const sig = SIGNATURES[token];
        if (!sig) return null;
        return {
          value: {
            signatures: [
              {
                label: sig.label,
                documentation: sig.documentation,
                parameters: sig.parameters.map((p) => ({ label: p })),
              },
            ],
            activeSignature: 0,
            activeParameter: 0,
          },
          dispose: () => {},
        };
      },
    });
  };

  const registerHover = () => {
    monaco.languages.registerHoverProvider("tale", {
      provideHover: (model, position) => {
        const markers = monaco.editor.getModelMarkers({ resource: model.uri });
        const marker = markers.find((m) => m.startLineNumber === position.lineNumber);
        if (!marker) return null;
        return {
          range: new monaco.Range(marker.startLineNumber, 1, marker.endLineNumber, marker.endColumn || 200),
          contents: [{ value: "I could not understand this line" }],
        };
      },
    });
  };

  const updatePromptOverlay = () => {
    if (!promptOverlay || !editor) return;
    const show = promptMode && editor.getValue().trim().length === 0;
    promptOverlay.classList.toggle("visible", show);
  };

  const enterPromptMode = () => {
    if (!editor || promptMode) return;
    promptMode = true;
    codeSnapshot = editor.getValue();
    wrapBeforePrompt = editor.getOption(monaco.editor.EditorOption.wordWrap);
    clearTimeout(analyzeTimer);
    editor.updateOptions({ theme: "tale-prompt", wordWrap: "on" });
    editor.setValue("");
    monaco.editor.setModelMarkers(editor.getModel(), "tale", []);
    setStatus("idle", "Prompt");
    document.body.classList.add("prompt-mode");
    if (runBtn) runBtn.disabled = true;
    updatePromptOverlay();
    editor.focus();
  };

  const exitPromptMode = (nextCode) => {
    if (!editor || !promptMode) return;
    promptMode = false;
    document.body.classList.remove("prompt-mode");
    editor.updateOptions({ theme: "tale-dark", wordWrap: wrapBeforePrompt });
    editor.setValue(typeof nextCode === "string" ? nextCode : codeSnapshot);
    if (runBtn) runBtn.disabled = false;
    setStatus("idle", "Ready");
    updatePromptOverlay();
    analyze();
    editor.focus();
  };

  const analyze = () => {
    if (promptMode) return;
    clearTimeout(analyzeTimer);
    analyzeTimer = setTimeout(async () => {
      if (!editor) return;
      const version = ++analyzeVersion;
      const code = editor.getValue();
      try {
        const res = await fetch("/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const data = await res.json();
        if (version !== analyzeVersion) return;
        if (data.ok) {
          monaco.editor.setModelMarkers(editor.getModel(), "tale", []);
          setStatus("idle", "Ready");
          return;
        }
        const diag = (data.diagnostics || []).map((d) => ({
          severity: monaco.MarkerSeverity.Error,
          startLineNumber: d.line || 1,
          startColumn: 1,
          endLineNumber: d.line || 1,
          endColumn: 200,
          message: d.message || "I could not understand this line",
        }));
        monaco.editor.setModelMarkers(editor.getModel(), "tale", diag);
        setStatus("error", "Syntax issues");
      } catch (err) {
        setStatus("error", "Analyzer offline");
      }
    }, 350);
  };

  const submitPrompt = async () => {
    if (!promptMode || !editor) return;
    const prompt = editor.getValue().trim();
    updatePromptOverlay();
    if (!prompt) {
      setStatus("error", "Empty prompt");
      renderError("Enter a prompt to generate code.");
      return;
    }

    setStatus("running", "Generating");
    showSpinner("Crafting your TALE...");
    if (runBtn) runBtn.disabled = true;

    try {
      const res = await fetch("/ai_generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (res.ok && data.ok && data.code) {
        exitPromptMode(data.code);
        renderOutput("AI generation complete.");
      } else {
        const msg = data.error || "AI generation failed";
        setStatus("error", "AI failed");
        renderError(msg);
      }
    } catch (err) {
      setStatus("error", "AI offline");
      renderError("Network error while generating.");
    } finally {
      hideSpinner();
      if (runBtn) runBtn.disabled = promptMode;
    }
  };

  const runTale = async (useSelection) => {
    if (promptMode) {
      renderError("Exit prompt mode to run code.");
      setStatus("error", "Prompt active");
      return;
    }
    if (!editor) return;
    const model = editor.getModel();
    const selection = editor.getSelection();
    const code = useSelection && selection && !selection.isEmpty()
      ? model.getValueInRange(selection)
      : model.getValue();

    if (!code.trim()) {
      renderError("Nothing to run");
      return;
    }

    const askMatches = Array.from(code.matchAll(/^\s*ask\s+(.+)/gim)) || [];
    const promptLabels = askMatches.map((m) => {
      const body = (m[1] || "").trim();
      if (!body) return "input";

      if (body.toLowerCase().includes(" as ")) {
        const parts = body.split(/\s+as\s+/i);
        const target = (parts[1] || "").trim();
        return target || "input";
      }

      const ident = body.match(/^([A-Za-z_][\w]*)$/);
      if (ident) return ident[1];

      // Strip surrounding quotes for labels and truncate for neatness.
      const sanitized = body.replace(/^['"]|['"]$/g, "").slice(0, 18).trim();
      return sanitized || "input";
    });

    const needsInput = askMatches.length > 0;
    const inputs = needsInput ? await collectInputsInteractive(askMatches.length, promptLabels) : [];
    if (needsInput && inputs.length === 0) {
      renderError("No inputs provided");
      return;
    }

    setStatus("running", "Running");
    runBtn.disabled = true;
    appendLine("");
    appendLine(`▶ Run at ${new Date().toLocaleTimeString()}`, "input");
    appendLine("Running...", "stdout");

    try {
      const res = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, inputs }),
      });
      const data = await res.json();
      if (data.ok) {
        renderOutput(data.output || "");
        setStatus("idle", "Completed");
      } else {
        renderError(data.error || "Unknown error");
        setStatus("error", "Failed");
      }
    } catch (err) {
      renderError("Network error while running code.");
      setStatus("error", "Failed");
    } finally {
      runBtn.disabled = false;
    }
  };

  const initResizableLayout = () => {
    if (!mainStack || !workspaceShell || !workspaceEl || !editorPane || !sidePane || !terminalPane) return;

    const attachDrag = (divider, direction) => {
      if (!divider) return;

      const onMouseDown = (event) => {
        event.preventDefault();
        const startX = event.clientX;
        const startY = event.clientY;
        const startEditorWidth = editorPane.getBoundingClientRect().width;
        const startSideWidth = sidePane.getBoundingClientRect().width;
        const containerHeight = mainStack.getBoundingClientRect().height;
        const startTopHeight = workspaceShell.getBoundingClientRect().height;
        const startBottomHeight = terminalPane.getBoundingClientRect().height;

        const onMouseMove = (moveEvent) => {
          if (direction === "vertical") {
            const deltaX = moveEvent.clientX - startX;
            const total = startEditorWidth + startSideWidth;
            const minEditor = 280;
            const minSide = 240;
            let nextEditor = startEditorWidth + deltaX;
            nextEditor = Math.max(minEditor, Math.min(total - minSide, nextEditor));
            const editorPct = (nextEditor / total) * 100;
            const sidePct = 100 - editorPct;
            editorPane.style.flexBasis = `${editorPct}%`;
            sidePane.style.flexBasis = `${sidePct}%`;
          } else {
            const deltaY = moveEvent.clientY - startY;
            const totalHeight = Math.max(containerHeight, startTopHeight + startBottomHeight);
            const minTop = 200;
            const minBottom = 140;
            let nextTop = startTopHeight + deltaY;
            nextTop = Math.max(minTop, Math.min(totalHeight - minBottom, nextTop));
            const topPct = (nextTop / totalHeight) * 100;
            const bottomPct = 100 - topPct;
            workspaceShell.style.flexBasis = `${topPct}%`;
            terminalPane.style.flexBasis = `${bottomPct}%`;
            editor.layout();
            if (examplePanel && !examplePanel.classList.contains("collapsed")) {
              // ensure side content refreshes height as container changes
              examplePanel.style.height = "auto";
            }
          }
          document.body.style.userSelect = "none";
          document.body.style.cursor = direction === "vertical" ? "col-resize" : "row-resize";
        };

        const onMouseUp = () => {
          document.body.style.userSelect = "";
          document.body.style.cursor = "";
          window.removeEventListener("mousemove", onMouseMove);
          window.removeEventListener("mouseup", onMouseUp);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
      };

      divider.addEventListener("mousedown", onMouseDown);
      divider.addEventListener("touchstart", (event) => {
        const touch = event.touches[0];
        if (!touch) return;
        onMouseDown({
          preventDefault: () => event.preventDefault(),
          clientX: touch.clientX,
          clientY: touch.clientY,
        });
      }, { passive: false });
    };

    attachDrag(verticalDivider, "vertical");
    attachDrag(horizontalDivider, "horizontal");
  };

  const initEditor = () => {
    registerLanguage();
    registerHover();
    editor = monaco.editor.create(document.getElementById("editor"), {
      value: sample,
      language: "tale",
      theme: "tale-dark",
      automaticLayout: true,
      fontSize: Number(fontSlider.value),
      fontFamily: "JetBrains Mono, Consolas, monospace",
      minimap: { enabled: false },
      lineNumbers: "on",
      scrollBeyondLastLine: false,
      renderWhitespace: "selection",
      smoothScrolling: true,
      wordWrap: "off",
      autoClosingBrackets: "always",
      autoClosingQuotes: "always",
      autoIndent: "advanced",
      renderLineHighlight: "all",
      matchBrackets: "always",
      folding: true,
      tabSize: 2,
      insertSpaces: true,
      quickSuggestions: true,
      suggestOnTriggerCharacters: true,
    });

    // Ensure F8 works even when the Monaco editor has focus (Monaco reserves F8 by default).
    editor.addCommand(monaco.KeyMod.None | monaco.KeyCode.F8, () => {
      if (promptMode) {
        submitPrompt();
      } else {
        enterPromptMode();
      }
    });

    const editorDom = editor.getDomNode();
    promptOverlay = document.createElement("div");
    promptOverlay.className = "prompt-overlay";
    promptOverlay.textContent = PROMPT_PLACEHOLDER;
    if (editorDom) editorDom.appendChild(promptOverlay);

    editor.onDidChangeModelContent(() => {
      if (promptMode) {
        updatePromptOverlay();
        return;
      }
      analyze();
    });
  };

  const bindUI = () => {
    wrapToggle.addEventListener("click", () => {
      const wrapOn = editor.getOption(monaco.editor.EditorOption.wordWrap) === "on";
      editor.updateOptions({ wordWrap: wrapOn ? "off" : "on" });
      wrapToggle.setAttribute("title", `Word wrap ${wrapOn ? "off" : "on"}`);
    });

    const updateExampleControls = () => {
      if (!exampleShowBtn) return;
      exampleShowBtn.style.display = examplesHidden ? "inline-flex" : "none";
    };

    const hideExamples = () => {
      examplesHidden = true;
      document.body.classList.add("examples-hidden");
      updateExampleControls();
      editor.layout();
    };

    const showExamples = () => {
      examplesHidden = false;
      document.body.classList.remove("examples-hidden");
      updateExampleControls();
      editor.layout();
    };

    if (exampleShowBtn) {
      exampleShowBtn.addEventListener("click", showExamples);
    }

    if (exampleHideBtn) {
      exampleHideBtn.addEventListener("click", hideExamples);
    }

    const updateTerminalButtons = () => {
      if (!terminalOnBtn || !terminalOffBtn) return;
      const hidden = mainStack.classList.contains("terminal-hidden");
      terminalOnBtn.style.display = hidden ? "inline-flex" : "none";
      terminalOffBtn.style.display = hidden ? "none" : "inline-flex";
    };

    const hideTerminal = () => {
      mainStack.classList.add("terminal-hidden");
      updateTerminalButtons();
      editor.layout();
    };

    const showTerminal = () => {
      mainStack.classList.remove("terminal-hidden");
      updateTerminalButtons();
      editor.layout();
    };

    if (terminalOffBtn) {
      terminalOffBtn.addEventListener("click", hideTerminal);
    }

    if (terminalOnBtn) {
      terminalOnBtn.addEventListener("click", showTerminal);
    }

    if (terminalClear) {
      terminalClear.addEventListener("click", () => clearTerminal());
    }

    // initial state
    updateExampleControls();
    updateTerminalButtons();

    fontSlider.addEventListener("input", (e) => {
      editor.updateOptions({ fontSize: Number(e.target.value) });
    });

    runBtn.addEventListener("click", () => runTale(false));
    insertExampleBtn.addEventListener("click", () => editor.setValue(document.querySelector(".example").textContent));

    window.addEventListener("keydown", (e) => {
      if (e.key === "F2") {
        e.preventDefault();
        enterPromptMode();
      }
      if (e.key === "F8") {
        e.preventDefault();
        submitPrompt();
      }
      if (e.key === "Escape" && promptMode) {
        e.preventDefault();
        exitPromptMode();
      }
      if (e.key === "F5") {
        e.preventDefault();
        runTale(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        runTale(true);
      }
    });
  };

  require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
  window.MonacoEnvironment = { getWorkerUrl: () => "data:text/javascript;charset=utf-8," + encodeURIComponent(`self.MonacoEnvironment={baseUrl:'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/'};importScripts('https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/base/worker/workerMain.js');`) };

  require(["vs/editor/editor.main"], () => {
    initEditor();
    bindUI();
    initResizableLayout();
    analyze();
    renderOutput("Ready.");
  });
})();
