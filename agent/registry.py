from pathlib import Path
import importlib

TRIGGER_TO_ROLE = {
    "support_ticket": "support_agent",
    "cron":             "email_reviewer",
    "microsoft_email":  "email_reviewer",
    "message":        "personal_assistant",
    "market_event":   "market_watcher",
}

ROLE_MAX_TOKENS = {
    "email_reviewer": 8192,
    "market_watcher": 4096,
}

ROLE_MODELS = {
    # "market_watcher": "gemma-2-2b-it",  # uncomment to override default
}

def get_role(trigger_type: str) -> dict:
    role_name = TRIGGER_TO_ROLE.get(trigger_type)
    if not role_name:
        raise ValueError(f"No role registered for trigger type: {trigger_type}")
    module = importlib.import_module(f"roles.{role_name}.role")

    # Use Microsoft tools for microsoft_email trigger
    if trigger_type == "microsoft_email":
        tools_module = importlib.import_module(f"roles.{role_name}.microsoft_tools")
        account_label = "microsoft"
    else:
        tools_module = importlib.import_module(f"roles.{role_name}.tools")
        account_label = "gmail"

    skills = _load_skills(role_name)
    return {
        "name":       role_name,
        "persona":    module.PERSONA,
        "tools":      tools_module.TOOLS,
        "registry":   tools_module.TOOL_REGISTRY,
        "skills":     skills,
        "max_tokens": ROLE_MAX_TOKENS.get(role_name, 1024),
        "model":      ROLE_MODELS.get(role_name),  # optional override
    }

def _load_skills(role_name: str) -> str:
    base = Path(__file__).parent.parent / "skills"
    parts = []
    names = []

    for skill_file in sorted((base / "shared").glob("*.md")) if (base / "shared").exists() else []:
        parts.append(skill_file.read_text())
        names.append(skill_file.stem)

    for skill_file in sorted((base / "roles" / role_name).glob("*.md")) if (base / "roles" / role_name).exists() else []:
        parts.append(skill_file.read_text())
        names.append(skill_file.stem)

    if names:
        print(f"  [skills] loaded {len(names)} skill(s): {', '.join(names)}")
    return "\n\n---\n\n".join(parts)

def register_trigger(trigger_type: str, role_name: str):
    TRIGGER_TO_ROLE[trigger_type] = role_name
    print(f"[registry] registered '{trigger_type}' → '{role_name}'")
