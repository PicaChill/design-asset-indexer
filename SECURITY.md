# Security

## Model

The application runs offline, has no telemetry, and treats the input tree as
read-only. It writes only to an explicit output location and rejects output
directories nested inside the input tree. ZIP archives are indexed without
extracting or executing their contents.

## Reports

Please report a vulnerability through the repository's private security
reporting channel once a public repository exists. Until then, report it
directly to the maintainer. Do not attach private design assets to a report;
use a minimal programmatically generated reproducer.

## Scope limits

This is a metadata indexing tool, not a file sanitizer. Its generated reports
can contain relative filenames supplied by the operator. Review outputs before
sharing them.
