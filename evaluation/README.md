# Agent evaluation

The executable routing dataset lives in `apps/api/evaluation/cases.json`; the runner is `apps/api/evaluation/run.py`.

```sh
docker compose run --rm api uv run --no-sync python -m evaluation.run
```

Ten cases cover knowledge, ticket/task creation, read operations, scheduling, protected CRM updates and an adversarial request. Each case checks the selected specialist and expected tool. With `AI_PROVIDER=demo`, this is a reproducible regression check of the explicit command router. With OpenAI configured, it performs real provider calls and reports usage. Live runs may cost money and can expose the synthetic evaluation inputs to that provider.

The API integration suite additionally evaluates outcome persistence, grounding/citations, tenant isolation, missing evidence, document prompt injection, approval rejection/expiry/tampering/stale-resource protection, revocation, process-style recovery, duplicate resumes and booking races. These assertions are the business acceptance checks, beyond routing labels.

There is no claim that a ten-case routing score measures general natural-language quality or that demo-mode results establish OpenAI behavior. Before deployment, add representative organizational questions, known relevant source IDs, insufficient-evidence cases, locale/time-zone scenarios and approved action examples. Keep personal data out of fixtures. Evaluate route accuracy, tool arguments, citation validity, action success, latency and costs separately.
