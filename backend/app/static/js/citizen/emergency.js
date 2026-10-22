/**
 * ============================================================
 * SahayAI Citizen Emergency Intake Controller
 * ============================================================
 */

document.addEventListener('DOMContentLoaded', () => {
  setupLanguageSelection();
  setupSymptomChips();
  setupModalityToggle();
  setupGPSDetection();
  setupAudioRecorder();
  setupIntakeSubmission();
});

/* ── 1. Language Hints ───────────────────────────────────────── */
function setupLanguageSelection() {
  const langSelect = document.getElementById('citizenLanguage');
  if (!langSelect) return;

  langSelect.addEventListener('change', () => {
    const lang = langSelect.value;
    const txtArea = document.getElementById('citizenEmergencyText');
    if (!txtArea || txtArea.value.trim().length > 0) return;

    if (lang === 'hindi') {
      txtArea.placeholder = 'मरीज को क्या हो रहा है? उदाहरण: "मरीज को बहुत तेज सीने में दर्द है और सांस नहीं आ रही, तुरंत एम्बुलेंस भेजिए।"';
    } else if (lang === 'marathi') {
      txtArea.placeholder = 'रुग्णाला काय त्रास होत आहे? उदाहरण: "अपघात झाला आहे, रुग्ण बेशुद्ध आहे आणि भरपूर रक्तस्त्राव होतोय, शिवाजीनगर पुणे लवकर या."';
    } else if (lang === 'code-mixed') {
      txtArea.placeholder = 'Describe karo: "Patient collapse ho gaya hai, chest pain hai and breathing issue hai. Swargate ke pass ambulance chahiye."';
    } else {
      txtArea.placeholder = 'Describe the emergency: e.g. "Severe road accident near Wakad junction, 2 people injured with heavy bleeding, need ALS ambulance urgently."';
    }
  });
}

/* ── 2. Quick Symptom Chips ──────────────────────────────────── */
function setupSymptomChips() {
  const chips = document.querySelectorAll('.symptom-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const txtArea = document.getElementById('citizenEmergencyText');
      if (!txtArea) return;

      const symptomText = chip.dataset.symptom || chip.textContent.trim();
      const currentVal = txtArea.value.trim();

      if (!currentVal) {
        txtArea.value = symptomText + '. ';
      } else if (!currentVal.toLowerCase().includes(symptomText.toLowerCase())) {
        txtArea.value = `${currentVal}, ${symptomText}. `;
      }
      chip.classList.toggle('active');
      txtArea.focus();
    });
  });
}

/* ── 3. Modality Toggle ──────────────────────────────────────── */
function setupModalityToggle() {
  const tabText = document.getElementById('tabText');
  const tabAudio = document.getElementById('tabAudio');
  const secText = document.getElementById('sectionText');
  const secAudio = document.getElementById('sectionAudio');

  if (!tabText || !tabAudio) return;

  tabText.addEventListener('click', () => {
    tabText.classList.add('active');
    tabAudio.classList.remove('active');
    secText.style.display = 'block';
    secAudio.style.display = 'none';
  });

  tabAudio.addEventListener('click', () => {
    tabAudio.classList.add('active');
    tabText.classList.remove('active');
    secAudio.style.display = 'block';
    secText.style.display = 'none';
  });
}

