# Validation of this build setup

Checked on 11 October 2026.

- The firmware source, GPIO profiles and partition CSVs match the files in
  `ESP32_Flash_Configure_v2_1.zip`. The setup reuses that app's original builder
  and image validator.
- The workflow YAML was parsed and checked for its manual trigger, read-only
  repository permission, saved CLI version and upload-on-success behavior.
- Build orchestration was exercised for all 15 targets using a simulated CLI
  that supplied the existing compiled firmware images. This checks the command
  flow and package creation; it is not a fresh firmware compilation.
- The resulting test package was accepted by the actual, unchanged flashing
  app importer, and all 15 activated bundles passed the app's validator.
- An incomplete set of targets was rejected before package publication.
- A binary with the wrong chip ID was rejected even after its SHA-256 was
  updated in the test manifest.
- A simulated compiler failure stopped the run and removed any previous output
  ZIP with the same version label.
- A supplied version label was applied only to the temporary build copy and
  target manifests. The original source `Config.h` remained unchanged.

Arduino CLI and its ESP32 compiler toolchain were not available for fresh
compilation in this environment. No GitHub repository was created, no GitHub
workflow was executed, and no physical board was flashed during these checks.
The first successful GitHub run will confirm tool downloads and actual
compilation of this source with the saved toolchain.
