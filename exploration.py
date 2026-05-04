"""
exploration.py
Dungeon exploration: room generation, trap resolution, puzzle solving.
Implements multi-step puzzle logic (chain-of-thought hints).
"""

from modules.game_state import GameState
from modules.lore_database import LoreDatabase
from modules.llm_client import LLMClient
from modules.dice_service import DiceService


# ── Dungeon Map Definition ────────────────────────────────────────────────────

DUNGEON_MAP = {
    "entrance": {
        "name": "Hall of Echoes",
        "description_hint": "a grand entrance hall with cracked stone pillars and flickering torchlight",
        "exits": ["vault", "ritual_chamber"],
        "has_trap": False,
        "has_treasure": False,
        "has_puzzle": False,
        "encounter": None,
    },
    "vault": {
        "name": "Vault of Shadows",
        "description_hint": "a treasure vault with shattered display cases, most already looted",
        "exits": ["entrance", "throne"],
        "has_trap": True,
        "trap_type": "pressure_plate",
        "trap_dc": 14,
        "has_treasure": True,
        "treasure": {"gold": 75, "item": "Potion of Greater Healing"},
        "has_puzzle": False,
        "encounter": "skeleton",
    },
    "ritual_chamber": {
        "name": "Chamber of Binding",
        "description_hint": "a circular ritual room with arcane runes carved into the floor",
        "exits": ["entrance", "throne"],
        "has_trap": False,
        "has_treasure": False,
        "has_puzzle": True,
        "puzzle_id": "binding_seal",
        "encounter": None,
    },
    "throne": {
        "name": "Throne of Stone",
        "description_hint": "a massive throne room with an obsidian throne and the faint glow of an artifact",
        "exits": ["vault", "ritual_chamber"],
        "has_trap": True,
        "trap_type": "magical_ward",
        "trap_dc": 17,
        "has_treasure": True,
        "treasure": {"gold": 200, "item": "Shard of the Shattered Crown"},
        "has_puzzle": False,
        "encounter": "troll",
    },
}

PUZZLES = {
    "binding_seal": {
        "title": "The Binding Seal",
        "description": (
            "Three concentric rings of arcane runes glow on the floor. "
            "Each ring rotates independently. Ancient script reads: "
            "'The Moon yields to the Sun, Fire submits to Water, Stone bows to Wind.' "
            "Three stone levers on the wall correspond to the three rings."
        ),
        "solution": "Pull levers in order: Wind (1), Water (2), Sun (3)",
        "hints": [
            "The outer ring shows celestial symbols — moon and sun face each other.",
            "The middle ring has elemental symbols arranged in a cycle.",
            "The inner ring's symbols match the levers on the wall.",
        ],
        "attempts": 0,
        "solved": False,
    }
}


