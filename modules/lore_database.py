"""
lore_database.py
RAG-based lore retrieval system.
Stores world lore, monster entries, and spell descriptions as embedded chunks.
Uses simple TF-IDF-style keyword search (no external vector DB required).
"""

from __future__ import annotations
import re
import math
from collections import Counter
from typing import Optional


# ── Lore Documents ────────────────────────────────────────────────────────────

LORE_DOCUMENTS: list[dict] = [
    # ── World Lore ────────────────────────────────────────────────────────────
    {
        "id": "world_overview",
        "category": "world",
        "title": "The Realm of Valdris",
        "content": (
            "The Realm of Valdris is an ancient land scarred by the God Wars of the Third Age. "
            "Three major powers vie for control: the Arcane Consortium (a guild of wizards based in the "
            "city of Thalindor), the Iron Throne (a militaristic human empire), and the Sylvan Compact "
            "(an alliance of elves and druids protecting the eastern forests). "
            "The land is riddled with dungeons — ruins left by the Elder Giants who once ruled. "
            "Deep within these ruins lies the Shattered Crown, an artifact said to grant godlike power. "
            "Many adventurers seek it; none have returned."
        ),
    },
    {
        "id": "dungeon_lore",
        "category": "world",
        "title": "The Dungeon of Keth'mara",
        "content": (
            "Keth'mara was a fortress-city of the Elder Giants, now buried beneath the Ashwood forest. "
            "Its halls are divided into four wings: The Hall of Echoes (entrance), the Vault of Shadows "
            "(treasure storage), the Chamber of Binding (ritual room), and the Throne of Stone (the final "
            "sanctum). Ancient traps — pressure plates, swinging blades, and magical wards — still function. "
            "The dungeon is rumored to hold the Shattered Crown's first fragment."
        ),
    },
    {
        "id": "tavern_lore",
        "category": "world",
        "title": "The Rusty Flagon Tavern",
        "content": (
            "The Rusty Flagon is the most notorious tavern in the town of Millhaven, located at the "
            "edge of the Ashwood. Run by a gruff half-orc named Bram, it serves as the primary gathering "
            "spot for adventurers, merchants, and spies. The back room is rumored to host dealings "
            "between the Thieves' Guild and local merchants. A jobs board near the entrance always lists "
            "bounties, escort quests, and retrieval missions."
        ),
    },
    # ── Monster Entries ───────────────────────────────────────────────────────
    {
        "id": "monster_goblin",
        "category": "monster",
        "title": "Goblin",
        "content": (
            "Goblins are small, cunning humanoids that lurk in caves, dungeons, and ruined buildings. "
            "Stats: AC 15 (leather + shield), HP 7 (2d6), Speed 30 ft. "
            "Attributes: STR 8, DEX 14, CON 10, INT 10, WIS 8, CHA 8. "
            "Attack: Scimitar +4 to hit, 1d6+2 slashing. Shortbow +4 to hit, 1d6+2 piercing (80/320 ft). "
            "Special: Nimble Escape — goblins can Disengage or Hide as a bonus action. "
            "Lore: Goblins are organized in warrens led by a Goblin Boss. They favor ambush tactics "
            "and often work alongside worgs or hobgoblins. Challenge Rating: 1/4 (50 XP)."
        ),
    },
    {
        "id": "monster_skeleton",
        "category": "monster",
        "title": "Skeleton",
        "content": (
            "Skeletons are undead warriors animated by dark magic, often found guarding ancient tombs. "
            "Stats: AC 13 (armor scraps), HP 13 (2d8+4), Speed 30 ft. "
            "Attributes: STR 10, DEX 14, CON 15, INT 6, WIS 8, CHA 5. "
            "Vulnerabilities: Bludgeoning damage. Immunities: Poison, Exhaustion, conditions (frightened, etc.). "
            "Attack: Shortsword +4 to hit, 1d6+2 piercing. Shortbow +4 to hit, 1d6+2 piercing. "
            "Lore: Skeletons are mindless and follow the last command of the necromancer who raised them. "
            "They do not tire, feel fear, or negotiate. Challenge Rating: 1/4 (50 XP)."
        ),
    },
    {
        "id": "monster_troll",
        "category": "monster",
        "title": "Troll",
        "content": (
            "Trolls are massive, regenerating humanoids with voracious appetites. "
            "Stats: AC 15 (natural armor), HP 84 (8d10+40), Speed 30 ft. "
            "Attributes: STR 18, DEX 13, CON 20, INT 7, WIS 9, CHA 7. "
            "Special: Regeneration — the troll regains 10 HP at the start of its turn unless it took "
            "acid or fire damage last round. Keen Smell — advantage on Perception (smell). "
            "Attacks: Bite +7 to hit, 1d6+4 piercing. Claw ×2 +7 to hit, 2d6+4 slashing. "
            "Lore: Trolls fear only fire and acid. Striking one with flame prevents its regeneration. "
            "They are sometimes enslaved by giants or ogres. Challenge Rating: 5 (1,800 XP)."
        ),
    },
    {
        "id": "monster_dragon",
        "category": "monster",
        "title": "Young Red Dragon",
        "content": (
            "Young Red Dragons are arrogant, territorial fire-breathers obsessed with hoarding treasure. "
            "Stats: AC 18 (natural armor), HP 178 (17d10+85), Speed 40 ft / Fly 80 ft. "
            "Attributes: STR 23, DEX 10, CON 21, INT 14, WIS 11, CHA 19. "
            "Saving Throws: DEX +4, CON +9, WIS +4, CHA +8. "
            "Immunities: Fire. Skills: Perception +8, Stealth +4. "
            "Fire Breath (Recharge 5–6): 30-ft cone, 16d6 fire damage (DC 21 DEX half). "
            "Attacks: Bite +10 to hit, 2d10+6 piercing + 1d6 fire. Claw ×2 +10, 2d6+6 slashing. "
            "Lore: Red dragons are the most covetous chromatic dragons, hoarding gold and gems. "
            "They demand tribute from nearby settlements. Challenge Rating: 10 (5,900 XP)."
        ),
    },
    # ── Spells ────────────────────────────────────────────────────────────────
    {
        "id": "spell_fireball",
        "category": "spell",
        "title": "Fireball (3rd Level Evocation)",
        "content": (
            "Casting Time: 1 action. Range: 150 ft. Components: V, S, M (bat guano + sulfur). Duration: Instant. "
            "Effect: A bright streak flashes from your finger to a point within range, then blossoms into a "
            "20-foot-radius sphere of fire. Each creature in the area must make a DC (8 + spellcasting mod + proficiency) "
            "DEX saving throw, taking 8d6 fire damage on a failure, or half on success. "
            "The fire ignites flammable objects that aren't being worn or carried. "
            "At Higher Levels: +1d6 damage per slot level above 3rd."
        ),
    },
    {
        "id": "spell_healing_word",
        "category": "spell",
        "title": "Healing Word (1st Level Evocation)",
        "content": (
            "Casting Time: 1 bonus action. Range: 60 ft. Components: V. Duration: Instant. "
            "Effect: A creature of your choice within range regains HP equal to 1d4 + your spellcasting modifier. "
            "This spell has no effect on undead or constructs. "
            "At Higher Levels: +1d4 per slot level above 1st. "
            "Note: As a bonus action, this is highly valuable in combat for keeping allies alive."
        ),
    },
    {
        "id": "spell_charm_person",
        "category": "spell",
        "title": "Charm Person (1st Level Enchantment)",
        "content": (
            "Casting Time: 1 action. Range: 30 ft. Components: V, S. Duration: 1 hour. "
            "Effect: Target humanoid must succeed on a WIS saving throw or be charmed. "
            "The charmed target regards you as a friendly acquaintance and is inclined to trust you. "
            "The spell ends if you or your allies harm the target. On success, target knows it was charmed. "
            "At Higher Levels: Target +1 creature per slot level above 1st."
        ),
    },
    # ── NPC Profiles ──────────────────────────────────────────────────────────
    {
        "id": "npc_bram",
        "category": "npc",
        "title": "Bram the Tavernkeeper",
        "content": (
            "Bram is a 52-year-old half-orc with graying hair and a broken tusk. "
            "He runs the Rusty Flagon with an iron fist, tolerating no brawls on his floor. "
            "Personality: Gruff but fair. He secretly funds the local orphanage. "
            "He knows most adventurers by name and tracks their debts carefully. "
            "Bargaining: Bram responds well to honesty and upfront payment. "
            "He is suspicious of magic users after a wizard burned down his storage shed. "
            "Quest hook: Bram's daughter was kidnapped by goblins three days ago. He will pay 200 gold for her return."
        ),
    },
    {
        "id": "npc_merchant",
        "category": "npc",
        "title": "Elara the Traveling Merchant",
        "content": (
            "Elara is a shrewd human merchant, mid-30s, who travels the roads between Millhaven and Thalindor. "
            "She sells potions, basic adventuring gear, and occasionally rare spell components. "
            "Prices: Healing Potion (50g), Antitoxin (50g), Rope (1g), Torches (1cp each), "
            "Thieves' Tools (25g), Identify Scroll (75g). "
            "Personality: Friendly but profit-driven. She will haggle. Players who aided her in past "
            "encounters get a 10% discount. She carries rumors from other towns."
        ),
    },
]

