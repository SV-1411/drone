# VanniKawachh — IEEE Journal LaTeX Source

`JOURNAL_PAPER.tex` is the submission-ready IEEEtran version of
`docs/JOURNAL_PAPER.md`. Figures are referenced from `../figures/v2/`
(via `\graphicspath`), so keep the `docs/figures` directory alongside
`docs/latex`.

## Compile locally

```
cd docs/latex
tectonic JOURNAL_PAPER.tex
```

Tectonic downloads IEEEtran and all other packages from CTAN automatically.
Plain `pdflatex JOURNAL_PAPER.tex` (run twice for cross-references) also
works with any TeX Live / MiKTeX install that has the `IEEEtran` class.

## Compile on Overleaf

1. Create a new project and upload the contents of `docs/latex`.
2. Upload the `docs/figures/v2` PNGs, preserving the relative layout
   (i.e., a `figures/v2/` folder one level above the `.tex` file — or
   simply put the PNGs next to the `.tex` and Overleaf will still find
   them if you adjust `\graphicspath`). Easiest: upload the whole `docs`
   folder as a zip and set `latex/JOURNAL_PAPER.tex` as the main document.
3. IEEEtran is available on Overleaf by default; no extra packages needed.

## Notes

- Only standard packages are used: `cite`, `amsmath`, `amssymb`,
  `graphicx`, `booktabs`, `url`.
- Bibliography is inline (`thebibliography`), so no BibTeX run is needed.
