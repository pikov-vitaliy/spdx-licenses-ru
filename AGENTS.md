# AGENTS.md

This repository is a static SPDX license reference site with Russian translations
and short reference assessments.

## Commands

- `py rbpo\generate.py [ID ...]` regenerates translated pages. With no
  arguments, it regenerates every SPDX identifier listed in `rbpo\verdicts.json`.
- `py rbpo\generate.py` should be idempotent: running it twice should not produce
  additional changes.
- `py -m http.server 8765` from `website\` starts a local static preview.

Use `py`, not `python`, on Windows.

## Repository Layout

- `website/` is the ready-to-publish static site.
- `rbpo/generate.py` renders Russian blocks into pages.
- `rbpo/verdicts.json` contains assessment metadata.
- `rbpo/translations/` contains the Russian translations.
- `rbpo/pristine/` contains byte-preserved upstream SPDX HTML snapshots used as
  regeneration sources.
- `json/`, `text/`, `html/`, `rdfa/`, `rdf*`, `SPDXv3/`, and
  `license-list-XML/` are upstream SPDX data formats.

Do not hand-edit generated pages in `website/`. Update `rbpo/verdicts.json` or
`rbpo/translations/`, then run `py rbpo\generate.py`.

## Translation Rules

- Keep a 1:1 paragraph relationship with the English SPDX source whenever
  possible.
- Preserve URLs, names, dates, amounts, section numbers, and legal modality.
- Do not soften license terms or remove offensive text that is part of an
  original license.
- English SPDX text remains the authoritative source.
