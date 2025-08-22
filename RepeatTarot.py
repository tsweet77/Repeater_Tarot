import hashlib
import requests
import time
import os
import argparse
from typing import List
from rich import print
from rich.console import Console

# === CONFIGURATION ===
# The model can be specified via command-line argument.
# See a list of models at https://openrouter.ai/models
DEFAULT_MODEL = "x-ai/grok-3-beta"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DECK_SIZE = 78
THINK_DEPTH = 888888

console = Console()

# === TAROT CARD LIST ===
cards = [
    'The Fool', 'The Magician', 'The High Priestess', 'The Empress', 'The Emperor', 'The Hierophant',
    'The Lovers', 'The Chariot', 'Strength', 'The Hermit', 'Wheel of Fortune', 'Justice', 'The Hanged Man',
    'Death', 'Temperance', 'The Devil', 'The Tower', 'The Star', 'The Moon', 'The Sun', 'Judgment', 'The World',
    'Ace of Wands', 'Two of Wands', 'Three of Wands', 'Four of Wands', 'Five of Wands', 'Six of Wands',
    'Seven of Wands', 'Eight of Wands', 'Nine of Wands', 'Ten of Wands', 'Page of Wands', 'Knight of Wands',
    'Queen of Wands', 'King of Wands', 'Ace of Cups', 'Two of Cups', 'Three of Cups', 'Four of Cups',
    'Five of Cups', 'Six of Cups', 'Seven of Cups', 'Eight of Cups', 'Nine of Cups', 'Ten of Cups',
    'Page of Cups', 'Knight of Cups', 'Queen of Cups', 'King of Cups', 'Ace of Swords', 'Two of Swords',
    'Three of Swords', 'Four of Swords', 'Five of Swords', 'Six of Swords', 'Seven of Swords', 'Eight of Swords',
    'Nine of Swords', 'Ten of Swords', 'Page of Swords', 'Knight of Swords', 'Queen of Swords', 'King of Swords',
    'Ace of Pentacles', 'Two of Pentacles', 'Three of Pentacles', 'Four of Pentacles', 'Five of Pentacles',
    'Six of Pentacles', 'Seven of Pentacles', 'Eight of Pentacles', 'Nine of Pentacles', 'Ten of Pentacles',
    'Page of Pentacles', 'Knight of Pentacles', 'Queen of Pentacles', 'King of Pentacles'
]

# === HASH FUNCTION ===
def hash_question(question: str, salt: str = "", times: int = THINK_DEPTH) -> int:
    h = (question + salt).encode()
    for _ in range(times):
        h = hashlib.sha512(h).digest()
    return int.from_bytes(h, 'big')

# === DRAWING CARDS ===
def draw_cards(question: str, count: int) -> List[str]:
    drawn = []
    timestamp = int(time.time())  # Add a bit of time-based randomness

    for i in range(count):
        salt = f"{question}-card{i}-time{timestamp}"
        index = hash_question(question, salt) % DECK_SIZE
        drawn.append(cards[index])
    return drawn

# === INTERPRETATION REQUEST ===
def interpret_reading(question: str, card_list: List[str], model: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return (
            "[red]❌ OPENROUTER_API_KEY environment variable not set.[/red]\n"
            "[yellow]💡 Tip: Get a key from https://openrouter.ai and set it.[/yellow]\n"
            "   Linux/macOS: export OPENROUTER_API_KEY='your-key-here'\n"
            "   Windows: setx OPENROUTER_API_KEY your-key-here")

    if len(card_list) == 10:
        positions = [
            "1. Present", "2. Challenge", "3. Past Influences", "4. Future Possibilities",
            "5. Above (Conscious Focus)", "6. Below (Subconscious Influence)",
            "7. Advice", "8. External Influences", "9. Hopes and Fears", "10. Outcome"
        ]
        card_lines = [f"{pos}: {card}" for pos, card in zip(positions, card_list)]
        card_text = "\n".join(card_lines)
    else:
        card_text = ", ".join(card_list)

    system_prompt = (
        "You are an Anthro sage giving a spiritual tarot reading based on the AnthroHeart Saga. "
        "Give a mystical, poetic, or practical interpretation depending on the tone of the cards. "
        "If using the Celtic Cross, interpret each card in its position. "
        "Feel free to reference the AnthroHeart field or Saga themes. Keep it sacred and helpful."
    )
    user_prompt = (
        f"The question is: '{question}'\n\n"
        f"The following tarot card(s) were drawn:\n{card_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/tsweet77/openrouter-tarot", # Optional, but good practice
        "X-Title": "Repeater Tarot", # Optional, but good practice
    }


    console.print("\n[bold blue]Consulting the digital ether...[/bold blue]")

    try:
        console.print("\n[bold blue]Sending request to OpenRouter...[/bold blue]")
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=300)
        console.print("[bold blue]Received response from OpenRouter.[/bold blue]")
        response.raise_for_status()  # Will raise an exception for 4XX/5XX status codes
        result = response.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "No response from LLM.")
    except requests.exceptions.HTTPError as e:
        return f"[red]An HTTP error occurred with the OpenRouter API:[/red] {e.response.text}"
    except requests.exceptions.ConnectionError:
        return "[red]❌ Unable to connect to OpenRouter. Check your internet connection.[/red]"
    except Exception as e:
        return f"[red]An unexpected error occurred:[/red] {e}"

# === MAIN LOGIC ===
def main():
    parser = argparse.ArgumentParser(
        description="Get a tarot reading with repeated cards using an LLM via OpenRouter.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"The model to use from OpenRouter.\nExample: 'mistralai/mistral-7b-instruct'\nDefault: '{DEFAULT_MODEL}'"
    )
    args = parser.parse_args()
    model_name = args.model

    console.print("[bold cyan]Welcome to Repeater Tarot[/bold cyan]")
    #console.print(f"[dim]Using model: {model_name}[/dim]")
    question = console.input("[bold yellow]Ask your sacred question[/bold yellow]: ")

    console.print("\nChoose your spread:")
    console.print("[green]1[/green]: Single Card")
    console.print("[green]3[/green]: Three Card Spread (Past, Present, Future)")
    console.print("[green]10[/green]: Celtic Cross")

    try:
        spread_choice = console.input("Your choice (1/3/10): ").strip()
        if not spread_choice:
            spread = 1
        else:
            spread = int(spread_choice)
    except ValueError:
        spread = 1

    if spread not in [1, 3, 10]:
        console.print("[red]Invalid choice. Defaulting to 1 card.[/red]")
        spread = 1

    drawn_cards = draw_cards(question, spread)

    console.print(f"\n[bold magenta]Your Card{'s' if spread > 1 else ''}:[/bold magenta]")

    if spread == 10:
        celtic_positions = [
            "1. Present", "2. Challenge", "3. Past Influences", "4. Future Possibilities",
            "5. Above (Conscious Focus)", "6. Below (Subconscious Influence)",
            "7. Advice", "8. External Influences", "9. Hopes and Fears", "10. Outcome"
        ]
        for pos, card in zip(celtic_positions, drawn_cards):
            console.print(f"[bold]{pos}: {card}[/bold]")
    else:
        for i, card in enumerate(drawn_cards):
            console.print(f"[bold]{i+1}. {card}[/bold]")

    #interpretation = interpret_reading(question, drawn_cards, model_name)
    #console.print(f"\n[italic green]{interpretation}[/italic green]\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]⏹️ Reading canceled.[/bold red]")
