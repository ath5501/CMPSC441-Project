"""
game_state.py
Manages all persistent game state: player, inventory, quests, explored rooms.
"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class PlayerCharacter:
    name: str
    character_class: str
    race: str
    level: int = 1
    hp: int = 20
    max_hp: int = 20
    armor_class: int = 10
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    inventory: list = field(default_factory=list)
    gold: int = 50
    xp: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    def stat_block(self) -> str:
        return (
            f"**{self.name}** | {self.race} {self.character_class} (Lv.{self.level})\n"
            f"HP: {self.hp}/{self.max_hp} | AC: {self.armor_class} | Gold: {self.gold}g\n"
            f"STR:{self.strength} DEX:{self.dexterity} CON:{self.constitution} "
            f"INT:{self.intelligence} WIS:{self.wisdom} CHA:{self.charisma}"
        )


@dataclass
class Quest:
    title: str
    description: str
    objectives: list[str]
    completed_objectives: list[str] = field(default_factory=list)
    completed: bool = False
    reward_gold: int = 0
    reward_xp: int = 0

    def progress_summary(self) -> str:
        done = len(self.completed_objectives)
        total = len(self.objectives)
        status = "COMPLETE" if self.completed else f"{done}/{total} objectives"
        return f"**{self.title}** [{status}]\n{self.description}"


class GameState:
    """Central game state container passed between all modules."""

    def __init__(self):
        self.player: Optional[PlayerCharacter] = None
        self.current_room: str = "entrance"
        self.explored_rooms: list[str] = []
        self.room_history: list[dict] = []          # {room, description}
        self.conversation_history: list[dict] = []  # LLM message history
        self.active_quests: list[Quest] = []
        self.completed_quests: list[Quest] = []
        self.npc_memory: dict[str, list[str]] = {}  # npc_name -> list[interactions]
        self.combat_active: bool = False
        self.current_enemy: Optional[dict] = None
        self.session_log: list[str] = []

    # ── conversation history helpers ──────────────────────────────────────────

    def add_message(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})

    def get_history(self, max_turns: int = 20) -> list[dict]:
        """Return recent conversation history to keep context window manageable."""
        return self.conversation_history[-max_turns * 2:]

    # ── NPC memory ────────────────────────────────────────────────────────────

    def remember_npc_interaction(self, npc_name: str, summary: str):
        if npc_name not in self.npc_memory:
            self.npc_memory[npc_name] = []
        self.npc_memory[npc_name].append(summary)

    def recall_npc(self, npc_name: str) -> str:
        interactions = self.npc_memory.get(npc_name, [])
        if not interactions:
            return f"You have not met {npc_name} before."
        return f"Past interactions with {npc_name}: " + "; ".join(interactions[-3:])

    # ── quest helpers ─────────────────────────────────────────────────────────

    def add_quest(self, quest: Quest):
        self.active_quests.append(quest)

    def complete_objective(self, quest_title: str, objective: str):
        for q in self.active_quests:
            if q.title == quest_title and objective in q.objectives:
                q.completed_objectives.append(objective)
                if set(q.objectives) == set(q.completed_objectives):
                    q.completed = True
                    self.active_quests.remove(q)
                    self.completed_quests.append(q)
                    if self.player:
                        self.player.gold += q.reward_gold
                        self.player.xp += q.reward_xp
                break

    def quest_summary(self) -> str:
        if not self.active_quests and not self.completed_quests:
            return "No quests yet."
        lines = []
        for q in self.active_quests:
            lines.append(q.progress_summary())
        for q in self.completed_quests:
            lines.append(f"~~{q.title}~~")
        return "\n".join(lines)

    # ── room tracking ─────────────────────────────────────────────────────────

    def enter_room(self, room_id: str, description: str):
        self.current_room = room_id
        if room_id not in self.explored_rooms:
            self.explored_rooms.append(room_id)
        self.room_history.append({"room": room_id, "description": description})

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "player": self.player.to_dict() if self.player else None,
            "current_room": self.current_room,
            "explored_rooms": self.explored_rooms,
            "active_quests": [q.__dict__ for q in self.active_quests],
            "completed_quests": [q.__dict__ for q in self.completed_quests],
            "npc_memory": self.npc_memory,
        }

    def save(self, path: str = "savegame.json"):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"[GameState] Saved to {path}")

    def log(self, msg: str):
        self.session_log.append(msg)
