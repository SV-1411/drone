# Stressed short-word detection

## Decision path

The phone node treats a short spoken alert as distress only when all three
independent checks pass:

1. Browser ASR returns a **final** transcript containing a narrow emergency
   phrase (`help`, `bachao`, `madad`, `save me`, etc.). Elongated spellings such
   as `heeelp` and `bachaaaooo` are normalized, while `hello` is not matched.
2. The ASR confidence meets `SPEECH_KEYWORD_MIN_CONF` (default `0.65`).
3. The captured microphone window passes the server's prosodic gate:
   sustained voiced duration >= `0.45 s`, composite prosody score >= `0.58`,
   and signal-to-noise ratio >= `6 dB`.

The prosody score weights voiced duration (0.55), high F0 (0.35), and
speech-band spectral centroid (0.10). Its values are returned to the phone UI
as stress score, F0, voiced duration, and SNR so a rejected word is auditable.
The code deliberately does **not** use an absolute volume trigger: quiet,
intelligible stressed speech can pass if it is above the measured local noise
floor. White/street noise is rejected by the voiced-pitch and SNR checks.

## Research basis

- Protopapas & Lieberman, *Fundamental frequency of phonation and perceived
  emotional stress* (JASA, 1997) found mean/maximum F0 strongly related to
  perceived stress: <https://pubmed.ncbi.nlm.nih.gov/9104028/>.
- Schewski et al., *Measuring negative emotions and stress through acoustic
  correlates in speech* (PLoS One, 2025) identifies prosodic features, notably
  F0 and intensity, as the most investigated and most accurate family of
  acoustic correlates: <https://pubmed.ncbi.nlm.nih.gov/40705747/>.
- Potisuk, Gandour & Harper, *Acoustic correlates of stress* (Phonetica, 1996)
  found duration to be a predominant cue for lexical stress:
  <https://pubmed.ncbi.nlm.nih.gov/8865675/>.
- Michaely et al., *Keyword Spotting for Google Assistant Using Contextual
  Speech Recognition* (ASRU, 2017) supports a two-stage keyword + contextual
  ASR design for reducing false accepts:
  <https://research.google/pubs/keyword-spotting-for-google-assistant-using-contextual-speech-recognition/>.

## Calibration boundary

These conservative initial thresholds are not a substitute for a labelled
field evaluation. Before a real street deployment, collect consented examples
of normal and stressed help/bachao/madad calls across speakers, distances and
traffic conditions, then measure false accepts and false rejects before
changing the thresholds or training a dedicated KWS model.
