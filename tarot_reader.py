#!/usr/bin/env python3
"""
tarot_reader.py
🐺 Anthro-friendly deterministic Tarot with reversals and color output.
Enhanced with protection through cryptographic hashing.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import List, Tuple, Optional
import hashlib
import sys

# ----- Optional color UI via rich -----
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# ----- Constants and Configuration -----
class SpreadType(IntEnum):
    """Enum for spread types with their card counts."""
    SINGLE = 1
    THREE_CARD = 3
    CELTIC_CROSS = 10


@dataclass(frozen=True)
class TarotCard:
    """Immutable representation of a Tarot card."""
    name: str
    is_major: bool
    deck_position: int


@dataclass(frozen=True)
class DrawnCard:
    """Represents a drawn card with orientation and hash."""
    card: TarotCard
    is_reversed: bool
    hash_digest: str


@dataclass(frozen=True)
class ReadingMetadata:
    """Metadata for a tarot reading."""
    timestamp: str
    seed_hash: str
    query: str


class TarotDeck:
    """Manages the 78-card Tarot deck."""
    
    MAJOR_ARCANA = [
        "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
        "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
        "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
        "The Devil", "The Tower", "The Star", "The Moon", "The Sun", 
        "Judgement", "The World"
    ]
    
    SUITS = ["Wands", "Cups", "Swords", "Pentacles"]
    RANKS = ["Ace"] + [str(n) for n in range(2, 11)] + ["Page", "Knight", "Queen", "King"]
    
    def __init__(self):
        self.cards: List[TarotCard] = self._build_deck()
    
    def _build_deck(self) -> List[TarotCard]:
        """Constructs the complete 78-card deck."""
        deck = []
        
        # Add Major Arcana
        for i, name in enumerate(self.MAJOR_ARCANA):
            deck.append(TarotCard(name=name, is_major=True, deck_position=i))
        
        # Add Minor Arcana
        position = len(self.MAJOR_ARCANA)
        for suit in self.SUITS:
            for rank in self.RANKS:
                name = f"{rank} of {suit}"
                deck.append(TarotCard(name=name, is_major=False, deck_position=position))
                position += 1
        
        return deck
    
    def __len__(self) -> int:
        return len(self.cards)
    
    def __getitem__(self, index: int) -> TarotCard:
        return self.cards[index]


class SpreadPositions:
    """Manages position labels for different spread types."""
    
    SINGLE_CARD = ["Message"]
    THREE_CARD = ["Past", "Present", "Future"]
    CELTIC_CROSS = [
        "Present (Significator)",
        "Challenge (Crossing)",
        "Subconscious (Below)",
        "Recent Past (Behind)",
        "Conscious (Above)",
        "Near Future (Before You)",
        "Self",
        "Environment",
        "Hopes & Fears",
        "Outcome"
    ]
    
    @classmethod
    def get_positions(cls, spread_type: SpreadType) -> List[str]:
        """Returns position labels for the given spread type."""
        return {
            SpreadType.SINGLE: cls.SINGLE_CARD,
            SpreadType.THREE_CARD: cls.THREE_CARD,
            SpreadType.CELTIC_CROSS: cls.CELTIC_CROSS
        }[spread_type]


class ProtectiveHasher:
    """Handles cryptographic operations for reading protection."""
    
    # Sacred number for protection iterations
    PROTECTION_ITERATIONS = 888_888
    HASH_LENGTH = 32
    
    @staticmethod
    def derive_protected_bytes(
        base_bytes: bytes, 
        salt_bytes: bytes, 
        iterations: int = None, 
        dklen: int = None
    ) -> bytes:
        """
        Derives protected bytes using PBKDF2-HMAC-SHA256.
        The high iteration count provides spiritual protection against interference.
        """
        iterations = iterations or ProtectiveHasher.PROTECTION_ITERATIONS
        dklen = dklen or ProtectiveHasher.HASH_LENGTH
        
        try:
            return hashlib.pbkdf2_hmac('sha256', base_bytes, salt_bytes, iterations, dklen=dklen)
        except Exception as e:
            # Fallback implementation (slower but functional)
            print(f"Warning: Using fallback hashing method: {e}", file=sys.stderr)
            result = base_bytes
            for _ in range(iterations):
                result = hashlib.sha256(result + salt_bytes).digest()
            return result[:dklen]
    
    @staticmethod
    def create_seed(query: str, timestamp: str) -> Tuple[bytes, str]:
        """Creates the base seed and its hex representation."""
        seed_string = f"{query}|{timestamp}"
        seed_bytes = hashlib.sha256(seed_string.encode("utf-8")).digest()
        seed_hex = seed_bytes.hex()
        return seed_bytes, seed_hex


class TarotReader:
    """Main tarot reading engine with protective hashing."""
    
    def __init__(self):
        self.deck = TarotDeck()
        self.hasher = ProtectiveHasher()
    
    def draw_cards(self, query: str, spread_type: SpreadType) -> Tuple[List[DrawnCard], ReadingMetadata]:
        """
        Draws cards for a reading with cryptographic protection.
        Each card is protected by 888,888 iterations of hashing.
        """
        # Generate timestamp and base seed
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        base_seed, seed_hex = self.hasher.create_seed(query, timestamp)
        
        # Track available cards (no duplicates in a spread)
        available_indices = list(range(len(self.deck)))
        drawn_cards = []
        
        for card_position in range(spread_type.value):
            # Create unique salt for each card position
            salt = f"card-{card_position}".encode("utf-8")
            
            # Apply protective hashing (888,888 iterations)
            protected_digest = self.hasher.derive_protected_bytes(base_seed, salt)
            
            # Select card from remaining pool
            selection_value = int.from_bytes(protected_digest[:8], "big")
            selected_index = selection_value % len(available_indices)
            deck_position = available_indices.pop(selected_index)
            
            # Determine orientation (reversed if last byte is odd)
            is_reversed = (protected_digest[-1] & 1) == 1
            
            # Create drawn card
            drawn_card = DrawnCard(
                card=self.deck[deck_position],
                is_reversed=is_reversed,
                hash_digest=protected_digest.hex()
            )
            drawn_cards.append(drawn_card)
        
        metadata = ReadingMetadata(
            timestamp=timestamp,
            seed_hash=seed_hex[:16] + "…",
            query=query
        )
        
        return drawn_cards, metadata


class ReadingDisplay:
    """Handles the display of tarot readings."""
    
    @staticmethod
    def print_rich(
        drawn_cards: List[DrawnCard], 
        metadata: ReadingMetadata, 
        spread_type: SpreadType
    ):
        """Displays reading using rich formatting."""
        positions = SpreadPositions.get_positions(spread_type)
        
        # Header
        title = f"Tarot Reading • {spread_type.value}-Card Spread"
        subtitle = f'Query: "{metadata.query}"  •  UTC: {metadata.timestamp}  •  Seed: {metadata.seed_hash}'
        
        console.print(Panel.fit(
            Text(title, style="bold magenta"), 
            subtitle=subtitle, 
            border_style="magenta"
        ))
        
        # Table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Position", style="cyan", no_wrap=True)
        table.add_column("Card", style="bold white")
        table.add_column("Orientation", style="yellow")
        
        for drawn_card, position_label in zip(drawn_cards, positions):
            card_style = "bright_white" if drawn_card.card.is_major else "white"
            orient_style = "red" if drawn_card.is_reversed else "green"
            orientation = "Reversed" if drawn_card.is_reversed else "Upright"
            
            table.add_row(
                f"[cyan]{position_label}[/cyan]",
                f"[{card_style}]{drawn_card.card.name}[/{card_style}]",
                f"[{orient_style}]{orientation}[/{orient_style}]"
            )
        
        console.print(table)
        console.print()
        console.rule("[magenta]May the right paws receive the right message[/magenta]")
    
    @staticmethod
    def print_plain(
        drawn_cards: List[DrawnCard], 
        metadata: ReadingMetadata, 
        spread_type: SpreadType
    ):
        """Displays reading using plain text formatting."""
        positions = SpreadPositions.get_positions(spread_type)
        
        title = f"Tarot Reading • {spread_type.value}-Card Spread"
        subtitle = f'Query: "{metadata.query}"  •  UTC: {metadata.timestamp}  •  Seed: {metadata.seed_hash}'
        
        print(title)
        print(subtitle)
        print("=" * 72)
        
        for drawn_card, position_label in zip(drawn_cards, positions):
            orientation = "Reversed" if drawn_card.is_reversed else "Upright"
            print(f"{position_label:>25}: {drawn_card.card.name}  —  {orientation}")
        
        print("=" * 72)
        print("May the right paws receive the right message")


class TarotApp:
    """Main application controller."""
    
    def __init__(self):
        self.reader = TarotReader()
        self.display = ReadingDisplay()
    
    def perform_reading(self, query: str, spread_choice: str):
        """Performs and displays a tarot reading."""
        # Validate spread choice
        try:
            spread_map = {"1": SpreadType.SINGLE, "3": SpreadType.THREE_CARD, "10": SpreadType.CELTIC_CROSS}
            spread_type = spread_map[spread_choice.strip()]
        except KeyError:
            raise ValueError("Spread must be 1, 3, or 10.")
        
        # Draw cards
        drawn_cards, metadata = self.reader.draw_cards(query, spread_type)
        
        # Display reading
        if RICH_AVAILABLE:
            self.display.print_rich(drawn_cards, metadata, spread_type)
        else:
            self.display.print_plain(drawn_cards, metadata, spread_type)
    
    def run_interactive(self):
        """Runs the interactive CLI mode."""
        print("Welcome to Anthro Tarot 🐾")
        
        query = input("Ask your sacred question: ").strip()
        if not query:
            raise ValueError("A question is required for the reading.")
        
        print("\nChoose your spread:")
        print("  1: Single Card")
        print("  3: Three Card (Past/Present/Future)")
        print(" 10: Celtic Cross")
        
        spread = input("\nYour choice (1/3/10): ").strip()
        print()
        
        self.perform_reading(query, spread)
    
    def run_piped(self, args: List[str]):
        """Runs in piped mode (non-interactive)."""
        if not args:
            raise SystemExit("Usage: echo \"question\" | python tarot_reader.py <1|3|10>")
        
        spread = args[0]
        query = sys.stdin.read().strip()
        
        if not query:
            raise ValueError("A question is required for the reading.")
        
        self.perform_reading(query, spread)


def main():
    """Main entry point."""
    app = TarotApp()
    
    try:
        if sys.stdin.isatty():
            app.run_interactive()
        else:
            app.run_piped(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n\nReading canceled. Stay cozy, packmate. 🐺")
        sys.exit(0)
    except (ValueError, SystemExit) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()