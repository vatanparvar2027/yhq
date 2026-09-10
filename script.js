/* ==========================================================
   AVTOTEST UZ — Asosiy JavaScript Dastur Logikasi
   ========================================================== */

// --- TELEGRAM WEBAPP INTEGRATSIYASI ---
if (window.Telegram && window.Telegram.WebApp) {
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();
  if (tg.colorScheme) {
    document.documentElement.setAttribute('data-theme', tg.colorScheme);
  }
}

// --- DASTUR HOLATI (STATE) ---
const AppState = {
  currentView: 'home',
  quizMode: 'exam', // 'exam' | 'practice' | 'mistakes'
  activeQuestions: [],
  currentIndex: 0,
  userAnswers: {}, // { questionIndex: selectedOptionIndex }
  timerInterval: null,
  timeRemaining: 20 * 60, // 20 daqiqa
  timeSpent: 0,
  soundEnabled: true,
  stats: {
    totalTaken: 0,
    passedCount: 0,
    totalScoreSum: 0,
    mistakesIds: [] // xato qilingan savollar ID lari
  }
};

// --- AUDIO SINTIZATORI (Web Audio API) ---
class SoundEffects {
  constructor() {
    this.ctx = null;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
  }

  playTone(freq, type, duration, startDelay = 0) {
    if (!AppState.soundEnabled) return;
    this.init();
    if (!this.ctx) return;

    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime + startDelay);

      gain.gain.setValueAtTime(0.15, this.ctx.currentTime + startDelay);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + startDelay + duration);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start(this.ctx.currentTime + startDelay);
      osc.stop(this.ctx.currentTime + startDelay + duration);
    } catch (e) {
      console.log("Audio error:", e);
    }
  }

  correct() {
    this.playTone(523.25, 'sine', 0.12, 0);       // C5
    this.playTone(659.25, 'sine', 0.12, 0.08);    // E5
    this.playTone(783.99, 'sine', 0.25, 0.16);    // G5
  }

  wrong() {
    this.playTone(220, 'sawtooth', 0.2, 0);       // Past chastota
    this.playTone(180, 'sawtooth', 0.25, 0.1);
  }

  click() {
    this.playTone(600, 'sine', 0.05, 0);
  }

  finish() {
    this.playTone(440, 'triangle', 0.1, 0);
    this.playTone(554.37, 'triangle', 0.1, 0.1);
    this.playTone(659.25, 'triangle', 0.1, 0.2);
    this.playTone(880, 'triangle', 0.35, 0.3);
  }
}

const SFX = new SoundEffects();

// --- LOCAL STORAGE BILAN ISHLASH ---
function loadSavedData() {
  // Sozlamalar
  const savedTheme = localStorage.getItem('avtotest_theme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
  }

  const savedSound = localStorage.getItem('avtotest_sound');
  if (savedSound !== null) {
    AppState.soundEnabled = savedSound === 'true';
    updateSoundIcon();
  }

  // Statistika
  const savedStats = localStorage.getItem('avtotest_stats');
  if (savedStats) {
    try {
      AppState.stats = JSON.parse(savedStats);
    } catch (e) {}
  }
  updateStatsUI();
}

function saveStats() {
  localStorage.setItem('avtotest_stats', JSON.stringify(AppState.stats));
  updateStatsUI();
}

function updateStatsUI() {
  document.getElementById('stat-total-taken').textContent = AppState.stats.totalTaken;
  document.getElementById('stat-passed').textContent = AppState.stats.passedCount;
  
  const avg = AppState.stats.totalTaken > 0
    ? Math.round(AppState.stats.totalScoreSum / AppState.stats.totalTaken)
    : 0;
  document.getElementById('stat-avg-score').textContent = `${avg}%`;

  const mistakesCount = AppState.stats.mistakesIds ? AppState.stats.mistakesIds.length : 0;
  document.getElementById('stat-mistakes').textContent = mistakesCount;
  document.getElementById('badge-mistakes').textContent = mistakesCount;
}

// --- MAVZU (THEME) VA OVOZ ---
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('avtotest_theme', next);
  updateThemeIcon(next);
  SFX.click();
}

