"""
llm_client.py
Wrapper around the Ollama local LLM API.
Handles all model calls with configurable parameters and role-based prompts.

Ollama must be running locally: https://ollama.com
Default model: llama3 — override via OLLAMA_MODEL env var.
Default host:  http://localhost:11434 — override via OLLAMA_HOST env var.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional

# ── Model Configuration ───────────────────────────────────────────────────────

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
OLLAMA_HOST   = os.environ.get("OLLAMA_HOST",  "http://localhost:11434")

# Parameter rationale:
# - NARRATIVE: temperature=0.9 for creative, varied storytelling
# - COMBAT: temperature=0.6 for reliable mechanical descriptions with some flair
# - PLANNING: temperature=0.3 for logical, coherent multi-step enemy strategy
# - DIALOGUE: temperature=0.8 for natural NPC conversation with personality
# - STRICT: temperature=0.1 for deterministic rules lookups

SCENARIO_PARAMS = {
    "narrative":  {"temperature": 0.9, "num_predict": 600},
    "combat":     {"temperature": 0.6, "num_predict": 400},
    "planning":   {"temperature": 0.3, "num_predict": 500},
    "dialogue":   {"temperature": 0.8, "num_predict": 400},
    "strict":     {"temperature": 0.1, "num_predict": 300},
}

# ── System Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "dungeon_master": """You are an expert Dungeon Master narrating an immersive D&D 5e adventure
set in the Realm of Valdris. Your role:
- Narrate in vivid, second-person prose ("You see...", "You hear...")
- Maintain consistent world lore and NPC personalities
- Respect game mechanics (HP, AC, dice rolls) provided to you
- When a dice result is given, weave it naturally into narration
- Keep responses focused and under 200 words unless deep narration is requested
- Never break character unless the user asks an out-of-game question
- Track consequences: actions have lasting effects on the world""",

    "combat_narrator": """You are a combat narrator for a D&D 5e battle.
Given dice roll results and combatant stats, narrate the combat round dramatically.
Rules to follow:
- Natural 20 = spectacular critical hit with vivid description
- Natural 1 = humorous or dramatic fumble
- Always state the mechanical outcome (damage dealt, HP remaining) after narration
- Keep each round description to 3-5 sentences
- Reference the specific weapons, spells, or abilities used""",

    "npc_actor": """You are roleplaying an NPC in a D&D setting. Stay in character completely.
Use the NPC's background, personality, and relationship to the player when responding.
- Speak in first person with the NPC's voice and vocabulary
- React to player actions based on prior interactions (provided in context)
- If bargaining, make realistic counter-offers based on NPC motivation
- Do not reveal secret information unless persuasion/deception DCs are met""",

    "enemy_strategist": """You are a tactical AI planning enemy strategy in D&D combat.
Think step-by-step (chain-of-thought) before deciding:
1. Assess the battlefield (enemy positions, cover, terrain)
2. Evaluate threats (who is highest damage dealer, who is weakest)
3. Consider monster abilities and limitations
4. Formulate a 2-3 step tactical plan
5. State the final action clearly

Output format:
REASONING: [your tactical analysis]
PLAN: [numbered action steps]
ACTION: [immediate action this turn]""",

    "puzzle_master": """You are presenting a multi-stage dungeon puzzle to players.
