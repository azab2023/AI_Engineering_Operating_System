# Prompts

This directory holds AEOS's versioned prompt assets, managed by the
Phase-08 Prompt Management System (`orchestrator/prompts/`; see
[ADR-0006](../docs/architecture/decision-records/ADR-0006-prompt-management-system.md)
for the full design).

## Layout

```
prompts/
├── prompt_registry.yaml   # validated entries: category, purpose, agents,
│                            priority, version, template_path, variables
├── templates/
│   └── <category>/<prompt_id>.md   # $variable substitution (string.Template)
└── workflows/               # reserved for future multi-step prompt chains
```

## Adding a new prompt

1. Add a template file under `templates/<category>/<prompt_id>.md`, using
   `$variable_name` for substitution points.
2. Add one entry to `prompt_registry.yaml` under `prompts:` with a unique
   key (the `prompt_id`). Declare every variable the template uses under
   `variables:`, marking each `required: true` or `required: false`.
3. List every agent name (matching `config/agent_registry.yaml`) allowed
   to use this prompt under `agents:`.

No code changes are needed to add a prompt -- `PromptRegistry` loads and
validates the file at construction time, failing loudly on a missing
field, a missing `template_path`, or a duplicate top-level key.

## Using a prompt

```python
from orchestrator.prompts import PromptManager

manager = PromptManager()
rendered = manager.render(
    "code_generation",
    agent_name="codex",
    variables={"task_description": "add a retry helper", "language": "Python"},
)
```

In practice, this happens automatically inside `SubprocessAgentInvoker` /
`HttpAgentInvoker` whenever an `AgentTask` is constructed with
`prompt_id` set:

```python
AgentTask(
    task_type="code_generation",
    description="add a retry helper",  # ignored when prompt_id is set
    prompt_id="code_generation",
    prompt_variables={"task_description": "add a retry helper", "language": "Python"},
)
```

If `prompt_id` is left as `None` (the default), `description` is sent to
the agent as-is -- the pre-Phase-08 behavior, unchanged.
