"""
Anti-spam module for content randomization.
Implements spintax processing, emoji insertion, and zero-width character injection.
"""

import re
import random
from typing import List, Optional, Callable


EMOJI_POOL = [
    "✅", "👍", "💯", "🔥", "⭐", "😊", "🎉", "💪", "🚀", "📱",
    "💬", "📞", "💼", "🎯", "⚡", "✨", "🌟", "💡", "🔔", "📢",
    "👏", "🙏", "💝", "🎁", "🏆", "🎊", "🌈", "✔️", "📌", "💫"
]

ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff"]


def _ensure_text(text: str) -> bool:
    """Helper to validate text before processing."""
    return bool(text)


def _split_sentences(text: str) -> tuple:
    """Splits text into sentences with punctuation preserved."""
    return re.split(r'([.!?])', text)


def _process_sentence_pair(sentence: str, punctuation: str, processor: Callable) -> str:
    """Processes a sentence-punctuation pair through given function."""
    if not sentence.strip():
        return ""
    return processor(sentence, punctuation)


def process_spintax(text: str) -> str:
    """Processes spintax format {option1|option2|option3}."""
    if not _ensure_text(text):
        return ""
    
    pattern = r'\{([^{}]+)\}'
    for _ in range(100):
        match = re.search(pattern, text)
        if not match:
            break
        
        options = [opt.strip() for opt in match.group(1).split('|') if opt.strip()]
        replacement = random.choice(options) if options else ""
        text = text[:match.start()] + replacement + text[match.end():]
    
    return text


def inject_zero_width_spaces(text: str, density: float = 0.05) -> str:
    """Injects invisible characters (2-8% density)."""
    if not _ensure_text(text) or density <= 0:
        return text
    
    result = []
    for char in text:
        result.append(char)
        if random.random() < density:
            result.append(random.choice(ZERO_WIDTH_CHARS))
    
    return "".join(result)


def insert_random_emojis(text: str, emoji_count: int = None) -> str:
    """Inserts 1-2 random emojis logically in text."""
    if not _ensure_text(text):
        return text
    
    if emoji_count is None:
        emoji_count = random.randint(1, 2)
    
    emoji_count = max(0, min(emoji_count, 3))
    if emoji_count == 0:
        return text
    
    lines = text.split("\n")
    insertion_positions = []
    
    for line_idx, line in enumerate(lines):
        if not line.strip():
            continue
        
        punct_indices = [i for i, char in enumerate(line) if char in ".!?,:;…" and i < len(line) - 1]
        
        if punct_indices:
            for _ in range(emoji_count):
                if punct_indices:
                    insertion_positions.append((line_idx, random.choice(punct_indices) + 1))
        else:
            insertion_positions.append((line_idx, len(line)))
    
    insertion_positions = insertion_positions[:emoji_count]
    for line_idx, char_pos in sorted(insertion_positions, reverse=True):
        if line_idx < len(lines):
            line = lines[line_idx]
            lines[line_idx] = line[:char_pos] + " " + random.choice(EMOJI_POOL) + line[char_pos:]
    
    return "\n".join(lines)


def randomize_sentence_structure(text: str) -> str:
    """Randomizes sentence structure by reordering clauses."""
    if not _ensure_text(text) or len(text) < 50:
        return text
    
    sentences = _split_sentences(text)
    processed = []
    
    for i in range(0, len(sentences), 2):
        if i >= len(sentences):
            break
        
        sentence = sentences[i].strip()
        punctuation = sentences[i + 1] if i + 1 < len(sentences) else "."
        
        if not sentence:
            continue
        
        if random.random() < 0.3 and "," in sentence:
            clauses = [c.strip() for c in sentence.split(",")]
            if len(clauses) > 1:
                random.shuffle(clauses)
                sentence = ", ".join(clauses)
        
        processed.append(sentence + punctuation)
    
    return " ".join(processed)


def randomize_word_order(text: str, preserve_rate: float = 0.7) -> str:
    """Randomizes word order while preserving sentence structure."""
    if not _ensure_text(text):
        return text
    
    sentences = _split_sentences(text)
    processed = []
    
    for i in range(0, len(sentences), 2):
        if i >= len(sentences):
            break
        
        sentence = sentences[i].strip()
        punctuation = sentences[i + 1] if i + 1 < len(sentences) else "."
        
        if sentence and len(sentence.split()) > 3 and random.random() < 0.4:
            words = sentence.split()
            preserve_count = max(2, int(len(words) * preserve_rate))
            moveable = list(range(preserve_count, len(words)))
            
            if moveable:
                shuffled = [words[idx] for idx in moveable]
                random.shuffle(shuffled)
                for idx, word in zip(moveable, shuffled):
                    words[idx] = word
            
            sentence = " ".join(words)
        
        processed.append(sentence + punctuation)
    
    return " ".join(processed)


def uniqualize_text(text: str, apply_spintax: bool = True, add_emojis: bool = True,
                   add_zero_width: bool = True, randomize_structure: bool = True) -> str:
    """Applies multi-layer randomization for hash variation."""
    if not _ensure_text(text):
        return text
    
    result = text
    
    if apply_spintax:
        result = process_spintax(result)
    
    if randomize_structure and random.random() < 0.5:
        result = randomize_sentence_structure(result)
    
    if random.random() < 0.3:
        result = randomize_word_order(result)
    
    if add_emojis and random.random() < 0.6:
        result = insert_random_emojis(result)
    
    if add_zero_width:
        result = inject_zero_width_spaces(result, random.uniform(0.02, 0.08))
    
    return result


def create_message_variations(text: str, count: int = 5) -> List[str]:
    """Generates unique variations of text."""
    variations = []
    for _ in range(count):
        variation = uniqualize_text(text)
        if variation not in variations:
            variations.append(variation)
    
    return variations
