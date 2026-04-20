"""
main.py
AI Dungeon Master — Main Entry Point
CMPSC441 Final Project

Entry point that wires all modules together and runs the game loop.
"""

import os
import sys
from modules.game_state import GameState, Quest
from modules.dice_service import DiceService
from modules.lore_database import LoreDatabase
from modules.llm_client import LLMClient
from modules.character import create_character
from modules.combat import CombatManager
from modules.npc_dialogue import NPCDialogueManager
from modules.exploration import ExplorationManager, DUNGEON_MAP


BANNER = """
╔══════════════════════════════════════════════════════╗
║          ⚔️  AI DUNGEON MASTER SYSTEM  ⚔️             ║
║          CMPSC441 Final Project                      ║
║          Realm of Valdris Campaign                   ║
╚══════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
━━━━━━━━━━━━ COMMANDS ━━━━━━━━━━━━
  go <room>         — Move to adjacent room (entrance, vault, ritual_chamber, throne)
  attack [weapon]   — Attack current enemy
  talk <npc>        — Start conversation with an NPC
  say <message>     — Speak to active NPC
  bye               — End NPC conversation
  bargain <item> <price> — Haggle with merchant
  search            — Search current room for treasure
  puzzle <answer>   — Attempt to solve room puzzle
  inventory / inv   — View your items and stats
  quests            — View quest log
  roll <dice>       — Roll dice (e.g. 'roll 2d6+3', 'roll d20')
  lore <query>      — Look up lore / monster info
  ambush            — Trigger goblin ambush (demo)
  help              — Show this menu
  quit / exit       — Exit game
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class AIDungeonMaster:
    """Main game controller. Orchestrates all subsystems."""

    def __init__(self):
        # ── Initialize all modules ──
        # LLMClient connects to local Ollama — no API key needed.
        # Model: set OLLAMA_MODEL env var (default: llama3)
        # Host:  set OLLAMA_HOST  env var (default: http://localhost:11434)
        self.state = GameState()
        self.dice = DiceService()
        self.lore = LoreDatabase()
        try:
            self.llm = LLMClient()
        except RuntimeError as e:
            print(f"\nERROR: {e}")
            sys.exit(1)
        self.combat = CombatManager(self.state, self.dice, self.lore, self.llm)
        self.npc = NPCDialogueManager(self.state, self.lore, self.llm, self.dice)
        self.exploration = ExplorationManager(self.state, self.lore, self.llm, self.dice)

    def start(self):
        print(BANNER)
        print("Welcome, adventurer. Your quest begins in the town of Millhaven...")

        # ── Character Creation ──
        self.state.player = create_character(self.state, self.dice)

        # ── Starter Quest ──
        starter_quest = Quest(
            title="Into the Depths",
            description="Explore the Dungeon of Keth'mara and retrieve the Shard of the Shattered Crown.",
            objectives=["Enter the dungeon", "Solve the Chamber of Binding puzzle", "Reach the Throne of Stone"],
            reward_gold=300,
            reward_xp=500,
        )
        self.state.add_quest(starter_quest)

        # ── Opening Narration ──
        opening = self.llm.generate(
            user_prompt=(
                f"The player {self.state.player.name}, a {self.state.player.race} "
                f"{self.state.player.character_class}, stands at the entrance of the Dungeon of Keth'mara "
                "in the Realm of Valdris. Write a dramatic 3-sentence opening that sets the scene."
            ),
            system_role="dungeon_master",
            scenario="narrative",
            extra_system=self.lore.format_for_prompt(self.lore.retrieve("Keth'mara dungeon")),
        )
        print(f"\n{opening}\n")

        # ── Enter Starting Room ──
        print(self.exploration.enter_room("entrance"))
        self.state.complete_objective("Into the Depths", "Enter the dungeon")

        self._game_loop()

    def _game_loop(self):
        print(HELP_TEXT)
        while True:
            try:
                raw = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nFarewell, adventurer.")
                break

            if not raw:
                continue

            tokens = raw.split(maxsplit=1)
            cmd = tokens[0].lower()
            args = tokens[1] if len(tokens) > 1 else ""

            if cmd in ("quit", "exit"):
                self.state.save()
                print("Game saved. Farewell!")
                break
            elif cmd == "help":
                print(HELP_TEXT)
            elif cmd == "go":
                self._cmd_go(args)
            elif cmd == "attack":
                self._cmd_attack(args)
            elif cmd == "talk":
                self._cmd_talk(args)
            elif cmd == "say":
                self._cmd_say(args)
            elif cmd == "bye":
                print(self.npc.end_conversation())
            elif cmd == "bargain":
                self._cmd_bargain(args)
            elif cmd == "search":
                print(self.exploration.check_for_treasure(self.state.current_room))
            elif cmd == "puzzle":
                self._cmd_puzzle(args)
            elif cmd in ("inventory", "inv"):
                self._cmd_inventory()
            elif cmd == "quests":
                print("\n📜 **Quest Log**\n" + self.state.quest_summary())
            elif cmd == "roll":
                self._cmd_roll(args)
            elif cmd == "lore":
                self._cmd_lore(args)
            elif cmd == "ambush":
                self._cmd_ambush()
            else:
                # Free-form: pass to DM for narrative response
                response = self.llm.generate(
                    user_prompt=raw,
                    system_role="dungeon_master",
                    scenario="narrative",
                    conversation_history=self.state.get_history(10),
                )
                self.state.add_message("user", raw)
                self.state.add_message("assistant", response)
                print(f"\n{response}")

    # ── Command Handlers ──────────────────────────────────────────────────────

    def _cmd_go(self, destination: str):
        current_room = DUNGEON_MAP.get(self.state.current_room, {})
        exits = current_room.get("exits", [])

        # Match by partial name or ID
        matched = None
        for exit_id in exits:
            room_data = DUNGEON_MAP.get(exit_id, {})
            if (destination.lower() in exit_id.lower() or
                    destination.lower() in room_data.get("name", "").lower()):
                matched = exit_id
                break

        if not matched:
            print(f"You can't go to '{destination}' from here.")
            return

        result = self.exploration.enter_room(matched)
        print(result)

        # Check for encounter in new room
        room = DUNGEON_MAP[matched]
        if room.get("encounter") and matched not in self.state.explored_rooms[:-1]:
            enemy = room["encounter"]
            print(f"\n⚠️ A {enemy} appears!")
            print(self.combat.start_encounter(enemy))

        # Quest objective tracking
        if matched == "ritual_chamber":
            pass  # puzzle triggers objective on solve
        if matched == "throne":
            self.state.complete_objective("Into the Depths", "Reach the Throne of Stone")

    def _cmd_attack(self, weapon: str = ""):
        if not self.state.combat_active:
            print("You're not in combat. Use 'go' to explore and find enemies.")
            return
        weapon = weapon or "longsword"
        damage_map = {"longsword": "1d8", "dagger": "1d4", "greataxe": "2d6", "shortbow": "1d6"}
        damage_dice = damage_map.get(weapon.lower(), "1d6")
        print(self.combat.player_attack(weapon=weapon, damage_dice=damage_dice))
        if self.state.combat_active:
            print(self.combat.enemy_turn())

    def _cmd_talk(self, npc_name: str):
        if not npc_name:
            print("Talk to whom? Try 'talk bram' or 'talk elara'.")
            return
        print(self.npc.start_conversation(npc_name))

    def _cmd_say(self, message: str):
        if not message:
            return
        print(self.npc.say(message))

    def _cmd_bargain(self, args: str):
        parts = args.rsplit(maxsplit=1)
        if len(parts) < 2:
            print("Usage: bargain <item name> <your price>")
            return
        item, price_str = parts
        try:
            price = int(price_str)
        except ValueError:
            print("Price must be a number.")
            return
        npc = self.npc.active_npc or "elara"
        print(self.npc.attempt_bargain(item, price, npc))

    def _cmd_puzzle(self, answer: str):
        room = DUNGEON_MAP.get(self.state.current_room, {})
        puzzle_id = room.get("puzzle_id")
        if not puzzle_id:
            print("There is no puzzle in this room.")
            return
        result = self.exploration.attempt_puzzle(puzzle_id, answer)
        print(result)
        if "Solved" in result:
            self.state.complete_objective("Into the Depths", "Solve the Chamber of Binding puzzle")

    def _cmd_inventory(self):
        p = self.state.player
        print(f"\n{p.stat_block()}")
        print("\n📦 **Inventory:**")
        for item in p.inventory:
            print(f"  • {item}")

    def _cmd_roll(self, notation: str):
        if not notation:
            print("Specify dice notation, e.g. 'roll 2d6+3'")
            return
        try:
            result = self.dice.parse_and_roll(notation)
            print(self.dice.format_result(result))
        except ValueError as e:
            print(f"Invalid dice: {e}")

    def _cmd_lore(self, query: str):
        if not query:
            print("What do you want to look up? e.g. 'lore goblin' or 'lore fireball'")
            return
        docs = self.lore.retrieve(query, top_k=2)
        if not docs:
            print("No lore found for that query.")
            return
        for doc in docs:
            print(f"\n📚 **{doc['title']}**\n{doc['content']}\n")

    def _cmd_ambush(self):
        """Demo scenario: trigger a goblin ambush."""
        plan = self.combat.plan_ambush(
            num_enemies=4,
            terrain="narrow corridor with alcoves and dim lighting",
        )
        print(plan)
        print("\n" + self.combat.start_encounter("goblin", ambush=True))


if __name__ == "__main__":
    game = AIDungeonMaster()
    game.start()
