# Scholia documentation

| I want to... | Read |
|---|---|
| Run Scholia on my machine and practise | [Setup guide](guides/setup.md) |
| Understand the system at a glance | [High-level design](architecture/hld.md) |
| Understand how the code works | [Low-level design](architecture/lld.md) |
| Know why it is built this way | [Decision log](architecture/decisions.md) |
| Build or extend the problem library | [Corpus guide](guides/corpus.md) |
| Configure, monitor, back up or debug it | [Operations guide](guides/operations.md) |
| Prepare to discuss this project in an interview | [Interview questions](interview/questions.md) |
| Contribute | [CONTRIBUTING](../CONTRIBUTING.md) |
| Report a security issue | [SECURITY](../SECURITY.md) |
| See the living specification and invariants | [CLAUDE.md](../CLAUDE.md) |

## Diagram index

All diagrams are Mermaid and render on GitHub.

| Diagram | Where |
|---|---|
| System context | [HLD 3](architecture/hld.md#3-system-context) |
| Containers | [HLD 4](architecture/hld.md#4-containers) |
| Session sequence | [HLD 5.1](architecture/hld.md#51-a-session-end-to-end) |
| Grading pipeline | [HLD 5.2](architecture/hld.md#52-grading-pipeline) |
| Corpus build | [HLD 5.3](architecture/hld.md#53-corpus-build) |
| Trust boundaries | [HLD 6](architecture/hld.md#6-trust-boundaries-and-security) |
| Data model (ER) | [HLD 7](architecture/hld.md#7-data-stores), [LLD 3](architecture/lld.md#3-data-model) |
| Deployment | [HLD 8](architecture/hld.md#8-deployment) |
| Package dependencies | [LLD 1](architecture/lld.md#1-packages-and-dependency-rules) |
| Shared types (class diagram) | [LLD 2](architecture/lld.md#2-shared-types-schema) |
| Session state machine | [LLD 5](architecture/lld.md#5-session-lifecycle) |
| Assistant proxy decision flow | [LLD 6](architecture/lld.md#6-assistant-proxy) |
| Fix grading | [LLD 7.4](architecture/lld.md#74-code-fixes-fixpy) |
| Corpus filter flow and planted bugs | [LLD 10](architecture/lld.md#10-corpus-pipeline) |
| Frontend component tree | [LLD 11](architecture/lld.md#11-frontend) |

Screenshots live in [`assets/`](assets/).