function updateThemeIcon(theme) {
  document.getElementById('theme-icon').textContent = theme === 'dark' ? '🌙' : '☀️';
}

function toggleSound() {
  AppState.soundEnabled = !AppState.soundEnabled;
  localStorage.setItem('avtotest_sound', AppState.soundEnabled);
  updateSoundIcon();
  if (AppState.soundEnabled) SFX.click();
}

function updateSoundIcon() {
  document.getElementById('sound-icon').textContent = AppState.soundEnabled ? '🔊' : '🔇';
}

// --- SAHIFALARNI ALMASHTIRISH (VIEW NAVIGATION) ---
function switchView(viewName) {
  AppState.currentView = viewName;

  // Barcha bo'limlarni yashirish
  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));

  // Kerakli bo'limni ko'rsatish
  const targetSec = document.getElementById(`view-${viewName}`);
  if (targetSec) {
    targetSec.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Header menyu faolligi
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.getAttribute('data-view') === viewName);
  });

  // Mobil bottom nav faolligi
  document.querySelectorAll('.bottom-nav-item').forEach(item => {
    item.classList.toggle('active', item.getAttribute('data-view') === viewName);
  });

  // Agar biletlar bo'limi ochilsa, yangilash
  if (viewName === 'tickets') {
    renderTicketsGrid();
  } else if (viewName === 'signs') {
    renderRoadSigns('all');
  } else if (viewName === 'mistakes') {
    renderMistakesView();
  }
}

// --- BILETLARNI GENERATSIYA QILISH ---
function renderTicketsGrid() {
  const container = document.getElementById('tickets-container');
  container.innerHTML = '';

  // Bazadagi biletlar sonini aniqlash
  const ticketsMap = {};
  QUESTIONS_DATABASE.forEach(q => {
    if (!ticketsMap[q.ticket]) ticketsMap[q.ticket] = 0;
    ticketsMap[q.ticket]++;
  });

  const ticketNumbers = Object.keys(ticketsMap).map(Number).sort((a, b) => a - b);

  ticketNumbers.forEach(tNum => {
    const qCount = ticketsMap[tNum];
    const card = document.createElement('div');
    card.className = 'ticket-card';
    card.innerHTML = `
      <div>
        <div class="ticket-header">
          <div class="ticket-number">${tNum}-Bilet</div>
          <span class="ticket-status-badge">Mashq</span>
        </div>
        <div class="ticket-meta">Savollar soni: ${qCount} ta</div>
      </div>
      <button class="btn btn-primary" onclick="startPracticeTicket(${tNum})">
        Mashqni Boshlash ➡
      </button>
    `;
    container.appendChild(card);
  });
}

// --- TESTNI BOSHLASH ---
function startExamMode() {
  SFX.click();
  AppState.quizMode = 'exam';
  
  // Tasodifiy 20 ta savol tanlash
  const shuffled = [...QUESTIONS_DATABASE].sort(() => 0.5 - Math.random());
  AppState.activeQuestions = shuffled.slice(0, 20);
  
  initQuizSession("⏱ Haqiqiy Imtihon", 20 * 60);
}

function startPracticeTicket(ticketNum) {
  SFX.click();
  AppState.quizMode = 'practice';
  
  AppState.activeQuestions = QUESTIONS_DATABASE.filter(q => q.ticket === ticketNum);
  if (AppState.activeQuestions.length === 0) {
    AppState.activeQuestions = QUESTIONS_DATABASE.slice(0, 20);
  }
  
  initQuizSession(`📖 ${ticketNum}-Bilet Mashqi`, 20 * 60);
}

function startMistakesPractice() {
  SFX.click();
  if (!AppState.stats.mistakesIds || AppState.stats.mistakesIds.length === 0) {
    alert("Hozircha xatolar mavjud emas!");
    return;
  }

  AppState.quizMode = 'mistakes';
  AppState.activeQuestions = QUESTIONS_DATABASE.filter(q => AppState.stats.mistakesIds.includes(q.id));
  
  initQuizSession("❌ Xatolar Ustida Mashq", AppState.activeQuestions.length * 60);
}