For each puzzle:
- Describe the mechanism and visual elements vividly
- Provide cryptic hints if asked (not direct answers)
- Track which clues have been given
- Reveal solutions only when players demonstrate understanding
- Escalate tension if they struggle (rumbling sounds, time pressure)""",
}


class LLMClient:
    """
    Ollama API client with scenario-aware parameter selection.
    Uses the /api/chat endpoint with OpenAI-compatible message format.
    No external Python packages required beyond the standard library.
    """

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        self.model = model or DEFAULT_MODEL
        self.host  = (host or OLLAMA_HOST).rstrip("/")
        self._verify_connection()

    def _verify_connection(self):
        """Check Ollama is reachable and the chosen model is available."""
        try:
            req = urllib.request.urlopen(f"{self.host}/api/tags", timeout=5)
            data = json.loads(req.read())
            available = [m["name"].split(":")[0] for m in data.get("models", [])]
            base = self.model.split(":")[0]
            if base not in available:
                print(
                    f"[WARNING] Model '{self.model}' not found in Ollama. "
                    f"Available: {available or ['(none)']}\n"
                    f"Pull it with: ollama pull {self.model}"
                )
        except Exception as e:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.host}. "
                "Is Ollama running? Start it with: ollama serve"
            ) from e

    def _chat(self, messages: list[dict], params: dict) -> str:
        """
        POST to /api/chat (non-streaming).
        messages format: [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        payload = json.dumps({
            "model":   self.model,
            "messages": messages,
            "stream":  False,
            "options": {
                "temperature": params["temperature"],
                "num_predict": params["num_predict"],
            },
        }).encode()

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data["message"]["content"].strip()
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    def generate(
        self,
        user_prompt: str,
        system_role: str = "dungeon_master",
        scenario: str = "narrative",
        conversation_history: Optional[list[dict]] = None,
        extra_system: str = "",
    ) -> str:
        """
        Generate a response from the local Ollama model.

        Args:
            user_prompt: The current user message.
            system_role: Key into SYSTEM_PROMPTS dict.
            scenario: Key into SCENARIO_PARAMS for temperature/num_predict config.
            conversation_history: Prior messages for multi-turn context.
            extra_system: Additional context appended to system prompt (e.g., RAG lore).

        Returns:
            The assistant's text response.
        """
        params = SCENARIO_PARAMS.get(scenario, SCENARIO_PARAMS["narrative"])
        system = SYSTEM_PROMPTS.get(system_role, SYSTEM_PROMPTS["dungeon_master"])
        if extra_system:
            system = system + "\n\n" + extra_system

        # Build message list: system first, then history, then current user turn
        messages: list[dict] = [{"role": "system", "content": system}]
        messages.extend(conversation_history or [])
        messages.append({"role": "user", "content": user_prompt})

        return self._chat(messages, params)

    def generate_with_chain_of_thought(
        self,
        situation: str,
        system_role: str = "enemy_strategist",
    ) -> str:
        """
        Force multi-step reasoning (chain-of-thought) for planning scenarios.
        Uses low temperature for coherent logic.
        """
        cot_prompt = (
            f"Situation: {situation}\n\n"
            "Think through this step by step before giving your final answer. "
            "Show your reasoning process clearly."
        )
        return self.generate(
            user_prompt=cot_prompt,
            system_role=system_role,
            scenario="planning",
        )

    def narrate_room(self, room_id: str, context: str, lore_context: str = "") -> str:
        """Generate a vivid room description with optional lore injection."""
        prompt = (
            f"The player enters: {room_id}\n"
            f"Context: {context}\n"
            "Describe this location in 3-4 atmospheric sentences. "
            "Note any exits, items of interest, or threats visible."
        )
        return self.generate(
            user_prompt=prompt,
            system_role="dungeon_master",
            scenario="narrative",
            extra_system=lore_context,
        )

    def narrate_combat_round(
        self,
        attacker: str,
        defender: str,
        action: str,
        roll_result: dict,
        hit: bool,
        damage: Optional[int] = None,
    ) -> str:
        """Generate combat narration given mechanical results."""
        prompt = (
            f"Attacker: {attacker}\n"
            f"Defender: {defender}\n"
            f"Action: {action}\n"
            f"Roll: {roll_result['total']} (rolls: {roll_result['rolls']})\n"
            f"{'HIT' if hit else 'MISS'}"
            + (f" — {damage} damage dealt" if hit and damage else "")
            + ("\n⚡ CRITICAL HIT!" if roll_result.get('is_nat20') else "")
            + ("\n💀 CRITICAL FAIL!" if roll_result.get('is_nat1') else "")
        )
        return self.generate(
            user_prompt=prompt,
            system_role="combat_narrator",
            scenario="combat",
        )

    def generate_npc_dialogue(
        self,
        npc_name: str,
        npc_profile: str,
        player_message: str,
        relationship_history: str = "",
        conversation_history: Optional[list[dict]] = None,
    ) -> str:
        """Generate in-character NPC dialogue."""
        extra = f"NPC Profile:\n{npc_profile}"
        if relationship_history:
            extra += f"\n\nRelationship History:\n{relationship_history}"
        prompt = f'The player says to {npc_name}: "{player_message}"'
        return self.generate(
            user_prompt=prompt,
            system_role="npc_actor",
            scenario="dialogue",
            conversation_history=conversation_history,
            extra_system=extra,
        )
