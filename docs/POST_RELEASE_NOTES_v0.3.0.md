# v0.3.0 post-release maintenance notes

`v0.3.0` is the first stable release with the Premium Simple GUI and Windows x64 portable distribution.

## Verified release properties

- original PSD files are not overwritten;
- the GUI requires explicit confirmation before frozen-plan execution;
- Windows portable runs without an external Python installation;
- release artifacts are accompanied by SHA-256 checksums;
- Windows + Photoshop integration and packaged GUI paths were validated before release;
- third-party notices and Qt/PySide distribution information ship with the portable package.

## Follow-up maintenance

The first post-release maintenance item is to make GUI path handling independent of process working directory by normalizing or rejecting relative input/output paths. This is a usability hardening item rather than a v0.3.0 release blocker.

See [`ROADMAP.md`](../ROADMAP.md) for broader maintenance priorities and [`docs/MAINTAINING.md`](MAINTAINING.md) for release/triage responsibilities.