function initQuizSession(title, timeSeconds) {
  AppState.currentIndex = 0;
  AppState.userAnswers = {};
  AppState.timeRemaining = timeSeconds;
  AppState.timeSpent = 0;

  document.getElementById('quiz-mode-title').textContent = title;
  
  // Taymerni ishga tushirish
  clearInterval(AppState.timerInterval);
  updateTimerDisplay();
  AppState.timerInterval = setInterval(() => {
    AppState.timeRemaining--;
    AppState.timeSpent++;
    updateTimerDisplay();

    if (AppState.timeRemaining <= 0) {
      clearInterval(AppState.timerInterval);
      alert("Vaqt tugadi! Imtihon yakunlanmoqda.");
      finishQuiz();
    }
  }, 1000);

  renderQuestionNavigator();
  displayCurrentQuestion();
  switchView('quiz');
}

function updateTimerDisplay() {
  const mins = Math.floor(AppState.timeRemaining / 60);
  const secs = AppState.timeRemaining % 60;
  const formatted = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  
  const timerText = document.getElementById('quiz-timer-text');
  const timerBox = document.getElementById('quiz-timer-box');
  timerText.textContent = formatted;

  if (AppState.timeRemaining <= 180) { // 3 daqiqa qolganda ogohlantirish
    timerBox.classList.add('warning');
  } else {
    timerBox.classList.remove('warning');
  }
}

// --- SAVOLLAR NAVIGATORI (1..20) ---
function renderQuestionNavigator() {
  const container = document.getElementById('quiz-nav-grid');
  container.innerHTML = '';

  AppState.activeQuestions.forEach((q, idx) => {
    const btn = document.createElement('button');
    btn.className = 'nav-q-btn';
    btn.id = `nav-q-${idx}`;
    btn.textContent = idx + 1;
    btn.addEventListener('click', () => {
      SFX.click();
      AppState.currentIndex = idx;
      displayCurrentQuestion();
    });
    container.appendChild(btn);
  });
}

function updateNavigatorStatus() {
  AppState.activeQuestions.forEach((q, idx) => {
    const btn = document.getElementById(`nav-q-${idx}`);
    if (!btn) return;

    btn.className = 'nav-q-btn';
    if (idx === AppState.currentIndex) {
      btn.classList.add('current');
    }

    const answered = AppState.userAnswers[idx];
    if (answered !== undefined) {
      if (AppState.quizMode === 'practice' || AppState.quizMode === 'mistakes') {
        if (answered === q.correct) {
          btn.classList.add('correct');
        } else {
          btn.classList.add('wrong');
        }
      } else {
        // Imtihon rejimida faqat belgilanganini ko'rsatish
        btn.style.background = 'rgba(59, 130, 246, 0.4)';
        btn.style.borderColor = '#3b82f6';
      }
    }
  });
}