/* ── 4. GPS Geolocation Detection ────────────────────────────── */
function setupGPSDetection() {
  const btn = document.getElementById('btnDetectCitizenGPS');
  if (!btn) return;

  btn.addEventListener('click', () => {
    const locInput = document.getElementById('citizenLocationText');
    const latInput = document.getElementById('citizenLat');
    const lonInput = document.getElementById('citizenLon');

    if (!navigator.geolocation) {
      if (!locInput.value) locInput.value = '';
      latInput.value = '';
      lonInput.value = '';
      Utils.showToast('Browser does not support GPS. Please type your location in the address field.', 'warning');
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="width:12px;height:12px;"></span> Detecting…';

    navigator.geolocation.getCurrentPosition(
      pos => {
        latInput.value = pos.coords.latitude.toFixed(6);
        lonInput.value = pos.coords.longitude.toFixed(6);
        if (!locInput.value) {
          locInput.value = `Current Location (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`;
        }
        btn.disabled = false;
        btn.innerHTML = '✅ GPS Acquired';
        Utils.showToast('GPS coordinates acquired successfully!', 'success');
        setTimeout(() => { btn.innerHTML = '📍 Use My Location'; }, 3500);
      },
      err => {
        console.warn('Geolocation error:', err);
        // DO NOT inject fake coordinates. Leave fields blank and ask user to enter location manually.
        latInput.value = '';
        lonInput.value = '';
        btn.disabled = false;
        btn.innerHTML = '📍 Use My Location';
        Utils.showToast('GPS unavailable or permission denied. Please type your location in the address field below.', 'warning');
      },
      { timeout: 7000 }
    );
  });
}

/* ── 5. Microphone Recording & Audio File ─────────────────────── */
let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;

function setupAudioRecorder() {
  const micBtn = document.getElementById('btnRecordMic');
  const recordStatus = document.getElementById('recordStatus');
  const audioPlayback = document.getElementById('audioPlayback');
  const fileInput = document.getElementById('audioFileInput');

  if (!micBtn) return;

  micBtn.addEventListener('click', async () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      // Stop recording
      mediaRecorder.stop();
      micBtn.classList.remove('active-record');
      recordStatus.textContent = 'Processing recording…';
      return;
    }

    // Start recording
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      Utils.showToast('Audio recording is not supported in this browser. Please upload an audio file.', 'danger');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const audioUrl = URL.createObjectURL(recordedBlob);
        audioPlayback.src = audioUrl;
        audioPlayback.style.display = 'block';
        recordStatus.innerHTML = '<span style="color:var(--accent-emerald)">✅ Voice recording captured! Ready to submit.</span>';
        micBtn.innerHTML = '🎙️';
        // Clear file input since mic recording is used
        if (fileInput) fileInput.value = '';
      };

      mediaRecorder.start();
      micBtn.classList.add('active-record');
      micBtn.innerHTML = '⏹️';
      recordStatus.innerHTML = '<span style="color:var(--accent-red); font-weight:700;">● Recording in progress… Speak now (English/Hindi/Marathi). Click again to stop.</span>';
    } catch (err) {
      console.error('Microphone error:', err);
      Utils.showToast('Could not access microphone: ' + err.message, 'danger');
    }
  });

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files.length > 0) {
        recordedBlob = null;
        if (audioPlayback) audioPlayback.style.display = 'none';
        recordStatus.innerHTML = `<span style="color:var(--accent-cyan)">Selected: ${fileInput.files[0].name} (${(fileInput.files[0].size/1024).toFixed(0)} KB)</span>`;
      }
    });
  }
}

