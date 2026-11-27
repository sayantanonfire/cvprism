# capture

Everything that turns work signals into candidate evidence cards on a single device: the Claude Code `SessionEnd` hook and the global git hook dispatcher (both only enqueue, see ADR-007 and ADR-008), the opt-in folder watcher, the file-based job queue and worker, the code-only reducer that builds a privacy-safe digest, the `claude -p` extractor, and the redactor. Nothing here writes to a transport. Its output goes to `novelty/`.