// --- JORIY SAVOLNI CHIQARISH ---
function displayCurrentQuestion() {
  const q = AppState.activeQuestions[AppState.currentIndex];
  if (!q) return;

  const total = AppState.activeQuestions.length;
  document.getElementById('q-counter').textContent = `Savol ${AppState.currentIndex + 1} / ${total}`;
  document.getElementById('q-ticket-badge').textContent = `${q.ticket}-Bilet`;

  // Progress Bar
  const progressPercent = ((AppState.currentIndex + 1) / total) * 100;
  document.getElementById('quiz-progress-fill').style.width = `${progressPercent}%`;

  // Vizual Rasm / SVG
  const visualBox = document.getElementById('question-visual-box');
  if (q.svg) {
    visualBox.innerHTML = q.svg;
    visualBox.classList.remove('hidden');
  } else {
    visualBox.classList.add('hidden');
  }

  // Savol matni
  document.getElementById('question-text').textContent = q.question;

  // Variantlar
  const optionsList = document.getElementById('options-list');
  optionsList.innerHTML = '';
  const optionLetters = ['A', 'B', 'C', 'D'];

  const answeredIndex = AppState.userAnswers[AppState.currentIndex];
  const isAnswered = answeredIndex !== undefined;

  q.options.forEach((optText, optIdx) => {
    const btn = document.createElement('button');
    btn.className = 'option-button';
    
    // Agar oldin javob berilgan bo'lsa
    if (isAnswered) {
      btn.classList.add('disabled');
      if (AppState.quizMode === 'practice' || AppState.quizMode === 'mistakes') {
        if (optIdx === q.correct) {
          btn.classList.add('correct');
        } else if (optIdx === answeredIndex) {
          btn.classList.add('incorrect');
        }
      } else {
        // Imtihon rejimida tanlanganini ko'rsatish
        if (optIdx === answeredIndex) {
          btn.style.borderColor = 'var(--accent)';
          btn.style.background = 'rgba(59, 130, 246, 0.15)';
        }
      }
    } else {
      btn.addEventListener('click', () => selectOption(optIdx));
    }

    btn.innerHTML = `
      <span class="option-badge">${optionLetters[optIdx] || optIdx + 1}</span>
      <span class="option-label">${optText}</span>
    `;
    optionsList.appendChild(btn);
  });

  // Izoh (Explanation) bloki
  const expBox = document.getElementById('explanation-box');
  if (isAnswered && (AppState.quizMode === 'practice' || AppState.quizMode === 'mistakes')) {
    expBox.classList.remove('hidden');
    document.getElementById('explanation-text').textContent = q.explanation;
  } else {
    expBox.classList.add('hidden');
  }

  // Pastki tugmalar holati
  document.getElementById('btn-prev-question').disabled = AppState.currentIndex === 0;
  
  const isLast = AppState.currentIndex === total - 1;
  const btnNext = document.getElementById('btn-next-question');
  const btnFinish = document.getElementById('btn-finish-quiz');

  if (isLast) {
    btnNext.classList.add('hidden');
    btnFinish.classList.remove('hidden');
  } else {
    btnNext.classList.remove('hidden');
    btnFinish.classList.add('hidden');
  }

  updateNavigatorStatus();
}

// --- JAVOBNI TANLASH ---
function selectOption(selectedIdx) {
  const q = AppState.activeQuestions[AppState.currentIndex];
  AppState.userAnswers[AppState.currentIndex] = selectedIdx;

  const isCorrect = selectedIdx === q.correct;

  if (isCorrect) {
    SFX.correct();
    // Agar xatolar ro'yxatida bo'lsa, to'g'ri topsa olib tashlash
    if (AppState.stats.mistakesIds) {
      AppState.stats.mistakesIds = AppState.stats.mistakesIds.filter(id => id !== q.id);
      saveStats();
    }
  } else {
    SFX.wrong();
    // Xatolar ro'yxatiga qo'shish
    if (!AppState.stats.mistakesIds) AppState.stats.mistakesIds = [];
    if (!AppState.stats.mistakesIds.includes(q.id)) {
      AppState.stats.mistakesIds.push(q.id);
      saveStats();
    }
  }

  displayCurrentQuestion();

  // Imtihon rejimida 3 tadan ko'p xato bo'lsa ogohlantirish
  if (AppState.quizMode === 'exam') {
    let wrongCount = 0;
    Object.keys(AppState.userAnswers).forEach(idx => {
      const qItem = AppState.activeQuestions[idx];
      if (AppState.userAnswers[idx] !== qItem.correct) {
        wrongCount++;
      }
    });

    if (wrongCount >= 3) {
      // 3 ta xato bo'lganda
      setTimeout(() => {
        if (confirm("Diqqat! Siz 3 ta xatoga yo'l qo'ydingiz. Davlat imtihonida bunday holatda imtihon to'xtatiladi. Natijani ko'rishni xohlaysizmi?")) {
          finishQuiz();
        }
      }, 500);
    }
  }
}

