(() => {
  const lessons = Array.from(document.querySelectorAll(".lesson"));
  const tocLinks = Array.from(document.querySelectorAll(".toc a"));
  const progressCount = document.getElementById("progress-count");
  const progressBar = document.getElementById("progress-bar");
  const progressPercent = document.getElementById("progress-percent");
  const expandAllBtn = document.getElementById("expand-all");
  const progressKey = "tale-learn-progress-v1";

  const loadProgress = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(progressKey) || "[]");
      return new Set(saved);
    } catch (err) {
      return new Set();
    }
  };

  const done = loadProgress();

  const saveProgress = () => {
    localStorage.setItem(progressKey, JSON.stringify(Array.from(done)));
  };

  const markStatus = () => {
    const total = lessons.length;
    lessons.forEach((lesson) => {
      const id = lesson.dataset.lessonId || lesson.id;
      const isDone = done.has(id);
      lesson.classList.toggle("done", isDone);
      const statusChip = document.querySelector(`[data-lesson-status="${id}"]`);
      if (statusChip) {
        statusChip.textContent = isDone ? "Done" : "Not done yet";
      }
      const markBtn = lesson.querySelector(".mark-done");
      if (markBtn) {
        markBtn.textContent = isDone ? "Mark undone" : "Mark done";
      }
    });
    const finished = done.size;
    const percent = Math.round((finished / total) * 100);
    if (progressCount) progressCount.textContent = `${finished} / ${total} lessons done`;
    if (progressBar) progressBar.style.width = `${percent}%`;
    if (progressPercent) progressPercent.textContent = `${percent}%`;
    tocLinks.forEach((link) => {
      const targetId = link.getAttribute("href")?.replace("#", "");
      link.classList.toggle("done", done.has(targetId));
    });
  };

  lessons.forEach((lesson) => {
    const id = lesson.dataset.lessonId || lesson.id;
    const markBtn = lesson.querySelector(".mark-done");
    const collapseBtn = lesson.querySelector(".collapse-btn");

    if (done.has(id)) {
      lesson.classList.add("done");
    }

    if (markBtn) {
      markBtn.addEventListener("click", () => {
        if (done.has(id)) {
          done.delete(id);
        } else {
          done.add(id);
        }
        saveProgress();
        markStatus();
      });
    }

    if (collapseBtn) {
      collapseBtn.addEventListener("click", () => {
        lesson.classList.toggle("collapsed");
        collapseBtn.textContent = lesson.classList.contains("collapsed") ? "Expand" : "Collapse";
      });
    }
  });

  if (expandAllBtn) {
    expandAllBtn.addEventListener("click", () => {
      lessons.forEach((l) => l.classList.remove("collapsed"));
      const collapseButtons = document.querySelectorAll(".collapse-btn");
      collapseButtons.forEach((btn) => {
        btn.textContent = "Collapse";
      });
    });
  }

  const renderOutput = (el, text, isError) => {
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("error", Boolean(isError));
  };

  const getInputs = (card) => {
    const raw = card?.dataset?.inputs;
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  };

  const attachExamples = () => {
    const cards = document.querySelectorAll(".example-card");
    cards.forEach((card) => {
      const codeEl = card.querySelector("code");
      const runBtn = card.querySelector(".example-run");
      const copyBtn = card.querySelector(".example-copy");
      const outputEl = card.querySelector(".example-output");
      if (!codeEl) return;

      const getCode = () => codeEl.innerText.trim();

      if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(getCode());
            copyBtn.textContent = "Copied";
            setTimeout(() => { copyBtn.textContent = "Copy"; }, 1200);
          } catch (err) {
            copyBtn.textContent = "Copy failed";
            setTimeout(() => { copyBtn.textContent = "Copy"; }, 1400);
          }
        });
      }

      if (runBtn) {
        runBtn.addEventListener("click", async () => {
          const code = getCode();
          localStorage.setItem("TALE_TRANSFER_CODE", code);
          window.location.href = "/?from=learn";
        });
      }
    });
  };

  const observeSections = () => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const id = entry.target.id;
        tocLinks.forEach((link) => {
          const targetId = link.getAttribute("href")?.replace("#", "");
          link.classList.toggle("active", targetId === id);
        });
      });
    }, {
      threshold: 0.3,
      rootMargin: "-30% 0px -50% 0px",
    });
    lessons.forEach((lesson) => observer.observe(lesson));
  };

  attachExamples();
  markStatus();
  observeSections();
})();
