"""
combat.py
Handles combat resolution: initiative, attack rolls, damage, enemy AI, ambushes.
Integrates with DiceService, LLMClient, LoreDatabase, and GameState.
"""

from __future__ import annotations
from typing import Optional
from modules.dice_service import DiceService
from modules.game_state import GameState
from modules.lore_database import LoreDatabase
from modules.llm_client import LLMClient


class CombatManager:
    """
    Manages a single combat encounter from start to finish.
    Tracks initiative order, HP, turn state, and generates narration.
    """

    def __init__(
        self,
        state: GameState,
        dice: DiceService,
        lore: LoreDatabase,
        llm: LLMClient,
    ):
        self.state = state
        self.dice = dice
        self.lore = lore
        self.llm = llm
        self.initiative_order: list[dict] = []
        self.round_number: int = 0

    # ── Combat Setup ──────────────────────────────────────────────────────────

    def start_encounter(self, enemy_name: str, ambush: bool = False) -> str:
        """
        Initialize a combat encounter.
        If ambush=True, enemies act first regardless of initiative.
        Returns the opening narration.
        """
        # Look up monster stats from lore database (RAG)
        monster_doc = self.lore.monster_lookup(enemy_name)
        if monster_doc:
            # Parse basic stats from lore text
            enemy = self._parse_monster(monster_doc, enemy_name)
        else:
            # Fallback generic enemy
            enemy = {
                "name": enemy_name,
                "hp": 15, "max_hp": 15,
                "ac": 12,
                "attack_bonus": 3,
                "damage_dice": "1d6",
                "damage_bonus": 1,
            }

        self.state.current_enemy = enemy
        self.state.combat_active = True

        # Roll initiative
        player = self.state.player
        player_init = self.dice.roll(20, modifier=self._stat_mod(player.dexterity))["total"]
        enemy_init = self.dice.roll(20, modifier=2)["total"]

        if ambush:
            # Enemies get surprise round
            self.initiative_order = [enemy, {"name": player.name, "is_player": True, "initiative": player_init}]
            opening = f"⚠️ **AMBUSH!** The {enemy_name} strikes before you can react!\n\n"
        elif player_init >= enemy_init:
            self.initiative_order = [
                {"name": player.name, "is_player": True, "initiative": player_init},
                {**enemy, "initiative": enemy_init},
            ]
            opening = f"You draw your weapon first! (Initiative: {player_init} vs {enemy_init})\n\n"
        else:
            self.initiative_order = [
                {**enemy, "initiative": enemy_init},
                {"name": player.name, "is_player": True, "initiative": player_init},
            ]
            opening = f"The {enemy_name} moves first! (Initiative: {enemy_init} vs {player_init})\n\n"

        self.round_number = 1

        # Generate dramatic encounter narration
        lore_context = self.lore.format_for_prompt([monster_doc] if monster_doc else [])
        narration = self.llm.narrate_room(
            f"combat start vs {enemy_name}",
            f"Player {player.name} faces a {enemy_name} in combat.",
            lore_context,
        )
        return opening + narration

    def _parse_monster(self, doc: dict, name: str) -> dict:
        """Extract key stats from lore document text."""
        content = doc["content"]
        # Simple regex extraction from standardized lore format
        import re
        hp_match = re.search(r"HP: (\d+)", content)
        ac_match = re.search(r"AC (\d+)", content)
        atk_match = re.search(r"\+(\d+) to hit", content)
        dmg_match = re.search(r"(\d+d\d+)(?:\+(\d+))? (?:slashing|piercing|bludgeoning|fire|cold)", content)

        return {
            "name": name,
            "hp": int(hp_match.group(1)) if hp_match else 15,
            "max_hp": int(hp_match.group(1)) if hp_match else 15,
            "ac": int(ac_match.group(1)) if ac_match else 12,
            "attack_bonus": int(atk_match.group(1)) if atk_match else 3,
            "damage_dice": dmg_match.group(1) if dmg_match else "1d6",
            "damage_bonus": int(dmg_match.group(2)) if (dmg_match and dmg_match.group(2)) else 1,
        }

    # ── Player Actions ────────────────────────────────────────────────────────

    def player_attack(self, weapon: str = "longsword", damage_dice: str = "1d8") -> str:
        """Process a player attack action."""
        player = self.state.player
        enemy = self.state.current_enemy
        if not enemy:
            return "No active combat."

        str_mod = self._stat_mod(player.strength)
        proficiency = 2 + (player.level - 1) // 4

        attack = self.dice.attack_roll(attack_bonus=str_mod + proficiency)
        hit = attack["total"] >= enemy["ac"] or attack.get("is_nat20")
        miss = attack.get("is_nat1") or (not hit)

        damage_dealt = 0
        if not miss:
            dmg = self.dice.damage_roll(damage_dice, bonus=str_mod)
            if attack.get("is_nat20"):
                # Critical: double the dice
                dmg2 = self.dice.damage_roll(damage_dice, bonus=0)
                dmg["total"] += dmg2["total"]
            damage_dealt = dmg["total"]
            enemy["hp"] = max(0, enemy["hp"] - damage_dealt)

        narration = self.llm.narrate_combat_round(
            attacker=player.name,
            defender=enemy["name"],
            action=f"attacks with {weapon}",
            roll_result=attack,
            hit=not miss,
            damage=damage_dealt if not miss else None,
        )

        result = f"🗡️ **{player.name} attacks with {weapon}**\n"
        result += self.dice.format_result(attack) + "\n"
        result += narration + "\n"

        if enemy["hp"] <= 0:
            result += self._enemy_defeated()
        else:
            result += f"\n*{enemy['name']} HP: {enemy['hp']}/{enemy['max_hp']}*"

        return result

    def enemy_turn(self) -> str:
        """Process the enemy's turn using AI-planned strategy."""
        enemy = self.state.current_enemy
        player = self.state.player
        if not enemy or not self.state.combat_active:
            return ""

        # Use chain-of-thought for strategy if enemy HP is below half
        if enemy["hp"] < enemy["max_hp"] // 2:
            situation = (
                f"Enemy: {enemy['name']} (HP: {enemy['hp']}/{enemy['max_hp']}), "
                f"Player: {player.name} (HP: {player.hp}/{player.max_hp}). "
                f"The enemy is injured. Should they attack, retreat, or attempt something special?"
            )
            strategy = self.llm.generate_with_chain_of_thought(situation)
            self.state.log(f"[Enemy Strategy] {strategy}")

        # Resolve the attack mechanically
        attack = self.dice.attack_roll(attack_bonus=enemy["attack_bonus"])
        hit = attack["total"] >= player.armor_class or attack.get("is_nat20")
        miss = attack.get("is_nat1") or not hit

        damage_dealt = 0
        if not miss:
            dmg = self.dice.damage_roll(enemy["damage_dice"], bonus=enemy["damage_bonus"])
            if attack.get("is_nat20"):
                dmg2 = self.dice.damage_roll(enemy["damage_dice"], bonus=0)
                dmg["total"] += dmg2["total"]
            damage_dealt = dmg["total"]
            player.hp = max(0, player.hp - damage_dealt)

        narration = self.llm.narrate_combat_round(
            attacker=enemy["name"],
            defender=player.name,
            action="attacks",
            roll_result=attack,
            hit=not miss,
            damage=damage_dealt if not miss else None,
        )

        result = f"\n⚔️ **{enemy['name']}'s turn**\n"
        result += self.dice.format_result(attack) + "\n"
        result += narration + "\n"

        if player.hp <= 0:
            result += "\n💀 **You have fallen unconscious!** The adventure ends here... or does it?"
            self.state.combat_active = False
        else:
            result += f"\n*Your HP: {player.hp}/{player.max_hp}*"

        return result

    def plan_ambush(self, num_enemies: int, terrain: str) -> str:
        """
        Use chain-of-thought reasoning to plan a coordinated enemy ambush.
        """
        situation = (
            f"A group of {num_enemies} goblins is planning an ambush. "
            f"Terrain: {terrain}. "
            f"Target: {self.state.player.name}, a level {self.state.player.level} "
            f"{self.state.player.character_class}. "
            "Plan a coordinated ambush with flanking, archer positions, and a trigger signal."
        )
        plan = self.llm.generate_with_chain_of_thought(situation, system_role="enemy_strategist")
        return f"🗺️ **Enemy Ambush Plan**\n\n{plan}"

    def _enemy_defeated(self) -> str:
        enemy = self.state.current_enemy
        xp_reward = 50  # base
        gold_reward = self.dice.roll(6, count=2)["total"]
        self.state.player.xp += xp_reward
        self.state.player.gold += gold_reward
        self.state.combat_active = False
        self.state.current_enemy = None
        return (
            f"\n\n✅ **{enemy['name']} defeated!**\n"
            f"Gained: {xp_reward} XP, {gold_reward} gold\n"
            f"Total XP: {self.state.player.xp} | Gold: {self.state.player.gold}g"
        )

    @staticmethod
    def _stat_mod(score: int) -> int:
        return (score - 10) // 2