// --- IMTIHONNI YAKUNLASH VA NATIJA ---
function finishQuiz() {
  clearInterval(AppState.timerInterval);
  SFX.finish();

  let correctCount = 0;
  let wrongCount = 0;
  const total = AppState.activeQuestions.length;

  AppState.activeQuestions.forEach((q, idx) => {
    const userChoice = AppState.userAnswers[idx];
    if (userChoice === q.correct) {
      correctCount++;
    } else {
      wrongCount++;
    }
  });

  const percentage = Math.round((correctCount / total) * 100);
  const passed = correctCount >= 18 || (total < 20 && percentage >= 85);

  // Statistikani yangilash
  AppState.stats.totalTaken++;
  if (passed) AppState.stats.passedCount++;
  AppState.stats.totalScoreSum += percentage;
  saveStats();

  // Natija UI ma'lumotlarini to'ldirish
  const badgeEl = document.getElementById('result-status-badge');
  const titleEl = document.getElementById('result-title');
  const subtitleEl = document.getElementById('result-subtitle');

  if (passed) {
    badgeEl.textContent = '🎉';
    badgeEl.classList.remove('failed');
    titleEl.textContent = "TABRIKLAYMIZ! IMTIHONDAN O'TDINGIZ";
    subtitleEl.textContent = "Siz O'zbekiston YHQ talablariga to'liq javob berdingiz va haydovchilik imtihoniga tayyorsiz!";
  } else {
    badgeEl.textContent = '❌';
    badgeEl.classList.add('failed');
    titleEl.textContent = "AFSUSKI, IMTIHONDAN O'TMADINGIZ";
    subtitleEl.textContent = "Davlat imtihonidan o'tish uchun kamida 18 ta to'g'ri javob talab etiladi. Xatolaringiz ustida ishlang!";
  }

  document.getElementById('result-score-percent').textContent = `${percentage}%`;
  document.getElementById('result-score-fraction').textContent = `${correctCount} / ${total}`;
  document.getElementById('result-correct-count').textContent = `${correctCount} ta`;
  document.getElementById('result-wrong-count').textContent = `${wrongCount} ta`;

  const minsSpent = Math.floor(AppState.timeSpent / 60);
  const secsSpent = AppState.timeSpent % 60;
  document.getElementById('result-time-taken').textContent = 
    `${minsSpent.toString().padStart(2, '0')}:${secsSpent.toString().padStart(2, '0')}`;

  switchView('result');
}

// --- YO'L BELGILARI KATALOGI ---
function renderRoadSigns(category = 'all', searchQuery = '') {
  const container = document.getElementById('signs-cards-container');
  container.innerHTML = '';

  let filtered = ROAD_SIGNS_CATALOG;

  if (category !== 'all') {
    filtered = filtered.filter(s => s.category === category);
  }

  if (searchQuery.trim() !== '') {
    const q = searchQuery.toLowerCase().trim();
    filtered = filtered.filter(s => 
      s.name.toLowerCase().includes(q) || 
      s.code.toLowerCase().includes(q) || 
      s.desc.toLowerCase().includes(q)
    );
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-icon">🔍</div>
        <h3>Belgilar topilmadi</h3>
        <p>Boshqa so'z bilan qidirib ko'ring.</p>
      </div>
    `;
    return;
  }

  filtered.forEach(sign => {
    const card = document.createElement('div');
    card.className = 'sign-card';
    card.innerHTML = `
      <div class="sign-card-svg">${sign.svg}</div>
      <span class="sign-card-code">${sign.code}</span>
      <h4 class="sign-card-name">${sign.name}</h4>
      <p class="sign-card-desc">${sign.desc}</p>
    `;
    container.appendChild(card);
  });
}

// --- XATOLAR BANKI KO'RINISHI ---
function renderMistakesView() {
  const container = document.getElementById('mistakes-container');
  container.innerHTML = '';

  const mistakesIds = AppState.stats.mistakesIds || [];

  if (mistakesIds.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎉</div>
        <h3>Xatolar mavjud emas!</h3>
        <p>Sizda hech qanday to'plangan xatolar yo'q. Imtihon topshirib o'z bilimingizni sinab ko'ring!</p>
        <button class="btn btn-primary" style="margin-top: 1rem;" onclick="startExamMode()">
          ⏱ Imtihonni Boshlash
        </button>
      </div>
    `;
    return;
  }

  const mistakesQuestions = QUESTIONS_DATABASE.filter(q => mistakesIds.includes(q.id));

  // Tepada qayta ishlash tugmasi
  const actionWrap = document.createElement('div');
  actionWrap.style.marginBottom = '1.5rem';
  actionWrap.innerHTML = `
    <button class="btn btn-primary" onclick="startMistakesPractice()">
      🔄 Faqat Xatolarni Qayta Ishlash (${mistakesQuestions.length} ta)
    </button>
  `;
  container.appendChild(actionWrap);

  mistakesQuestions.forEach((q, idx) => {
    const card = document.createElement('div');
    card.className = 'mistake-item-card';
    card.innerHTML = `
      <div class="question-header">
        <span class="q-badge">${idx + 1}-Xato</span>
        <span class="q-ticket-badge">${q.ticket}-Bilet</span>
      </div>
      ${q.svg ? `<div style="display:flex; justify-content:center; margin-bottom:1rem;">${q.svg}</div>` : ''}
      <h4>${q.question}</h4>
      <div style="margin-top: 0.5rem; color: var(--primary); font-weight: 600;">
        To'g'ri javob: ${q.options[q.correct]}
      </div>
      <div class="explanation-box" style="margin-top: 0.5rem;">
        <strong>Qoida izohi:</strong> ${q.explanation}
      </div>
    `;
    container.appendChild(card);
  });
}

