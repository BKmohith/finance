const fs = require('fs');
let content = fs.readFileSync('frontend/js/dashboard.js', 'utf8');

content = content.replace(
  /if \(voiceToastAudioIndicator\) \{\s*voiceToastAudioIndicator\.style\.display = 'inline-flex';\s*if \(voiceToastAudioText\) voiceToastAudioText\.textContent = '[^']+';\s*\}/g,
  `if (voiceAudioSpeakingPill) {
      voiceAudioSpeakingPill.style.display = 'inline-flex';
      voiceAudioSpeakingPill.textContent = '🔊 Bulbul TTS';
    }`
);

content = content.replace(/voiceToastAudioIndicator/g, 'voiceAudioSpeakingPill');
content = content.replace(/Saaras STT • \${langName} Voice/g, 'Sarvam AI • ${langName} Voice');
content = content.replace(/🎙️ Heard: "<em>/g, 'VOICE INPUT: "<em>');
content = content.replace(/⚡ Transcribing via Sarvam Saaras AI \(STT\)\.\.\./g, 'TRANSCRIBING AUDIO...');
content = content.replace(/⚡ Processing with Sarvam AI\.\.\./g, 'PROCESSING REQUEST...');
content = content.replace(/🔴 Listening\.\.\. \(Max 6s\)/g, 'RECORDING AUDIO...');
content = content.replace(/🔴 Listening\.\.\. \(Tap to finish\)/g, 'Listening at Counter...');

fs.writeFileSync('frontend/js/dashboard.js', content, 'utf8');
console.log('Successfully updated dashboard.js text labels');