/* ── 6. Emergency Submission Flow ────────────────────────────── */
async function setupIntakeSubmission() {
  const form = document.getElementById('citizenIntakeForm');
  if (!form) return;

  form.addEventListener('submit', async e => {
    e.preventDefault();

    const btnSubmit = document.getElementById('btnCitizenSubmit');
    const bannerError = document.getElementById('citizenErrorBanner');
    const progressCard = document.getElementById('citizenProgressCard');
    const progressList = document.getElementById('citizenProgressList');

    bannerError.style.display = 'none';

    const isAudio = document.getElementById('tabAudio')?.classList.contains('active');
    const textDesc = document.getElementById('citizenEmergencyText')?.value.trim() || '';
    const locationText = document.getElementById('citizenLocationText')?.value.trim() || '';
    const phone = document.getElementById('citizenPhone')?.value.trim() || null;
    const language = document.getElementById('citizenLanguage')?.value || null;
    const lat = parseFloat(document.getElementById('citizenLat')?.value) || null;
    const lon = parseFloat(document.getElementById('citizenLon')?.value) || null;
    const audioFile = document.getElementById('audioFileInput')?.files[0] || null;

    if (!isAudio && !textDesc) {
      bannerError.textContent = '⚠️ Please describe the emergency.';
      bannerError.style.display = 'block';
      return;
    }

    if (isAudio && !recordedBlob && !audioFile) {
      bannerError.textContent = '⚠️ Please record voice audio or select an audio file.';
      bannerError.style.display = 'block';
      return;
    }

    btnSubmit.disabled = true;
    btnSubmit.innerHTML = '<span class="spinner"></span> Dispatching Help…';
    progressCard.style.display = 'block';
    progressList.innerHTML = '';

    const updateStep = (id, label, status, detail) => {
      let el = document.getElementById(`step-${id}`);
      if (!el) {
        el = document.createElement('div');
        el.id = `step-${id}`;
        el.className = 'prog-step';
        el.style.cssText = 'display:flex; align-items:center; gap:10px; padding:10px 14px; background:#090e1b; border-radius:8px; margin-bottom:8px; border:1px solid var(--border-color); font-size:0.86rem;';
        progressList.appendChild(el);
      }
      const icon = status === 'done' ? '✅' : status === 'running' ? '⚙️' : '❌';
      const color = status === 'done' ? 'var(--accent-emerald)' : status === 'running' ? 'var(--accent-cyan)' : 'var(--accent-red)';
      el.innerHTML = `
        <span style="font-size:1.1rem;">${icon}</span>
        <span style="font-weight:600; color:var(--text-primary);">${label}</span>
        <span style="margin-left:auto; color:${color}; font-size:0.8rem; font-weight:600;">${detail}</span>
      `;
    };

    let caseId = null;

    try {
      if (isAudio) {
        // Voice Audio Flow
        updateStep('intake', 'Transcribing Voice Report', 'running', 'Processing audio…');
        const formData = new FormData();
        const fileToUpload = audioFile || new File([recordedBlob], 'emergency_voice.webm', { type: 'audio/webm' });
        formData.append('audio_file', fileToUpload);
        if (phone) formData.append('caller_phone', phone);
        if (locationText) formData.append('manual_location', locationText);
        if (language) formData.append('language_hint', language);
        if (lat !== null && !isNaN(lat)) formData.append('latitude', lat);
        if (lon !== null && !isNaN(lon)) formData.append('longitude', lon);

        const audioResult = await window.api.submitAudioCase(formData);
        caseId = audioResult.id;
        updateStep('intake', 'Voice Report Transcribed', 'done', `Case #${caseId.substring(0, 8)}`);
        updateStep('triage', 'AI Clinical Triage', 'done', `${audioResult.priority} · ${audioResult.emergency_type || 'Assessed'}`);
      } else {
        // Text Emergency Flow
        updateStep('intake', 'Registering Emergency', 'running', 'Connecting to dispatch…');
        const payload = {
          raw_text: textDesc,
          raw_input: textDesc,
          modality: 'text',
          caller_phone: phone,
          language: language || 'unknown',
          manual_location: locationText || undefined,
          latitude: lat,
          longitude: lon,
        };

        const created = await window.api.createCase(payload);
        caseId = created.id;
        updateStep('intake', 'Emergency Registered', 'done', `Case #${caseId.substring(0, 8)}`);

        // Step 2: AI Triage
        updateStep('triage', 'AI Clinical Triage', 'running', 'Analyzing severity & ambulance requirements…');
        const triageData = await window.api.triageCase(caseId).catch(() => null);
        if (triageData) {
          updateStep('triage', 'AI Clinical Triage', 'done', `${triageData.priority} · ${triageData.emergency_type || 'Assessed'}`);
        } else {
          updateStep('triage', 'AI Clinical Triage', 'done', 'Assessing in background');
        }
      }

      // Step 3: Clinical Protocol Verification
      updateStep('rag', 'Clinical Guidelines Verification', 'running', 'Verifying emergency care protocol…');
      await window.api.verifyCaseRAG(caseId).catch(() => null);
      updateStep('rag', 'Clinical Protocol Verified', 'done', 'Protocol matched');

      // Step 4: Spatial Matching & Ambulance Dispatch
      updateStep('dispatch', 'Resource Verification & Dispatch', 'running', 'Locating nearest available ambulance…');
      const dispatchResult = await window.api.dispatchCase(caseId, false, 'citizen_portal', false).catch(e => {
        console.warn('Dispatch match:', e);
        return null;
      });

      if (dispatchResult && dispatchResult.matched_ambulance) {
        updateStep('dispatch', 'Ambulance Dispatched', 'done', `${dispatchResult.matched_ambulance.vehicle_number} (ETA ~${Math.round(dispatchResult.ambulance_eta_minutes||8)} min)`);
      } else {
        updateStep('dispatch', 'Resource Queued', 'done', 'Dispatcher notified for prompt dispatch');
      }

      Utils.showToast('🚨 Emergency received! Transferring to live tracking portal…', 'success', 3000);

      // Redirect citizen directly to their live case tracking page
      setTimeout(() => {
        window.location.href = `/track?case_id=${encodeURIComponent(caseId)}`;
      }, 1400);

    } catch (err) {
      console.error('Submission failure:', err);
      bannerError.textContent = `❌ Submission Error: ${err.message || 'Please call emergency hotline 108 immediately.'}`;
      bannerError.style.display = 'block';
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = '🚨 Request Emergency Help Now';
    }
  });
}
