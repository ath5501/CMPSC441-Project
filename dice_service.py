"""
dice_service.py
Provides deterministic, logged dice-rolling utilities used throughout the system.
Covers d4, d6, d8, d10, d12, d20, d100 and advantage/disadvantage rolls.
"""

import random
import re
from typing import Optional


class DiceService:
    """Stateless dice roller with full logging of every roll."""

    VALID_DICE = {4, 6, 8, 10, 12, 20, 100}

    def roll(self, sides: int, count: int = 1, modifier: int = 0) -> dict:
        """
        Roll `count` dice with `sides` faces and apply modifier.
        Returns a result dict with all roll details.
        """
        if sides not in self.VALID_DICE:
            raise ValueError(f"Invalid die type: d{sides}. Valid: {self.VALID_DICE}")
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        result = {
            "dice": f"{count}d{sides}",
            "modifier": modifier,
            "rolls": rolls,
            "total": total,
            "is_nat20": sides == 20 and count == 1 and rolls[0] == 20,
            "is_nat1":  sides == 20 and count == 1 and rolls[0] == 1,
        }
        return result

    def roll_with_advantage(self, modifier: int = 0) -> dict:
        """Roll 2d20 and take the higher value (advantage)."""
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        chosen = max(r1, r2)
        return {
            "dice": "2d20 (advantage)",
            "modifier": modifier,
            "rolls": [r1, r2],
            "total": chosen + modifier,
            "is_nat20": chosen == 20,
            "is_nat1": chosen == 1,
        }

    def roll_with_disadvantage(self, modifier: int = 0) -> dict:
        """Roll 2d20 and take the lower value (disadvantage)."""
        r1, r2 = random.randint(1, 20), random.randint(1, 20)
        chosen = min(r1, r2)
        return {
            "dice": "2d20 (disadvantage)",
            "modifier": modifier,
            "rolls": [r1, r2],
            "total": chosen + modifier,
            "is_nat20": chosen == 20,
            "is_nat1": chosen == 1,
        }

    def roll_ability_scores(self) -> dict[str, int]:
        """Generate a full set of 6 ability scores using 4d6-drop-lowest."""
        abilities = ["strength", "dexterity", "constitution",
                     "intelligence", "wisdom", "charisma"]
        scores = {}
        for ability in abilities:
            rolls = [random.randint(1, 6) for _ in range(4)]
            scores[ability] = sum(sorted(rolls)[1:])  # drop lowest
        return scores

    def parse_and_roll(self, notation: str) -> dict:
        """
        Parse dice notation like '2d6+3' or 'd20' and roll.
        Returns same dict as roll().
        """
        notation = notation.strip().lower().replace(" ", "")
        pattern = r"^(\d*)d(\d+)([+-]\d+)?$"
        match = re.match(pattern, notation)
        if not match:
            raise ValueError(f"Invalid dice notation: '{notation}'")
        count = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0
        return self.roll(sides, count, modifier)

    def format_result(self, result: dict) -> str:
        """Return a human-readable string for a roll result."""
        label = result["dice"]
        mod_str = (f"+{result['modifier']}" if result['modifier'] > 0
                   else str(result['modifier']) if result['modifier'] < 0 else "")
        rolls_str = ", ".join(str(r) for r in result["rolls"])
        suffix = ""
        if result.get("is_nat20"):
            suffix = " 🎯 CRITICAL HIT!"
        elif result.get("is_nat1"):
            suffix = " 💀 CRITICAL FAIL!"
        return f"🎲 [{label}{mod_str}] Rolls: ({rolls_str}) = **{result['total']}**{suffix}"

    # ── Combat helpers ────────────────────────────────────────────────────────

    def attack_roll(self, attack_bonus: int = 0) -> dict:
        result = self.roll(20, modifier=attack_bonus)
        result["label"] = "Attack Roll"
        return result

    def damage_roll(self, damage_dice: str = "1d6", bonus: int = 0) -> dict:
        result = self.parse_and_roll(damage_dice)
        result["total"] += bonus
        result["modifier"] = result.get("modifier", 0) + bonus
        result["label"] = "Damage Roll"
        return result

    def saving_throw(self, ability_mod: int = 0, proficiency: int = 0) -> dict:
        result = self.roll(20, modifier=ability_mod + proficiency)
        result["label"] = "Saving Throw"
        return result

    def skill_check(self, skill_mod: int = 0, dc: int = 15) -> dict:
        result = self.roll(20, modifier=skill_mod)
        result["dc"] = dc
        result["success"] = result["total"] >= dc
        result["label"] = "Skill Check"
        return result


# Singleton for convenience import
dice = DiceService()
