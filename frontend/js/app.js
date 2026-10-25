/**
 * Sahayak Financial Copilot Application Bootstrap
 * Connects visualizer, recorder, Margin Guard interactive simulator, and navigation.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Visualizer
  const visualizer = new AudioVisualizer('waveformCanvas');

  // 2. Initialize Voice Recorder
  const recorder = new VoiceRecorder(visualizer);

  // 3. Header scroll effects
  const siteHeader = document.querySelector('.site-header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 30) {
      siteHeader.classList.add('scrolled');
    } else {
      siteHeader.classList.remove('scrolled');
    }
  });

  // 4. Sample Preset Buttons
  const sampleBtns = document.querySelectorAll('.sample-pill-btn');
  sampleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      sampleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const profileKey = btn.dataset.profile || 'kannada_khata';
      recorder.selectedProfile = profileKey;
    });
  });

  // 5. Interactive Bottom Audio Player Bar
  const playerPlayBtn = document.getElementById('playerPlayBtn');
  const playerProgressFill = document.getElementById('playerProgressFill');
  const playerTimeBadge = document.getElementById('playerTimeBadge');
  const playerTrackWrap = document.querySelector('.player-track-wrap');

  let isPlaying = false;
  let playerInterval = null;
  let playbackSeconds = 0;
  const totalDuration = 5;

  function formatTime(secs) {
    const s = Math.floor(secs);
    return `0:0${s}`;
  }

  function startPlayback() {
    isPlaying = true;
    playerPlayBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor">
        <rect x="6" y="4" width="4" height="16" rx="1"></rect>
        <rect x="14" y="4" width="4" height="16" rx="1"></rect>
      </svg>
    `;
    visualizer.startSimulatedVoice();

    playerInterval = setInterval(() => {
      playbackSeconds += 0.1;
      const pct = (playbackSeconds / totalDuration) * 100;
      playerProgressFill.style.width = `${pct}%`;
      playerTimeBadge.textContent = `${formatTime(playbackSeconds)} / 0:05`;

      if (playbackSeconds >= totalDuration) {
        stopPlayback();
      }
    }, 100);
  }

  function stopPlayback() {
    isPlaying = false;
    clearInterval(playerInterval);
    playerPlayBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor">
        <polygon points="5,3 19,12 5,21"></polygon>
      </svg>
    `;
    visualizer.stopListening();
    playbackSeconds = 0;
    playerProgressFill.style.width = '0%';
    playerTimeBadge.textContent = '0:00 / 0:05';
  }

  if (playerPlayBtn) {
    playerPlayBtn.addEventListener('click', () => {
      if (isPlaying) {
        stopPlayback();
      } else {
        startPlayback();
      }
    });
  }

  if (playerTrackWrap) {
    playerTrackWrap.addEventListener('click', (e) => {
      const rect = playerTrackWrap.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, clickX / rect.width));
      playbackSeconds = ratio * totalDuration;
      playerProgressFill.style.width = `${ratio * 100}%`;
      playerTimeBadge.textContent = `${formatTime(playbackSeconds)} / 0:05`;
      if (!isPlaying) {
        startPlayback();
      }
    });
  }

  // 6. Interactive Margin-Guard Simulator (From phase.md formula)
  const oldPriceInput = document.getElementById('simOldPrice');
  const newPriceInput = document.getElementById('simNewPrice');
  const targetMarginInput = document.getElementById('simTargetMargin');
  
  const valOldPrice = document.getElementById('valOldPrice');
  const valNewPrice = document.getElementById('valNewPrice');
  const valTargetMargin = document.getElementById('valTargetMargin');

  const outDeltaPct = document.getElementById('outDeltaPct');
  const outNewMrp = document.getElementById('outNewMrp');
  const whatsappPreview = document.getElementById('simWhatsappAlert');

  function updateMarginSimulation() {
    if (!oldPriceInput || !newPriceInput || !targetMarginInput) return;

    const oldRate = parseFloat(oldPriceInput.value);
    const newRate = parseFloat(newPriceInput.value);
    const marginPct = parseFloat(targetMarginInput.value);

    valOldPrice.textContent = `₹${oldRate.toFixed(2)}`;
    valNewPrice.textContent = `₹${newRate.toFixed(2)}`;
    valTargetMargin.textContent = `${marginPct}%`;

    const deltaAmount = newRate - oldRate;
    const deltaPct = ((deltaAmount) / oldRate) * 100;
    const recommendedMrp = Math.round(newRate * (1 + (marginPct / 100)));

    outDeltaPct.textContent = `${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(1)}%`;
    outDeltaPct.style.color = deltaPct > 3 ? '#E3536C' : '#1B8354';
    outNewMrp.textContent = `₹${recommendedMrp}`;

    if (deltaPct > 3) {
      whatsappPreview.innerHTML = `
        <strong>⚠️ Margin-Guard WhatsApp Alert:</strong><br>
        Fortune Oil wholesale cost rose by <strong>₹${deltaAmount.toFixed(0)} (₹${oldRate} ➔ ₹${newRate})</strong>. 
        Raise shelf price to <strong>₹${recommendedMrp}</strong> to protect your <strong>${marginPct}% margin</strong>.
      `;
    } else {
      whatsappPreview.innerHTML = `
        <strong>✅ Cost Stable:</strong><br>
        Price variance within safe buffer (${deltaPct.toFixed(1)}%). No shelf price adjustment required.
      `;
    }
  }

  if (oldPriceInput && newPriceInput && targetMarginInput) {
    oldPriceInput.addEventListener('input', updateMarginSimulation);
    newPriceInput.addEventListener('input', updateMarginSimulation);
    targetMarginInput.addEventListener('input', updateMarginSimulation);
    updateMarginSimulation();
  }

  // 7. Navigation Smooth Scrolling
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href === '#' || !href) return;
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  // 8. Trigger Live Contract Inspector Preview
  const previewContractBtn = document.getElementById('previewContractBtn');
  if (previewContractBtn) {
    previewContractBtn.addEventListener('click', (e) => {
      e.preventDefault();
      recorder.showContractResults('kannada_khata');
    });
  }
});
