# AI Dungeon Master System — Project Report

**Course:** CMPSC441 — Artificial Intelligence  
**Project:** AI-Powered Dungeon Master for D&D 5e  
**Campaign Setting:** The Realm of Valdris  

---

## Section 1 — Base System Functionality

The AI DM System is a modular, CLI-based Dungeon Master that manages a full D&D 5e campaign session. All components run without errors and handle the following scenarios:

### Scenarios the System Handles

1. **Character Creation** — Player selects race, class, and name. The system rolls ability scores using the 4d6-drop-lowest method and applies racial bonuses. Starting gear is assigned by class. (`modules/character.py`)

2. **Dungeon Exploration** — Player navigates a four-room dungeon (Hall of Echoes → Vault of Shadows → Chamber of Binding → Throne of Stone). Each room is narrated by the LLM with atmospheric prose. Rooms track first-visit vs. revisit state. (`modules/exploration.py`)

3. **Trap Resolution** — Rooms with traps trigger automatic Perception skill checks. Success avoids the trap; failure deals dice-rolled damage. Trap types include pressure plates and magical wards. (`modules/exploration.py`)

4. **Treasure Discovery** — Players can `search` rooms. An Investigation skill check determines whether hidden treasure (gold + items) is found. Items are added to the player's inventory. (`modules/exploration.py`)

5. **Combat Encounters** — Full initiative-based combat against monsters (goblin, skeleton, troll, dragon). Player attacks, enemy turns, critical hits, critical fails, and death are all handled. (`modules/combat.py`)

6. **Enemy Ambush Planning** — Using chain-of-thought reasoning, the system plans a coordinated ambush with flanking, positioning, and trigger signals before executing it. (`modules/combat.py`)

7. **Talk to NPC** — Players open conversations with named NPCs (Bram the Tavernkeeper, Elara the Merchant). The LLM adopts the NPC's persona based on their lore profile. (`modules/npc_dialogue.py`)

8. **NPC Bargaining** — Players attempt to haggle with merchants. A Persuasion skill check determines whether the NPC accepts a discounted price. The NPC responds in character. (`modules/npc_dialogue.py`)

9. **Multi-Step Puzzle Solving** — The Chamber of Binding contains a three-lever puzzle. Incorrect attempts unlock progressive hint tiers rather than outright failure. Solving it marks a quest objective. (`modules/exploration.py`)

10. **Quest Tracking** — The system maintains a quest log with objectives, completion state, and rewards. Completing all objectives grants gold and XP automatically. (`modules/game_state.py`)

11. **Inventory Management** — Players view their stat block, inventory items, gold, and XP at any time with the `inv` command. (`modules/game_state.py`)

12. **Free-Form Narration** — Any unrecognized command is forwarded to the LLM as a natural language request. The DM responds in-character using rolling conversation history. (`main.py`)

13. **Lore Lookup** — Players can query the lore database directly (`lore goblin`, `lore fireball`). The RAG engine returns ranked relevant documents. (`modules/lore_database.py`)

14. **Game State Save** — On exit, the full game state (player, quests, NPC memory, explored rooms) is serialized to `savegame.json`. (`modules/game_state.py`)

---

## Section 2 — Prompt Engineering and Model Parameter Choice

### Parameter Rationale

All LLM calls route through `modules/llm_client.py`, which defines five scenario parameter sets:

| Scenario Key | Temperature | Tokens (num_predict) | Rationale |
|---|---|---|---|
| `narrative` | 0.9 | num_predict=600 | High creativity for varied, immersive room/story descriptions |
| `combat` | 0.6 | num_predict=400 | Moderate creativity; needs dramatic flair but mechanical accuracy |
| `planning` | 0.3 | num_predict=500 | Low temperature for logical, coherent multi-step enemy strategy |
| `dialogue` | 0.8 | num_predict=400 | Natural NPC conversation with personality and variation |
| `strict` | 0.1 | num_predict=300 | Deterministic for rules lookups and mechanical outputs |

