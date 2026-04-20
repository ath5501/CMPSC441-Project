# Lab 14 — Project Feature Submission

## Completed Use Case: Fight Monster

The **Fight Monster** use case has been fully implemented across `modules/combat.py`, `modules/dice_service.py`, and `modules/lore_database.py`.

### How It Works

When a player enters a room containing an enemy, the system runs a full D&D 5e combat encounter:

1. **Initiative** — Both the player and enemy roll d20 + DEX modifier. The higher roll acts first.
2. **Monster Stat Retrieval** — Before combat begins, `CombatManager.start_encounter()` queries the lore database (RAG) for the enemy's AC, HP, attack bonus, and damage dice. This satisfies the `<<include>>` relationship to **Generate Monster Stats**.
3. **Player Attack** — `player_attack()` rolls a d20 attack roll against the enemy's AC, then rolls weapon damage on a hit. A natural 20 doubles the damage dice (critical hit); a natural 1 is an automatic miss. This satisfies the `<<include>>` relationship to **Roll Dice**.
4. **Enemy Turn** — `enemy_turn()` rolls the monster's attack against the player's AC and applies damage to player HP. When the enemy's HP drops below 50%, chain-of-thought reasoning is used to decide whether to attack, retreat, or act differently.
5. **Combat Narration** — After every mechanical roll, the Ollama LLM narrates the round dramatically using the `combat_narrator` system prompt, referencing the weapon used, roll result, and hit/miss outcome.
6. **End Conditions** — If enemy HP reaches 0, the player earns XP and gold. If player HP reaches 0, the session ends.

The **Enemy Ambush** `<<extend>>` use case is also implemented via `plan_ambush()`, which uses chain-of-thought reasoning to coordinate a surprise multi-enemy attack with flanking positions before combat begins.

### Files

| File | Role |
|---|---|
| `modules/combat.py` | Core combat loop — initiative, attack/damage resolution, enemy AI |
| `modules/dice_service.py` | All dice rolls — d20 attacks, weapon damage, initiative |
| `modules/lore_database.py` | Monster stat retrieval via RAG |
| `modules/llm_client.py` | Combat narration via local Ollama model |
| `modules/game_state.py` | HP tracking, XP and gold rewards |
