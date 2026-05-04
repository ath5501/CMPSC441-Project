"""
tests/test_core.py
Unit tests for non-LLM modules: DiceService, LoreDatabase, GameState.
Run with: pytest tests/
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.dice_service import DiceService
from modules.lore_database import LoreDatabase
from modules.game_state import GameState, PlayerCharacter, Quest


# ── DiceService Tests ─────────────────────────────────────────────────────────

class TestDiceService:
    def setup_method(self):
        self.dice = DiceService()

    def test_basic_roll(self):
        result = self.dice.roll(20)
        assert 1 <= result["total"] <= 20
        assert len(result["rolls"]) == 1

    def test_multiple_dice(self):
        result = self.dice.roll(6, count=3, modifier=2)
        assert result["total"] == sum(result["rolls"]) + 2
        assert len(result["rolls"]) == 3

    def test_modifier(self):
        result = self.dice.roll(6, count=1, modifier=5)
        assert result["total"] == result["rolls"][0] + 5

    def test_nat20_detection(self):
        # Monkeypatch to force a 20
        import random
        original = random.randint
        random.randint = lambda a, b: b  # always return max
        result = self.dice.roll(20)
        random.randint = original
        assert result["is_nat20"] is True

    def test_nat1_detection(self):
        import random
        original = random.randint
        random.randint = lambda a, b: a  # always return min
        result = self.dice.roll(20)
        random.randint = original
        assert result["is_nat1"] is True

    def test_invalid_die(self):
        with pytest.raises(ValueError):
            self.dice.roll(7)

    def test_parse_notation(self):
        result = self.dice.parse_and_roll("2d6+3")
        assert result["dice"] == "2d6"
        assert result["modifier"] == 3
        assert len(result["rolls"]) == 2

    def test_parse_notation_no_count(self):
        result = self.dice.parse_and_roll("d20")
        assert len(result["rolls"]) == 1

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            self.dice.parse_and_roll("not_dice")

    def test_advantage(self):
        result = self.dice.roll_with_advantage()
        assert len(result["rolls"]) == 2
        assert result["total"] >= max(result["rolls"])  # chosen + modifier(0) = max

    def test_disadvantage(self):
        result = self.dice.roll_with_disadvantage()
        assert len(result["rolls"]) == 2
        assert result["total"] <= max(result["rolls"])

    def test_skill_check_success(self):
        import random
        original = random.randint
        random.randint = lambda a, b: b
        result = self.dice.skill_check(skill_mod=0, dc=10)
        random.randint = original
        assert result["success"] is True

    def test_ability_score_generation(self):
        scores = self.dice.roll_ability_scores()
        assert set(scores.keys()) == {"strength", "dexterity", "constitution",
                                      "intelligence", "wisdom", "charisma"}
        for v in scores.values():
            assert 3 <= v <= 18

    def test_format_result(self):
        result = self.dice.roll(6)
        formatted = self.dice.format_result(result)
        assert str(result["total"]) in formatted


# ── LoreDatabase Tests ────────────────────────────────────────────────────────

class TestLoreDatabase:
    def setup_method(self):
        self.lore = LoreDatabase()

    def test_retrieve_goblin(self):
        docs = self.lore.retrieve("goblin attack nimble")
        assert any("Goblin" in d["title"] for d in docs)

    def test_retrieve_with_category(self):
        docs = self.lore.retrieve("dragon fire breath", category="monster")
        assert all(d["category"] == "monster" for d in docs)

    def test_retrieve_spell(self):
        docs = self.lore.retrieve("fireball evocation damage", category="spell")
        assert any("Fireball" in d["title"] for d in docs)

    def test_monster_lookup(self):
        doc = self.lore.monster_lookup("goblin")
        assert doc is not None
        assert "monster" == doc["category"]

    def test_spell_lookup(self):
        doc = self.lore.spell_lookup("fireball")
        assert doc is not None
        assert "spell" == doc["category"]

    def test_get_by_id(self):
        doc = self.lore.get_by_id("npc_bram")
        assert doc is not None
        assert doc["title"] == "Bram the Tavernkeeper"

    def test_get_by_id_missing(self):
        doc = self.lore.get_by_id("nonexistent_id")
        assert doc is None

    def test_add_document(self):
        self.lore.add_document("test_custom", "world", "Test Location", "A test location with dragons and magic.")
        doc = self.lore.get_by_id("test_custom")
        assert doc is not None
        assert doc["title"] == "Test Location"

    def test_format_for_prompt(self):
        docs = self.lore.retrieve("goblin")
        formatted = self.lore.format_for_prompt(docs)
        assert "LORE CONTEXT" in formatted
        assert "Goblin" in formatted

    def test_empty_query_returns_empty(self):
        docs = self.lore.retrieve("xyzzy_impossible_query_12345")
        assert docs == []


# ── GameState Tests ───────────────────────────────────────────────────────────

class TestGameState:
    def setup_method(self):
        self.state = GameState()
        self.state.player = PlayerCharacter(
            name="Aria", character_class="Wizard", race="Elf",
            hp=10, max_hp=10, armor_class=12,
        )

    def test_add_message(self):
        self.state.add_message("user", "Hello")
        assert self.state.conversation_history[-1]["content"] == "Hello"

    def test_get_history_limit(self):
        for i in range(50):
            self.state.add_message("user" if i % 2 == 0 else "assistant", f"msg {i}")
        history = self.state.get_history(max_turns=5)
        assert len(history) <= 10

    def test_npc_memory(self):
        self.state.remember_npc_interaction("Bram", "Bought ale")
        recall = self.state.recall_npc("Bram")
        assert "Bram" in recall
        assert "Bought ale" in recall

    def test_npc_no_memory(self):
        recall = self.state.recall_npc("Unknown NPC")
        assert "not met" in recall.lower()

    def test_add_quest(self):
        q = Quest("Test Quest", "Do something", ["obj1", "obj2"])
        self.state.add_quest(q)
        assert len(self.state.active_quests) == 1

    def test_complete_objective(self):
        q = Quest("Test Quest", "Do something", ["obj1", "obj2"], reward_gold=100, reward_xp=50)
        self.state.add_quest(q)
        self.state.complete_objective("Test Quest", "obj1")
        assert "obj1" in self.state.active_quests[0].completed_objectives
        assert not self.state.active_quests[0].completed

    def test_complete_quest(self):
        q = Quest("Test Quest", "Do something", ["obj1"], reward_gold=100, reward_xp=50)
        self.state.add_quest(q)
        self.state.complete_objective("Test Quest", "obj1")
        assert len(self.state.active_quests) == 0
        assert len(self.state.completed_quests) == 1
        assert self.state.player.gold == 150  # started with 50

    def test_enter_room(self):
        self.state.enter_room("vault", "A dark vault.")
        assert self.state.current_room == "vault"
        assert "vault" in self.state.explored_rooms

    def test_save_creates_file(self, tmp_path):
        save_path = str(tmp_path / "test_save.json")
        self.state.save(save_path)
        import os
        assert os.path.exists(save_path)

    def test_to_dict(self):
        data = self.state.to_dict()
        assert "player" in data
        assert data["player"]["name"] == "Aria"
