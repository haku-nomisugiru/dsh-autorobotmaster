# Third-party references and components

## Hermes Agent

Research and architecture reference: https://github.com/NousResearch/hermes-agent

Pinned research commit: `3bcd071226d3d605a2bb3b4f3933e7d583e189d6`.

RoboMaster Studio contains an independently written Rust implementation of selected memory, context summarization and procedural skill patterns. Research source copies under `docs/research` retain their original MIT license in `docs/research/LICENSE`.

Copyright (c) 2025 Nous Research.

## SolidWorks Automation Skill

https://github.com/wzyn20051216/solidworks-automation-skill

Upstream runtime is installed separately and connected using MCP. No SolidWorks binaries or proprietary CAD assets are included. The upstream project is MIT licensed; follow its notices when distributing that runtime.

## step.parts

https://github.com/earthtojake/step.parts

The application calls the public catalog API and retains source metadata. Downloaded model licenses and source conditions remain applicable. A successful download or matching SHA-256 is not a license grant or a mechanical acceptance result.

## Visual identity

The interface uses an original robot line mark and three mechanical exploded-view images supplied by the user in `images/`. The original PNG files are bundled unchanged; CSS controls presentation and motion. No people or human sculptures are included. The editorial typography, electric-blue accents and interaction study reference https://nousresearch.com/; website assets and commercial fonts are not redistributed. Research screenshots remain outside the release package. The project is not affiliated with Nous Research, DJI, RoboMaster, or Dassault Systèmes. Third-party names identify interoperability and user context.

## Runtime dependencies

Default interface typography uses the user's locally installed OCR A Extended and Noto Sans SC Thin fonts. The desktop application reads these installed files into memory for rendering; it does not copy them to the release or install fonts. The fonts retain their respective licenses.

Rust and frontend dependency versions are pinned by `src-tauri/Cargo.lock` and `package-lock.json`. Dependencies include Tauri, Tokio, reqwest, rusqlite, serde, keyring, React, Lucide, react-markdown, and remark-gfm. Their own licenses and notices apply.