# ── TF-IDF Retrieval Engine ───────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def _build_idf(docs: list[dict]) -> dict[str, float]:
    N = len(docs)
    df: Counter = Counter()
    for doc in docs:
        tokens = set(_tokenize(doc["title"] + " " + doc["content"]))
        df.update(tokens)
    return {term: math.log(N / (1 + freq)) for term, freq in df.items()}


_IDF = _build_idf(LORE_DOCUMENTS)


def _tf_idf_score(query_tokens: list[str], doc: dict) -> float:
    text = doc["title"] + " " + doc["content"]
    tf_counts = Counter(_tokenize(text))
    total_terms = sum(tf_counts.values()) or 1
    score = 0.0
    for token in query_tokens:
        tf = tf_counts.get(token, 0) / total_terms
        idf = _IDF.get(token, 0.0)
        score += tf * idf
    return score


class LoreDatabase:
    """
    Retrieval-Augmented Generation (RAG) lore store.
    Provides keyword search over curated lore documents.
    """

    def __init__(self):
        self.documents = LORE_DOCUMENTS

    def retrieve(self, query: str, top_k: int = 3, category: Optional[str] = None) -> list[dict]:
        """
        Retrieve the top-k most relevant lore documents for a given query.
        Optionally filter by category ('monster', 'world', 'spell', 'npc').
        """
        query_tokens = _tokenize(query)
        candidates = [d for d in self.documents if not category or d["category"] == category]
        scored = [(doc, _tf_idf_score(query_tokens, doc)) for doc in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, score in scored[:top_k] if score > 0]

    def get_by_id(self, doc_id: str) -> Optional[dict]:
        for doc in self.documents:
            if doc["id"] == doc_id:
                return doc
        return None

    def format_for_prompt(self, docs: list[dict]) -> str:
        """Format retrieved docs as a RAG context block for LLM prompts."""
        if not docs:
            return ""
        sections = []
        for doc in docs:
            sections.append(f"### {doc['title']}\n{doc['content']}")
        return "--- LORE CONTEXT ---\n" + "\n\n".join(sections) + "\n--- END LORE ---"

    def add_document(self, doc_id: str, category: str, title: str, content: str):
        """Dynamically add a new lore document (e.g., player discoveries)."""
        global _IDF
        new_doc = {"id": doc_id, "category": category, "title": title, "content": content}
        self.documents.append(new_doc)
        _IDF = _build_idf(self.documents)  # rebuild IDF with new doc

    def monster_lookup(self, monster_name: str) -> Optional[dict]:
        results = self.retrieve(monster_name, top_k=1, category="monster")
        return results[0] if results else None

    def spell_lookup(self, spell_name: str) -> Optional[dict]:
        results = self.retrieve(spell_name, top_k=1, category="spell")
        return results[0] if results else None


# Singleton
lore_db = LoreDatabase()
