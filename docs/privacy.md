# Privacy and retention

The local demo is intended for synthetic data. Do not upload real customer records, confidential policy documents or regulated data into a shared demo.

PostgreSQL stores customers, tickets, appointments, tasks, documents/chunks, chat messages, workflow checkpoints, idempotency results, tool metadata and audit events. Uploaded source files are stored in the configured upload volume. Browser storage contains only the theme preference; session credentials use HttpOnly cookies, and the CSRF token remains in memory.

Demo mode performs no model-provider calls. OpenAI mode sends bounded recent conversation context, validated tool schemas/plans, relevant retrieved passages, selected tool results and document text for embeddings to OpenAI. Optional LangSmith tracing may also send prompts, outputs and metadata to the tracing provider. Enable it only after reviewing organizational consent and provider settings. Never put API keys in documents or prompts.

Local demo data remains until you remove it. There is no automatic global retention purge in this version. Demo operators should use synthetic data, reset disposable demo environments within seven days of an evaluation, and keep no public shared demo credentials. An organizational production retention policy must define separate lifetimes for records, files, messages, checkpoints, idempotency receipts and audits. Do not delete idempotency receipts while replayable workflows can still execute.

Deleting a knowledge document atomically removes searchable chunks and then removes its stored file. Existing messages/checkpoints that already quoted the document may still contain excerpts. Removing a document is not a full conversation erasure operation. Backups can retain prior copies until their configured expiry. Files left orphaned by a crash during upload or file cleanup should be reconciled by an operator against stored document keys.

Avoid full request/body logging. The application exposes safe error codes and writes audit metadata rather than complete sensitive records. Database administrators can still access stored business information and must protect database credentials and backups.
