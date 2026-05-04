"""
npc_dialogue.py
Manages NPC interactions, dialogue generation, and merchant bargaining.
Uses LLMClient with npc_actor system prompt + lore RAG for character profiles.
"""

from modules.game_state import GameState
from modules.lore_database import LoreDatabase
from modules.llm_client import LLMClient
from modules.dice_service import DiceService


KNOWN_NPCS = {
    "bram": "npc_bram",
    "elara": "npc_merchant",
}


class NPCDialogueManager:
    """Handles talk-to-NPC scenarios with memory and bargaining support."""

    def __init__(self, state: GameState, lore: LoreDatabase, llm: LLMClient, dice: DiceService):
        self.state = state
        self.lore = lore
        self.llm = llm
        self.dice = dice
        self.active_npc: str = ""
        self.npc_conversation: list[dict] = []

    def start_conversation(self, npc_name: str) -> str:
        """Initialize conversation with an NPC."""
        self.active_npc = npc_name.lower()
        self.npc_conversation = []

        # Retrieve NPC profile from lore DB (RAG)
        lore_id = KNOWN_NPCS.get(self.active_npc)
        npc_doc = self.lore.get_by_id(lore_id) if lore_id else None

        if not npc_doc:
            # Generic NPC — generate basic profile
            profile = f"{npc_name} is a local resident of Millhaven with no particular allegiance."
        else:
            profile = npc_doc["content"]

        self.current_profile = profile

        # Recall prior interactions
        history = self.state.recall_npc(npc_name)

        opening = self.llm.generate_npc_dialogue(
            npc_name=npc_name,
            npc_profile=profile,
            player_message=f"(Player approaches {npc_name} for the first time in this session.)",
            relationship_history=history,
            conversation_history=[],
        )
        self.npc_conversation.append({"role": "assistant", "content": opening})
        return f"\n**{npc_name.title()}:** {opening}"

    def say(self, player_message: str) -> str:
        """Player says something to the active NPC."""
        if not self.active_npc:
            return "There's no one to talk to. Try 'talk to <NPC name>' first."

        response = self.llm.generate_npc_dialogue(
            npc_name=self.active_npc,
            npc_profile=self.current_profile,
            player_message=player_message,
            conversation_history=self.npc_conversation[-10:],  # rolling window
        )
        self.npc_conversation.append({"role": "user", "content": player_message})
        self.npc_conversation.append({"role": "assistant", "content": response})
        return f"\n**{self.active_npc.title()}:** {response}"

    def attempt_bargain(self, item: str, offered_price: int, npc_name: str) -> str:
        """
        Player attempts to negotiate a price with a merchant NPC.
        Uses Persuasion skill check to determine outcome.
        """
        player = self.state.player
        cha_mod = (player.charisma - 10) // 2
        proficiency = 2 + (player.level - 1) // 4

        # Persuasion check (DC 13 for standard haggling)
        check = self.dice.skill_check(skill_mod=cha_mod + proficiency, dc=13)
        self.state.log(f"[Bargain] Persuasion check: {check['total']} vs DC 13")

        if check.get("is_nat20") or check["success"]:
            final_price = max(1, int(offered_price * 0.85))  # 15% discount
            outcome = "success"
            dm_note = f"Persuasion check succeeded ({check['total']})! Price reduced to {final_price}g."
        else:
            final_price = offered_price
            outcome = "fail"
            dm_note = f"Persuasion check failed ({check['total']}). Standard price holds."

        # Generate NPC response
        bargain_context = f"Player wants to buy {item} for {offered_price}g (normal price). " \
                         f"Persuasion check result: {outcome}. Final price: {final_price}g."
        npc_response = self.llm.generate_npc_dialogue(
            npc_name=npc_name,
            npc_profile=self.current_profile or f"{npc_name} is a merchant.",
            player_message=f"I'd like to buy {item} for {offered_price} gold.",
            relationship_history=bargain_context,
        )

        self.state.remember_npc_interaction(
            npc_name, f"Player bargained for {item} — {outcome} — final price: {final_price}g"
        )

        result = f"{self.dice.format_result(check)}\n"
        result += f"*{dm_note}*\n\n"
        result += f"**{npc_name.title()}:** {npc_response}"
        return result

    def end_conversation(self) -> str:
        """Record the conversation summary in NPC memory and close."""
        if not self.active_npc:
            return ""
        summary = f"Had a conversation ({len(self.npc_conversation)//2} exchanges)"
        self.state.remember_npc_interaction(self.active_npc, summary)
        npc = self.active_npc
        self.active_npc = ""
        self.npc_conversation = []
        return f"*You part ways with {npc.title()}.*"
