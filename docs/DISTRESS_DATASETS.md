# Distress classifier dataset plan

The repository intentionally does **not** commit downloaded audio datasets. Download them locally and place curated WAV files under:

```text
dataset/
├── distress/
├── normal/
└── noise/
```

## Recommended sources

### 1. ASVP-ESD — primary distress/emotional source

ASVP-ESD contains realistic, non-scripted emotional sounds. The dataset includes non-speech fear recordings such as **scream** and **panic**, sadness/crying, and pain/groans, with normal/high intensity and noisy/mixed recordings. The audio is 16 kHz mono WAV and the dataset is roughly 11 hours in the documented release.

Use these as positive examples:
- fear / scream
- fear / panic
- sadness / cry
- pain / groan

Also use its normal/neutral, happy/laugh, anger and other non-distress vocalizations as hard negatives.

Official Zenodo records:
- https://zenodo.org/records/7132783
- https://zenodo.org/records/4782712

### 2. FSD50K — primary environmental/hard-negative source

FSD50K is an open, human-labeled sound-event dataset with 51,197 clips and 200 classes. It contains useful negatives such as alarm, bark, music, siren and many environmental sounds. Each clip has its own Creative Commons license, so preserve the supplied metadata when redistributing any subset.

Official source:
https://zenodo.org/records/4060432

For this project, curate only a small hard-negative subset rather than downloading the entire corpus.

### 3. CREMA-D — normal/emotional speech source

CREMA-D contains 7,442 audio clips from 91 actors with anger, disgust, fear, happy, neutral and sad expressions. It is useful for normal human speech and emotionally intense speech that should **not automatically be classified as distress**.

Official project:
https://github.com/CheyneyComputerScience/CREMA-D

Do not label all fear/anger clips as distress. Use them mainly as hard negatives and only manually promote clearly distress-like vocal bursts if the annotation supports that decision.

### 4. RAVDESS — additional normal/emotional speech

RAVDESS contains 7,356 recordings from 24 professional actors, including fearful, angry, sad, neutral and other emotional speech. It is useful for speaker diversity and for preventing the classifier from equating emotional speech with distress.

Official Zenodo source:
https://zenodo.org/records/1188976

### 5. H-VB — useful if access is available

The Hume Vocal Burst dataset includes a **Distress** label and many speakers. The public Zenodo record is useful for research, but the raw files may be access-restricted depending on the release. Do not make this a deadline dependency.

https://zenodo.org/records/6320973

## Important limitation

There is no single free dataset that perfectly represents "real emergency distress". Most public corpora contain acted emotional expressions. Therefore the classifier should be trained with a mixture of:

1. direct distress vocalizations,
2. realistic emotional/non-distress human vocalizations,
3. environmental hard negatives,
4. synthetic/adversarial noise used only for testing.

For a final-year project, this is a defensible approach as long as the presentation explicitly says that the model detects **acoustic distress-like vocalizations**, not clinically verified emergencies.

## Suggested first training set

Aim for roughly balanced counts before spending time on a huge corpus:

- 200–400 distress clips
- 200–400 normal-human clips
- 300–500 noise/hard-negative clips

Keep a speaker/source-aware test split whenever possible. Never put different crops of the same original recording into both train and test sets.

## Hard-negative checklist

At minimum include:

- siren
- alarm
- car horn
- dog bark
- music
- crowd
- laughter
- singing
- normal speech
- normal shouting
- construction/engine noise
- rain/wind
- synthetic tone
- frequency sweep
- speaker distortion

The last three are especially useful as adversarial tests, but they should not dominate the training set because the deployment problem is natural-world audio.

## Training

After curation:

```bash
python -m hub.train_distress_classifier --dataset dataset --output hub/models
```

Then evaluate:

```bash
python -m hub.evaluate_distress_classifier --dataset dataset
```
