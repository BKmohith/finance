/**
 * Sahayak Voice Perception & Counter Ingestion Controller
 * Handles vernacular speech session, Jev reflex latency ticker, and ACID contract presentation.
 */

class VoiceRecorder {
  constructor(visualizer) {
    this.visualizer = visualizer;
    this.micButton = document.getElementById('mainMicBtn');
    this.micLabel = document.getElementById('micLabelAction');
    this.countdownBadge = document.getElementById('countdownBadge');
    this.modal = document.getElementById('diagnosticModal');
    this.closeModalBtn = document.getElementById('modalCloseBtn');

    this.isRecording = false;
    this.timer = null;
    this.duration = 5; // 5-second quick retail speech window
    this.remainingTime = 5;
    this.mediaStream = null;
    this.selectedProfile = 'kannada_khata';

    this.initEvents();
  }

  initEvents() {
    if (this.micButton) {
      this.micButton.addEventListener('click', () => this.toggleRecording());
    }

    if (this.closeModalBtn) {
      this.closeModalBtn.addEventListener('click', () => this.closeModal());
    }

    if (this.modal) {
      this.modal.addEventListener('click', (e) => {
        if (e.target === this.modal) this.closeModal();
      });
    }

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal && this.modal.classList.contains('is-open')) {
        this.closeModal();
      }
    });
  }

  async toggleRecording() {
    if (this.isRecording) {
      this.finishRecording();
      return;
    }
    this.startRecording();
  }

  async startRecording() {
    this.isRecording = true;
    this.remainingTime = this.duration;
    
    if (window.FinancialEngine) {
      window.FinancialEngine.playChime('start');
    }

    this.micButton.classList.add('is-recording');
    this.updateRecordingUI(this.remainingTime);

    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.visualizer.attachAudioStream(this.mediaStream);
      } else {
        this.visualizer.startSimulatedVoice();
      }
    } catch (err) {
      this.visualizer.startSimulatedVoice();
    }

    this.timer = setInterval(() => {
      this.remainingTime--;
      this.updateRecordingUI(this.remainingTime);

      if (this.remainingTime <= 0) {
        this.finishRecording();
      }
    }, 1000);
  }

  updateRecordingUI(secondsLeft) {
    const formatted = `00:0${secondsLeft}`;
    this.micLabel.textContent = `Listening... Speak in Kannada / Hindi / Hinglish (${formatted})`;
    this.micLabel.style.color = 'var(--color-accent-coral)';
    if (this.countdownBadge) {
      this.countdownBadge.textContent = `${secondsLeft}s`;
      this.countdownBadge.style.display = 'block';
    }
  }

  finishRecording() {
    clearInterval(this.timer);
    this.isRecording = false;

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    this.visualizer.stopListening();
    this.micButton.classList.remove('is-recording');

    // System 1 Reflex transition
    this.micLabel.textContent = "System 1 Jev Reflex: Classifying Intent (<18ms)...";
    this.micLabel.style.color = "var(--color-accent-purple)";
    if (this.countdownBadge) {
      this.countdownBadge.style.display = 'none';
    }

    if (window.FinancialEngine) {
      window.FinancialEngine.playChime('complete');
    }

    setTimeout(() => {
      this.showContractResults();
      this.resetRecordingUI();
    }, 550);
  }

  resetRecordingUI() {
    this.micLabel.textContent = "Tap to speak (Kannada / Hindi / Hinglish)";
    this.micLabel.style.color = "var(--color-text-title)";
  }

  showContractResults(profileKey = null) {
    const key = profileKey || this.selectedProfile;
    const profile = window.FinancialEngine.getProfile(key);

    // Update modal elements
    document.getElementById('modalIntent').textContent = profile.intent;
    document.getElementById('modalStatusText').textContent = profile.statusText;
    document.getElementById('modalStatusBadge').style.color = profile.statusColor;
    document.getElementById('modalStatusBadge').style.background = `${profile.statusColor}18`;

    document.getElementById('modalRawSpeech').textContent = `"${profile.rawAudioText}"`;
    document.getElementById('modalNormalizedText').textContent = `Normalized: ${profile.normalizedEnglish} (${profile.language})`;

    document.getElementById('modalLatencyValue').textContent = `${profile.latency} (${profile.cost})`;
    document.getElementById('modalCustomerValue').textContent = profile.customer;
    document.getElementById('modalMonetaryValue').textContent = profile.monetaryValue;

    // ACID double-entry entries
    const acidContainer = document.getElementById('modalAcidEntries');
    if (acidContainer) {
      acidContainer.innerHTML = profile.acidEntries.map(e => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed #E0D8CE; font-family:var(--font-mono); font-size:0.8rem;">
          <span style="font-weight:600; color:${e.type === 'DEBIT' ? '#1B8354' : '#C9972E'};">${e.type}</span>
          <span>${e.account}</span>
          <span style="font-weight:600;">${e.amount}</span>
        </div>
      `).join('');
    }

    // JSON Contract Payload Preview
    const codeElem = document.getElementById('modalJsonPayload');
    if (codeElem) {
      codeElem.textContent = JSON.stringify(profile.contractPayload, null, 2);
    }

    // WhatsApp Message
    document.getElementById('modalWhatsappPreview').textContent = profile.whatsappMessage;
    document.getElementById('modalTimestamp').textContent = `Processed in ${profile.latency} • SHA-256 Idempotency Lock OK • Session RLS Active`;

    this.modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  closeModal() {
    this.modal.classList.remove('is-open');
    document.body.style.overflow = '';
  }
}

window.VoiceRecorder = VoiceRecorder;
