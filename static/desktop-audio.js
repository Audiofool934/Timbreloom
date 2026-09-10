// A compact, keyboard-accessible surface over the existing HTML media elements.
// Source ownership, streaming queues, and recording lifecycle stay with their controllers.
export function installDesktopAudio({ icon }) {
  const names = {
    audioPlayer: "Generated speech", transcriptAudio: "Transcription source", vcSourceAudio: "Original performance", vcOutputAudio: "Converted voice",
    dubSourceAudio: "Dubbing source audio", cloneStreamAudio: "Speech in progress", vcStreamAudio: "Conversion in progress",
    asrStreamAudio: "Transcription source", dubStreamAudio: "Dubbing in progress", cloneRecordPreview: "Reference recording",
    asrRecordPreview: "Transcription recording", vcRecordPreview: "Source recording",
  };
  const formatTime = (seconds) => {
    if (!Number.isFinite(seconds) || seconds < 0) return "00:00";
    const value = Math.floor(seconds);
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor(value % 3600 / 60).toString().padStart(2, "0");
    const remainder = (value % 60).toString().padStart(2, "0");
    return hours ? `${hours}:${minutes}:${remainder}` : `${minutes}:${remainder}`;
  };
  for (const audio of document.querySelectorAll("audio[controls]")) {
    const name = names[audio.id] || "Audio";
    const player = document.createElement("div"); player.className = "desktop-player";
    player.setAttribute("role", "group"); player.setAttribute("aria-label", `${name} player`);
    const play = document.createElement("button"); play.type = "button"; play.id = `${audio.id}-play`; play.className = "desktop-play";
    const elapsed = document.createElement("span"); elapsed.className = "desktop-time";
    elapsed.setAttribute("aria-hidden", "true");
    const seek = document.createElement("input"); seek.type = "range"; seek.id = `${audio.id}-seek`; seek.className = "desktop-seek";
    seek.min = "0"; seek.max = "0"; seek.step = "0.01"; seek.value = "0";
    seek.setAttribute("aria-label", `${name} position`);
    const duration = document.createElement("span"); duration.className = "desktop-time";
    duration.setAttribute("aria-hidden", "true");
    const speed = document.createElement("select"); speed.className = "desktop-speed"; speed.id = `${audio.id}-speed`;
    speed.setAttribute("aria-label", `${name} speed`);
    for (const value of [.75, 1, 1.25, 1.5, 2]) speed.add(new Option(`${value}×`, String(value), value === 1, value === 1));
    const error = document.createElement("span"); error.className = "desktop-player-error";
    error.setAttribute("role", "status"); error.hidden = true;
    player.append(play, elapsed, seek, duration, speed, error);
    audio.after(player); audio.controls = false; audio.classList.add("desktop-media");
    let renderedState;
    const update = () => {
      player.hidden = audio.hidden || !audio.getAttribute("src");
      const playing = !audio.paused && !audio.ended;
      if (renderedState !== playing) {
        play.replaceChildren(icon(playing ? "pause.fill" : "play.fill")); renderedState = playing;
      }
      play.setAttribute("aria-label", `${playing ? "Pause" : "Play"} ${name}`);
      play.title = `${playing ? "Pause" : "Play"} ${name}`;
      elapsed.textContent = formatTime(audio.currentTime);
      duration.textContent = formatTime(audio.duration);
      seek.disabled = !Number.isFinite(audio.duration) || audio.duration <= 0;
      seek.max = seek.disabled ? "0" : String(audio.duration);
      seek.value = String(audio.currentTime || 0);
      seek.style.setProperty("--progress", `${seek.disabled ? 0 : audio.currentTime / audio.duration * 100}%`);
      seek.setAttribute("aria-valuetext", `${formatTime(audio.currentTime)} / ${formatTime(audio.duration)}`);
      speed.value = String(audio.playbackRate);
    };
    play.addEventListener("click", async () => {
      if (!audio.paused) { audio.pause(); return; }
      error.hidden = true;
      try {
        if (audio.error) audio.load();
        await audio.play();
      } catch (failure) {
        if (failure.name !== "AbortError") {
          error.textContent = "Cannot play right now. Select Play to try again."; error.hidden = false;
        }
      }
    });
    seek.addEventListener("input", () => { audio.currentTime = Number(seek.value); update(); });
    speed.addEventListener("change", () => { audio.playbackRate = Number(speed.value); });
    for (const event of ["timeupdate", "loadedmetadata", "durationchange", "play", "pause", "ended", "emptied", "ratechange"]) audio.addEventListener(event, update);
    audio.addEventListener("error", () => { error.textContent = "Cannot read this audio yet. Select Play to try again."; error.hidden = false; });
    audio.addEventListener("loadstart", () => { error.hidden = true; update(); });
    new MutationObserver(update).observe(audio, { attributes: true, attributeFilter: ["src", "hidden"] });
    update();
  }
}
