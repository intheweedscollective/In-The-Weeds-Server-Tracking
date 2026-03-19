"""
Intelligent Name Matching System

This module provides fuzzy name matching to handle:
- OCR errors (Dhaka! vs Dhakal, CrandaH vs Crandall)
- Nicknames (Trey vs Treyanna, Tad vs Thaddeus)
- Typos and variations (Starwars vs Stanvars)
- First name / last name matching
"""

from rapidfuzz import fuzz, process
from typing import Optional, List, Dict, Tuple
import re
import logging

logger = logging.getLogger(__name__)


# Common nickname mappings
NICKNAME_MAP = {
    # Short -> Full names
    "trey": ["treyanna", "trey"],
    "tad": ["thaddeus", "tad"],
    "terry": ["terrance", "terry"],
    "mike": ["michael", "mike"],
    "bob": ["robert", "bob"],
    "rob": ["robert", "rob"],
    "bill": ["william", "bill"],
    "will": ["william", "will"],
    "jim": ["james", "jim"],
    "jimmy": ["james", "jimmy"],
    "tom": ["thomas", "tom"],
    "tommy": ["thomas", "tommy"],
    "dan": ["daniel", "dan"],
    "danny": ["daniel", "danny"],
    "joe": ["joseph", "joe"],
    "joey": ["joseph", "joey"],
    "chris": ["christopher", "christian", "chris"],
    "matt": ["matthew", "matt"],
    "nick": ["nicholas", "nick"],
    "tony": ["anthony", "tony"],
    "alex": ["alexander", "alexandra", "alex"],
    "sam": ["samuel", "samantha", "sam"],
    "ben": ["benjamin", "ben"],
    "jen": ["jennifer", "jen"],
    "kate": ["katherine", "kate"],
    "liz": ["elizabeth", "liz"],
    "beth": ["elizabeth", "beth"],
    "meg": ["megan", "margaret", "meg"],
    "pat": ["patrick", "patricia", "pat"],
    "rick": ["richard", "rick"],
    "dick": ["richard", "dick"],
    "ed": ["edward", "eddie", "ed"],
    "eddie": ["edward", "eddie", "ed"],
    "steve": ["steven", "stephen", "steve"],
    "dave": ["david", "dave"],
    "max": ["maxwell", "maximilian", "max"],
    "jake": ["jacob", "jake"],
    "jack": ["john", "jackson", "jack"],
    "jon": ["jonathan", "jon"],
    "andy": ["andrew", "andy"],
    "drew": ["andrew", "drew"],
}

# Build reverse map (full -> short)
FULL_TO_NICKNAME = {}
for short, fulls in NICKNAME_MAP.items():
    for full in fulls:
        if full not in FULL_TO_NICKNAME:
            FULL_TO_NICKNAME[full] = []
        FULL_TO_NICKNAME[full].append(short)


def clean_name(name: str) -> str:
    """
    Clean a name for comparison:
    - Remove special characters (!@#$%^&*) 
    - Normalize whitespace
    - Handle common OCR errors
    """
    if not name:
        return ""
    
    # Convert to lowercase
    cleaned = name.lower().strip()
    
    # Remove trailing punctuation (!, ?, etc.)
    cleaned = re.sub(r'[!?.,;:]+$', '', cleaned)
    
    # Replace common OCR errors
    ocr_fixes = {
        'h$': 'll',  # CrandaH -> Crandall
        '!': 'l',    # Dhaka! -> Dhakal
        '0': 'o',    # R0bert -> Robert
        '1': 'l',    # Wi1son -> Wilson
        '|': 'l',    # Wi|son -> Wilson
        '—': '-',    # em-dash to hyphen
        '–': '-',    # en-dash to hyphen
    }
    
    for bad, good in ocr_fixes.items():
        if bad == 'h$':
            # Only replace H at end of word
            cleaned = re.sub(r'H\b', 'll', cleaned, flags=re.IGNORECASE)
        else:
            cleaned = cleaned.replace(bad, good)
    
    # Normalize whitespace
    cleaned = ' '.join(cleaned.split())
    
    return cleaned


def get_name_parts(name: str) -> Dict[str, str]:
    """Split a name into first, middle, last parts"""
    parts = clean_name(name).split()
    
    if len(parts) == 0:
        return {"first": "", "last": "", "full": ""}
    elif len(parts) == 1:
        return {"first": parts[0], "last": "", "full": parts[0]}
    elif len(parts) == 2:
        return {"first": parts[0], "last": parts[1], "full": " ".join(parts)}
    else:
        return {
            "first": parts[0], 
            "last": parts[-1], 
            "middle": " ".join(parts[1:-1]),
            "full": " ".join(parts)
        }


def get_nickname_variants(name: str) -> List[str]:
    """Get possible nickname variants for a name"""
    name_lower = name.lower()
    variants = [name_lower]
    
    # Check if this is a nickname -> get full names
    if name_lower in NICKNAME_MAP:
        variants.extend(NICKNAME_MAP[name_lower])
    
    # Check if this is a full name -> get nicknames
    if name_lower in FULL_TO_NICKNAME:
        variants.extend(FULL_TO_NICKNAME[name_lower])
    
    return list(set(variants))


def calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between two names using multiple strategies.
    Returns a score from 0-100.
    """
    if not name1 or not name2:
        return 0.0
    
    clean1 = clean_name(name1)
    clean2 = clean_name(name2)
    
    # Exact match after cleaning
    if clean1 == clean2:
        return 100.0
    
    # Get name parts
    parts1 = get_name_parts(name1)
    parts2 = get_name_parts(name2)
    
    scores = []
    
    # Full name fuzzy match
    full_score = fuzz.ratio(clean1, clean2)
    scores.append(full_score)
    
    # Token sort ratio (handles word order differences)
    token_sort = fuzz.token_sort_ratio(clean1, clean2)
    scores.append(token_sort)
    
    # Partial ratio (handles substring matches)
    partial = fuzz.partial_ratio(clean1, clean2)
    scores.append(partial * 0.9)  # Slightly penalize partial matches
    
    # First name + last name matching
    if parts1["first"] and parts2["first"] and parts1["last"] and parts2["last"]:
        first_score = fuzz.ratio(parts1["first"], parts2["first"])
        last_score = fuzz.ratio(parts1["last"], parts2["last"])
        
        # Check nickname variants for first name
        first_variants1 = get_nickname_variants(parts1["first"])
        first_variants2 = get_nickname_variants(parts2["first"])
        
        # Check if any variants match
        for v1 in first_variants1:
            for v2 in first_variants2:
                if v1 == v2:
                    first_score = 100
                    break
        
        # Combined first + last score
        name_parts_score = (first_score * 0.4) + (last_score * 0.6)
        scores.append(name_parts_score)
    
    # Return the best score
    return max(scores)


def find_best_match(
    search_name: str, 
    candidates: List[Dict], 
    threshold: float = 75.0
) -> Tuple[Optional[Dict], float, str]:
    """
    Find the best matching employee from a list of candidates.
    
    Args:
        search_name: The name to search for
        candidates: List of employee dicts with 'name', 'display_name', 'report_name', 'aliases'
        threshold: Minimum score to consider a match (0-100)
    
    Returns:
        Tuple of (best_match_employee, score, match_reason)
    """
    if not search_name or not candidates:
        return None, 0.0, "no_candidates"
    
    clean_search = clean_name(search_name)
    best_match = None
    best_score = 0.0
    match_reason = "no_match"
    
    for candidate in candidates:
        candidate_names = []
        
        # Collect all possible names for this candidate
        if candidate.get('report_name'):
            candidate_names.append(('report_name', candidate['report_name']))
        if candidate.get('name'):
            candidate_names.append(('name', candidate['name']))
        if candidate.get('display_name'):
            candidate_names.append(('display_name', candidate['display_name']))
        
        # Include aliases
        aliases = candidate.get('aliases', []) or []
        for alias in aliases:
            candidate_names.append(('alias', alias))
        
        # Score against each candidate name
        for name_type, candidate_name in candidate_names:
            # Exact match (after cleaning)
            if clean_name(candidate_name) == clean_search:
                return candidate, 100.0, f"exact_{name_type}"
            
            # Fuzzy match
            score = calculate_name_similarity(search_name, candidate_name)
            
            if score > best_score:
                best_score = score
                best_match = candidate
                match_reason = f"fuzzy_{name_type}"
    
    # Only return if above threshold
    if best_score >= threshold:
        return best_match, best_score, match_reason
    
    return None, best_score, "below_threshold"


def match_employees_batch(
    upload_names: List[str],
    existing_employees: List[Dict],
    threshold: float = 75.0
) -> Dict[str, Dict]:
    """
    Match a batch of uploaded names to existing employees.
    
    Returns a dict mapping upload_name -> {
        'matched': True/False,
        'employee': employee dict or None,
        'score': match score,
        'reason': match reason,
        'action': 'update' or 'create'
    }
    """
    results = {}
    
    for upload_name in upload_names:
        match, score, reason = find_best_match(
            upload_name, 
            existing_employees, 
            threshold
        )
        
        if match:
            results[upload_name] = {
                'matched': True,
                'employee': match,
                'score': score,
                'reason': reason,
                'action': 'update',
                'matched_to': match.get('name') or match.get('display_name')
            }
            logger.info(f"Matched '{upload_name}' -> '{match.get('name')}' (score: {score:.1f}, {reason})")
        else:
            results[upload_name] = {
                'matched': False,
                'employee': None,
                'score': score,
                'reason': reason,
                'action': 'create',
                'matched_to': None
            }
            logger.info(f"No match for '{upload_name}' (best score: {score:.1f})")
    
    return results


# Test function
if __name__ == "__main__":
    # Test cases
    test_pairs = [
        ("Sheridan Dhaka!", "Sheriden Dhakal"),
        ("Starwars Mckinnon-Herrera", "Stanvars McKinnon-Herrera"),
        ("Lexi CrandaH", "Lexi Crandall"),
        ("Trey Quick", "Treyanna Quick"),
        ("Tad Hashey", "Thaddeus Hashey"),
        ("Terry Kott", "Terrance Kott"),
        ("Robert Smith", "Bob Smith"),
        ("Michael Johnson", "Mike Johnson"),
    ]
    
    for name1, name2 in test_pairs:
        score = calculate_name_similarity(name1, name2)
        print(f"'{name1}' vs '{name2}': {score:.1f}")
