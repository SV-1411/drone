# VanniKawachh: Stage 1 & 2 Refinement Blueprint

This document outlines the technical strategy to transition the VanniKawachh system from a functional prototype to a production-ready, women-centric safety network. The primary focus is on improving detection accuracy for female voices and ensuring robustness against audio degradation during transfer.

## 1. Women-Centric Acoustic Intelligence
Generic distress models often fail to distinguish between high-pitched laughter, children's voices, and genuine adult female distress.

### Acoustic Markers
Instead of relying solely on Fundamental Frequency ($\text{F}_0$), the system will target **Non-Linear Phenomena**:
- **Bifurcations & Subharmonics:** Detection of frequencies at $\text{F}_0/2$ and $\text{F}_0/3$, which indicate physiological glottal instability during extreme stress.
- **Spectral Roughness:** High-energy modulations in the $30\text{--}150\text{ Hz}$ range.
- **Critical Analysis Band:** Priority focus on the $1\text{ kHz} \text{--} 5\text{ kHz}$ range where distress markers are most prominent.

### Dataset Strategy
| Category | Recommended Sources | Goal |
| :--- | :--- | :--- |
| **Positive (Distress)** | CREMA-D, RAVDESS, Non-linguistic Emotional Scream Corpus, BERSt | Capture adult female fear/anger/screams. |
| **Keywords** | Mozilla Common Voice (Female subset) | Train on "Help", "Bachao", "Stop". |
| **Hard Negatives** | UrbanSound8K, Female Laughter, Children's voices | Reduce False Positives from non-distress high-pitch sounds. |

---

## 2. Degradation-Aware Training (DAT)
To solve the "Bad Audio Transfer" problem, the model must be trained on audio that mimics the actual hardware chain (ESP32 $\rightarrow$ Hub).

### The Augmentation Pipeline
The training script will process samples through the following sequence:
1. **Time-Domain:** $\text{Mix-Up} \rightarrow \text{Additive White Gaussian Noise (AWGN, } -20\text{--}-40\text{ dB)}$.
2. **Hardware Simulation:** 
   - **Band-pass Filter:** $300\text{ Hz} \text{--} 8\text{ kHz}$ (matching INMP441/ESP32 ADC).
   - **Quantization:** Inject 12-bit dithered noise.
3. **Codec Simulation:** Encode/Decode using **Opus (low bitrate $16\text{--}32\text{ kbps}$)** or **ADPCM**.
4. **Frequency-Domain:** $\text{SpecAugment (Time/Freq Masking)} \rightarrow \text{Pitch Shifting}$.
5. **Network Simulation:** **Temporal Masking** (randomly dropping $50\text{--}100\text{ms}$ chunks) to simulate packet loss.

---

## 3. High-Performance Audio Transfer Stack
To ensure the Hub's PANNs verifier receives high-quality, continuous audio.

### Transfer Architecture
**$\text{Edge (ESP32)} \xrightarrow{\text{Opus Codec}} \text{WiFi/LoRa} \xrightarrow{\text{Ring Buffer}} \text{Hub (Pi 5)} \xrightarrow{\text{PANNs Verifier}}$**

### Implementation Details
- **Codec:** Use **Opus** for the best trade-off between bandwidth and spectral preservation.
- **Hub Buffer:** Implement a **Circular (Ring) Buffer** with a $200\text{--}500\text{ ms}$ window.
- **Packet Loss Concealment (PLC):** Use linear interpolation or frame repetition to fill gaps before verification.
- **Hybrid Triggering:**
  - **Trigger:** Send MFCC coefficients (low bandwidth).
  - **Verification:** Send Opus-compressed audio (higher bandwidth, used only on trigger).

---

## 4. Implementation Roadmap
1. **Refine Training:** Implement the DAT pipeline in `ml/train_muffled_distress.py`.
2. **Expand Data:** Integrate female-specific non-linear scream datasets and laughter negatives.
3. **Stabilize Hub:** Add the Circular Buffer to `hub/pipeline.py`.
4. **Optimize Edge:** Implement Opus encoding on the ESP32.