Temperature is the most critical parameter. Narrative scenarios benefit from high temperature because variation and surprise serve the storytelling. Enemy planning deliberately uses low temperature: when coordinating a 4-goblin ambush with flanking positions, we need a coherent logical sequence, not creative randomness.

Max tokens are capped conservatively to keep the game loop responsive. Room descriptions are capped at 600 tokens (roughly 2–3 paragraphs); combat rounds at 400 (a vivid but concise round summary).

### System Prompts

Five role-based system prompts are defined in `SYSTEM_PROMPTS` (`llm_client.py`):

**`dungeon_master`** — Core DM persona. Instructs the model to narrate in second person, maintain world lore consistency, respect game mechanics, and keep consequences lasting. Used for all general narration and free-form commands.

**`combat_narrator`** — Specialized for battle scenes. Explicitly instructs the model to distinguish critical hits (natural 20) from critical fails (natural 1), always state mechanical outcomes after narration, and limit each round to 3–5 sentences.

**`npc_actor`** — Instructs the model to speak exclusively in first person as the NPC, use the NPC's vocabulary, and react to the relationship history provided (prior bargaining outcomes, past conversations).

**`enemy_strategist`** — Structures the output format explicitly: `REASONING`, `PLAN`, `ACTION`. This enforces chain-of-thought reasoning and ensures the planning process is visible. Used for enemy turns when HP falls below 50% and for ambush planning.

**`puzzle_master`** — Instructs the model to give cryptic hints progressively rather than spoilers. Used when players request hints after failed puzzle attempts.

### Context and Role Management

Each LLM call can inject:
- `extra_system`: RAG lore context appended to the system prompt
- `conversation_history`: Rolling message history (capped at 20 turns) for multi-turn dialogue coherence
- Explicit role context in the user prompt (player name, level, current HP)

---

## Section 3 — Tools Usage

### Dice Service (`modules/dice_service.py`)

The `DiceService` class provides a complete dice-rolling tool used throughout the system:

- **`roll(sides, count, modifier)`** — Core roll for any die type (d4, d6, d8, d10, d12, d20, d100)
- **`roll_with_advantage()` / `roll_with_disadvantage()`** — Rolls 2d20 and takes the higher/lower per D&D 5e rules
- **`roll_ability_scores()`** — Generates 6 ability scores via 4d6-drop-lowest
- **`parse_and_roll(notation)`** — Parses standard dice notation (`2d6+3`, `d20`, `1d8-1`)
- **`attack_roll()`, `damage_roll()`, `saving_throw()`, `skill_check()`** — Semantic wrappers used by combat and exploration

Every roll returns a structured dict with `rolls`, `total`, `is_nat20`, `is_nat1` flags, enabling the combat narrator to respond appropriately to critical events.

The `format_result()` method renders a human-readable roll summary with 🎲 emoji, individual roll values, and special markers for critical events — this is displayed to the player after every mechanical roll.

### Lore Database as RAG Tool

The lore database (`modules/lore_database.py`) functions as a structured retrieval tool. Queries return ranked documents that are injected into prompts. This is used:
- Before narrating a room (retrieve dungeon lore)
- Before combat begins (retrieve monster stats)
- During NPC conversations (retrieve NPC profile)
- Via the `lore` command for direct player lookup

### Skill Checks as Tool Calls

Skill checks (Perception, Investigation, Persuasion, Athletics) are executed as tool calls: the system rolls the dice, applies the relevant ability modifier and proficiency bonus, compares to a DC, and returns a structured result before the LLM narrates the outcome. This separation ensures mechanical accuracy is not left to LLM inference.

---

## Section 4 — Planning & Reasoning

### Chain-of-Thought Enemy Strategy

The `generate_with_chain_of_thought()` method in `LLMClient` forces structured multi-step reasoning by:

1. Setting temperature to 0.3 (low, for coherent logic)
2. Using the `enemy_strategist` system prompt, which enforces output format: `REASONING` → `PLAN` → `ACTION`
3. Prepending "Think through this step by step before giving your final answer. Show your reasoning process clearly." to the user prompt

