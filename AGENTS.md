# Project guidance

This is a public, reusable HR research tool, not a company-specific policy repository.

- Preserve the five topics and the distinction between general rules and case applicability.
- Never present absent evidence as permission or search snippets as opened legal text.
- Keep API keys, local reports, case facts and user configuration out of Git.
- Keep the core runtime on the Python standard library; PDF text extraction uses the declared `pypdf>=6.14.2,<7` dependency. Install with `python -m pip install -e .` before starting or testing, then test with `python -m unittest discover -s tests -v` (use `python3` on macOS/Linux).
- Keep frontend output text-only except trusted static markup; render external content with textContent.
- Follow the stable contract in docs/design.md. Document any interface changes and verify affected clients.
- Do not fabricate country laws in examples. Use an explicitly fictional demonstration jurisdiction.
