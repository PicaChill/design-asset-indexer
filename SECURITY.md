# Security

## Model

The application runs offline, has no telemetry, and treats the input tree as
read-only. It writes only to an explicit output location and rejects output
directories nested inside the input tree. ZIP archives are indexed without
extracting or executing their contents.

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
