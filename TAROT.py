#!/usr/bin/env python3
"""
TAROT.py
Deterministic Tarot with reversals and color output.
Interactive multi-card selection based on cryptographic hashing.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict
import hashlib
import sys
import random
import argparse

# ----- Optional color UI via rich -----
try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ----- Constants and Configuration -----
@dataclass(frozen=True)
class TarotCard:
    name: str
    is_major: bool
    deck_position: int

@dataclass(frozen=True)
class DrawnCard:
    card: TarotCard
    is_reversed: bool
    hash_digest: str

class TarotDeck:
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
        deck = []
        for i, name in enumerate(self.MAJOR_ARCANA):
            deck.append(TarotCard(name=name, is_major=True, deck_position=i))
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

class ProtectiveHasher:
    PROTECTION_ITERATIONS = 888_888
    HASH_LENGTH = 32

    @staticmethod
    def derive_protected_bytes(base_bytes: bytes, salt_bytes: bytes) -> bytes:
        try:
            return hashlib.pbkdf2_hmac(
                'sha256', base_bytes, salt_bytes,
                ProtectiveHasher.PROTECTION_ITERATIONS,
                dklen=ProtectiveHasher.HASH_LENGTH
            )
        except Exception as e:
            print(f"Warning: Using fallback hashing method: {e}", file=sys.stderr)
            result = base_bytes
            for _ in range(ProtectiveHasher.PROTECTION_ITERATIONS):
                result = hashlib.sha256(result + salt_bytes).digest()
            return result[:ProtectiveHasher.HASH_LENGTH]

    @staticmethod
    def create_seed(query: str) -> Tuple[bytes, str]:
        seed_bytes = hashlib.sha256(query.encode("utf-8")).digest()
        seed_hex = seed_bytes.hex()
        return seed_bytes, seed_hex

class TarotReader:
    def __init__(self):
        self.deck = TarotDeck()
        self.hasher = ProtectiveHasher()

    def prepare_interactive_deck(self, query: str, reversals_enabled: bool) -> Dict[str, DrawnCard]:
        base_seed, _ = self.hasher.create_seed(query)
        rng = random.Random(base_seed)

        card_indices = list(range(len(self.deck)))
        if reversals_enabled:
            hash_pool_indices = card_indices * 2
        else:
            hash_pool_indices = card_indices
        rng.shuffle(hash_pool_indices)

        interactive_deck: Dict[str, DrawnCard] = {}
        total_hashes = len(hash_pool_indices)

        for i, deck_position in enumerate(hash_pool_indices):
            print(f"Calculating hash {i+1}/{total_hashes}...", end='\r', file=sys.stderr)
            salt = f"card-{i}".encode("utf-8")
            protected_digest = self.hasher.derive_protected_bytes(base_seed, salt)

            is_reversed = ((protected_digest[-1] & 1) == 1) and reversals_enabled
            hash_hex = protected_digest.hex()

            drawn_card = DrawnCard(
                card=self.deck[deck_position],
                is_reversed=is_reversed,
                hash_digest=hash_hex
            )
            interactive_deck[hash_hex[:8]] = drawn_card
        print(file=sys.stderr)

        return interactive_deck

class TarotApp:
    POSITION_LABELS_3 = ["Past", "Present", "Future"]
    POSITION_LABELS_10 = [
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

    def __init__(self, reversals_enabled: bool):
        self.reader = TarotReader()
        self.reversals_enabled = reversals_enabled

    def display_card(self, card: DrawnCard, choice: str, index: int, label: str = None):
        orientation = "Reversed" if card.is_reversed else "Upright"
        label_prefix = f"{label}: " if label else ""
        if RICH_AVAILABLE:
            card_style = "bright_white" if card.card.is_major else "white"
            orient_style = "red" if card.is_reversed else "green"
            console.print(
                f"Card #{index+1} ([yellow]{choice}[/yellow]): {label_prefix}[{card_style}]{card.card.name}[/{card_style}] - [{orient_style}]{orientation}[/{orient_style}]"
            )
        else:
            print(f"Card #{index+1} ({choice}): {label_prefix}{card.card.name} - {orientation}")

    def display_overview(self, drawn_cards: List[DrawnCard], query: str, num_cards: int):
        print("\n--- Reading Overview ---")
        if not drawn_cards:
            print("No cards were drawn.")
            return

        if RICH_AVAILABLE:
            table = Table(title="Your Tarot Reading", caption=f"For your query: \"{query}\"")
            table.add_column("#", justify="right", style="cyan")
            table.add_column("Position", style="cyan")
            table.add_column("Card", style="magenta")
            table.add_column("Orientation", style="green")

            labels = []
            if num_cards == 3:
                labels = self.POSITION_LABELS_3
            elif num_cards == 10:
                labels = self.POSITION_LABELS_10

            for i, drawn_card in enumerate(drawn_cards):
                orientation = "Reversed" if drawn_card.is_reversed else "Upright"
                orient_style = "red" if drawn_card.is_reversed else "green"
                label = labels[i] if i < len(labels) else ""
                table.add_row(
                    str(i + 1),
                    label,
                    drawn_card.card.name,
                    f"[{orient_style}]{orientation}[/{orient_style}]"
                )
            console.print(table)
        else:
            print(f"For your query: \"{query}\" ")
            labels = []
            if num_cards == 3:
                labels = self.POSITION_LABELS_3
            elif num_cards == 10:
                labels = self.POSITION_LABELS_10

            for i, drawn_card in enumerate(drawn_cards):
                orientation = "Reversed" if drawn_card.is_reversed else "Upright"
                label = labels[i] if i < len(labels) else ""
                print(f"{i+1}. {label}: {drawn_card.card.name} - {orientation}")

    def run_interactive(self):
        print("Welcome to Anthro Tarot 🐾")
        if self.reversals_enabled:
            print("Reversals are ENABLED.")
        query = input("Ask your sacred question to generate the deck: ").strip()
        if not query:
            raise ValueError("A question is required for the reading.")

        print("\nGenerating your protected deck...")
        interactive_deck = self.reader.prepare_interactive_deck(query, self.reversals_enabled)
        available_hashes = list(interactive_deck.keys())

        while True:
            try:
                num_cards_str = input("How many cards to draw? (1, 3, or 10): ").strip()
                num_cards = int(num_cards_str)
                if num_cards not in [1, 3, 10]:
                    raise ValueError
                break
            except ValueError:
                print("Invalid input. Please enter 1, 3, or 10.")

        print(f"\nThe deck is ready. Choose {num_cards} hashes to reveal your cards.")
        print("\nAvailable Hashes:")
        cols = 4
        for i in range(0, len(available_hashes), cols):
            print("  ".join(f"[{h}]" for h in available_hashes[i:i + cols]))

        while True:
            choices_str = input(f"\nEnter {num_cards} hash prefixes (3+ chars), separated by commas: ").strip()
            choices = [c.strip().lower() for c in choices_str.split(',') if c.strip()]
            
            if len(choices) != num_cards:
                print(f"Please enter exactly {num_cards} comma-separated hashes.")
                continue

            invalid_choices = [c for c in choices if len(c) < 3]
            if invalid_choices:
                print("Error: All hash prefixes must be at least 3 characters long.")
                print(f"Invalid prefixes: {', '.join(invalid_choices)}")
                continue
            
            break

        drawn_cards: List[DrawnCard] = []
        print("\n--- Your Revealed Cards ---")
        for i, choice in enumerate(choices):
            matches = [h for h in available_hashes if h.startswith(choice)]
            if len(matches) == 1:
                chosen_hash = matches[0]
                card_to_reveal = interactive_deck[chosen_hash]
                label = None
                if num_cards == 3:
                    label = self.POSITION_LABELS_3[i]
                elif num_cards == 10:
                    label = self.POSITION_LABELS_10[i]
                self.display_card(card_to_reveal, chosen_hash, i, label)
                drawn_cards.append(card_to_reveal)
                available_hashes.remove(chosen_hash)
            elif len(matches) > 1:
                print(f"Card #{i+1}: Ambiguous choice '{choice}'. Multiple hashes match. Reading cannot continue.")
                return
            else:
                print(f"Card #{i+1}: Invalid choice '{choice}'. No matching hash found. Reading cannot continue.")
                return

        self.display_overview(drawn_cards, query, num_cards)

def main():
    parser = argparse.ArgumentParser(
        description="Deterministic Tarot with reversals and color output.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-r', '--reversals',
        action='store_true',
        help='Enable card reversals, doubling the hash pool.'
    )
    args = parser.parse_args()

    app = TarotApp(reversals_enabled=args.reversals)
    try:
        app.run_interactive()
    except KeyboardInterrupt:
        print("\n\nReading canceled.")
        sys.exit(0)
    except (ValueError, SystemExit) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
