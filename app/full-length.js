async function runFullLength(examId, cfg, fullConfig) {
  const componentSections = (fullConfig.sectionIds || []).map(sectionId =>
    cfg.sections.find(section => section.id === sectionId)
  );

  if (
    componentSections.length !== 5 ||
    componentSections.some(section => !section)
  ) {
    qs("title").textContent = "Full-Length configuration error";
    qs("desc").textContent = "The five HSPT sections are not configured correctly.";
    return;
  }

  const allExamSets = await Promise.all(
    componentSections.map(section => loadQuestionsForSection(examId, section))
  );

  const availableExamCount = Math.min(
    Number(fullConfig.examCount || 0) || Infinity,
    ...allExamSets.map(sets => sets.length)
  );

  if (!Number.isFinite(availableExamCount) || availableExamCount < 1) {
    qs("title").textContent = "No Full-Length exam available";
    qs("desc").textContent = "No complete HSPT exam set could be loaded.";
    return;
  }

  const rotationKey = `fullLengthRotation_${examId}`;
  let examIndex = parseInt(localStorage.getItem(rotationKey) || "0", 10);
  if (!Number.isInteger(examIndex) || examIndex >= availableExamCount) examIndex = 0;
  localStorage.setItem(
    rotationKey,
    String((examIndex + 1) % availableExamCount)
  );

  const examNumber = String(examIndex + 1).padStart(2, "0");
  const sessions = componentSections.map((section, index) => {
    const chosen = allExamSets[index][examIndex];
    if (!chosen) throw new Error(`Missing Full-Length set for ${section.id}`);

    const questions = chosen.questions
      .slice(0, section.examQuestions)
      .map(question => ({
        ...question,
        fullLengthSectionId: section.id,
        fullLengthSectionLabel: section.label,
      }));

    if (questions.length !== section.examQuestions) {
      throw new Error(
        `${section.id}: expected ${section.examQuestions} questions, found ${questions.length}`
      );
    }

    return { section, chosen, questions };
  });

  const answers = {};
  const sectionTimes = Array(sessions.length).fill(0);
  let sectionIndex = 0;
  let questionIndex = 0;
  let remaining = sessions[0].section.timeMin * 60;
  let timerInterval = null;
  let sectionClosing = false;

  const runnerPanel = qs("runnerPanel");
  const transitionPanel = qs("transitionPanel");
  const resultsPanel = qs("resultsPanel");
  const timerEl = qs("timer");

  function currentSession() {
    return sessions[sectionIndex];
  }

  function showFullLengthConfirmation(title, message, confirmLabel) {
    const dialog = qs("fullLengthConfirm");
    const titleEl = qs("fullLengthConfirmTitle");
    const messageEl = qs("fullLengthConfirmMessage");
    const cancelBtn = qs("fullLengthCancelBtn");
    const confirmBtn = qs("fullLengthConfirmBtn");

    titleEl.textContent = title;
    messageEl.textContent = message;
    confirmBtn.textContent = confirmLabel;

    return new Promise(resolve => {
      let settled = false;

      function closeDialog(result) {
        if (settled) return;
        settled = true;
        if (dialog.open) dialog.close();
        resolve(result);
      }

      cancelBtn.onclick = () => closeDialog(false);
      confirmBtn.onclick = () => closeDialog(true);
      dialog.oncancel = event => {
        event.preventDefault();
        closeDialog(false);
      };

      dialog.showModal();
    });
  }

  function renderQuestion() {
    const session = currentSession();
    const section = session.section;
    const question = session.questions[questionIndex];

    qs("title").textContent =
      `${section.label} — Full-Length Exam ${examNumber}`;
    qs("desc").textContent =
      `${section.examQuestions} questions in ${section.timeMin} minutes. ` +
      "Completed sections cannot be reopened.";
    qs("metaLine").textContent =
      `Full-Length Exam ${examNumber} of ${availableExamCount} • ` +
      `Section ${sectionIndex + 1} of ${sessions.length}`;
    qs("progress").textContent =
      `Section ${sectionIndex + 1} of ${sessions.length} • ` +
      `Question ${questionIndex + 1} of ${session.questions.length}`;

    const partEl = qs("itemPart");
    if (partEl) partEl.textContent = getPartLabel(question);

    const instructionEl = qs("itemInstruction");
    if (instructionEl) {
      instructionEl.textContent =
        question.instruction || getDefaultInstruction(question);
    }

    const stimulusPanel = qs("stimulusPanel");
    const stimulusType = qs("stimulusType");
    const stimulusTitle = qs("stimulusTitle");
    const stimulusText = qs("stimulusText");

    if (question.stimulusText) {
      stimulusPanel.classList.remove("hidden");
      stimulusType.textContent = question.stimulusType || "Passage";
      stimulusTitle.textContent = question.stimulusTitle || "";
      stimulusTitle.classList.toggle("hidden", !question.stimulusTitle);
      stimulusText.innerHTML = renderInlineMarkup(question.stimulusText);
    } else {
      stimulusPanel.classList.add("hidden");
      stimulusType.textContent = "";
      stimulusTitle.textContent = "";
      stimulusText.textContent = "";
    }

    qs("prompt").innerHTML = renderInlineMarkup(question.prompt);

    const choices = qs("choices");
    choices.innerHTML = "";

    ["A", "B", "C", "D"].forEach(letter => {
      if (!question.choices || question.choices[letter] == null) return;

      const row = document.createElement("label");
      row.className = "choice";

      const input = document.createElement("input");
      input.type = "radio";
      input.name = `choice_${question.id}`;
      input.value = letter;
      input.checked = answers[question.id] === letter;
      input.addEventListener("change", () => {
        answers[question.id] = letter;
      });

      const text = document.createElement("span");
      text.className = "choiceText";
      text.innerHTML =
        `${letter}. ${renderInlineMarkup(question.choices[letter])}`;

      row.appendChild(input);
      row.appendChild(text);
      choices.appendChild(row);
    });

    qs("prevBtn").disabled = questionIndex === 0;
    qs("nextBtn").disabled =
      questionIndex === session.questions.length - 1;
    qs("finishBtn").textContent =
      sectionIndex === sessions.length - 1
        ? "Finish Full-Length Exam"
        : "Finish Section";
  }

  function startTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerEl.classList.remove("hidden");
    timerEl.textContent = fmtTime(remaining);

    timerInterval = setInterval(() => {
      remaining--;
      timerEl.textContent = fmtTime(Math.max(0, remaining));
      if (remaining <= 0) completeSection(true);
    }, 1000);
  }

  function showCurrentSection() {
    sectionClosing = false;
    runnerPanel.classList.remove("hidden");
    transitionPanel.classList.add("hidden");
    resultsPanel.classList.add("hidden");
    renderQuestion();
    startTimer();
  }

  function sectionScore(session) {
    const correct = session.questions.reduce(
      (total, question) =>
        total + ((answers[question.id] || "") === question.correct ? 1 : 0),
      0
    );
    return {
      correct,
      total: session.questions.length,
      pct: Math.round((correct / session.questions.length) * 100),
    };
  }

  function appendReviewBlock(review, question, number) {
    const user = answers[question.id] || "(no answer)";
    const correct = user === question.correct;

    const block = document.createElement("div");
    block.className = "reviewBlock";

    const num = document.createElement("div");
    num.className = correct ? "qnum qnum-ok" : "qnum qnum-bad";
    num.textContent = `Q${number}`;

    const text = document.createElement("div");
    text.className = "reviewText";

    const part = document.createElement("div");
    part.className = "reviewAns";
    part.textContent =
      `${question.fullLengthSectionLabel} • ${getPartLabel(question)}`;

    const prompt = document.createElement("div");
    prompt.className = "reviewPrompt";
    prompt.innerHTML = renderInlineMarkup(question.prompt);

    const answer = document.createElement("div");
    answer.className = "reviewAns";
    answer.textContent =
      `Your answer: ${user}    |    Correct: ${question.correct}`;

    const explanation = document.createElement("div");
    explanation.className = "reviewExp";
    explanation.textContent = question.explanation;

    text.appendChild(part);
    text.appendChild(prompt);
    text.appendChild(answer);
    text.appendChild(explanation);
    block.appendChild(num);
    block.appendChild(text);
    review.appendChild(block);
  }

  function finishFullLength() {
    if (timerInterval) clearInterval(timerInterval);
    timerEl.classList.add("hidden");
    runnerPanel.classList.add("hidden");
    transitionPanel.classList.add("hidden");
    resultsPanel.classList.remove("hidden");

    const allQuestions = sessions.flatMap(session => session.questions);
    const totalCorrect = allQuestions.reduce(
      (total, question) =>
        total + ((answers[question.id] || "") === question.correct ? 1 : 0),
      0
    );
    const percentage = Math.round(
      (totalCorrect / allQuestions.length) * 100
    );
    const totalUsed = sectionTimes.reduce((sum, seconds) => sum + seconds, 0);

    qs("scoreLine").textContent =
      `Full-Length Exam ${examNumber}: ${percentage}% ` +
      `(${totalCorrect}/${allQuestions.length} correct).`;
    qs("timeLine").textContent =
      `Timed work used: ${fmtTime(totalUsed)} of ` +
      `${fmtTime(fullConfig.totalTimeMin * 60)}.`;

    const sectionResults = qs("sectionResults");
    sectionResults.classList.remove("hidden");
    sectionResults.innerHTML = "";

    const heading = document.createElement("h3");
    heading.textContent = "Section Results";
    heading.style.margin = "0 0 10px";
    sectionResults.appendChild(heading);

    sessions.forEach((session, index) => {
      const score = sectionScore(session);
      const line = document.createElement("p");
      line.className = "helper";
      line.textContent =
        `${session.section.label}: ${score.pct}% ` +
        `(${score.correct}/${score.total}) • ` +
        `Time used: ${fmtTime(sectionTimes[index])}`;
      sectionResults.appendChild(line);
    });

    const review = qs("review");
    review.innerHTML = "";
    let fullQuestionNumber = 0;

    sessions.forEach(session => {
      const sectionHeading = document.createElement("h3");
      sectionHeading.textContent = session.section.label;
      sectionHeading.style.marginTop = "22px";
      review.appendChild(sectionHeading);

      session.questions.forEach(question => {
        fullQuestionNumber++;
        appendReviewBlock(review, question, fullQuestionNumber);
      });
    });
  }

  function completeSection(timedOut) {
    if (sectionClosing) return;
    sectionClosing = true;
    if (timerInterval) clearInterval(timerInterval);

    const session = currentSession();
    const allowed = session.section.timeMin * 60;
    sectionTimes[sectionIndex] = Math.min(
      allowed,
      Math.max(0, allowed - remaining)
    );

    if (sectionIndex === sessions.length - 1) {
      finishFullLength();
      return;
    }

    const completed = session.section;
    const next = sessions[sectionIndex + 1].section;

    runnerPanel.classList.add("hidden");
    transitionPanel.classList.remove("hidden");
    timerEl.classList.add("hidden");

    qs("transitionTitle").textContent =
      `${completed.label} ${timedOut ? "Time Expired" : "Complete"}`;
    const transitionGuidance =
      sectionIndex === 1
        ? "Recommended HSPT break: 5 minutes."
        : sectionIndex === 3
          ? "Recommended HSPT break: about 2 minutes."
          : "Proceed when the directions for the next section are complete.";

    qs("transitionDesc").textContent =
      `Next: ${next.label} — ${next.examQuestions} questions in ` +
      `${next.timeMin} minutes. ${transitionGuidance}`;
    qs("transitionBtn").textContent = `Start ${next.label}`;
  }

  qs("prevBtn").addEventListener("click", () => {
    if (questionIndex > 0) {
      questionIndex--;
      renderQuestion();
    }
  });

  qs("nextBtn").addEventListener("click", () => {
    if (questionIndex < currentSession().questions.length - 1) {
      questionIndex++;
      renderQuestion();
    }
  });

  qs("finishBtn").addEventListener("click", async () => {
    const unanswered = currentSession().questions.filter(
      question => !answers[question.id]
    ).length;
    const isFinalSection = sectionIndex === sessions.length - 1;
    const label = isFinalSection ? "exam" : "section";

    if (unanswered) {
      const confirmed = await showFullLengthConfirmation(
        isFinalSection ? "Finish Full-Length Exam?" : "Finish Section?",
        `${unanswered} question${unanswered === 1 ? " is" : "s are"} ` +
          `unanswered. Are you sure you want to finish this ${label}?`,
        isFinalSection ? "Finish Exam" : "Finish Section"
      );

      if (!confirmed) return;
    }

    completeSection(false);
  });

  qs("transitionBtn").addEventListener("click", () => {
    sectionIndex++;
    questionIndex = 0;
    remaining = currentSession().section.timeMin * 60;
    showCurrentSection();
  });

  qs("backLink").addEventListener("click", async event => {
    event.preventDefault();

    const confirmed = await showFullLengthConfirmation(
      "Leave Full-Length Exam?",
      "Current answers will be lost if you leave this exam.",
      "Leave Exam"
    );

    if (confirmed) {
      window.location.href =
        `app.html?exam=${encodeURIComponent(examId)}`;
    }
  });

  qs("homeBtn").addEventListener("click", () => {
    window.location.href = `app.html?exam=${encodeURIComponent(examId)}`;
  });

  showCurrentSection();
}