class ExplorationManager:
    """Manages dungeon navigation, traps, puzzles, and room discovery."""

    def __init__(self, state: GameState, lore: LoreDatabase, llm: LLMClient, dice: DiceService):
        self.state = state
        self.lore = lore
        self.llm = llm
        self.dice = dice
        self.puzzles = {k: dict(v) for k, v in PUZZLES.items()}  # mutable copy

    def enter_room(self, room_id: str) -> str:
        """Move player to a room and generate its description."""
        room = DUNGEON_MAP.get(room_id)
        if not room:
            return f"There is no path to '{room_id}'."

        # Check if this room has been visited
        first_visit = room_id not in self.state.explored_rooms

        # RAG: pull dungeon lore for context
        lore_docs = self.lore.retrieve(room["name"], top_k=2)
        lore_context = self.lore.format_for_prompt(lore_docs)

        # Generate room description
        description = self.llm.narrate_room(
            room_id=room["name"],
            context=room["description_hint"] + (" (first visit — reveal all details)" if first_visit else " (revisit — be brief)"),
            lore_context=lore_context,
        )

        self.state.enter_room(room_id, description)

        result = f"\n**{room['name']}**\n\n{description}\n"

        # List exits
        exits = ", ".join(DUNGEON_MAP[e]["name"] for e in room["exits"] if e in DUNGEON_MAP)
        result += f"\n*Exits: {exits}*"

        # Trigger trap check on first visit
        if first_visit and room.get("has_trap"):
            result += "\n\n" + self._trap_check(room)

        # Note puzzle
        if first_visit and room.get("has_puzzle"):
            puzzle_id = room.get("puzzle_id")
            if puzzle_id and not self.puzzles.get(puzzle_id, {}).get("solved"):
                result += "\n\n" + self._introduce_puzzle(puzzle_id)

        return result

    def _trap_check(self, room: dict) -> str:
        """Resolve a trap using Perception + Investigation checks."""
        player = self.state.player
        wis_mod = (player.wisdom - 10) // 2
        dc = room.get("trap_dc", 14)

        perception = self.dice.skill_check(skill_mod=wis_mod, dc=dc)
        trap_type = room.get("trap_type", "hidden trap")

        if perception["success"]:
            return (
                f"*Trap Detected!*\n"
                f"{self.dice.format_result(perception)}\n"
                f"Your sharp eyes spot a {trap_type.replace('_', ' ')} just in time. You carefully avoid it."
            )
        else:
            # Trigger trap damage
            damage = self.dice.roll(6, count=2)["total"]
            player.hp = max(0, player.hp - damage)
            return (
                f"*Trap Triggered!*\n"
                f"{self.dice.format_result(perception)}\n"
                f"The {trap_type.replace('_', ' ')} activates! You take {damage} damage.\n"
                f"*Your HP: {player.hp}/{player.max_hp}*"
            )

    def _introduce_puzzle(self, puzzle_id: str) -> str:
        puzzle = self.puzzles.get(puzzle_id)
        if not puzzle:
            return ""
        return f"**Puzzle: {puzzle['title']}**\n\n{puzzle['description']}"

    def attempt_puzzle(self, puzzle_id: str, player_answer: str) -> str:
        """
        Player attempts to solve a puzzle.
        Multi-step: incorrect attempts unlock progressive hints (chain-of-thought style).
        """
        puzzle = self.puzzles.get(puzzle_id)
        if not puzzle:
            return f"No puzzle named '{puzzle_id}' found."
        if puzzle["solved"]:
            return "This puzzle has already been solved."

        solution = puzzle["solution"].lower()
        attempt = player_answer.lower()

        if any(key in attempt for key in ["wind", "water", "sun"]) and \
           all(key in attempt for key in ["wind", "water", "sun"]):
            # Correct!
            puzzle["solved"] = True
            reward_narration = self.llm.generate(
                user_prompt=f"The player solves The Binding Seal puzzle by pulling levers in order: Wind, Water, Sun. "
                            "Describe the dramatic magical effect as the seal breaks open. 3-4 sentences.",
                system_role="dungeon_master",
                scenario="narrative",
            )
            return f"**Puzzle Solved!**\n\n{reward_narration}"
        else:
            puzzle["attempts"] += 1
            hint_idx = min(puzzle["attempts"] - 1, len(puzzle["hints"]) - 1)
            hint = puzzle["hints"][hint_idx]

            cot_hint = self.llm.generate(
                user_prompt=(
                    f"The player attempted: '{player_answer}' for The Binding Seal puzzle. "
                    f"This is attempt #{puzzle['attempts']}. "
                    f"Give them this hint subtly in character: '{hint}' "
                    "Do not reveal the solution directly. 2-3 sentences."
                ),
                system_role="puzzle_master",
                scenario="narrative",
            )
            return f"*The runes flicker but don't respond...*\n\n{cot_hint}"

    def check_for_treasure(self, room_id: str) -> str:
        """Search a room for treasure."""
        room = DUNGEON_MAP.get(room_id)
        if not room or not room.get("has_treasure"):
            return "You search thoroughly but find nothing of value."

        player = self.state.player
        int_mod = (player.intelligence - 10) // 2
        search = self.dice.skill_check(skill_mod=int_mod, dc=12)

        if search["success"]:
            treasure = room.get("treasure", {})
            gold = treasure.get("gold", 0)
            item = treasure.get("item", "")
            player.gold += gold
            if item:
                player.inventory.append(item)
            room["has_treasure"] = False  # Mark as looted
            return (
                f"*Search Check:* {self.dice.format_result(search)}\n"
                f"You discover hidden treasure! +{gold} gold" +
                (f" and a **{item}**!" if item else "!")
            )
        return f"*Search Check:* {self.dice.format_result(search)}\nYou find nothing hidden here."
