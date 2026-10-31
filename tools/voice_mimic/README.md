# Voice mimic: Furby-voiced lines for the show

These scripts made the Halloween show's voice lines: new words in something close to the Furby's own voice. The recipe:

1. **A sample of the voice.** [`make_ref.sh`](make_ref.sh) takes four speech-only clips from your stock DLC (decoded by [`audioutils/extract_voice.py`](../../audioutils/extract_voice.py)), trims their silence and joins them into about 10 seconds of sample audio. [`refs.py`](refs.py) builds a few more candidate samples from the clips [`analyze.py`](analyze.py) ranks most Furby-like, by pitch and voice similarity, using [`transcribe.py`](transcribe.py)'s Whisper transcripts to leave out songs and effects.
2. **Several takes per line.** [`gen2.py`](gen2.py) runs [Chatterbox](https://github.com/resemble-ai/chatterbox), an open-source text-to-speech model that mimics a sample voice, on every line in [`halloween/show.toml`](../../halloween/show.toml), with each candidate sample and a few settings. ([`gen.py`](gen.py) is the simpler first version: one sample, two takes a line.)
3. **Keep the best.** [`best.py`](best.py) keeps the takes [Whisper](https://github.com/openai/whisper) transcribes correctly, picks the one per line that sounds most like the real Furby (closest to the stock clips' voice embedding), raises the pitch a semitone ([`furbyize.json`](furbyize.json), chosen by a grid over the lines), and writes `build/cloned/<line>.wav`, where the show looks, with previews of how each sounds after the Furby's audio compression.

```sh
uv run audioutils/extract_voice.py   # once: decode your stock DLC's clips to build/voice/ (see stock_dlc.py)
tools/voice_mimic/run.sh             # the whole pipeline; resumable. --regrid, --fresh: see run2.sh
```

It needs a Mac with Apple silicon for [mlx-whisper](https://pypi.org/project/mlx-whisper/) (or swap in another Whisper), ffmpeg, and uv; `run2.sh` installs Chatterbox, Resemblyzer and Praat's Python bindings into throwaway environments. A full run makes about 90 takes at about 4 seconds each. Everything it writes goes in `build/`: working files in `build/voice_mimic/`, lines in `build/cloned/`. [`furbylib.py`](furbylib.py) holds the shared paths and helpers.

**Don't publish what it makes.** The samples are Hasbro's recordings, so the cloned lines, the samples, the transcripts and the similarity data are all derived from them: keep them on your computer. For lines you can share, use [`voices.py`](../../voices.py)'s stand-ins or record your own.