This is triggered in two scenarios:

**Enemy Turn (when HP < 50%):** When an enemy is injured, the system invokes chain-of-thought before mechanically resolving the attack. The model considers whether to attack, retreat, or attempt a special action. The reasoning is logged to `state.session_log`.

**Ambush Planning:** The `plan_ambush()` method gives the model terrain details and enemy/player counts, then requests a complete tactical plan with flanking positions, timing, and a trigger signal. Example situation fed to the model:

> "A group of 4 goblins is planning an ambush. Terrain: narrow corridor with alcoves and dim lighting. Target: Aria, a level 2 Wizard. Plan a coordinated ambush with flanking, archer positions, and a trigger signal."

The model reasons through the goblins' advantages (ambush, terrain, numbers) before committing to a plan.

### Multi-Step Puzzle Logic

The puzzle system implements a form of staged reasoning for players:

1. First incorrect attempt → outer-ring hint (celestial symbols)
2. Second incorrect attempt → middle-ring hint (elemental cycle)
3. Third incorrect attempt → inner-ring hint (lever correspondence)

Rather than giving the solution, each hint moves the player one step closer to the chain of reasoning needed. The LLM wraps each hint in in-world narration.

### Conversation Coherence

`GameState.get_history(max_turns=20)` maintains a rolling conversation window passed to every LLM call. This ensures the DM remembers:
- What rooms have been described
- What NPCs have said
- What the player has done in this session

The window is capped at 20 turns (40 messages) to respect context limits while maintaining narrative coherence.

---

## Section 5 — RAG Implementation

### Architecture

The RAG system is implemented in `modules/lore_database.py` using TF-IDF keyword scoring — no external vector database required, making the project fully self-contained.

