const SR =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export const recognitionSupported = Boolean(SR);

export const speechSupported =
  typeof window !== "undefined" &&
  "speechSynthesis" in window &&
  typeof SpeechSynthesisUtterance !== "undefined";

// Voice preferences, kept here so any component can speak with the chosen voice
let prefs = { voice: "", rate: 1 };

export function setVoicePrefs(p) {
  prefs = { ...prefs, ...p };
}

const NOVELTY =
  /^(albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|fred|junior|ralph|kathy)\b/i;

function score(v) {
  let s = 0;
  if (/premium/i.test(v.name)) s += 40;
  if (/enhanced|natural|neural|wavenet/i.test(v.name)) s += 30;
  if (/siri/i.test(v.name)) s += 25;
  if (/google/i.test(v.name)) s += 20;
  if (v.lang && v.lang.toLowerCase() === (navigator.language || "").toLowerCase()) s += 3;
  return s;
}

export function listVoices() {
  if (!speechSupported) return [];
  const base = (navigator.language || "en").slice(0, 2).toLowerCase();
  const all = window.speechSynthesis.getVoices();
  let list = all.filter((v) => v.lang.toLowerCase().startsWith(base));
  if (list.length === 0) list = all;
  return list
    .filter((v) => !NOVELTY.test(v.name))
    .map((v) => ({
      name: v.name,
      lang: v.lang,
      score: score(v),
      fancy: /premium|enhanced|natural|neural|siri|google/i.test(v.name),
    }))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}

export function onVoicesChanged(cb) {
  if (!speechSupported) return () => {};
  window.speechSynthesis.addEventListener("voiceschanged", cb);
  return () => window.speechSynthesis.removeEventListener("voiceschanged", cb);
}

function pickVoice() {
  const all = window.speechSynthesis.getVoices();
  if (prefs.voice) {
    const chosen = all.find((v) => v.name === prefs.voice);
    if (chosen) return chosen;
  }
  const best = listVoices()[0];
  return best ? all.find((v) => v.name === best.name) : null;
}

// Turns markdown into text that sounds natural when read aloud
export function plainText(md) {
  return md
    .replace(/```[\s\S]*?```/g, " (code block omitted). ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[\d+\]/g, "")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/[*_~|]/g, "")
    .replace(/([^.!?:\s])[ \t]*\n+/g, "$1. ")
    .replace(/\s+/g, " ")
    .trim();
}

// Long text is read in sentence-sized pieces, because some browsers cut off long speech
function chunk(text) {
  const sentences = text.match(/[^.!?]+[.!?]*\s*/g) || [text];
  const out = [];
  let cur = "";
  for (const s of sentences) {
    if (cur && (cur + s).length > 220) {
      out.push(cur.trim());
      cur = s;
    } else {
      cur += s;
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out.length ? out : [text];
}

let activeEnd = null;
let runId = 0;

export function stopSpeaking() {
  runId++;
  if (speechSupported) window.speechSynthesis.cancel();
  if (activeEnd) {
    const f = activeEnd;
    activeEnd = null;
    f();
  }
}

export function speak(text, onEnd) {
  if (!speechSupported) return;
  stopSpeaking();
  const id = ++runId;
  activeEnd = onEnd;
  const chunks = chunk(plainText(text));
  const voice = pickVoice();
  let i = 0;

  const next = () => {
    if (id !== runId) return;
    if (i >= chunks.length) {
      const f = activeEnd;
      activeEnd = null;
      if (f) f();
      return;
    }
    const u = new SpeechSynthesisUtterance(chunks[i++]);
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang;
    }
    u.rate = prefs.rate || 1;
    u.onend = next;
    u.onerror = () => {
      if (id === runId) stopSpeaking();
    };
    window.speechSynthesis.speak(u);
  };
  next();
}

export function startListening({ onText, onEnd, onError }) {
  const rec = new SR();
  rec.lang = navigator.language || "en-US";
  rec.interimResults = true;
  rec.continuous = false;

  rec.onresult = (e) => {
    let t = "";
    for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
    onText(t);
  };
  rec.onend = onEnd;
  rec.onerror = (e) => onError(e.error);

  rec.start();
  return rec;
}