// --- HODISALARNI BIRIKTIRISH (EVENT LISTENERS) ---
document.addEventListener('DOMContentLoaded', () => {
  loadSavedData();

  // Logo bosilganda bosh sahifaga o'tish
  document.getElementById('btn-logo').addEventListener('click', () => switchView('home'));

  // Navigatsiya tugmalari
  document.querySelectorAll('[data-view]').forEach(elem => {
    elem.addEventListener('click', (e) => {
      SFX.click();
      const view = elem.getAttribute('data-view');
      if (view === 'exam-direct') {
        startExamMode();
      } else {
        switchView(view);
      }
    });
  });

  // Mavzu va ovoz almashtirish
  document.getElementById('btn-theme').addEventListener('click', toggleTheme);
  document.getElementById('btn-sound').addEventListener('click', toggleSound);

  // Hero tugmalari
  document.getElementById('btn-start-exam-hero').addEventListener('click', startExamMode);
  document.getElementById('btn-view-tickets-hero').addEventListener('click', () => switchView('tickets'));

  // Test boshqaruvi
  document.getElementById('btn-prev-question').addEventListener('click', () => {
    if (AppState.currentIndex > 0) {
      SFX.click();
      AppState.currentIndex--;
      displayCurrentQuestion();
    }
  });

  document.getElementById('btn-next-question').addEventListener('click', () => {
    if (AppState.currentIndex < AppState.activeQuestions.length - 1) {
      SFX.click();
      AppState.currentIndex++;
      displayCurrentQuestion();
    }
  });

  document.getElementById('btn-finish-quiz').addEventListener('click', () => {
    if (confirm("Imtihonni rostdan ham yakunlamoqchimisiz?")) {
      finishQuiz();
    }
  });

  document.getElementById('btn-quit-quiz').addEventListener('click', () => {
    if (confirm("Testdan chiqishni xohlaysizmi? Natijalar saqlanmaydi.")) {
      clearInterval(AppState.timerInterval);
      switchView('home');
    }
  });

  // Natija ekrani tugmalari
  document.getElementById('btn-restart-quiz').addEventListener('click', () => {
    if (AppState.quizMode === 'exam') {
      startExamMode();
    } else {
      startPracticeTicket(1);
    }
  });

  document.getElementById('btn-view-mistakes-from-result').addEventListener('click', () => {
    switchView('mistakes');
  });

  document.getElementById('btn-return-home').addEventListener('click', () => {
    switchView('home');
  });

  // Xatolarni tozalash
  document.getElementById('btn-clear-mistakes').addEventListener('click', () => {
    if (confirm("Barcha saqlangan xatolarni tozalashni tasdiqlaysizmi?")) {
      AppState.stats.mistakesIds = [];
      saveStats();
      renderMistakesView();
    }
  });

  // Yo'l belgilari qidiruv va filtrlari
  const searchInput = document.getElementById('signs-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const activeChip = document.querySelector('.category-chip.active');
      const cat = activeChip ? activeChip.getAttribute('data-cat') : 'all';
      renderRoadSigns(cat, e.target.value);
    });
  }

  document.querySelectorAll('.category-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      SFX.click();
      document.querySelectorAll('.category-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const cat = chip.getAttribute('data-cat');
      const query = searchInput ? searchInput.value : '';
      renderRoadSigns(cat, query);
    });
  });

  // Boshlang'ich sahifani o'rnatish
  switchView('home');
});