**Document Corpus (15 documents):**
- 3 world lore documents (Realm of Valdris, Dungeon of Keth'mara, Rusty Flagon Tavern)
- 4 monster entries (Goblin, Skeleton, Troll, Young Red Dragon) with full stat blocks
- 3 spell descriptions (Fireball, Healing Word, Charm Person)
- 2 NPC profiles (Bram, Elara) with personality, motivations, and quest hooks

**Retrieval Pipeline:**
1. Query is tokenized and lowercased
2. IDF scores are precomputed from the corpus at initialization
3. TF-IDF scores are computed for each candidate document
4. Top-k documents are returned, sorted by relevance score
5. Retrieved documents are formatted via `format_for_prompt()` and appended to the system prompt

**Integration Points:**
- **Room Narration:** Dungeon lore injected before describing each room
- **Combat Start:** Monster stat block retrieved and parsed for AC, HP, attack bonus, damage dice
- **NPC Conversations:** NPC profile retrieved and passed as `extra_system` context
- **Player Lore Lookups:** Direct retrieval via `lore <query>` command

**Dynamic Updates:** New discoveries (secret rooms, unique items) can be added to the corpus at runtime via `lore_db.add_document()`, which triggers an IDF rebuild. This enables the lore base to grow as players explore.

### Monster Stat Parsing

When combat starts, `CombatManager._parse_monster()` uses regex to extract mechanical values (HP, AC, attack bonus, damage dice) from the standardized lore text format. This bridges the RAG retrieval output and the dice-based combat system — the lore document is the single source of truth for monster mechanics.

---

## Section 6 — Additional Tools / Innovation

### Persistent NPC Memory

The `npc_memory` dictionary in `GameState` tracks all interactions with each NPC across the session. Before any NPC conversation, `recall_npc()` retrieves the last 3 interactions as context. This enables:

- NPCs to remember previous bargaining outcomes ("You got a discount last time")
- Relationship evolution (an NPC who was deceived becomes suspicious)
- Quest state awareness (Bram knows if you've returned his daughter)

This is surfaced to the LLM via the `relationship_history` parameter in `generate_npc_dialogue()`.

### Structured Game State Serialization

The full game state (player stats, inventory, quests, explored rooms, NPC memories) serializes to `savegame.json` on exit. The `to_dict()` method on `GameState` and `PlayerCharacter` produces clean, human-readable JSON suitable for future session restoration.

### Extensible Lore Database

The `add_document()` method allows the DM system to dynamically add player-discovered lore during play. For example, when a player finds the Shard of the Shattered Crown, a new document about the artifact's powers can be added to the corpus — future `retrieve()` calls will include it in rankings.

### Combat Critical Event System

The dice service's `is_nat20` and `is_nat1` flags are propagated through the entire combat pipeline to the LLM narrator. The `combat_narrator` system prompt explicitly instructs the model to write a "spectacular critical hit with vivid description" on a natural 20 and a "humorous or dramatic fumble" on a natural 1. This produces contextually appropriate narration without requiring separate prompt calls for each case.

---

## Section 7 — Code Quality & Modular Design

### Module Structure

```
ai_dm/
├── main.py                    # Entry point and game loop
├── pyproject.toml             # Dependency management
├── modules/
│   ├── __init__.py
│   ├── game_state.py          # Central state container (PlayerCharacter, Quest, GameState)
│   ├── dice_service.py        # All dice mechanics (DiceService singleton)
│   ├── lore_database.py       # RAG corpus and TF-IDF retrieval (LoreDatabase singleton)
│   ├── llm_client.py          # Ollama API wrapper with scenario params (stdlib only)
│   ├── character.py           # Character creation wizard
│   ├── combat.py              # Combat resolution (CombatManager)
│   ├── npc_dialogue.py        # NPC interaction and bargaining (NPCDialogueManager)
│   └── exploration.py         # Room navigation, traps, puzzles (ExplorationManager)
└── tests/
    └── test_core.py           # Unit tests for non-LLM modules (34 tests)
```

### Design Principles

**Single Responsibility:** Each module owns one concern. `DiceService` only rolls dice. `LoreDatabase` only retrieves lore. `CombatManager` only resolves combat. The `GameState` is the shared data bus — modules read and write to it but don't import each other.

**Dependency Injection:** All managers (`CombatManager`, `NPCDialogueManager`, `ExplorationManager`) receive their dependencies (`GameState`, `DiceService`, `LoreDatabase`, `LLMClient`) via constructor injection. This makes modules independently testable.

**Separation of Mechanics and Narration:** Dice rolls are always resolved before the LLM is called. The LLM receives mechanical results (hit/miss, damage, skill check pass/fail) and narrates them — it never decides outcomes. This ensures game rule integrity.

**Singletons for Stateless Services:** `DiceService` and `LoreDatabase` are exposed as module-level singletons (`dice`, `lore_db`) for convenient import while remaining injected into managers for testability.

### Testing

`tests/test_core.py` contains 34 unit tests covering all non-LLM logic:
- DiceService: roll ranges, modifiers, nat20/nat1 detection, notation parsing, ability score generation
- LoreDatabase: retrieval accuracy, category filtering, dynamic document addition, format output
- GameState: message history, NPC memory, quest completion, room tracking, serialization

Tests are written with pytest and use monkeypatching to control `random.randint` for deterministic verification of critical-hit and critical-fail detection.

### Environment Management

The project uses `pyproject.toml` with **zero runtime Python dependencies** — the Ollama client is implemented using only Python's standard library (`urllib`, `json`). No API key is required. The Ollama host and model are read from `OLLAMA_HOST` and `OLLAMA_MODEL` environment variables (with sensible defaults). A `.gitignore` entry excludes `savegame.json` and `__pycache__/`.

---

## Running the System

```bash
# 1. Install Ollama  (https://ollama.com)
#    macOS / Linux:
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a model (llama3 recommended; mistral or phi3 also work)
ollama pull llama3

# 3. Run the game (no API key required)
python main.py

# 4. Optional — override model or host
OLLAMA_MODEL=mistral python main.py
OLLAMA_HOST=http://192.168.1.10:11434 python main.py

# 5. Run unit tests (no Ollama needed)
pytest tests/
```
