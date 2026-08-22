# Security

## Model

The application runs offline, has no telemetry, and treats the input tree as
read-only. It writes only to an explicit output location and rejects output
directories nested inside the input tree. ZIP archives are indexed without
extracting or executing their contents.

## Photoshop automation

The optional PSD signature workflow accesses only PSD files under the input
directory explicitly selected by the operator. It does not upload files or
send telemetry. Source PSDs are opened only for inspection and closed without
saving. Files selected for replacement are first copied to a separate output
directory; only those output copies may be changed and saved by Photoshop.

Input and output directories must not be equal or nested in either direction,
and existing output PSDs are not overwritten. The automation does not change
Photoshop global preferences, close unrelated user documents, flatten layers,
or alter Smart Objects.

## Reports

Once the project is hosted on GitHub, use the repository's GitHub Security
Advisories private vulnerability reporting channel for sensitive reports. If
that channel is not yet available, do not disclose a suspected vulnerability
publicly; retain a minimal programmatically generated reproducer until the
maintainer provides a private reporting channel. Do not attach private design
assets to a report.

## Scope limits

This is a metadata indexing tool, not a file sanitizer. Its generated reports
can contain relative filenames supplied by the operator. Review outputs before
sharing them.

`signature-inspect` reports can also contain text read from PSD text layers.
Treat those reports as potentially private and review them before sharing.
