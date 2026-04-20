# Lab 14 — Project Feature Submission


## Completed Use Case: Start Game (including Update Game State)

The **Start Game** use case has been fully implemented across `modules/character.py`, `modules/game_state.py`, and `main.py`.

### How It Works

When the player launches the system, the Start Game use case runs automatically and sets up the full game session:

1. **Character Creation** — The player is prompted to enter a name, choose a race, and choose a class. The system rolls ability scores using the 4d6-drop-lowest method, applies racial bonuses, assigns starting gear by class, and calculates starting HP and AC.
2. **Update Game State** — Once the character is built, a `PlayerCharacter` object is written into the central `GameState`. This satisfies the `<<include>>` relationship to **Update Game State** — the game state is initialized with the player's stats, inventory, gold, XP, and current room.
3. **Starter Quest Assigned** — A starting quest ("Into the Depths") is added to the quest log with objectives and rewards, also written into `GameState`.
4. **Opening Narration** — The Ollama LLM generates a dramatic opening scene personalized to the player's race and class, using dungeon lore retrieved from the lore database (RAG) as context.
5. **First Room Entered** — The player is placed in the starting room (Hall of Echoes), which triggers another `GameState` update: `current_room`, `explored_rooms`, and `room_history` are all recorded.

All subsequent actions in the game (combat, exploration, quests) read from and write back to the same `GameState` object, making it the single source of truth for the entire session.

### Files

| File | Role |
|---|---|
| `modules/game_state.py` | `GameState` and `PlayerCharacter` dataclasses — central state container |
| `modules/character.py` | Interactive character creation, ability score rolling, gear assignment |
| `main.py` | `AIDungeonMaster.start()` — wires character creation into game state and triggers opening narration |
| `modules/llm_client.py` | Opening narration generated via local Ollama model |
| `modules/lore_database.py` | Dungeon lore injected into opening narration prompt (RAG) |
