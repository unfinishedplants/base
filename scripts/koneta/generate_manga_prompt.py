import os
import sys
import yaml
import argparse
from pathlib import Path

# Windows UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent.resolve()
GITV_ROOT = SCRIPT_DIR.parent.parent
CONFIG_PATH = GITV_ROOT / "config" / "koneta" / "manga_render_contract.yaml"
CANDIDATES_DIR = GITV_ROOT / "workbench" / "candidates" / "article-images"

def load_contract():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Render contract not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def compile_prompt(panels_data):
    """
    panels_data: list of dict, length 4
    each element: {
        'character': 'captain' | 'nagi' | 'sumi' | 'yura' | 'other',
        'action': 'holding phone...',
        'dialogue': 'ひぎィッ！' (or None)
    }
    """
    contract = load_contract()
    layout = contract["layout"]
    invariants = contract["character_invariants"]

    header = (
        f"High quality 4-panel manga comic strip, {layout['grid']}, {layout['aspect_ratio']} aspect ratio, "
        f"{layout['style']}, {layout['margins']}, {layout['borders']}, {layout['gutters']}. "
        f"Setting: {layout['lighting']}."
    )

    # Collect characters
    char_keys = set()
    for p in panels_data:
        chars = p.get("characters", [p.get("character")]) if "characters" in p else [p.get("character")]
        for c in chars:
            name = c.get("name") if isinstance(c, dict) else c
            if name and str(name).lower() in invariants:
                char_keys.add(str(name).lower())

    char_definitions = [invariants[k] for k in sorted(char_keys)]
    char_section = "Strict Character Invariants: " + "; ".join(char_definitions) + "." if char_definitions else ""
    rule_section = "Strict Text Rule: Exactly ONE clean speech bubble per panel (no duplicate or empty bubbles)."

    panel_descriptions = []
    panel_labels = ["Panel 1 (top-left)", "Panel 2 (top-right)", "Panel 3 (bottom-left)", "Panel 4 (bottom-right)"]

    for i, p in enumerate(panels_data):
        label = panel_labels[i]
        action = p.get("action", "")
        dialogue = p.get("dialogue", None)

        panel_str = f"{label}: {action}"
        if dialogue:
            panel_str += f' Speech bubble: "{dialogue}"'
        else:
            panel_str += " No speech bubbles."
        panel_descriptions.append(panel_str)

    compiled = f"{header}\n\n{char_section}\n{rule_section}\n\n" + "\n".join(panel_descriptions)
    return compiled

def compile_storyboard_prompt(panels_data, storyboard_ref="Image 1", canon_ref="Image 2"):
    """
    Compiles a prompt specifically conditioned on a programmatic storyboard draft.
    """
    contract = load_contract()
    layout = contract["layout"]
    invariants = contract["character_invariants"]

    header = (
        f"High quality expressive cute anime chibi 4-panel manga comic strip, {layout['grid']}, {layout['aspect_ratio']} aspect ratio, "
        f"{layout['style']}, {layout['margins']}, {layout['borders']}, {layout['gutters']}. "
        f"Setting: {layout['lighting']}."
    )

    guidance = (
        f"CRITICAL COMPOSITION & LAYOUT INSTRUCTION (STORYBOARD REFERENCE):\n"
        f"- {storyboard_ref} is the mandatory rough storyboard / layout sketch.\n"
        f"- Strictly follow {storyboard_ref}'s 2x2 panel borders, camera angles/zoom levels, character stage positions (who is on left vs right vs center), and character poses.\n"
        f"- Strictly follow the speech bubble positions and bubble tail directions in {storyboard_ref} (each tail points directly towards the speaking character). Do NOT swap speech bubble positions and do NOT generate duplicate or extra speech bubbles.\n\n"
        f"CHARACTER APPEARANCE & ART STYLE REFERENCE:\n"
        f"- {canon_ref} is the official character appearance canon sheet. Render clean, detailed, expressive anime chibi art following the exact hair, eyes, clothes, and colors from {canon_ref}."
    )

    char_keys = set()
    for p in panels_data:
        chars = p.get("characters", [p.get("character")]) if "characters" in p else [p.get("character")]
        for c in chars:
            name = c.get("name") if isinstance(c, dict) else c
            if name and str(name).lower() in invariants:
                char_keys.add(str(name).lower())

    char_definitions = [invariants[k] for k in sorted(char_keys)]
    char_section = "Strict Character Invariants: " + "; ".join(char_definitions) + "." if char_definitions else ""

    panel_descriptions = []
    panel_labels = ["Panel 1 (top-left)", "Panel 2 (top-right)", "Panel 3 (bottom-left)", "Panel 4 (bottom-right)"]

    for i, p in enumerate(panels_data):
        label = panel_labels[i]
        action = p.get("action", "")
        dialogue = p.get("dialogue", None)

        panel_str = f"{label}: {action}"
        if dialogue:
            panel_str += f' Speech bubble: "{dialogue}"'
        else:
            panel_str += " No speech bubbles."
        panel_descriptions.append(panel_str)

    compiled = f"{header}\n\n{guidance}\n\n{char_section}\n\n" + "\n".join(panel_descriptions)
    return compiled

def main():
    parser = argparse.ArgumentParser(description="Generate deterministic 4-panel manga prompt from contract")
    parser.add_argument("--card", type=str, help="Path to koneta card file to inspect")
    parser.add_argument("--output", type=str, choices=["text", "json"], default="text")
    args = parser.parse_args()

    contract = load_contract()
    print("===================================================")
    print(f"  🎨 Manga Render Contract: {contract.get('profile_version')} (v{contract.get('schema_version')})")
    print("===================================================")
    print(f"Config Path: {CONFIG_PATH}")
    print(f"Candidates Output Target: {CANDIDATES_DIR}")
    print()
    print("Available Character Invariants:")
    for k in contract.get("character_invariants", {}):
        print(f"  • {k.capitalize()}")
    print()
    print("Contract is loaded and valid! Ready for deterministic compilation.")

if __name__ == "__main__":
    main()
