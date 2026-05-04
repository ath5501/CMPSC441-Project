"""
character.py
Character creation module. Guides player through building their character.
"""

from modules.game_state import GameState, PlayerCharacter
from modules.dice_service import DiceService


CLASS_HP = {
    "Barbarian": 12, "Fighter": 10, "Paladin": 10, "Ranger": 10,
    "Bard": 8, "Cleric": 8, "Druid": 8, "Monk": 8, "Rogue": 8, "Warlock": 8,
    "Sorcerer": 6, "Wizard": 6,
}

RACE_BONUSES = {
    "Human":    {"strength": 1, "dexterity": 1, "constitution": 1, "intelligence": 1, "wisdom": 1, "charisma": 1},
    "Elf":      {"dexterity": 2, "intelligence": 1},
    "Dwarf":    {"constitution": 2, "wisdom": 1},
    "Halfling": {"dexterity": 2, "charisma": 1},
    "Half-Orc": {"strength": 2, "constitution": 1},
    "Tiefling": {"charisma": 2, "intelligence": 1},
}

STARTING_GEAR = {
    "Fighter":  ["Longsword", "Shield", "Chain Mail", "5x Javelin"],
    "Wizard":   ["Quarterstaff", "Spellbook", "Arcane Focus", "Dagger"],
    "Rogue":    ["Shortsword", "Shortbow", "Leather Armor", "Thieves' Tools"],
    "Cleric":   ["Mace", "Scale Mail", "Holy Symbol", "Shield"],
    "Ranger":   ["Longbow", "Shortsword x2", "Leather Armor", "Explorer's Pack"],
    "Barbarian":["Greataxe", "2x Handaxe", "Explorer's Pack"],
}


def create_character(state: GameState, dice: DiceService) -> PlayerCharacter:
    """
    Interactive character creation via CLI prompts.
    Rolls ability scores using 4d6-drop-lowest method.
    """
    print("\n" + "="*50)
    print("CHARACTER CREATION")
    print("="*50)

    name = input("\nEnter your character's name: ").strip() or "Hero"

    print("\nAvailable races:", ", ".join(RACE_BONUSES.keys()))
    race = input("Choose your race: ").strip().title()
    if race not in RACE_BONUSES:
        race = "Human"
        print(f"Unknown race — defaulting to Human.")

    print("\nAvailable classes:", ", ".join(CLASS_HP.keys()))
    char_class = input("Choose your class: ").strip().title()
    if char_class not in CLASS_HP:
        char_class = "Fighter"
        print(f"Unknown class — defaulting to Fighter.")

    print("\nRolling ability scores (4d6 drop lowest)...")
    scores = dice.roll_ability_scores()

    # Apply racial bonuses
    bonuses = RACE_BONUSES.get(race, {})
    for stat, bonus in bonuses.items():
        scores[stat] = scores.get(stat, 10) + bonus

    print("\nYour ability scores:")
    for stat, val in scores.items():
        mod = (val - 10) // 2
        mod_str = f"+{mod}" if mod >= 0 else str(mod)
        print(f"  {stat.capitalize():15} {val:2d}  ({mod_str})")

    # Build character
    hit_die = CLASS_HP.get(char_class, 8)
    con_mod = (scores.get("constitution", 10) - 10) // 2
    max_hp = hit_die + con_mod

    player = PlayerCharacter(
        name=name,
        character_class=char_class,
        race=race,
        hp=max_hp,
        max_hp=max_hp,
        armor_class=10 + (scores.get("dexterity", 10) - 10) // 2,
        strength=scores.get("strength", 10),
        dexterity=scores.get("dexterity", 10),
        constitution=scores.get("constitution", 10),
        intelligence=scores.get("intelligence", 10),
        wisdom=scores.get("wisdom", 10),
        charisma=scores.get("charisma", 10),
        inventory=STARTING_GEAR.get(char_class, ["Dagger"]) + ["Healing Potion", "Torch x5"],
        gold=50,
    )

    state.player = player
    print(f"\nCharacter created!\n")
    print(player.stat_block())
    return player
