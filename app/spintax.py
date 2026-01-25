import re
import random

def process_spintax(text):
    """
    Processes a string with spintax format {option1|option2|option3}
    and returns a string with one of the options selected randomly.
    """
    if not text:
        return ""
    
    pattern = r'\{([^{}]+)\}'
    
    while True:
        match = re.search(pattern, text)
        if not match:
            break
        
        options = match.group(1).split('|')
        replacement = random.choice(options)
        text = text[:match.start()] + replacement + text[match.end():]
        
    return text
