/**
 * Sahayak Multi-Layer Financial Voice Waveform Visualizer
 * Layered sinusoidal curves in warm gold, lilac, and mint green.
 */

class AudioVisualizer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    
    this.dpr = window.devicePixelRatio || 1;
    this.resize();
    window.addEventListener('resize', () => this.resize());

    this.phase = 0;
    this.baseAmplitude = 18;
    this.targetAmplitude = 18;
    this.currentAmplitude = 18;
    this.frequency = 0.015;
    this.speed = 0.022;
    this.isListening = false;
    this.isSimulating = false;

    this.audioContext = null;
    this.analyser = null;
    this.dataArray = null;

    // Harmonic financial palettes: saffron gold, lilac, emerald mint
    this.waves = [
      { color: 'rgba(201, 151, 46, 0.45)', lineWidth: 1.5, freqMult: 0.9, speedMult: 1.0, phaseOffset: 0 },
      { color: 'rgba(121, 82, 179, 0.75)', lineWidth: 2.0, freqMult: 1.2, speedMult: 1.25, phaseOffset: 1.2 },
      { color: 'rgba(27, 131, 84, 0.45)', lineWidth: 1.2, freqMult: 0.7, speedMult: 0.85, phaseOffset: 2.4 },
      { color: 'rgba(227, 83, 108, 0.35)', lineWidth: 1.0, freqMult: 1.4, speedMult: 1.4, phaseOffset: 3.8 },
      { color: 'rgba(201, 151, 46, 0.30)', lineWidth: 1.0, freqMult: 1.7, speedMult: 0.7, phaseOffset: 4.6 }
    ];

    this.animate();
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.ctx.scale(this.dpr, this.dpr);
  }

  attachAudioStream(stream) {
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioContextClass();
      const source = this.audioContext.createMediaStreamSource(stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      source.connect(this.analyser);
      this.isListening = true;
    } catch (e) {
      this.startSimulatedVoice();
    }
  }

  startSimulatedVoice() {
    this.isSimulating = true;
    this.isListening = true;
  }

  stopListening() {
    this.isListening = false;
    this.isSimulating = false;
    this.targetAmplitude = 18;
    if (this.audioContext && this.audioContext.state !== 'closed') {
      try {
        this.audioContext.close();
      } catch (e) {}
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    if (!this.ctx) return;

    this.ctx.clearRect(0, 0, this.width, this.height);

    if (this.isListening) {
      if (this.analyser && this.dataArray) {
        this.analyser.getByteFrequencyData(this.dataArray);
        let sum = 0;
        for (let i = 0; i < this.dataArray.length; i++) {
          sum += this.dataArray[i];
        }
        const avg = sum / this.dataArray.length;
        this.targetAmplitude = 20 + (avg * 0.45);
      } else if (this.isSimulating) {
        const voiceCadence = Math.sin(this.phase * 3.5) * Math.cos(this.phase * 1.8);
        this.targetAmplitude = 34 + (voiceCadence * 20) + (Math.random() * 8);
      }
    } else {
      this.targetAmplitude = 16 + Math.sin(this.phase * 0.8) * 4;
    }

    this.currentAmplitude += (this.targetAmplitude - this.currentAmplitude) * 0.12;
    this.phase += this.speed;

    const centerY = this.height / 2;

    this.waves.forEach((wave) => {
      this.ctx.beginPath();
      this.ctx.strokeStyle = wave.color;
      this.ctx.lineWidth = wave.lineWidth;
      this.ctx.lineCap = 'round';
      this.ctx.lineJoin = 'round';

      const points = [];
      const step = 6;

      for (let x = 0; x <= this.width; x += step) {
        const edgeEnvelope = Math.sin((x / this.width) * Math.PI);
        const y = centerY + Math.sin((x * this.frequency * wave.freqMult) + (this.phase * wave.speedMult) + wave.phaseOffset) 
                          * (this.currentAmplitude * edgeEnvelope)
                          + Math.cos((x * this.frequency * 0.5) + this.phase) * (6 * edgeEnvelope);
        points.push({ x, y });
      }

      if (points.length > 0) {
        this.ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length - 1; i++) {
          const xc = (points[i].x + points[i + 1].x) / 2;
          const yc = (points[i].y + points[i + 1].y) / 2;
          this.ctx.quadraticCurveTo(points[i].x, points[i].y, xc, yc);
        }
      }

      this.ctx.stroke();
    });
  }
}

window.AudioVisualizer = AudioVisualizer;
