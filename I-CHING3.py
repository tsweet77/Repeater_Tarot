#!/usr/bin/env python3
"""
I-CHING.py — Secure deterministic I-Ching divination via cryptographic hashing.

This implementation uses the three-coin method with PBKDF2 key derivation to ensure
deterministic, repeatable results while maintaining cryptographic security against
interference. The high iteration count (888,888) provides strong entropy mixing.

Usage:
    python3 i-ching.py -q "Your question here"
    python3 i-ching.py  # Interactive mode
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from enum import IntEnum

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Pretty output support
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logger.info("Rich library not available. Using plain text output.")

# === Security Configuration ===
# High iteration count prevents rainbow table attacks and ensures thorough entropy mixing
PBKDF2_ITERATIONS = 888_888  # Numerologically significant (8 = prosperity in Chinese culture)
DERIVED_KEY_LENGTH = 32  # 256 bits

# === I-Ching Constants ===
class LineValue(IntEnum):
    """Three-coin method line values."""
    OLD_YIN = 6      # ⚊⚊ → ⚋⚋ (changing yin to yang)
    YOUNG_YANG = 7   # ⚋⚋ (stable yang)
    YOUNG_YIN = 8    # ⚊⚊ (stable yin)
    OLD_YANG = 9     # ⚋⚋ → ⚊⚊ (changing yang to yin)

# === Complete 64 Hexagrams Database ===
# King Wen sequence with full metadata
HEXAGRAM_DATABASE: Dict[Tuple[str, str], Dict[str, Any]] = {
    # Format: (lower_trigram, upper_trigram): {metadata}
    ("☰", "☰"): {
        "number": 1,
        "name": "Qian / The Creative",
        "chinese": "乾",
        "judgement": "The Creative works sublime success, furthering through perseverance.",
        "image": "Heaven above Heaven: The movement of heaven is full of power. Thus the superior man makes himself strong and untiring.",
        "lines": [
            "Hidden dragon. Do not act.",
            "Dragon appearing in the field. It furthers one to see the great man.",
            "All day long the superior man is creatively active. At nightfall his mind is still beset with cares. Danger. No blame.",
            "Wavering flight over the depths. No blame.",
            "Flying dragon in the heavens. It furthers one to see the great man.",
            "Arrogant dragon will have cause to repent."
        ]
    },
    ("☷", "☷"): {
        "number": 2,
        "name": "Kun / The Receptive",
        "chinese": "坤",
        "judgement": "The Receptive brings about sublime success, furthering through the perseverance of a mare.",
        "image": "Earth above Earth: The earth's condition is receptive devotion. Thus the superior man who has breadth of character carries the outer world.",
        "lines": [
            "When there is hoarfrost underfoot, solid ice is not far off.",
            "Straight, square, great. Without purpose, yet nothing remains unfurthered.",
            "Hidden lines. One is able to remain persevering. If by chance you are in the service of a king, seek not works, but bring to completion.",
            "A tied-up sack. No blame, no praise.",
            "A yellow lower garment brings supreme good fortune.",
            "Dragons fight in the meadow. Their blood is black and yellow."
        ]
    },
    ("☵", "☳"): {
        "number": 3,
        "name": "Zhun / Difficulty at the Beginning",
        "chinese": "屯",
        "judgement": "Difficulty at the Beginning works supreme success, furthering through perseverance. Nothing should be undertaken. It furthers one to appoint helpers.",
        "image": "Clouds and Thunder: Difficulty at the Beginning. Thus the superior man brings order out of confusion.",
        "lines": [
            "Hesitation and hindrance. It furthers one to remain persevering. It furthers one to appoint helpers.",
            "Difficulties pile up. Horse and wagon part. He is not a robber; He wants to woo when the time comes. The maiden is chaste, she does not pledge herself. Ten years—then she pledges herself.",
            "Whoever hunts deer without the forester only loses his way in the forest. The superior man understands the signs of the time and prefers to desist. To go on brings humiliation.",
            "Horse and wagon part. Strive for union. To go brings good fortune. Everything acts to further.",
            "Difficulties in blessing. A little perseverance brings good fortune. Great perseverance brings misfortune.",
            "Horse and wagon part. Bloody tears flow."
        ]
    },
    ("☶", "☵"): {
        "number": 4,
        "name": "Meng / Youthful Folly",
        "chinese": "蒙",
        "judgement": "Youthful Folly has success. It is not I who seek the young fool; The young fool seeks me. At the first oracle I inform him. If he asks two or three times, it is importunity. If he importunes, I give him no information. Perseverance furthers.",
        "image": "A spring wells up at the foot of the mountain: The image of Youth. Thus the superior man fosters his character by thoroughness in all that he does.",
        "lines": [
            "To make a fool develop, it furthers one to apply discipline. The fetters should be removed. To go on in this way brings humiliation.",
            "To bear with fools in kindliness brings good fortune. To know how to take women brings good fortune. The son is capable of taking charge of the household.",
            "Take not a maiden who, when she sees a man of bronze, loses possession of herself. Nothing furthers.",
            "Entangled folly brings humiliation.",
            "Childlike folly brings good fortune.",
            "In punishing folly it does not further one to commit transgressions. The only thing that furthers is to prevent transgressions."
        ]
    },
    ("☵", "☰"): {
        "number": 5,
        "name": "Xu / Waiting (Nourishment)",
        "chinese": "需",
        "judgement": "Waiting. If you are sincere, you have light and success. Perseverance brings good fortune. It furthers one to cross the great water.",
        "image": "Clouds rise up to heaven: The image of Waiting. Thus the superior man eats and drinks, is joyous and of good cheer.",
        "lines": [
            "Waiting in the meadow. It furthers one to abide in what endures. No blame.",
            "Waiting on the sand. There is some gossip. The end brings good fortune.",
            "Waiting in the mud brings about the arrival of the enemy.",
            "Waiting in blood. Get out of the pit.",
            "Waiting at meat and drink. Perseverance brings good fortune.",
            "One falls into the pit. Three uninvited guests arrive. Honor them, and in the end there will be good fortune."
        ]
    },
    ("☰", "☵"): {
        "number": 6,
        "name": "Song / Conflict",
        "chinese": "訟",
        "judgement": "Conflict. You are sincere and are being obstructed. A cautious halt halfway brings good fortune. Going through to the end brings misfortune. It furthers one to see the great man. It does not further one to cross the great water.",
        "image": "Heaven and Water go their opposite ways: The image of Conflict. Thus in all his transactions the superior man carefully considers the beginning.",
        "lines": [
            "If one does not perpetuate the affair, there is a little gossip. In the end, good fortune comes.",
            "One cannot engage in conflict; one returns home, gives way. The people of his town, three hundred households, remain free of guilt.",
            "To nourish oneself on ancient virtue induces perseverance. Danger. In the end, good fortune comes. If by chance you are in the service of a king, seek not works.",
            "One cannot engage in conflict. One turns back and submits to fate, changes one's attitude, and finds peace in perseverance. Good fortune.",
            "To contend before him brings supreme good fortune.",
            "Even if by chance a leather belt is bestowed on one, by the end of a morning it will have been snatched away three times."
        ]
    },
    ("☷", "☵"): {
        "number": 7,
        "name": "Shi / The Army",
        "chinese": "師",
        "judgement": "The Army. The army needs perseverance and a strong man. Good fortune without blame.",
        "image": "In the middle of the earth is water: The image of the Army. Thus the superior man increases his masses by generosity toward the people.",
        "lines": [
            "An army must set forth in proper order. If the order is not good, misfortune threatens.",
            "In the midst of the army. Good fortune. No blame. The king bestows a triple decoration.",
            "Perchance the army carries corpses in the wagon. Misfortune.",
            "The army retreats. No blame.",
            "There is game in the field. It furthers one to catch it. Without blame. Let the eldest lead the army. The younger transports corpses; then perseverance brings misfortune.",
            "The great prince issues commands, founds states, vests families with fiefs. Inferior people should not be employed."
        ]
    },
    ("☵", "☷"): {
        "number": 8,
        "name": "Bi / Holding Together (Union)",
        "chinese": "比",
        "judgement": "Holding Together brings good fortune. Inquire of the oracle once again whether you possess sublimity, constancy, and perseverance; then there is no blame. Those who are uncertain gradually join. Whoever comes too late meets with misfortune.",
        "image": "On the earth is water: The image of Holding Together. Thus the kings of antiquity bestowed the different states as fiefs and cultivated friendly relations with the feudal lords.",
        "lines": [
            "Hold to him in truth and loyalty; this is without blame. Truth, like a full earthen bowl: Thus in the end good fortune comes from without.",
            "Hold to him inwardly. Perseverance brings good fortune.",
            "You hold together with the wrong people.",
            "Hold to him outwardly also. Perseverance brings good fortune.",
            "Manifestation of holding together. In the hunt the king uses beaters on three sides only and foregoes game that runs off in front. The citizens need no warning. Good fortune.",
            "He finds no head for holding together. Misfortune."
        ]
    },
    ("☴", "☰"): {
        "number": 9,
        "name": "Xiao Chu / The Taming Power of the Small",
        "chinese": "小畜",
        "judgement": "The Taming Power of the Small has success. Dense clouds, no rain from our western region.",
        "image": "The wind drives across heaven: The image of The Taming Power of the Small. Thus the superior man refines the outward aspect of his nature.",
        "lines": [
            "Return to the way. How could there be blame in this? Good fortune.",
            "He allows himself to be drawn into returning. Good fortune.",
            "The spokes burst out of the wagon wheels. Man and wife roll their eyes.",
            "If you are sincere, blood vanishes and fear gives way. No blame.",
            "If you are sincere and loyally attached, you are rich in your neighbor.",
            "The rain comes, there is rest. This is due to the lasting effect of character. Perseverance brings the woman into danger. The moon is nearly full. If the superior man persists, misfortune comes."
        ]
    },
    ("☰", "☱"): {
        "number": 10,
        "name": "Lu / Treading (Conduct)",
        "chinese": "履",
        "judgement": "Treading. Treading upon the tail of the tiger. It does not bite the man. Success.",
        "image": "Heaven above, the lake below: The image of Treading. Thus the superior man discriminates between high and low, and thereby fortifies the thinking of the people.",
        "lines": [
            "Simple conduct. Progress without blame.",
            "Treading a smooth, level course. The perseverance of a dark man brings good fortune.",
            "A one-eyed man is able to see, a lame man is able to tread. He treads on the tail of the tiger. The tiger bites the man. Misfortune. Thus does a warrior act on behalf of his great prince.",
            "He treads on the tail of the tiger. Caution and circumspection lead ultimately to good fortune.",
            "Resolute conduct. Perseverance with awareness of danger.",
            "Look to your conduct and weigh the favorable signs. When everything is fulfilled, supreme good fortune comes."
        ]
    },
    ("☷", "☰"): {
        "number": 11,
        "name": "Tai / Peace",
        "chinese": "泰",
        "judgement": "Peace. The small departs, the great approaches. Good fortune. Success.",
        "image": "Heaven and earth unite: the image of Peace. Thus the ruler divides and completes the course of heaven and earth; he furthers and regulates the gifts of heaven and earth, and so aids the people.",
        "lines": [
            "When ribbon grass is pulled up, the sod comes with it. Each according to his kind. Undertakings bring good fortune.",
            "Bearing with the uncultured in gentleness, fording the river with resolution, not neglecting what is distant, not regarding one's companions: thus one may manage to walk in the middle.",
            "No plain not followed by a slope. No going not followed by a return. He who remains persevering in danger is without blame. Do not complain about this truth; enjoy the good fortune you still possess.",
            "He comes fluttering down, not boasting of his wealth, together with his neighbor, guileless and sincere.",
            "The sovereign I gives his daughter in marriage. This brings blessing and supreme good fortune.",
            "The wall falls back into the moat. Use no army now. Make your commands known within your own town. Perseverance brings humiliation."
        ]
    },
    ("☰", "☷"): {
        "number": 12,
        "name": "Pi / Standstill (Stagnation)",
        "chinese": "否",
        "judgement": "Standstill. Evil people do not further the perseverance of the superior man. The great departs; the small approaches.",
        "image": "Heaven and earth do not unite: The image of Standstill. Thus the superior man falls back upon his inner worth in order to escape the difficulties. He does not permit himself to be honored with revenue.",
        "lines": [
            "When ribbon grass is pulled up, the sod comes with it. Each according to his kind. Perseverance brings good fortune and success.",
            "They bear and endure; this means good fortune for inferior people. The standstill serves to help the great man to attain success.",
            "They bear shame.",
            "He who acts at the command of the highest remains without blame. Those of like mind partake of the blessing.",
            "Standstill is giving way. Good fortune for the great man. What if it should fail, what if it should fail? In this way he ties it to a cluster of mulberry shoots.",
            "The standstill comes to an end. First standstill, then good fortune."
        ]
    },
    ("☰", "☲"): {
        "number": 13,
        "name": "Tong Ren / Fellowship with Men",
        "chinese": "同人",
        "judgement": "Fellowship with Men in the open. Success. It furthers one to cross the great water. The perseverance of the superior man furthers.",
        "image": "Heaven together with fire: The image of Fellowship with Men. Thus the superior man organizes the clans and makes distinctions between things.",
        "lines": [
            "Fellowship with men at the gate. No blame.",
            "Fellowship with men in the clan. Humiliation.",
            "He hides weapons in the thicket; he climbs the high hill in front of it. For three years he does not rise up.",
            "He climbs up on his wall; he cannot attack. Good fortune.",
            "Men bound in fellowship first weep and lament, but afterward they laugh. After great struggles they succeed in meeting.",
            "Fellowship with men in the meadow. No remorse."
        ]
    },
    ("☲", "☰"): {
        "number": 14,
        "name": "Da You / Possession in Great Measure",
        "chinese": "大有",
        "judgement": "Possession in Great Measure. Supreme success.",
        "image": "Fire in heaven above: The image of Possession in Great Measure. Thus the superior man curbs evil and furthers good, and thereby obeys the benevolent will of heaven.",
        "lines": [
            "No relationship with what is harmful; there is no blame in this. If one remains conscious of difficulty, one remains without blame.",
            "A big wagon for loading. One may undertake something. No blame.",
            "A prince offers it to the Son of Heaven. A petty man cannot do this.",
            "He makes a difference between himself and his neighbor. No blame.",
            "He whose truth is accessible, yet dignified, has good fortune.",
            "He is blessed by heaven. Good fortune. Nothing that does not further."
        ]
    },
    ("☷", "☶"): {
        "number": 15,
        "name": "Qian / Modesty",
        "chinese": "謙",
        "judgement": "Modesty creates success. The superior man carries things through.",
        "image": "Within the earth, a mountain: The image of Modesty. Thus the superior man reduces that which is too much, and augments that which is too little. He weighs things and makes them equal.",
        "lines": [
            "A superior man modest about his modesty may cross the great water. Good fortune.",
            "Modesty that comes to expression. Perseverance brings good fortune.",
            "A superior man of modesty and merit carries things to conclusion. Good fortune.",
            "Nothing that would not further modesty in movement.",
            "No boasting of wealth before one's neighbor. It is favorable to attack with force. Nothing that would not further.",
            "Modesty that comes to expression. It is favorable to set armies marching to chastise one's own city and one's country."
        ]
    },
    ("☳", "☷"): {
        "number": 16,
        "name": "Yu / Enthusiasm",
        "chinese": "豫",
        "judgement": "Enthusiasm. It furthers one to install helpers and to set armies marching.",
        "image": "Thunder comes resounding out of the earth: The image of Enthusiasm. Thus the ancient kings made music in order to honor merit, and offered it with splendor to the Supreme Deity, inviting their ancestors to be present.",
        "lines": [
            "Enthusiasm that expresses itself brings misfortune.",
            "Firm as a rock. Not a whole day. Perseverance brings good fortune.",
            "Enthusiasm that looks upward creates remorse. Hesitation brings remorse.",
            "The source of enthusiasm. He achieves great things. Doubt not. You gather friends around you as a hair clasp gathers the hair.",
            "Persistently ill, and still does not die.",
            "Deluded enthusiasm. But if after completion one changes, there is no blame."
        ]
    },
    ("☱", "☳"): {
        "number": 17,
        "name": "Sui / Following",
        "chinese": "隨",
        "judgement": "Following has supreme success. Perseverance furthers. No blame.",
        "image": "Thunder in the middle of the lake: The image of Following. Thus the superior man at nightfall goes indoors for rest and recuperation.",
        "lines": [
            "The standard is changing. Perseverance brings good fortune. To go out of the door in company produces deeds.",
            "If one clings to the little boy, one loses the strong man.",
            "If one clings to the strong man, one loses the little boy. Through following one finds what one seeks. It furthers one to remain persevering.",
            "Following creates success. Perseverance brings misfortune. To go one's way with sincerity brings clarity. How could there be blame in this?",
            "Sincere in the good. Good fortune.",
            "He meets with firm allegiance and is still further bound. The king introduces him to the Western Mountain."
        ]
    },
    ("☶", "☴"): {
        "number": 18,
        "name": "Gu / Work on What Has Been Spoiled (Decay)",
        "chinese": "蠱",
        "judgement": "Work on What Has Been Spoiled has supreme success. It furthers one to cross the great water. Before the starting point, three days. After the starting point, three days.",
        "image": "The wind blows low on the mountain: The image of Decay. Thus the superior man stirs up the people and strengthens their spirit.",
        "lines": [
            "Setting right what has been spoiled by the father. If there is a son, no blame rests upon the departed father. Danger. In the end good fortune.",
            "Setting right what has been spoiled by the mother. One must not be too persevering.",
            "Setting right what has been spoiled by the father. There will be a little remorse. No great blame.",
            "Tolerating what has been spoiled by the father. In continuing one sees humiliation.",
            "Setting right what has been spoiled by the father. One meets with praise.",
            "He does not serve kings and princes, sets himself higher goals."
        ]
    },
    ("☷", "☱"): {
        "number": 19,
        "name": "Lin / Approach",
        "chinese": "臨",
        "judgement": "Approach has supreme success. Perseverance furthers. When the eighth month comes, there will be misfortune.",
        "image": "The earth above the lake: The image of Approach. Thus the superior man is inexhaustible in his will to teach, and without limits in his tolerance and protection of the people.",
        "lines": [
            "Joint approach. Perseverance brings good fortune.",
            "Joint approach. Good fortune. Everything furthers.",
            "Comfortable approach. Nothing that would further. If one is induced to grieve over it, one becomes free of blame.",
            "Complete approach. No blame.",
            "Wise approach. This is right for a great prince. Good fortune.",
            "Great-hearted approach. Good fortune. No blame."
        ]
    },
    ("☴", "☷"): {
        "number": 20,
        "name": "Guan / Contemplation (View)",
        "chinese": "觀",
        "judgement": "Contemplation. The ablution has been made, but not yet the offering. Full of trust they look up to him.",
        "image": "The wind blows over the earth: The image of Contemplation. Thus the kings of old visited the regions of the world, contemplated the people, and gave them instruction.",
        "lines": [
            "Boy-like contemplation. For an inferior man, no blame. For a superior man, humiliation.",
            "Contemplation through the crack of the door. Furthering for the perseverance of a woman.",
            "Contemplation of my life decides the choice between advance and retreat.",
            "Contemplation of the light of the kingdom. It furthers one to exert influence as the guest of a king.",
            "Contemplation of my life. The superior man is without blame.",
            "Contemplation of his life. The superior man is without blame."
        ]
    },
    ("☲", "☳"): {
        "number": 21,
        "name": "Shi He / Biting Through",
        "chinese": "噬嗑",
        "judgement": "Biting Through has success. It is favorable to let justice be administered.",
        "image": "Thunder and lightning: The image of Biting Through. Thus the kings of former times made firm the laws through clearly defined penalties.",
        "lines": [
            "His feet are fastened in the stocks, so that his toes disappear. No blame.",
            "Bites through tender meat, so that his nose disappears. No blame.",
            "Bites on old dried meat and strikes on something poisonous. Slight humiliation. No blame.",
            "Bites on dried gristly meat. Receives metal arrows. It furthers one to be mindful of difficulties and to be persevering. Good fortune.",
            "Bites on dried lean meat. Receives yellow gold. Perseveringly aware of danger. No blame.",
            "His neck is fastened in the wooden cangue, so that his ears disappear. Misfortune."
        ]
    },
    ("☶", "☲"): {
        "number": 22,
        "name": "Bi / Grace",
        "chinese": "賁",
        "judgement": "Grace has success. In small matters it is favorable to undertake something.",
        "image": "Fire at the foot of the mountain: The image of Grace. Thus does the superior man proceed when clearing up current affairs. But he dare not decide controversial issues in this way.",
        "lines": [
            "He lends grace to his toes, leaves the carriage, and walks.",
            "Lends grace to the beard on his chin.",
            "Graceful and moist. Constant perseverance brings good fortune.",
            "Grace or simplicity? A white horse comes as if on wings. He is not a robber, he will woo at the right time.",
            "Grace in hills and gardens. The roll of silk is meager and small. Humiliation, but in the end good fortune.",
            "Simple grace. No blame."
        ]
    },
    ("☶", "☷"): {
        "number": 23,
        "name": "Bo / Splitting Apart",
        "chinese": "剝",
        "judgement": "Splitting Apart. It does not further one to go anywhere.",
        "image": "The mountain rests on the earth: The image of Splitting Apart. Thus those above can ensure their position only by giving generously to those below.",
        "lines": [
            "The leg of the bed is split. Those who persevere are destroyed. Misfortune.",
            "The bed is split at the edge. Those who persevere are destroyed. Misfortune.",
            "He splits with them. No blame.",
            "The bed is split up to the skin. Misfortune.",
            "A shoal of fishes. Favor comes through the court ladies. Everything acts to further.",
            "There is a large fruit still uneaten. The superior man receives a carriage. The house of the inferior man is split apart."
        ]
    },
    ("☷", "☳"): {
        "number": 24,
        "name": "Fu / Return (The Turning Point)",
        "chinese": "復",
        "judgement": "Return. Success. Going out and coming in without error. Friends come without blame. To and fro goes the way. On the seventh day comes return. It furthers one to have somewhere to go.",
        "image": "Thunder within the earth: The image of the Turning Point. Thus the kings of antiquity closed the passes at the time of solstice. Merchants and strangers did not go about, and the ruler did not travel through the provinces.",
        "lines": [
            "Return from a short distance. No need for remorse. Great good fortune.",
            "Quiet return. Good fortune.",
            "Repeated return. Danger. No blame.",
            "Walking in the midst of others, one returns alone.",
            "Noble-hearted return. No remorse.",
            "Missing the return. Misfortune. Misfortune from within and without. If armies are set marching in this way, one will in the end suffer a great defeat, disastrous for the ruler of the country. For ten years it will not be possible to attack again."
        ]
    },
    ("☰", "☳"): {
        "number": 25,
        "name": "Wu Wang / Innocence (The Unexpected)",
        "chinese": "無妄",
        "judgement": "Innocence. Supreme success. Perseverance furthers. If someone is not as he should be, he has misfortune, and it does not further him to undertake anything.",
        "image": "Under heaven thunder rolls: All things attain the natural state of innocence. Thus the kings of old, rich in virtue, and in harmony with the time, fostered and nourished all beings.",
        "lines": [
            "Innocent behavior brings good fortune.",
            "If one does not count on the harvest while plowing, nor on the use of the ground while clearing it, it furthers one to undertake something.",
            "Undeserved misfortune. The cow that was tethered by someone is the wanderer's gain, the citizen's loss.",
            "He who can be persevering remains without blame.",
            "Use no medicine in an illness incurred through no fault of your own. It will pass of itself.",
            "Innocent action brings misfortune. Nothing furthers."
        ]
    },
    ("☶", "☰"): {
        "number": 26,
        "name": "Da Chu / The Taming Power of the Great",
        "chinese": "大畜",
        "judgement": "The Taming Power of the Great. Perseverance furthers. Not eating at home brings good fortune. It furthers one to cross the great water.",
        "image": "Heaven within the mountain: The image of The Taming Power of the Great. Thus the superior man acquaints himself with many sayings of antiquity and many deeds of the past, in order to strengthen his character thereby.",
        "lines": [
            "Danger is at hand. It furthers one to desist.",
            "The axletrees are taken from the wagon.",
            "A good horse that follows others. Awareness of danger, with perseverance, furthers. Practice chariot driving and armed defense daily. It furthers one to have somewhere to go.",
            "The headboard of a young bull. Great good fortune.",
            "The tusk of a gelded boar. Good fortune.",
            "One attains the way of heaven. Success."
        ]
    },
    ("☶", "☳"): {
        "number": 27,
        "name": "Yi / The Corners of the Mouth (Providing Nourishment)",
        "chinese": "頤",
        "judgement": "The Corners of the Mouth. Perseverance brings good fortune. Pay heed to the providing of nourishment and to what a man seeks to fill his own mouth with.",
        "image": "At the foot of the mountain, thunder: The image of Providing Nourishment. Thus the superior man is careful of his words and temperate in eating and drinking.",
        "lines": [
            "You let your magic tortoise go, and look at me with the corners of your mouth drooping. Misfortune.",
            "Turning to the summit for nourishment, deviating from the path to seek nourishment from the hill. Continuing to do this brings misfortune.",
            "Turning away from nourishment. Perseverance brings misfortune. Do not act thus for ten years. Nothing serves to further.",
            "Turning to the summit for provision of nourishment brings good fortune. Spying about with sharp eyes like a tiger with insatiable craving. No blame.",
            "Turning away from the path. To remain persevering brings good fortune. One should not cross the great water.",
            "The source of nourishment. Awareness of danger brings good fortune. It furthers one to cross the great water."
        ]
    },
    ("☱", "☴"): {
        "number": 28,
        "name": "Da Guo / Preponderance of the Great",
        "chinese": "大過",
        "judgement": "Preponderance of the Great. The ridgepole sags to the breaking point. It furthers one to have somewhere to go. Success.",
        "image": "The lake rises above the trees: The image of Preponderance of the Great. Thus the superior man, when he stands alone, is unconcerned, and if he has to renounce the world, he is undaunted.",
        "lines": [
            "To spread white rushes underneath. No blame.",
            "A dry poplar sprouts at the root. An older man takes a young wife. Everything furthers.",
            "The ridgepole sags to the breaking point. Misfortune.",
            "The ridgepole is braced. Good fortune. If there are ulterior motives, it is humiliating.",
            "A withered poplar puts forth flowers. An older woman takes a husband. No blame. No praise.",
            "One must go through the water. It goes over one's head. Misfortune. No blame."
        ]
    },
    ("☵", "☵"): {
        "number": 29,
        "name": "Kan / The Abysmal (Water)",
        "chinese": "坎",
        "judgement": "The Abysmal repeated. If you are sincere, you have success in your heart, and whatever you do succeeds.",
        "image": "Water flows on uninterruptedly and reaches its goal: The image of the Abysmal repeated. Thus the superior man walks in lasting virtue and carries on the business of teaching.",
        "lines": [
            "Repetition of the Abysmal. In the abyss one falls into a pit. Misfortune.",
            "The abyss is dangerous. One should strive to attain small things only.",
            "Forward and backward, abyss on abyss. In danger like this, pause at first and wait, otherwise you will fall into a pit in the abyss. Do not act.",
            "A jug of wine, a bowl of rice with it; earthen vessels simply handed in through the window. There is certainly no blame in this.",
            "The abyss is not filled to overflowing, it is filled only to the rim. No blame.",
            "Bound with cords and ropes, shut in between thorn-hedged prison walls: for three years one does not find the way. Misfortune."
        ]
    },
    ("☲", "☲"): {
        "number": 30,
        "name": "Li / The Clinging (Fire)",
        "chinese": "離",
        "judgement": "The Clinging. Perseverance furthers. It brings success. Care of the cow brings good fortune.",
        "image": "That which is bright rises twice: The image of Fire. Thus the great man, by perpetuating this brightness, illumines the four quarters of the world.",
        "lines": [
            "The footprints run crisscross. If one is seriously intent, no blame.",
            "Yellow light. Supreme good fortune.",
            "In the light of the setting sun, men either beat the pot and sing or loudly bewail the approach of old age. Misfortune.",
            "Its coming is sudden; it flames up, dies down, is thrown away.",
            "Tears in floods, sighing and lamenting. Good fortune.",
            "The king uses him to march forth and chastise. Then it is best to kill the leaders and take captive the followers. No blame."
        ]
    },
    ("☱", "☶"): {
        "number": 31,
        "name": "Xian / Influence (Wooing)",
        "chinese": "咸",
        "judgement": "Influence. Success. Perseverance furthers. To take a maiden to wife brings good fortune.",
        "image": "A lake on the mountain: The image of Influence. Thus the superior man encourages people to approach him by his readiness to receive them.",
        "lines": [
            "The influence shows itself in the big toe.",
            "The influence shows itself in the calves of the legs. Misfortune. Tarrying brings good fortune.",
            "The influence shows itself in the thighs. Holds to that which follows it. To continue is humiliating.",
            "Perseverance brings good fortune. Remorse disappears. If a man is agitated in mind, and his thoughts go hither and thither, only those friends on whom he fixes his conscious thoughts will follow.",
            "The influence shows itself in the back of the neck. No remorse.",
            "The influence shows itself in the jaws, cheeks, and tongue."
        ]
    },
    ("☳", "☴"): {
        "number": 32,
        "name": "Heng / Duration",
        "chinese": "恆",
        "judgement": "Duration. Success. No blame. Perseverance furthers. It furthers one to have somewhere to go.",
        "image": "Thunder and wind: the image of Duration. Thus the superior man stands firm and does not change his direction.",
        "lines": [
            "Seeking duration too hastily brings misfortune persistently. Nothing that would further.",
            "Remorse disappears.",
            "He who does not give duration to his character meets with disgrace. Persistent humiliation.",
            "No game in the field.",
            "Giving duration to one's character through perseverance. This is good fortune for a woman, misfortune for a man.",
            "Restlessness as an enduring condition brings misfortune."
        ]
    },
    ("☰", "☶"): {
        "number": 33,
        "name": "Dun / Retreat",
        "chinese": "遯",
        "judgement": "Retreat. Success. In what is small, perseverance furthers.",
        "image": "Mountain under heaven: the image of Retreat. Thus the superior man keeps the inferior man at a distance, not angrily but with reserve.",
        "lines": [
            "At the tail in retreat. This is dangerous. One must not wish to undertake anything.",
            "He holds him fast with yellow oxhide. No one can tear him loose.",
            "A halted retreat is nerve-wracking and dangerous. To retain people as men- and maidservants brings good fortune.",
            "Voluntary retreat brings good fortune to the superior man and downfall to the inferior man.",
            "Friendly retreat. Perseverance brings good fortune.",
            "Cheerful retreat. Everything serves to further."
        ]
    },
    ("☳", "☰"): {
        "number": 34,
        "name": "Da Zhuang / The Power of the Great",
        "chinese": "大壯",
        "judgement": "The Power of the Great. Perseverance furthers.",
        "image": "Thunder in heaven above: The image of The Power of the Great. Thus the superior man does not tread upon paths that do not accord with established order.",
        "lines": [
            "Power in the toes. Continuing brings misfortune. This is certainly true.",
            "Perseverance brings good fortune.",
            "The inferior man works through power. The superior man does not act thus. To continue is dangerous. A goat butts against a hedge and entangles its horns.",
            "Perseverance brings good fortune. Remorse disappears. The hedge opens; there is no entanglement. Power depends upon the axle of a big cart.",
            "Loses the goat with ease. No remorse.",
            "A goat butts against a hedge. It cannot go backward, it cannot go forward. Nothing serves to further. If one notes the difficulty, this brings good fortune."
        ]
    },
    ("☲", "☷"): {
        "number": 35,
        "name": "Jin / Progress",
        "chinese": "晉",
        "judgement": "Progress. The powerful prince is honored with horses in large numbers. In a single day he is granted audience three times.",
        "image": "The sun rises over the earth: The image of Progress. Thus the superior man himself brightens his bright virtue.",
        "lines": [
            "Progressing, but turned back. Perseverance brings good fortune. If one meets with no confidence, one should remain calm. No blame.",
            "Progressing, but in sorrow. Perseverance brings good fortune. Then one obtains great happiness from one's ancestress.",
            "All are in accord. Remorse disappears.",
            "Progress like a hamster. Perseverance brings danger.",
            "Remorse disappears. Take not gain and loss to heart. Undertakings bring good fortune. Everything serves to further.",
            "Making progress with the horns is permissible only for the purpose of punishing one's own city. To be conscious of danger brings good fortune. No blame. Perseverance brings humiliation."
        ]
    },
    ("☷", "☲"): {
        "number": 36,
        "name": "Ming Yi / Darkening of the Light",
        "chinese": "明夷",
        "judgement": "Darkening of the Light. In adversity it furthers one to be persevering.",
        "image": "The light has sunk into the earth: The image of Darkening of the Light. Thus does the superior man live with the great mass: He veils his light, yet still shines.",
        "lines": [
            "Darkening of the light during flight. He lowers his wings. The superior man does not eat for three days on his wanderings. But he has somewhere to go. The host has occasion to gossip about him.",
            "Darkening of the light injures him in the left thigh. He gives aid with the strength of a horse. Good fortune.",
            "Darkening of the light during the hunt in the south. Their great leader is captured. One must not expect perseverance too soon.",
            "He penetrates the left side of the belly. One gets at the very heart of the darkening of the light, and leaves gate and courtyard.",
            "Darkening of the light as with Prince Chi. Perseverance furthers.",
            "Not light but darkness. First he climbed up to heaven, then he plunged into the depths of the earth."
        ]
    },
    ("☴", "☲"): {
        "number": 37,
        "name": "Jia Ren / The Family",
        "chinese": "家人",
        "judgement": "The Family. The perseverance of the woman furthers.",
        "image": "Wind comes forth from fire: The image of the Family. Thus the superior man has substance in his words and duration in his way of life.",
        "lines": [
            "Firm seclusion within the family. Remorse disappears.",
            "She should not follow her whims. She must attend within to the food. Perseverance brings good fortune.",
            "When tempers flare up in the family, too great severity brings remorse. Good fortune nonetheless. When woman and child dally and laugh, it leads in the end to humiliation.",
            "She is the treasure of the house. Great good fortune.",
            "As a king he approaches his family. Fear not. Good fortune.",
            "His work commands respect. In the end good fortune comes."
        ]
    },
    ("☲", "☱"): {
        "number": 38,
        "name": "Kui / Opposition",
        "chinese": "睽",
        "judgement": "Opposition. In small matters, good fortune.",
        "image": "Above, fire; below, the lake: The image of Opposition. Thus amid all fellowship the superior man retains his individuality.",
        "lines": [
            "Remorse disappears. If you lose your horse, do not run after it; it will come back of its own accord. When you see evil people, guard yourself against mistakes.",
            "One meets his lord in a narrow street. No blame.",
            "One sees the wagon dragged back, the oxen halted, a man's hair and nose cut off. Not a good beginning, but a good end.",
            "Isolated through opposition, one meets a like-minded man with whom one can associate in good faith. Despite the danger, no blame.",
            "Remorse disappears. The companion bites his way through the wrappings. If one goes to him, how could it be a mistake?",
            "Isolated through opposition, one sees one's companion as a pig covered with dirt, as a wagon full of devils. First one draws a bow against him, then one lays the bow aside. He is not a robber; he will woo at the right time. As one goes, rain falls; then good fortune comes."
        ]
    },
    ("☵", "☶"): {
        "number": 39,
        "name": "Jian / Obstruction",
        "chinese": "蹇",
        "judgement": "Obstruction. The southwest furthers. The northeast does not further. It furthers one to see the great man. Perseverance brings good fortune.",
        "image": "Water on the mountain: The image of Obstruction. Thus the superior man turns his attention to himself and molds his character.",
        "lines": [
            "Going leads to obstructions, coming meets with praise.",
            "The king's servant is beset by obstruction upon obstruction, but it is not his own fault.",
            "Going leads to obstructions; hence he comes back.",
            "Going leads to obstructions, coming leads to union.",
            "In the midst of the greatest obstructions, friends come.",
            "Going leads to obstructions, coming leads to great good fortune. It furthers one to see the great man."
        ]
    },
    ("☳", "☵"): {
        "number": 40,
        "name": "Xie / Deliverance",
        "chinese": "解",
        "judgement": "Deliverance. The southwest furthers. If there is no longer anything where one has to go, return brings good fortune. If there is still something where one has to go, hastening brings good fortune.",
        "image": "Thunder and rain set in: The image of Deliverance. Thus the superior man pardons mistakes and forgives misdeeds.",
        "lines": [
            "Without blame.",
            "One kills three foxes in the field and receives a yellow arrow. Perseverance brings good fortune.",
            "If a man carries a burden on his back and nonetheless rides in a carriage, he thereby encourages robbers to draw near. Perseverance leads to humiliation.",
            "Deliver yourself from your big toe. Then the companion comes, and him you can trust.",
            "If only the superior man can deliver himself, it brings good fortune. Thus he proves to inferior men that he is in earnest.",
            "The prince shoots at a hawk on a high wall. He kills it. Everything serves to further."
        ]
    },
    ("☶", "☱"): {
        "number": 41,
        "name": "Sun / Decrease",
        "chinese": "損",
        "judgement": "Decrease combined with sincerity brings about supreme good fortune without blame. One may be persevering in this. It furthers one to undertake something. How is this to be carried out? One may use two small bowls for the sacrifice.",
        "image": "At the foot of the mountain, the lake: The image of Decrease. Thus the superior man controls his anger and restrains his instincts.",
        "lines": [
            "Going quickly when one's tasks are finished is without blame. But one must reflect on how much one may decrease others.",
            "Perseverance furthers. To undertake something brings misfortune. Without decreasing oneself, one is able to bring increase to others.",
            "When three people journey together, their number decreases by one. When one man journeys alone, he finds a companion.",
            "If a man decreases his faults, it makes the other hasten to come and rejoice. No blame.",
            "Someone does indeed increase him. Ten pairs of tortoises cannot oppose it. Supreme good fortune.",
            "If one is increased without depriving others, there is no blame. Perseverance brings good fortune. It furthers one to undertake something. One obtains servants but no longer has a separate home."
        ]
    },
    ("☴", "☳"): {
        "number": 42,
        "name": "Yi / Increase",
        "chinese": "益",
        "judgement": "Increase. It furthers one to undertake something. It furthers one to cross the great water.",
        "image": "Wind and thunder: the image of Increase. Thus the superior man: If he sees good, he imitates it; if he has faults, he rids himself of them.",
        "lines": [
            "It furthers one to accomplish great deeds. Supreme good fortune. No blame.",
            "Someone does indeed increase him; ten pairs of tortoises cannot oppose it. Constant perseverance brings good fortune. The king presents him before God. Good fortune.",
            "One is enriched through unfortunate events. No blame, if you are sincere and walk in the middle, and report with a seal to the prince.",
            "If you walk in the middle and report to the prince, he will follow. It furthers one to be used in the removal of the capital.",
            "If in truth you have a kind heart, ask not. Supreme good fortune. Truly, kindness will be recognized as your virtue.",
            "He brings increase to no one. Indeed, someone even strikes him. He does not keep his heart constantly steady. Misfortune."
        ]
    },
    ("☱", "☰"): {
        "number": 43,
        "name": "Guai / Break-through (Resoluteness)",
        "chinese": "夬",
        "judgement": "Break-through. One must resolutely make the matter known at the court of the king. It must be announced truthfully. Danger. It is necessary to notify one's own city. It does not further to resort to arms. It furthers one to undertake something.",
        "image": "The lake has risen up to heaven: The image of Break-through. Thus the superior man dispenses riches downward and refrains from resting on his virtue.",
        "lines": [
            "Mighty in the forward-striding toes. When one goes and is not equal to the task, one makes a mistake.",
            "A cry of alarm. Arms at evening and at night. Fear nothing.",
            "To be powerful in the cheekbones brings misfortune. The superior man is firmly resolved. He walks alone and is caught in the rain. He is bespattered, and people murmur against him. No blame.",
            "There is no skin on his thighs, and walking comes hard. If a man were to let himself be led like a sheep, remorse would disappear. But if these words are heard they will not be believed.",
            "In dealing with weeds, firm resolution is necessary. Walking in the middle remains free of blame.",
            "No cry. In the end misfortune comes."
        ]
    },
    ("☰", "☴"): {
        "number": 44,
        "name": "Gou / Coming to Meet",
        "chinese": "姤",
        "judgement": "Coming to Meet. The maiden is powerful. One should not marry such a maiden.",
        "image": "Under heaven, wind: The image of Coming to Meet. Thus does the prince act when disseminating his commands and proclaiming them to the four quarters of heaven.",
        "lines": [
            "It must be checked with a brake of bronze. Perseverance brings good fortune. If one lets it take its course, one experiences misfortune. Even a lean pig has it in him to rage around.",
            "There is a fish in the tank. No blame. Does not further guests.",
            "There is no skin on his thighs, and walking comes hard. If one is mindful of the danger, no great mistake is made.",
            "No fish in the tank. This leads to misfortune.",
            "A melon covered with willow leaves. Hidden lines. Then it drops down to one from heaven.",
            "He comes to meet with his horns. Humiliation. No blame."
        ]
    },
    ("☱", "☷"): {
        "number": 45,
        "name": "Cui / Gathering Together (Massing)",
        "chinese": "萃",
        "judgement": "Gathering Together. Success. The king approaches his temple. It furthers one to see the great man. This brings success. Perseverance furthers. To bring great offerings creates good fortune. It furthers one to undertake something.",
        "image": "Over the earth, the lake: The image of Gathering Together. Thus the superior man renews his weapons in order to meet the unforeseen.",
        "lines": [
            "If you are sincere, but not to the end, there will sometimes be confusion, sometimes gathering together. If you call out, then after one grasp of the hand you can laugh again. Regret not. Going is without blame.",
            "Letting oneself be drawn brings good fortune and remains blameless. If one is sincere, it furthers one to bring even a small offering.",
            "Gathering together amid sighs. Nothing that would further. Going is without blame. Slight humiliation.",
            "Great good fortune. No blame.",
            "If in gathering together one has position, this brings no blame. If there are some who are not yet sincerely in the work, sublime and enduring perseverance is needed. Then remorse disappears.",
            "Lamenting and sighing, floods of tears. No blame."
        ]
    },
    ("☷", "☴"): {
        "number": 46,
        "name": "Sheng / Pushing Upward",
        "chinese": "升",
        "judgement": "Pushing Upward has supreme success. One must see the great man. Fear not. Departure toward the south brings good fortune.",
        "image": "Within the earth, wood grows: The image of Pushing Upward. Thus the superior man of devoted character heaps up small things in order to achieve something high and great.",
        "lines": [
            "Pushing upward that meets with confidence brings great good fortune.",
            "If one is sincere, it furthers one to bring even a small offering. No blame.",
            "One pushes upward into an empty city.",
            "The king offers him Mount Chi. Good fortune. No blame.",
            "Perseverance brings good fortune. One pushes upward by steps.",
            "Pushing upward in darkness. It furthers one to be unremittingly persevering."
        ]
    },
    ("☱", "☵"): {
        "number": 47,
        "name": "Kun / Oppression (Exhaustion)",
        "chinese": "困",
        "judgement": "Oppression. Success. Perseverance. The great man brings about good fortune. No blame. When one has something to say, it is not believed.",
        "image": "There is no water in the lake: The image of Exhaustion. Thus the superior man stakes his life on following his will.",
        "lines": [
            "One sits oppressed under a bare tree and strays into a gloomy valley. For three years one sees nothing.",
            "One is oppressed while at meat and drink. The man with the scarlet knee bands is just coming. It furthers one to offer sacrifice. To set forth brings misfortune. No blame.",
            "A man permits himself to be oppressed by stone, and leans on thorns and thistles. He enters his house and does not see his wife. Misfortune.",
            "He comes very quietly, oppressed in a golden carriage. Humiliation, but the end is reached.",
            "His nose and feet are cut off. Oppression at the hands of the man with the purple knee bands. Joy comes softly. It furthers one to make offerings and libations.",
            "He is oppressed by creeping vines. He moves uncertainly and says, 'Movement brings remorse.' If one feels remorse over this and makes a start, good fortune comes."
        ]
    },
    ("☵", "☴"): {
        "number": 48,
        "name": "Jing / The Well",
        "chinese": "井",
        "judgement": "The Well. The town may be changed, but the well cannot be changed. It neither decreases nor increases. They come and go and draw from the well. If one gets down almost to the water and the rope does not go all the way, or the jug breaks, it brings misfortune.",
        "image": "Water over wood: the image of the Well. Thus the superior man encourages the people at their work, and exhorts them to help one another.",
        "lines": [
            "One does not drink the mud of the well. No animals come to an old well.",
            "At the wellhole one shoots fishes. The jug is broken and leaks.",
            "The well is cleaned, but no one drinks from it. This is my heart's sorrow, for one might draw from it. If the king were clear-minded, good fortune might be enjoyed in common.",
            "The well is being lined. No blame.",
            "In the well there is a clear, cold spring from which one can drink.",
            "One draws from the well without hindrance. It is dependable. Supreme good fortune."
        ]
    },
    ("☱", "☲"): {
        "number": 49,
        "name": "Ge / Revolution (Molting)",
        "chinese": "革",
        "judgement": "Revolution. On your own day you are believed. Supreme success, furthering through perseverance. Remorse disappears.",
        "image": "Fire in the lake: the image of Revolution. Thus the superior man sets the calendar in order and makes the seasons clear.",
        "lines": [
            "Wrapped in the hide of a yellow cow.",
            "When one's own day comes, one may create revolution. Starting brings good fortune. No blame.",
            "Starting brings misfortune. Perseverance brings danger. When talk of revolution has gone the rounds three times, one may commit himself, and men will believe him.",
            "Remorse disappears. Men believe him. Changing the form of government brings good fortune.",
            "The great man changes like a tiger. Even before he questions the oracle he is believed.",
            "The superior man changes like a panther. The inferior man molts in the face. Starting brings misfortune. To remain persevering brings good fortune."
        ]
    },
    ("☲", "☴"): {
        "number": 50,
        "name": "Ding / The Caldron",
        "chinese": "鼎",
        "judgement": "The Caldron. Supreme good fortune. Success.",
        "image": "Fire over wood: The image of the Caldron. Thus the superior man consolidates his fate by making his position correct.",
        "lines": [
            "A ting with legs upturned. Furthers removal of stagnating stuff. One takes a concubine for the sake of her son. No blame.",
            "There is food in the ting. My comrades are envious, but they cannot harm me. Good fortune.",
            "The handle of the ting is altered. One is impeded in his way of life. The fat of the pheasant is not eaten. Once rain falls, remorse is spent. Good fortune comes in the end.",
            "The legs of the ting are broken. The prince's meal is spilled and his person is soiled. Misfortune.",
            "The ting has yellow handles, golden carrying rings. Perseverance furthers.",
            "The ting has rings of jade. Great good fortune. Nothing that would not act to further."
        ]
    },
    ("☳", "☳"): {
        "number": 51,
        "name": "Zhen / The Arousing (Shock, Thunder)",
        "chinese": "震",
        "judgement": "Shock brings success. Shock comes—oh, oh! Laughing words—ha, ha! The shock terrifies for a hundred li, and he does not let fall the sacrificial spoon and chalice.",
        "image": "Thunder repeated: the image of Shock. Thus in fear and trembling the superior man sets his life in order and examines himself.",
        "lines": [
            "Shock comes—oh, oh! Then follow laughing words—ha, ha! Good fortune.",
            "Shock comes bringing danger. A hundred thousand times you lose your treasures and climb the nine hills. Do not go in pursuit of them. After seven days you will get them back again.",
            "Shock comes and makes one distraught. If shock spurs to action one remains free of misfortune.",
            "Shock is mired.",
            "Shock goes hither and thither. Danger. However, nothing at all is lost. Yet there are things to be done.",
            "Shock brings ruin and terrified gazing around. Going ahead brings misfortune. If it has not yet touched one's own body but has reached one's neighbor first, there is no blame. One's comrades have something to talk about."
        ]
    },
    ("☶", "☶"): {
        "number": 52,
        "name": "Gen / Keeping Still (Mountain)",
        "chinese": "艮",
        "judgement": "Keeping Still. Keeping his back still so that he no longer feels his body. He goes into his courtyard and does not see his people. No blame.",
        "image": "Mountains standing close together: The image of Keeping Still. Thus the superior man does not permit his thoughts to go beyond his situation.",
        "lines": [
            "Keeping his toes still. No blame. Continued perseverance furthers.",
            "Keeping his calves still. He cannot rescue him whom he follows. His heart is not glad.",
            "Keeping his hips still. Making his sacrum stiff. Dangerous. The heart suffocates.",
            "Keeping his trunk still. No blame.",
            "Keeping his jaws still. The words have order. Remorse disappears.",
            "Noble-hearted keeping still. Good fortune."
        ]
    },
    ("☴", "☶"): {
        "number": 53,
        "name": "Jian / Development (Gradual Progress)",
        "chinese": "漸",
        "judgement": "Development. The maiden is given in marriage. Good fortune. Perseverance furthers.",
        "image": "On the mountain, a tree: The image of Development. Thus the superior man abides in dignity and virtue, in order to improve the mores.",
        "lines": [
            "The wild goose gradually draws near the shore. The young son is in danger. There is talk. No blame.",
            "The wild goose gradually draws near the cliff. Eating and drinking in peace and concord. Good fortune.",
            "The wild goose gradually draws near the plateau. The man goes forth and does not return. The woman carries a child but does not bring it forth. Misfortune. It furthers one to fight off robbers.",
            "The wild goose gradually draws near the tree. Perhaps it will find a flat branch. No blame.",
            "The wild goose gradually draws near the summit. For three years the woman has no child. In the end nothing can hinder her. Good fortune.",
            "The wild goose gradually draws near the cloud heights. Its feathers can be used for the sacred dance. Good fortune."
        ]
    },
    ("☳", "☱"): {
        "number": 54,
        "name": "Gui Mei / The Marrying Maiden",
        "chinese": "歸妹",
        "judgement": "The Marrying Maiden. Undertakings bring misfortune. Nothing that would further.",
        "image": "Thunder over the lake: The image of the Marrying Maiden. Thus the superior man understands the transitory in the light of the eternity of the end.",
        "lines": [
            "The marrying maiden as a concubine. A lame man who is able to tread. Undertakings bring good fortune.",
            "A one-eyed man who is able to see. The perseverance of a solitary man furthers.",
            "The marrying maiden as a slave. She marries as a concubine.",
            "The marrying maiden draws out the allotted time. A late marriage comes in due course.",
            "The sovereign I gave his daughter in marriage. The embroidered garments of the princess were not as gorgeous as those of the servingmaid. The moon that is nearly full brings good fortune.",
            "The woman holds the basket, but there are no fruits in it. The man stabs the sheep, but no blood flows. Nothing that acts to further."
        ]
    },
    ("☳", "☲"): {
        "number": 55,
        "name": "Feng / Abundance (Fullness)",
        "chinese": "豐",
        "judgement": "Abundance has success. The king attains abundance. Be not sad. Be like the sun at midday.",
        "image": "Both thunder and lightning come: The image of Abundance. Thus the superior man decides lawsuits and carries out punishments.",
        "lines": [
            "When a man meets his destined ruler, they can be together ten days, and it is not a mistake. Going meets with recognition.",
            "The curtain is of such fullness that the polestars can be seen at noon. Through going one meets with mistrust and hate. If one rouses him through truth, good fortune comes.",
            "The underbrush is of such abundance that the small stars can be seen at noon. He breaks his right arm. No blame.",
            "The curtain is of such fullness that the polestars can be seen at noon. He meets his ruler, who is of like kind. Good fortune.",
            "Lines are coming, blessing and fame draw near. Good fortune.",
            "His house is in a state of abundance. He screens off his family. He peers through the gate and no longer perceives anyone. For three years he sees nothing. Misfortune."
        ]
    },
    ("☲", "☶"): {
        "number": 56,
        "name": "Lu / The Wanderer",
        "chinese": "旅",
        "judgement": "The Wanderer. Success through smallness. Perseverance brings good fortune to the wanderer.",
        "image": "Fire on the mountain: The image of the Wanderer. Thus the superior man is clear-minded and cautious in imposing penalties, and protracts no lawsuits.",
        "lines": [
            "If the wanderer busies himself with trivial things, he draws down misfortune upon himself.",
            "The wanderer comes to an inn. He has his property with him. He wins the steadfastness of a young servant.",
            "The wanderer's inn burns down. He loses the steadfastness of his young servant. Danger.",
            "The wanderer rests in a shelter. He obtains his property and an ax. My heart is not glad.",
            "He shoots a pheasant. It drops with the first arrow. In the end this brings both praise and office.",
            "The bird's nest burns up. The wanderer laughs first, then must needs lament and weep. Through carelessness he loses his cow. Misfortune."
        ]
    },
    ("☴", "☴"): {
        "number": 57,
        "name": "Xun / The Gentle (Wind)",
        "chinese": "巽",
        "judgement": "The Gentle. Success through what is small. It furthers one to have somewhere to go. It furthers one to see the great man.",
        "image": "Winds following one upon the other: The image of the Gentle. Thus the superior man spreads his commands abroad and carries out his undertakings.",
        "lines": [
            "In advancing and in retreating, the perseverance of a warrior furthers.",
            "Penetration under the bed. Priests and magicians are used in great number. Good fortune. No blame.",
            "Repeated penetration. Humiliation.",
            "Remorse vanishes. During the hunt three kinds of game are caught.",
            "Perseverance brings good fortune. Remorse vanishes. Nothing that does not further. No beginning, but an end. Before the change, three days. After the change, three days. Good fortune.",
            "Penetration under the bed. He loses his property and his ax. Perseverance brings misfortune."
        ]
    },
    ("☱", "☱"): {
        "number": 58,
        "name": "Dui / The Joyous (Lake)",
        "chinese": "兌",
        "judgement": "The Joyous. Success. Perseverance is favorable.",
        "image": "Lakes resting one on the other: The image of the Joyous. Thus the superior man joins with his friends for discussion and practice.",
        "lines": [
            "Contented joyousness. Good fortune.",
            "Sincere joyousness. Good fortune. Remorse disappears.",
            "Coming joyousness. Misfortune.",
            "Joyousness that is weighed is not at peace. After ridding himself of mistakes a man has joy.",
            "Sincerity toward disintegrating influences is dangerous.",
            "Seductive joyousness."
        ]
    },
    ("☴", "☵"): {
        "number": 59,
        "name": "Huan / Dispersion (Dissolution)",
        "chinese": "渙",
        "judgement": "Dispersion. Success. The king approaches his temple. It furthers one to cross the great water. Perseverance furthers.",
        "image": "The wind drives over the water: The image of Dispersion. Thus the kings of old sacrificed to the Lord and built temples.",
        "lines": [
            "He brings help with the strength of a horse. Good fortune.",
            "At the dissolution he hurries to that which supports him. Remorse disappears.",
            "He dissolves his self. No remorse.",
            "He dissolves his bond with his group. Supreme good fortune. Dispersion leads in turn to accumulation. This is something that ordinary men do not think of.",
            "His loud cries are as dissolving as sweat. Dissolution. A king abides without blame.",
            "He dissolves his blood. Departing, keeping at a distance, going out, is without blame."
        ]
    },
    ("☵", "☱"): {
        "number": 60,
        "name": "Jie / Limitation",
        "chinese": "節",
        "judgement": "Limitation. Success. Galling limitation must not be persevered in.",
        "image": "Water over lake: the image of Limitation. Thus the superior man creates number and measure, and examines the nature of virtue and correct conduct.",
        "lines": [
            "Not going out of the door and the courtyard is without blame.",
            "Not going out of the gate and the courtyard brings misfortune.",
            "He who knows no limitation will have cause to lament. No blame.",
            "Contented limitation. Success.",
            "Sweet limitation brings good fortune. Going brings esteem.",
            "Galling limitation. Perseverance brings misfortune. Remorse disappears."
        ]
    },
    ("☴", "☱"): {
        "number": 61,
        "name": "Zhong Fu / Inner Truth",
        "chinese": "中孚",
        "judgement": "Inner Truth. Pigs and fishes. Good fortune. It furthers one to cross the great water. Perseverance furthers.",
        "image": "Wind over lake: the image of Inner Truth. Thus the superior man discusses criminal cases in order to delay executions.",
        "lines": [
            "Being prepared brings good fortune. If there are secret designs, it is disquieting.",
            "A crane calling in the shade. Its young answers it. I have a good goblet. I will share it with you.",
            "He finds a comrade. Now he beats the drum, now he stops. Now he sobs, now he sings.",
            "The moon nearly at the full. The team horse goes astray. No blame.",
            "He possesses truth, which links together. No blame.",
            "Cockcrow penetrating to heaven. Perseverance brings misfortune."
        ]
    },
    ("☶", "☳"): {
        "number": 62,
        "name": "Xiao Guo / Preponderance of the Small",
        "chinese": "小過",
        "judgement": "Preponderance of the Small. Success. Perseverance furthers. Small things may be done; great things should not be done. The flying bird brings the message: It is not well to strive upward, it is well to remain below. Great good fortune.",
        "image": "Thunder on the mountain: The image of Preponderance of the Small. Thus in his conduct the superior man gives preponderance to reverence. In bereavement he gives preponderance to grief. In his expenditures he gives preponderance to thrift.",
        "lines": [
            "The bird meets with misfortune through flying.",
            "She passes by her ancestor and meets her ancestress. He does not reach his prince and meets the official. No blame.",
            "If one is not extremely careful, somebody may come up from behind and strike him. Misfortune.",
            "No blame. He meets him without passing by. Going brings danger. One must be on guard. Do not act. Be constantly persevering.",
            "Dense clouds, no rain from our western territory. The prince shoots and hits him who is in the cave.",
            "He passes him by, not meeting him. The flying bird leaves him. Misfortune. This means bad luck and injury."
        ]
    },
    ("☵", "☲"): {
        "number": 63,
        "name": "Ji Ji / After Completion",
        "chinese": "既濟",
        "judgement": "After Completion. Success in small matters. Perseverance furthers. At the beginning good fortune, at the end disorder.",
        "image": "Water over fire: the image of the condition in After Completion. Thus the superior man takes thought of misfortune and arms himself against it in advance.",
        "lines": [
            "He brakes his wheels. He gets his tail in the water. No blame.",
            "The woman loses the curtain of her carriage. Do not run after it; on the seventh day you will get it.",
            "The Illustrious Ancestor disciplines the Devil's Country. After three years he conquers it. Inferior people must not be employed.",
            "The finest clothes turn to rags. Be careful all day long.",
            "The neighbor in the east who slaughters an ox does not attain as much real happiness as the neighbor in the west with his small offering.",
            "He gets his head in the water. Danger."
        ]
    },
    ("☲", "☵"): {
        "number": 64,
        "name": "Wei Ji / Before Completion",
        "chinese": "未濟",
        "judgement": "Before Completion. Success. But if the little fox, after nearly completing the crossing, gets his tail in the water, there is nothing that would further.",
        "image": "Fire over water: The image of the condition before transition. Thus the superior man is careful in the differentiation of things, so that each finds its place.",
        "lines": [
            "He gets his tail in the water. Humiliating.",
            "He brakes his wheels. Perseverance brings good fortune.",
            "Before completion, attack brings misfortune. It furthers one to cross the great water.",
            "Perseverance brings good fortune. Remorse disappears. Shock, thus to discipline the Devil's Country. For three years, great realms are awarded.",
            "Perseverance brings good fortune. No remorse. The light of the superior man is true. Good fortune.",
            "There is drinking of wine in genuine confidence. No blame. But if one wets his head, he loses it, in truth."
        ]
    }
}

# Trigram symbols and names
TRIGRAM_SYMBOLS = {
    "☰": "Qian (Heaven/Creative)",
    "☱": "Dui (Lake/Joyous)", 
    "☲": "Li (Fire/Clinging)",
    "☳": "Zhen (Thunder/Arousing)",
    "☴": "Xun (Wind/Wood/Gentle)",
    "☵": "Kan (Water/Abysmal)",
    "☶": "Gen (Mountain/Keeping Still)",
    "☷": "Kun (Earth/Receptive)"
}

# Trigram attributes for Image generation
TRIGRAM_ATTRIBUTES = {
    "☰": "strong, creative, initiating",
    "☱": "joyous, open, reflecting",
    "☲": "clinging, illuminating, clarifying",
    "☳": "arousing, stirring, shocking",
    "☴": "gentle, penetrating, flexible",
    "☵": "dangerous, flowing, profound",
    "☶": "still, stopping, resting",
    "☷": "receptive, yielding, devoted"
}

# === Helper Functions ===
def secure_hash(data: bytes, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """
    Generate cryptographically secure hash using PBKDF2.
    High iteration count prevents interference and ensures deterministic results.
    """
    return hashlib.pbkdf2_hmac('sha256', data, salt, iterations, DERIVED_KEY_LENGTH)

def derive_line_value(entropy: bytes) -> int:
    """
    Convert entropy byte to I-Ching line value using three-coin method.
    Extracts 3 bits to simulate 3 coin tosses.
    """
    byte_value = entropy[0]
    heads_count = sum((byte_value >> i) & 1 for i in range(3))
    return 6 + heads_count  # Maps to 6,7,8,9

def line_to_yin_yang(line: int) -> int:
    """Convert line value to binary (0=yin, 1=yang)."""
    return 0 if line in (LineValue.OLD_YIN, LineValue.YOUNG_YIN) else 1

def bits_to_trigram(bits: List[int]) -> str:
    """Convert three bits to trigram symbol."""
    trigram_map = ["☷", "☶", "☵", "☴", "☳", "☲", "☱", "☰"]
    index = bits[0] + (bits[1] << 1) + (bits[2] << 2)
    return trigram_map[index]

def format_hexagram_lines(bits: List[int], moving: Optional[List[int]] = None) -> List[str]:
    """Format hexagram lines for display (top to bottom)."""
    lines = []
    for i in range(5, -1, -1):  # Top to bottom
        if bits[i] == 1:
            line = "━━━━━━━"  # Yang
        else:
            line = "━━   ━━"  # Yin
        
        if moving and i in moving:
            line += " ✦"  # Mark moving lines
        lines.append(line)
    return lines

def get_hexagram_info(lower: str, upper: str) -> Dict[str, Any]:
    """Retrieve hexagram information from database."""
    return HEXAGRAM_DATABASE.get((lower, upper), {
        "number": 0,
        "name": f"{TRIGRAM_SYMBOLS.get(upper, '?')} over {TRIGRAM_SYMBOLS.get(lower, '?')}",
        "chinese": "",
        "judgement": "Information not available.",
        "image": f"The image of {TRIGRAM_SYMBOLS.get(upper, '?')} above {TRIGRAM_SYMBOLS.get(lower, '?')}.",
        "lines": []
    })

# === Core Classes ===
@dataclass
class HexagramReading:
    """Complete I-Ching reading result."""
    query: str
    timestamp: str
    seed_hash: str
    authentication: str
    
    # Primary hexagram
    primary_lines: List[int]
    primary_bits: List[int]
    primary_info: Dict[str, Any]
    
    # Moving lines
    moving_positions: List[int] = field(default_factory=list)
    moving_line_texts: List[str] = field(default_factory=list)
    
    # Relating hexagram (if moving lines exist)
    relating_bits: Optional[List[int]] = None
    relating_info: Optional[Dict[str, Any]] = None
    
    # Nuclear hexagram
    nuclear_bits: Optional[List[int]] = None
    nuclear_info: Optional[Dict[str, Any]] = None

class IChing:
    """Main I-Ching divination system."""
    
    def __init__(self, show_nuclear: bool = True):
        self.show_nuclear = show_nuclear
        
    def cast(self, query: str) -> HexagramReading:
        """
        Perform complete I-Ching casting.
        Uses cryptographic hashing to ensure deterministic, secure results.
        """
        # Generate timestamp and create seed
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        seed_material = f"{query}|{timestamp}".encode('utf-8')
        seed = hashlib.sha256(seed_material).digest()
        
        # Authentication hash (first 8 hex chars)
        auth_hash = secure_hash(seed, b"hexagram-auth")
        auth_string = auth_hash.hex()[:8].upper()
        
        # Generate 6 lines (bottom to top)
        lines = []
        bits = []
        moving_positions = []
        
        for position in range(6):
            line_entropy = secure_hash(seed, f"line-{position}".encode('utf-8'))
            line_value = derive_line_value(line_entropy)
            lines.append(line_value)
            
            bit = line_to_yin_yang(line_value)
            bits.append(bit)
            
            # Check for moving lines
            if line_value in (LineValue.OLD_YIN, LineValue.OLD_YANG):
                moving_positions.append(position)
        
        # Build primary hexagram
        lower_trigram = bits_to_trigram(bits[0:3])
        upper_trigram = bits_to_trigram(bits[3:6])
        primary_info = get_hexagram_info(lower_trigram, upper_trigram)
        
        # Extract moving line texts
        moving_line_texts = []
        if moving_positions and primary_info.get("lines"):
            for pos in moving_positions:
                if pos < len(primary_info["lines"]):
                    moving_line_texts.append(f"Line {pos+1}: {primary_info['lines'][pos]}")
        
        # Build relating hexagram (if moving lines exist)
        relating_bits = None
        relating_info = None
        if moving_positions:
            relating_bits = bits.copy()
            for pos in moving_positions:
                relating_bits[pos] = 1 - relating_bits[pos]  # Flip bit
            
            rel_lower = bits_to_trigram(relating_bits[0:3])
            rel_upper = bits_to_trigram(relating_bits[3:6])
            relating_info = get_hexagram_info(rel_lower, rel_upper)
        
        # Build nuclear hexagram (lines 2-4 and 3-5)
        nuclear_bits = None
        nuclear_info = None
        if self.show_nuclear:
            nuclear_bits = [bits[1], bits[2], bits[3], bits[2], bits[3], bits[4]]
            nuc_lower = bits_to_trigram(nuclear_bits[0:3])
            nuc_upper = bits_to_trigram(nuclear_bits[3:6])
            nuclear_info = get_hexagram_info(nuc_lower, nuc_upper)
        
        return HexagramReading(
            query=query,
            timestamp=timestamp,
            seed_hash=seed.hex()[:16],
            authentication=auth_string,
            primary_lines=lines,
            primary_bits=bits,
            primary_info=primary_info,
            moving_positions=moving_positions,
            moving_line_texts=moving_line_texts,
            relating_bits=relating_bits,
            relating_info=relating_info,
            nuclear_bits=nuclear_bits,
            nuclear_info=nuclear_info
        )

# === Display Functions ===
def display_reading(reading: HexagramReading):
    """Display the complete reading."""
    
    if RICH_AVAILABLE:
        # Header
        console.rule(f"[bold cyan]☯ I-CHING DIVINATION ☯[/bold cyan]")
        console.print(f"[dim]Query:[/dim] {reading.query}")
        console.print(f"[dim]Time:[/dim] {reading.timestamp}")
        console.print(f"[dim]Auth:[/dim] [bold green]{reading.authentication}[/bold green]")
        console.print()
        
        # Primary Hexagram
        primary_panel_content = "\n".join([
            f"[bold]Hexagram #{reading.primary_info['number']}:[/bold] {reading.primary_info['name']}",
            f"[dim]Chinese:[/dim] {reading.primary_info.get('chinese', '')}",
            "",
            "[bold]Lines:[/bold]",
            *format_hexagram_lines(reading.primary_bits, reading.moving_positions),
            "",
            f"[bold]Judgement:[/bold] {reading.primary_info['judgement']}",
            "",
            f"[bold]Image:[/bold] {reading.primary_info['image']}"
        ])
        console.print(Panel(primary_panel_content, title="[bold]Primary Hexagram[/bold]", border_style="cyan"))
        
        # Moving Lines
        if reading.moving_positions:
            console.print()
            moving_content = "\n".join([
                f"[yellow]Moving positions: {', '.join(str(p+1) for p in reading.moving_positions)}[/yellow]",
                "",
                *reading.moving_line_texts
            ])
            console.print(Panel(moving_content, title="[bold]Moving Lines[/bold]", border_style="yellow"))
        
        # Relating Hexagram
        if reading.relating_info:
            console.print()
            relating_content = "\n".join([
                f"[bold]Hexagram #{reading.relating_info['number']}:[/bold] {reading.relating_info['name']}",
                "",
                "[bold]Lines:[/bold]",
                *format_hexagram_lines(reading.relating_bits),
                "",
                f"[bold]Judgement:[/bold] {reading.relating_info['judgement']}"
            ])
            console.print(Panel(relating_content, title="[bold]Relating Hexagram[/bold]", border_style="magenta"))
        
        # Nuclear Hexagram
        if reading.nuclear_info:
            console.print()
            nuclear_content = "\n".join([
                f"[bold]Hexagram #{reading.nuclear_info['number']}:[/bold] {reading.nuclear_info['name']}",
                "",
                f"[dim]Inner lines 2-5 form the nuclear hexagram[/dim]",
                "",
                f"[bold]Judgement:[/bold] {reading.nuclear_info['judgement']}"
            ])
            console.print(Panel(nuclear_content, title="[bold]Nuclear Hexagram[/bold]", border_style="blue"))
            
    else:
        # Plain text output
        print("\n" + "="*60)
        print("I-CHING DIVINATION")
        print("="*60)
        print(f"Query: {reading.query}")
        print(f"Time: {reading.timestamp}")
        print(f"Auth: {reading.authentication}")
        print()
        
        # Primary
        print(f"PRIMARY HEXAGRAM #{reading.primary_info['number']}: {reading.primary_info['name']}")
        print(f"Chinese: {reading.primary_info.get('chinese', '')}")
        print("\nLines (top to bottom):")
        for line in format_hexagram_lines(reading.primary_bits, reading.moving_positions):
            print(f"  {line}")
        print(f"\nJudgement: {reading.primary_info['judgement']}")
        print(f"Image: {reading.primary_info['image']}")
        
        # Moving lines
        if reading.moving_positions:
            print(f"\nMOVING LINES: {', '.join(str(p+1) for p in reading.moving_positions)}")
            for text in reading.moving_line_texts:
                print(f"  {text}")
        
        # Relating
        if reading.relating_info:
            print(f"\nRELATING HEXAGRAM #{reading.relating_info['number']}: {reading.relating_info['name']}")
            print("Lines:")
            for line in format_hexagram_lines(reading.relating_bits):
                print(f"  {line}")
            print(f"Judgement: {reading.relating_info['judgement']}")
        
        # Nuclear
        if reading.nuclear_info:
            print(f"\nNUCLEAR HEXAGRAM #{reading.nuclear_info['number']}: {reading.nuclear_info['name']}")
            print(f"Judgement: {reading.nuclear_info['judgement']}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-q', '--query',
        help='Your question or situation to divine'
    )
    parser.add_argument(
        '--no-nuclear',
        action='store_true',
        help='Omit the nuclear hexagram'
    )
    parser.add_argument(
        '--save',
        help='Save reading to JSON file'
    )
    parser.add_argument(
        '--seed',
        help='Use specific seed for testing (bypasses timestamp)'
    )
    
    args = parser.parse_args()
    
    # Get query
    if args.query:
        query = args.query
    else:
        if RICH_AVAILABLE:
            query = console.input("[bold cyan]Enter your question:[/bold cyan] ")
        else:
            query = input("Enter your question: ")
    
    if not query.strip():
        print("Error: A question is required for divination.", file=sys.stderr)
        sys.exit(1)
    
    # Perform casting
    iching = IChing(show_nuclear=not args.no_nuclear)
    
    if RICH_AVAILABLE:
        with console.status("[bold cyan]Consulting the oracle...[/bold cyan]", spinner="dots"):
            reading = iching.cast(query)
    else:
        print("Consulting the oracle...", end="", flush=True)
        reading = iching.cast(query)
        print(" done.")
    
    # Display results
    display_reading(reading)
    
    # Save if requested
    if args.save:
        try:
            save_data = asdict(reading)
            save_path = Path(args.save)
            
            if save_path.suffix.lower() == '.jsonl':
                # Append mode for JSONL
                with open(save_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(save_data, ensure_ascii=False) + '\n')
            else:
                # Regular JSON
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            if RICH_AVAILABLE:
                console.print(f"[green]✓ Reading saved to {save_path}[/green]")
            else:
                print(f"Reading saved to {save_path}")
                
        except Exception as e:
            logger.error(f"Failed to save reading: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDivination cancelled.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
